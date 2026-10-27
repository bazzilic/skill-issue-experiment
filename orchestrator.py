#!/usr/bin/env python3
"""Orchestrator for the Skill Issue experiment. See README.md.

Usage:
    python3 orchestrator.py build
    python3 orchestrator.py run [--agent SUBSTRING]... [--scenario N]... [--reps 5] [--dry-run]
    python3 orchestrator.py report

Sessions are stored in runs/<agent>/s<scenario>/r<rep>/. A session is recorded once its result.json
exists, so `run` only executes missing sessions and never retries a recorded one, failed or not.
To add sessions, raise --reps or narrow the selection with --agent and --scenario; the report is
regenerated after every run.

Credentials: Codex uses ~/.codex/auth.json. Claude Code uses the long-lived OAuth token (from
`claude setup-token`) stored in 1Password and read with `op read`, because its login lives in the
macOS Keychain and cannot be mounted into a Linux container.
"""

import argparse
import glob
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from itertools import product

ROOT = os.path.dirname(os.path.abspath(__file__))
IMAGE = "skill-issue-agent:1"
MAX_PARALLEL = 5
DEFAULT_REPS = 5
DEFAULT_TIMEOUT = 15 * 60
PLACEHOLDER = "{{TRIGGER_SENTENCE}}"
CLAUDE_TOKEN_REF = "op://Private/Claude Code OAuth Token/credential"

Skill = namedtuple("Skill", "name file cue indicator text")
SKILLS = {
    "short": Skill("copper-heron", "SKILL-copper-heron.md",
                   "When you finish, please follow the copper heron process.",
                   "complied-copper-heron.txt", "copper-heron complied"),
    "long": Skill("velvet-anchor", "SKILL-velvet-anchor.md",
                  "When you finish, please follow the velvet anchor process.",
                  "complied-velvet-anchor.txt", "velvet-anchor complied"),
}
PROMPT_FILES = {"simple": "PROMPT-simple.md", "complex": "PROMPT-complex.md"}

Scenario = namedtuple("Scenario", "id delivery trigger prompt")
SCENARIOS = [Scenario(i, *rest) for i, rest in enumerate([
    ("visible", None, "simple"), ("visible", None, "complex"),
    ("visible", "short", "simple"), ("visible", "short", "complex"),
    ("visible", "long", "simple"), ("visible", "long", "complex"),
    ("forced", "short", "simple"), ("forced", "short", "complex"),
    ("forced", "long", "simple"), ("forced", "long", "complex"),
], 1)]

Agent = namedtuple("Agent", "id label harness model effort")


def build_agents():
    agents = []
    for slug, name, model in [("haiku-5.5", "Haiku 5.5", "claude-haiku-5-5"),
                              ("sonnet-5.5", "Sonnet 5.5", "claude-sonnet-5-5"),
                              ("opus-5.5", "Opus 5.5", "claude-opus-5-5")]:
        for level in ("Low", "High", "Max"):
            agents.append(Agent(f"claude-{slug}-{level.lower()}", f"Claude Code, {name}, {level}",
                                "claude", model, level.lower()))
    for model, name in [("gpt-5.6-luna", "GPT 5.6 Luna"), ("gpt-5.6-terra", "GPT 5.6 Terra"),
                        ("gpt-5.6-sol", "GPT 5.6 Sol"), ("gpt-6-luna", "GPT 6 Luna"),
                        ("gpt-6-sol", "GPT 6 Sol"), ("gpt-6.1-sol", "GPT 6.1 Sol")]:
        for level, effort in (("Light", "low"), ("High", "high")):
            agents.append(Agent(f"codex-{model}-{level.lower()}", f"Codex, {name}, {level}",
                                "codex", model, effort))
    return agents


AGENTS = build_agents()

