# Attacking your own diff

You wrote the code, so you know what it is supposed to do. This pass is about what it actually allows. Do it after the feature works and before you report.

## Procedure

1. **List every input the change reads.** Path parameters, query string, body fields, headers (including `Host`, `X-Forwarded-For`, `Origin`), cookies, uploaded files, webhook payloads, environment variables, values from the database that another user wrote, third-party API responses, and LLM output.
2. **Follow each input to its sinks.** Database query, file system, outbound HTTP, HTML or template, shell, redirect, log, email, another service, the model's context or tools.
3. **Ask the questions below for each input and sink pair.** Write down only what is actually reachable.
4. **For each protection you added, imagine deleting it.** If no test fails, write the test.
5. **Look around the change, not only at it.** Other actions on the same resource (show, update, delete, export, download), background jobs, caches, search indexes, error paths, and old endpoints that still exist.

## Questions by input

| Question | What it catches |
|---|---|
| What if this ID belongs to another user or tenant? | IDOR, BOLA, cross-tenant leaks |
| What if the caller has a lower role? What if they are logged out? | BFLA, missing auth |
| What if the body contains extra fields like `role`, `owner_id`, `price`, `status`? | Mass assignment |
| What if the value is missing, empty, null, an array instead of a string, or the wrong type? | Type confusion, NoSQL operator injection, crashes that fail open |
| What if the number is negative, zero, huge, a float, or `NaN`? | Money bugs, overflow, resource exhaustion |
| What if the same request arrives twice, or twenty times at once? | Races, double spending, duplicate webhooks |
| What if the string contains `'`, `"`, `<`, `{{`, `$(`, `../`, `%00`, CR or LF? | Injection, traversal, header injection |
| What if the URL points to `127.0.0.1`, `169.254.169.254`, an internal name, or redirects there? | SSRF |
| What if the file is huge, a renamed executable, an SVG with script, or an archive with `../` paths? | Upload attacks |
| What if the text tells the model to ignore its instructions? | Prompt injection |
| What if a step of the flow is skipped or repeated out of order? | Workflow bypass |

## Questions by sink

| Sink | Check |
|---|---|
| Query | Parameterized? Scoped to the principal and tenant? Page size capped? |
| File system | Path built from user data? Resolved and contained? Private storage? |
| Outbound HTTP | User-controlled host? Redirects re-validated? Timeouts? |
| HTML or template | Escaped by default? Any raw sink? URL schemes allowlisted? |
| Shell | Argument array, no shell? `--` before positional arguments? |
| Redirect | Relative path or allowlisted destination only? |
| Logs | Secrets and personal data redacted? Newlines encoded? |
| Model and tools | Untrusted content separated? Destructive tools confirmed? Arguments validated? |

## Questions about failure

- When the auth check, payment call, or validation throws, does the code deny or continue?
- Does a `default` branch on a role or status deny?
- Does the error response include stack traces, SQL, file paths, or internal hostnames?
- Are transactions rolled back so a failure cannot leave money or permissions half-changed?

## Turning findings into tests

Each confirmed high-risk case gets a test that would fail if the protection disappeared. Name the test after the attack, not the feature: `test_user_cannot_download_another_users_invoice` tells the next developer why it exists.

Use the safe test values from `injection.md` against the user's own code only, in the local test suite.

## When you find something you cannot fix here

Fix what you can in this change. For the rest (a missing rate limiter at the edge, a legacy endpoint outside the task), list it as residual risk with the exact location. Do not silently widen the scope of the change, and do not hide it.
