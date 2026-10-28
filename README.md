# README.md

This repository contains an experiment designed to test reliability of skill invocation (loading) and compliance (following) by different agents.

To run, just ask your agent. But you will need to fiddle with the Codex and Claude authorization first to make it work on your host. Take note that in default configuration, it runs over a thousand sessions with agents, including the expensive ones, and eats into your limits like crazy.

## Experiment Specification

Experiment is held over a set of different agents and requires every agent to do several attempts to go through a trial. A trial tests different scenarios in which the agent should or should not invoke a skill.

### Skills

There are two synthetic skills, each contains a distinct trigger in the description. Agent prompts use phrasing that is very close to the trigger but is not 100% identical.

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

```markdown
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

To ensure proper isolation and repeatability, each scenario runs in a separate, fresh container (docker or podman, depending on what is available). At any time, orchestrator runs no more than 5 containers in parallel. If a scenario fails for any reason, the final report indicates that but does not undertake any retries. Orchestrator can do targeted additional trials/scenarios on request and recalculate the report with new data.

## Results and Metrics

Full trace of every session is saved after the scenario finishes. Invocation of the skill (reading the skill file) is tested by analyzing the trace. Compliance is tested by checking that skill was executed.

For every agent and scenario, the report provides the invocation frequency and the compliance frequency as `k/n` (percentage), where `n` is the number of sessions that ran to completion; failed sessions are listed separately and excluded from `n`. In scenarios with a trigger, a session counts as invoked when the trace shows the triggered skill's file being read, and as compliant when that skill's own indicator file exists in the workspace root with the expected text at the end of the session; the other skill's file does not count. In no-trigger scenarios, either skill's invocation or indicator file counts. Force-loaded scenarios have nothing to invoke, so only compliance is reported for them.

These are the actual results of a full experiment:

All **1,050 runs completed successfully**. Across the **840 triggered sessions**, there were **25 instances of non-compliance (3.0%)**.

| Model | Effort | Visible skill: misses | Force-loaded: misses | Overall non-compliance* |
|---|---|---:|---:|---:|
| Haiku 5.5 | Max | 0 | 1 | 1/40 (2.5%) |
| GPT 5.6 Terra | Light | 1 | 0 | 1/40 (2.5%) |
| GPT 6 Luna | High | 0 | 2 | 2/40 (5.0%) |
| GPT 6 Sol | Light | 3 | 0 | 3/40 (7.5%) |
| GPT 6 Sol | High | 5 | 3 | 8/40 (20.0%) |
| GPT 6.1 Sol | Light | 5 | 0 | 5/40 (12.5%) |
| GPT 6.1 Sol | High | 5 | 0 | 5/40 (12.5%) |
| Other 14 model/effort configurations | — | 0 | 0 | 0/560 (0%) |
| **Total** | | **19** | **6** | **25/840 (3.0%)** |

*Overall rates cover all eight triggered scenarios.*

All 25 misses occurred with the **long skill and complex prompt**.

## Repository

The following files and folders are in the repository root:

- [README.md](README.md): this experiment description.
- [SPECIFICATION.md](SPECIFICATION.md): specification of the synthetic localhost API used by the prompts.
- [server.py](server.py): implementation of that API (Python standard library only). It also writes `expected.json`, the correct answers, which is never served.
- [orchestrator.py](orchestrator.py): builds the image, runs the sessions in containers and writes the report (`python3 orchestrator.py build | run | report`). Sessions and the report are stored in `runs/`, which is git-ignored.
- [Dockerfile](Dockerfile): the agent image, with pinned Claude Code and Codex versions.
- [SKILL-copper-heron.md](SKILL-copper-heron.md): the short synthetic skill.
- [SKILL-velvet-anchor.md](SKILL-velvet-anchor.md): the long synthetic skill (over 15 KB).
- [PROMPT-simple.md](PROMPT-simple.md): the short and simple prompt.
- [PROMPT-complex.md](PROMPT-complex.md): the wordy and complex prompt.
- [runs/](runs/): traces and workspace artifacts of all runs done with the aforementioned agents and Claude Code v2.1.308 and Codex v0.164.0.

Both prompts contain a `{{TRIGGER_SENTENCE}}` placeholder, which is replaced with the trigger phrasing for a skill or removed for no-trigger scenarios.