# Runs inside the container. Parameters arrive as environment variables; the prompt and any visible
# skills are copied to /session beforehand. Everything worth keeping is left in /out and /workspace.
RUN_SCRIPT = r'''#!/bin/bash
set -u
mkdir -p /out
python3 /opt/skill-issue/server.py --port 8080 --expected /dev/null > /out/server.log 2>&1 &
for _ in $(seq 100); do curl -sf http://127.0.0.1:8080/value > /dev/null && break; sleep 0.1; done
cd /workspace
if [ "$AGENT_HARNESS" = claude ]; then
  if [ -d /session/skills ]; then mkdir -p ~/.claude/skills && cp -r /session/skills/. ~/.claude/skills/; fi
  timeout -k 10 "$AGENT_TIMEOUT" claude -p --model "$AGENT_MODEL" --effort "$AGENT_EFFORT" \
    --dangerously-skip-permissions --output-format stream-json --verbose \
    < /session/prompt.txt > /out/trace.jsonl 2> /out/stderr.log
  code=$?
  cp -r ~/.claude/projects /out/harness-logs 2> /dev/null
else
  mkdir -p ~/.codex && printf '%s' "$CODEX_AUTH_JSON" > ~/.codex/auth.json && chmod 600 ~/.codex/auth.json
  unset CODEX_AUTH_JSON
  if [ -d /session/skills ]; then mkdir -p ~/.agents/skills && cp -r /session/skills/. ~/.agents/skills/; fi
  timeout -k 10 "$AGENT_TIMEOUT" codex exec --json --skip-git-repo-check \
    --dangerously-bypass-approvals-and-sandbox -C /workspace -m "$AGENT_MODEL" \
    -c "model_reasoning_effort=\"$AGENT_EFFORT\"" - \
    < /session/prompt.txt > /out/trace.jsonl 2> /out/stderr.log
  code=$?
  cp -r ~/.codex/sessions /out/harness-logs 2> /dev/null
fi
echo "$code" > /out/exit_code
'''

print_lock = threading.Lock()
active_containers = set()
stop = threading.Event()


# --- Scenario inputs -------------------------------------------------------------------------------

def read(name):
    with open(os.path.join(ROOT, name)) as f:
        return f.read()


def scenario_label(scenario):
    delivery = "Visible" if scenario.delivery == "visible" else "Force-loaded"
    trigger = f"{scenario.trigger} trigger" if scenario.trigger else "no trigger"
    return f"{delivery}, {trigger}, {scenario.prompt} prompt"


def build_prompt(scenario):
    cue = f" {SKILLS[scenario.trigger].cue}" if scenario.trigger else ""
    prompt = re.sub(" ?" + re.escape(PLACEHOLDER), lambda _: cue, read(PROMPT_FILES[scenario.prompt]))
    if scenario.delivery == "forced":
        skill = read(SKILLS[scenario.trigger].file)
        if not skill.endswith("\n"):
            skill += "\n"
        prompt = ("The following skill is available to you:\n--- File: Skill.md ---\n"
                  f"{skill}--- End of Skill.md ---\n\n{prompt}")
    return prompt


# --- Containers ------------------------------------------------------------------------------------

def sh(args, **kwargs):
    return subprocess.run(args, capture_output=True, text=True, **kwargs)


def detect_runtime():
    for exe in ("docker", "podman"):
        if shutil.which(exe) and sh([exe, "info"]).returncode == 0:
            return exe
    sys.exit("No working container runtime (docker or podman). For podman, try: podman machine start")


def load_secrets(harnesses):
    env = {}
    if "claude" in harnesses:
        if not shutil.which("op"):
            sys.exit("The 1Password CLI (op) is needed to read the Claude Code token.")
        token = sh(["op", "read", CLAUDE_TOKEN_REF])
        if token.returncode != 0 or not token.stdout.strip():
            sys.exit(f"Cannot read {CLAUDE_TOKEN_REF} from 1Password: {token.stderr.strip()}")
        env["CLAUDE_CODE_OAUTH_TOKEN"] = token.stdout.strip()
    if "codex" in harnesses:
        path = os.path.join(os.environ.get("CODEX_HOME", os.path.expanduser("~/.codex")), "auth.json")
        try:
            with open(path) as f:
                env["CODEX_AUTH_JSON"] = f.read()
        except OSError:
            sys.exit(f"Cannot read {path}; run `codex login`.")
    return env


def session_dir_for(runs_dir, agent, scenario, rep):
    return os.path.join(runs_dir, agent.id, f"s{scenario.id:02d}", f"r{rep}")


