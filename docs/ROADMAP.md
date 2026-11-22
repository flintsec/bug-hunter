# Roadmap

## v0.1.0 (this scaffold)

SKILL.md with levels, workflow, secure defaults, and the report format. Reference files for every sensitive surface and framework notes for Laravel, Node, Python, Supabase and Firebase. `triage_diff.py` with 25 unit tests. Four eval cases, including one noise check. Bench design with 20 tasks.

## v0.2.0: proof

Build the bench harness for the first five tasks (L1, N1, P1, B1, X1). Run five times per configuration on two models. Publish results with transcripts. Fix whatever the results show, then extend to all 20 tasks.

Run a trigger test: 20 prompts that should load the skill and 20 that should not. Tune the description until both sides are above 90 percent.

## v0.3.0: depth

Abuse cases drawn from public, disclosed reports, organized by surface. Framework notes for Rails, Spring, Go and NestJS from contributors. Triage rules for GraphQL resolvers, gRPC handlers and queue consumers.

## v0.4.0: workflow

A GitHub Action that runs `triage_diff.py --format json` on pull requests and posts the level and hot spots as a comment. A pre-commit hook variant.

## Later

A companion skill for reviewing existing code, not only new changes. An Arabic edition of the reference files.
