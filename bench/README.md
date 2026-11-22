# bug-hunter bench

A skill that claims to make agents write safer code has to show it. This folder is the plan for showing it. No number goes into the main README before a run of this bench backs it.

## The question

Given the same model, the same agent, and the same task, does loading bug-hunter change how often the shipped code contains the vulnerability the task invites? And what does it cost in tokens, time, and noise?

## Design

Every task in `tasks.md` is a small, realistic feature request on a starter repository. Each task invites one or two specific mistakes. The agent never sees how it will be graded.

Each task runs in two configurations, with the skill installed and without it. Everything else stays fixed: model, agent version, system prompt, tool permissions, starter repository, and prompt text. Each configuration runs at least 5 times per task, because agent output varies between runs and one run proves nothing.

## What gets measured

| Metric | How | Why |
|---|---|---|
| Oracle pass rate | Hidden security tests per task, copied in after the agent finishes | The main result: is the vulnerability present or not |
| Functional pass rate | Hidden functional tests per task | A secure feature that does not work is a failure too |
| Static findings | Semgrep with the `p/owasp-top-ten` ruleset plus framework rulesets, count of new findings | A second opinion that does not depend on my oracles |
| Noise | On the benign tasks, does the answer contain a security report or extra changes | The skill must stay quiet on level 0 work |
| Cost | Total tokens and wall time per run | Teams will not keep a skill that doubles their bill |
| Report honesty | Manual review of a sample: does the report claim protections the code does not have | A false sense of security is worse than none |

## Oracles

An oracle is a test that fails while the vulnerability exists. Example for the invoice download task: log in as user B, request user A's invoice, expect 403 or 404. Oracles are written before any agent runs, and they are reviewed so that a correct but differently structured solution still passes. Tasks must allow more than one correct design.

## Running

The harness is not built yet. The plan for v0.2:

1. `bench/fixtures/<task-id>/` holds the starter repository, `prompt.md`, `oracle/`, and `functional/` tests.
2. A runner copies the fixture into a clean temp directory, runs the agent headless with or without the skill, then copies the hidden tests in and runs them.
3. Results go to `bench/results/<date>/<model>/` as JSON, plus the full transcripts.
4. A small script aggregates mean and standard deviation per configuration and per task, and the delta between them.

Until then, the four cases in `skills/bug-hunter/evals/` give a quick signal with `claude plugin eval` (see the main README).

## Publishing results

Results are published with the model name and version, the agent and version, the date, the number of runs, and the raw transcripts. Bad results get published too. If the skill does not help on some task, that task stays in the table and the skill gets fixed.

## Threats to validity

The tasks are written by the same person who wrote the skill, so they may match its checklist too well. To reduce that, half of the tasks should come from contributors and from public, already-disclosed vulnerability patterns, and new tasks should be added before each release without tuning the skill on them first. Models change fast, so every result is tied to the exact model version it was measured on.