def run_session(runtime, image_id, secrets, runs_dir, timeout, agent, scenario, rep):
    """Run one session in a fresh container and record it. Returns the result, or None if interrupted."""
    session_dir = session_dir_for(runs_dir, agent, scenario, rep)
    out_dir, workspace_dir = os.path.join(session_dir, "out"), os.path.join(session_dir, "workspace")
    shutil.rmtree(session_dir, ignore_errors=True)
    os.makedirs(out_dir)
    os.makedirs(workspace_dir)

    prompt = build_prompt(scenario)
    with open(os.path.join(session_dir, "prompt.txt"), "w") as f:
        f.write(prompt)

    stage = tempfile.mkdtemp(prefix="skill-issue-")
    name = f"si-{os.getpid()}-{agent.id}-s{scenario.id}-r{rep}"
    started = datetime.now(timezone.utc)
    clock = time.time()
    failure = None
    try:
        shutil.copy(os.path.join(session_dir, "prompt.txt"), stage)
        with open(os.path.join(stage, "run.sh"), "w") as f:
            f.write(RUN_SCRIPT)
        if scenario.delivery == "visible":
            for skill in SKILLS.values():
                skill_dir = os.path.join(stage, "skills", skill.name)
                os.makedirs(skill_dir)
                shutil.copy(os.path.join(ROOT, skill.file), os.path.join(skill_dir, "SKILL.md"))

        env = {"AGENT_HARNESS": agent.harness, "AGENT_MODEL": agent.model, "AGENT_EFFORT": agent.effort,
               "AGENT_TIMEOUT": str(timeout)}
        env_args = [arg for k, v in env.items() for arg in ("-e", f"{k}={v}")]
        env_args += [arg for k in secrets for arg in ("-e", k)]  # values inherited, not on the command line
        with print_lock:
            active_containers.add(name)
        created = sh([runtime, "create", "--name", name, *env_args, image_id, "bash", "/session/run.sh"],
                     env={**os.environ, **secrets})
        copied = sh([runtime, "cp", stage + "/.", f"{name}:/session"]) if created.returncode == 0 else None
        if created.returncode != 0:
            failure = f"container_create: {created.stderr.strip()[:200]}"
        elif copied.returncode != 0:
            failure = f"container_copy_in: {copied.stderr.strip()[:200]}"
        else:
            try:
                started_run = sh([runtime, "start", "-a", name], timeout=timeout + 120)
                with open(os.path.join(session_dir, "container.log"), "w") as f:
                    f.write(started_run.stdout + started_run.stderr)
            except subprocess.TimeoutExpired:
                sh([runtime, "kill", name])
                failure = "timeout"
            sh([runtime, "cp", f"{name}:/out/.", out_dir])
            sh([runtime, "cp", f"{name}:/workspace/.", workspace_dir])
    finally:
        sh([runtime, "rm", "-f", name])
        with print_lock:
            active_containers.discard(name)
        shutil.rmtree(stage, ignore_errors=True)

    if stop.is_set():
        shutil.rmtree(session_dir, ignore_errors=True)
        return None
    result = analyze(agent, scenario, rep, session_dir, failure)
    result.update(started=started.isoformat(timespec="seconds"), seconds=round(time.time() - clock),
                  image=image_id)
    with open(os.path.join(session_dir, "result.json"), "w") as f:
        json.dump(result, f, indent=2)
        f.write("\n")
    return result


# --- Trace analysis --------------------------------------------------------------------------------

CALL_TYPES = {"tool_use", "command_execution", "custom_tool_call", "function_call", "local_shell_call",
              "mcp_tool_call"}
CALL_FIELDS = ("command", "cmd", "input", "arguments", "action")  # what was called, never the output


def read_events(path):
    events = []
    try:
        with open(path) as f:
            for line in f:
                try:
                    events.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return events


def collect_calls(node, calls):
    if isinstance(node, dict):
        if node.get("type") in CALL_TYPES:
            calls.append((node.get("name"), json.dumps([node.get(k) for k in CALL_FIELDS])))
        for value in node.values():
            collect_calls(value, calls)
    elif isinstance(node, list):
        for item in node:
            collect_calls(item, calls)


def skill_invoked(calls, skill):
    """Invoked = a Skill tool call naming the skill, or any tool call touching its SKILL.md."""
    path = re.compile(re.escape(skill.name) + r"/SKILL\.md")
    word = re.compile(r"\b" + re.escape(skill.name) + r"\b")
    return any(path.search(text) or (tool == "Skill" and word.search(text)) for tool, text in calls)


def skill_complied(session_dir, skill):
    try:
        with open(os.path.join(session_dir, "workspace", skill.indicator)) as f:
            return skill.text in f.read()
    except OSError:
        return False


def trace_failure(harness, events):
    if not events:
        return "empty_trace"
    if harness == "claude":
        results = [e for e in events if e.get("type") == "result"]
        if not results:
            return "no_result_event"
        if results[-1].get("is_error"):
            return f"harness_error: {results[-1].get('subtype')}"
    else:
        types = [e.get("type") for e in events]
        if "turn.failed" in types:
            return "turn_failed"
        if "turn.completed" not in types:
            return "no_turn_completed"
    return None


