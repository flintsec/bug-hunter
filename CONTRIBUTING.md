# Contributing to bug-hunter

Thanks for helping. This skill is only as good as the cases it knows, so real-world experience is the most valuable thing you can bring.

## What helps most

Abuse cases from real bugs. Take a vulnerability you found or read about in a public, already disclosed report and turn it into one line in the "As actor, I action to impact" form, plus the defense and a test that proves it. Put it in the reference file for that surface.

Framework notes. Stack-specific traps belong in `skills/bug-hunter/references/frameworks/`. Rails, Spring, Go, ASP.NET and NestJS notes are wanted.

Bench tasks. A realistic feature request, a starter repository, and oracle tests. See `bench/tasks.md` for the format.

Triage rules. New patterns for `scripts/triage_diff.py`, each with a test in `scripts/test_triage_diff.py` that shows a true positive and, when you can, a near miss that must not match.

## Rules

Never include details of undisclosed vulnerabilities, private bug bounty reports, or anything a program asked you to keep confidential. Generalize the pattern, change the names, and keep only what is already public knowledge.

Keep the skill defensive. Content that helps attack systems the user does not own will not be merged.

Every claim needs evidence. If you add a rule to SKILL.md, add or update an eval case that fails without it.

Watch the budget. SKILL.md stays under 500 lines and holds only what applies to every sensitive change. Domain detail goes to `references/`. Reference files over 300 lines need a contents list at the top.

Explain why. A short reason works better for models than an instruction in capital letters.

## Workflow

1. Open an issue describing the failure you saw: the prompt, what the agent wrote, and why it is exploitable.
2. Add an eval case under `skills/bug-hunter/evals/` that reproduces it.
3. Change the skill.
4. Run the unit tests and the evals with and without the skill:

```bash
python -m unittest discover -s skills/bug-hunter/scripts -v
cd skills/bug-hunter && claude plugin eval . --allow-tools Write,Edit,Bash --scaffold
```

5. In the pull request, include the before and after results and the token cost difference.

## Style

Short sentences. Concrete routes, parameters and values in examples. American English spelling. No em-dashes.
