# Report format

The report is for a busy developer. It should take under a minute to read and every line should point to something they can check.

## Level 0

No report. Do not mention security.

## Level 1

No table. If a secure default changed behavior the user will notice (for example output is now escaped, or a field is now ignored on update), say it in one sentence.

## Level 2

Use this structure at the end of the answer:

```markdown
### Security notes

Level 2: <the sensitive surfaces this change touches, in a few words>

| # | Abuse case | Status | Evidence |
|---|---|---|---|
| 1 | <actor> <action> to <impact> | Mitigated, tested | <code location> + <test name> |
| 2 | ... | Mitigated, not tested | <code location> |
| 3 | ... | Partly mitigated | <what is done, what is missing> |
| 4 | ... | Not addressed | <why, and where it should be fixed> |

Tests added: <file> (<number> tests)
Residual risk: <one or two sentences, or "none identified for this change">
```

## Status values

| Status | Meaning |
|---|---|
| Mitigated, tested | A control exists and a test fails if it is removed |
| Mitigated, not tested | A control exists, no test proves it yet |
| Partly mitigated | Some vectors are closed, others remain (say which) |
| Not addressed | Real risk, outside this change or needs infrastructure |
| Not applicable | Considered and ruled out (use sparingly, one line of reasoning) |

## Rules

- One row per abuse case. Three to eight rows.
- Evidence is a file and function, a line, or a test name. "Validated input" is not evidence.
- Never write that the code is "secure", "fully protected", or "safe". Write what was checked.
- Dependencies added or updated get one line after the table: package, version, reason, what was verified.
- If a protection depends on deployment (a proxy rate limit, an environment variable, a bucket policy), put it in residual risk so it does not get lost.

## Example

```markdown
### Security notes

Level 2: invoice download (object access, private files)

| # | Abuse case | Status | Evidence |
|---|---|---|---|
| 1 | Customer B changes the invoice ID in the URL to download customer A's invoice | Mitigated, tested | `InvoiceDownloadController` uses `$request->user()->invoices()->findOrFail()`; `test_user_cannot_download_another_users_invoice` |
| 2 | Logged-out visitor guesses download URLs | Mitigated, tested | Route in `auth` group; `test_guest_is_redirected_to_login` |
| 3 | Attacker reads PDFs directly from `/storage` | Mitigated, not tested | Files stored on the `local` disk outside `public/` |
| 4 | Script enumerates IDs to measure which invoices exist | Partly mitigated | 404 for others' invoices, no rate limit on the route yet |

Tests added: `tests/Feature/InvoiceDownloadTest.php` (3 tests)
Residual risk: add `throttle:60,1` to the route group or an edge rate limit.
```