def analyze(agent, scenario, rep, session_dir, failure):
    out_dir = os.path.join(session_dir, "out")
    events = read_events(os.path.join(out_dir, "trace.jsonl"))
    if failure is None:
        try:
            with open(os.path.join(out_dir, "exit_code")) as f:
                code = int(f.read().strip())
        except (OSError, ValueError):
            code = None
        if code is None:
            failure = "no_exit_code"
        elif code in (124, 137):
            failure = "timeout"
        elif code != 0:
            failure = f"harness_exit_{code}"
        else:
            failure = trace_failure(agent.harness, events)

    calls = []
    for event in events:
        collect_calls(event, calls)
    for path in glob.glob(os.path.join(out_dir, "harness-logs", "**", "*.jsonl"), recursive=True):
        for event in read_events(path):
            collect_calls(event, calls)
    return {
        "agent": agent.id,
        "scenario": scenario.id,
        "rep": rep,
        "status": "failed" if failure else "ok",
        "reason": failure,
        "tool_calls": len(calls),
        "invoked": {key: skill_invoked(calls, skill) for key, skill in SKILLS.items()},
        "complied": {key: skill_complied(session_dir, skill) for key, skill in SKILLS.items()},
    }


def outcome(session):
    """(invoked, complied) for the scenario's rule; invoked is None where nothing can be invoked."""
    scenario = SCENARIOS[session["scenario"] - 1]
    keys = [scenario.trigger] if scenario.trigger else list(SKILLS)
    invoked = None if scenario.delivery == "forced" else any(session["invoked"][k] for k in keys)
    return invoked, any(session["complied"][k] for k in keys)


# --- Report ----------------------------------------------------------------------------------------

def load_sessions(runs_dir):
    sessions = []
    for path in sorted(glob.glob(os.path.join(runs_dir, "*", "s*", "r*", "result.json"))):
        with open(path) as f:
            sessions.append(json.load(f))
    return sessions


def cell(hits, total):
    return f"{hits}/{total} ({round(100 * hits / total)}%)" if total else "0/0"


def write_report(runs_dir):
    sessions = load_sessions(runs_dir)
    ok = [s for s in sessions if s["status"] == "ok"]
    failed = [s for s in sessions if s["status"] != "ok"]
    agents = [a for a in AGENTS if any(s["agent"] == a.id for s in sessions)]
    data = {}
    lines = ["# Results", "",
             f"{len(ok)} sessions ran to completion; {len(failed)} failed. Cells are k/n (percentage) over "
             "sessions that ran to completion; failed sessions are excluded and listed at the end.", ""]

    for title, index in (("Invocation frequency", 0), ("Compliance frequency", 1)):
        lines += [f"## {title}", "", "| Agent | " + " | ".join(f"S{s.id}" for s in SCENARIOS) + " |",
                  "| --- |" + " --- |" * len(SCENARIOS)]
        for agent in agents:
            row = []
            for scenario in SCENARIOS:
                runs = [outcome(s)[index] for s in ok if s["agent"] == agent.id and s["scenario"] == scenario.id]
                if index == 0 and scenario.delivery == "forced":
                    row.append("n/a")
                    continue
                row.append(cell(sum(runs), len(runs)))
                data.setdefault(agent.id, {}).setdefault(f"S{scenario.id}", {})[title.split()[0].lower()] = \
                    [sum(runs), len(runs)]
            lines.append(f"| {agent.label} | " + " | ".join(row) + " |")
        lines.append("")

    lines += ["## Scenarios", "", "| | Delivery | Trigger | Prompt |", "| --- | --- | --- | --- |"]
    for s in SCENARIOS:
        lines.append(f"| S{s.id} | {'visible' if s.delivery == 'visible' else 'force-loaded'} | "
                     f"{s.trigger or 'none'} | {s.prompt} |")
    lines.append("")

    if failed:
        lines += ["## Failed sessions", "", "| Agent | Scenario | Rep | Reason |", "| --- | --- | --- | --- |"]
        for s in failed:
            lines.append(f"| {s['agent']} | S{s['scenario']} | {s['rep']} | {s['reason']} |")
        lines.append("")

    suspect = [s for s in ok if SCENARIOS[s["scenario"] - 1].prompt == "complex" and s["tool_calls"] == 0]
    if suspect:
        lines += ["## Suspect traces", "",
                  "Completed complex sessions with no tool calls found in the trace (the trace format may not "
                  "have been parsed): " + ", ".join(f"{s['agent']} S{s['scenario']} r{s['rep']}" for s in suspect), ""]

    with open(os.path.join(runs_dir, "report.md"), "w") as f:
        f.write("\n".join(lines))
    with open(os.path.join(runs_dir, "report.json"), "w") as f:
        json.dump({"cells": data, "failed": [{k: s[k] for k in ("agent", "scenario", "rep", "reason")}
                                             for s in failed]}, f, indent=2)
        f.write("\n")
    return "\n".join(lines)


