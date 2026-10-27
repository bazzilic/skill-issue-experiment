# README.md

In this repository we test skill invocation and compliance reliability by different agents.

## Experiment Specification

Experiment is held over a set of different agents and requires every agent to do several attempts to go through a trial.
A trial tests different scenarios in which the agent should or should not invoke a skill.

### Skills

We create two synthetic skills, each contains a distinct trigger in the description. In the agent prompts we use phrasing that is very close to the trigger but is not 100% identical.

One skill is extremely short, another is very wordy and large, at least 15 KB.

Both skills don't do anything apart from very clearly indicating that they were executed (complied with). For example, "create a file 'complied.txt' in the workspace root after you finish working on the request". Each skill has its own easily identifiable indication.

### Trials

A full trial consists of the following scenarios:

- Skills are visible to the harness, no trigger is mentioned, short and simple prompt (output a value from a synthetic localhost API)
- Skills are visible to the harness, no trigger is mentioned, wordy and complex prompt (a long prompt that requests a task with a convoluted localhost API, trigger is buries in the middle of the prompt)
- Skills are visible to the harness, trigger for the short skill, simple prompt
- Skills are visible to the harness, trigger for the short skill, complex prompt
- Skills are visible to the harness, trigger for the long skill, simple prompt
- Skills are visible to the harness, trigger for the long skill, complex prompt
- Short skill is force-loaded (injected in the prompt), short skill trigger, simple prompt
- Short skill is force-loaded, short skill trigger, complex prompt
- Long skill is force-loaded, long skill trigger, simple prompt
- Long skill is force-loaded, long skill trigger, complex prompt

In scenarios where skills are force-loaded, they are not seen by the harness as a skill definition file. In the prompt, they are explicitly indicated to be a verbatim skill file inclusion including the frontmatter, surrounded by clear delimiters:

```
The following skill is available to you:
--- File: Skill.md ---
...
--- End of Skill.md ---
```

### Execution Strategy

A full agent test gets one agent to execute the full trial 5 times.

We run full tests for:

- Claude Code, Haiku 5.5, Low
- Claude Code, Haiku 5.5, High
- Claude Code, Haiku 5.5, Max
- Claude Code, Sonnet 5.5, Low
- Claude Code, Sonnet 5.5, High
- Claude Code, Sonnet 5.5, Max
- Claude Code, Opus 5.5, Low
- Claude Code, Opus 5.5, High
- Claude Code, Opus 5.5, Max
- Codex, GPT 5.6 Luna, Light
- Codex, GPT 5.6 Luna, High
- Codex, GPT 5.6 Terra, Light
- Codex, GPT 5.6 Terra, High
- Codex, GPT 5.6 Sol, Light
- Codex, GPT 5.6 Sol, High
- Codex, GPT 6 Luna, Light
- Codex, GPT 6 Luna, High
- Codex, GPT 6 Sol, Light
- Codex, GPT 6 Sol, High
- Codex, GPT 6.1 Sol, Light
- Codex, GPT 6.1 Sol, High

## Execution Environment

To ensure proper isolation and repeatability, each scenario should run in a separate, fresh container (docker or podman, depending on what is available). At any time, orchestrator should run no more than 5 containers in parallel. If a scenario fails for any reason, the final report should indicate that but not undertake any retries. Orchestrator should be able to do targeted additional trials/scenarios on request and recalculate the report with new data.

## Results and Metrics

Full trace of every session should be saved after the scenario finishes. Invocation of the skill (reading the skill file) is tested by analyzing the trace. Compliance is tested by checking that skill was executed.

The report contains only frequencies. For every agent and scenario it gives the invocation frequency and the compliance frequency as k/n (percentage), where n is the number of sessions that ran to completion; failed sessions are listed separately and excluded from n. In scenarios with a trigger, a session counts as invoked when the trace shows the triggered skill's file being read, and as compliant when that skill's own indicator file exists in the workspace root with the expected text at the end of the session; the other skill's file does not count. In no-trigger scenarios, either skill's invocation or indicator file counts. Force-loaded scenarios have nothing to invoke, so only compliance is reported for them.

| Scenario group | Invocation frequency | Compliance frequency |
| --- | --- | --- |
| Visible, no trigger | reported (ideal 0%) | reported (ideal 0%) |
| Visible, trigger | reported (ideal 100%) | reported (ideal 100%) |
| Force-loaded, trigger | not applicable | reported (ideal 100%) |

## Repository

All files are in the repository root.

- [README.md](README.md): this experiment description.
- [SPECIFICATION.md](SPECIFICATION.md): specification of the synthetic localhost API used by the prompts.
- [server.py](server.py): implementation of that API (Python standard library only). It also writes `expected.json`, the correct answers, which is never served.
- [orchestrator.py](orchestrator.py): builds the image, runs the sessions in containers and writes the report (`python3 orchestrator.py build | run | report`). Sessions and the report are stored in `runs/`, which is git-ignored.
- [Dockerfile](Dockerfile): the agent image, with pinned Claude Code and Codex versions.
- [SKILL-copper-heron.md](SKILL-copper-heron.md): the short synthetic skill.
- [SKILL-velvet-anchor.md](SKILL-velvet-anchor.md): the long synthetic skill (over 15 KB).
- [PROMPT-simple.md](PROMPT-simple.md): the short and simple prompt.
- [PROMPT-complex.md](PROMPT-complex.md): the wordy and complex prompt.

Both prompts contain a `{{TRIGGER_SENTENCE}}` placeholder, which is replaced with the trigger phrasing for a skill or removed for no-trigger scenarios.