# --- Commands --------------------------------------------------------------------------------------

def cmd_build(args):
    runtime = detect_runtime()
    with tempfile.TemporaryDirectory() as context:
        for name in ("Dockerfile", "server.py"):
            shutil.copy(os.path.join(ROOT, name), context)
        subprocess.run([runtime, "build", "-t", IMAGE, context], check=True)


def cmd_run(args):
    agents = [a for a in AGENTS if not args.agent or any(text in a.id for text in args.agent)]
    scenarios = [s for s in SCENARIOS if not args.scenario or s.id in args.scenario]
    if not agents or not scenarios:
        sys.exit("Nothing selected.")
    todo = [(a, s, r) for a, s in product(agents, scenarios) for r in range(1, args.reps + 1)
            if not os.path.exists(os.path.join(session_dir_for(args.runs_dir, a, s, r), "result.json"))]
    print(f"{len(agents)} agents x {len(scenarios)} scenarios x {args.reps} reps: {len(todo)} sessions to run")
    if args.dry_run or not todo:
        for a, s, r in todo[:20]:
            print(f"  {a.id} S{s.id} r{r}")
        if len(todo) > 20:
            print(f"  ... and {len(todo) - 20} more")
        return

    runtime = detect_runtime()
    image = sh([runtime, "image", "inspect", "--format", "{{.Id}}", IMAGE])
    if image.returncode != 0:
        sys.exit(f"Image {IMAGE} not found; run: python3 orchestrator.py build")
    secrets = load_secrets({a.harness for a, _, _ in todo})
    random.Random(0).shuffle(todo)  # spread agents and scenarios over time
    os.makedirs(args.runs_dir, exist_ok=True)

    with ThreadPoolExecutor(max_workers=min(args.parallel, MAX_PARALLEL)) as pool:
        futures = {pool.submit(run_session, runtime, image.stdout.strip(), secrets, args.runs_dir, args.timeout,
                               a, s, r): (a, s, r) for a, s, r in todo}
        try:
            for done, future in enumerate(as_completed(futures), 1):
                agent, scenario, rep = futures[future]
                result = future.result()
                if result is None:
                    continue
                if result["status"] == "ok":
                    invoked, complied = outcome(result)
                    detail = f"ok invoked={'n/a' if invoked is None else invoked} complied={complied}"
                else:
                    detail = f"FAILED ({result['reason']})"
                print(f"[{done}/{len(todo)}] {agent.id} S{scenario.id} r{rep}: {detail} ({result['seconds']}s)",
                      flush=True)
        except KeyboardInterrupt:
            stop.set()
            for future in futures:
                future.cancel()
            with print_lock:
                names = list(active_containers)
            for name in names:
                sh([runtime, "kill", name])
            print("Interrupted; unfinished sessions were discarded.")
    write_report(args.runs_dir)
    print(f"Report: {os.path.join(args.runs_dir, 'report.md')}")


def cmd_report(args):
    os.makedirs(args.runs_dir, exist_ok=True)
    print(write_report(args.runs_dir))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs-dir", default=os.path.join(ROOT, "runs"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("build", help="build the container image").set_defaults(func=cmd_build)
    commands.add_parser("report", help="regenerate the report from recorded sessions").set_defaults(func=cmd_report)
    run = commands.add_parser("run", help="run missing sessions")
    run.add_argument("--agent", action="append", help="substring of an agent id, e.g. haiku or gpt-6.1-sol-high")
    run.add_argument("--scenario", action="append", type=int, choices=[s.id for s in SCENARIOS])
    run.add_argument("--reps", type=int, default=DEFAULT_REPS, help="sessions per agent and scenario to have")
    run.add_argument("--parallel", type=int, default=MAX_PARALLEL)
    run.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="seconds per session")
    run.add_argument("--dry-run", action="store_true")
    run.set_defaults(func=cmd_run)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
