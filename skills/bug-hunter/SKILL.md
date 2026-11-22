---
name: bug-hunter
description: Builds and changes code the way a bug bounty hunter would attack it. Before touching authentication, authorization, sessions, payments or credits, file uploads, webhooks, server-side URL fetching, SQL, shell or template execution, secrets, multi-tenant data, new dependencies, or LLM and agent features, it maps the attack surface, writes concrete abuse cases, applies secure defaults, attacks its own diff, and proves the protections with tests. Use this skill whenever the user asks to build, change, review, refactor, or harden an endpoint, API, form, auth flow, admin panel, integration, upload, payment flow, or AI feature, even if they never mention security. Skip it for styling, copy, documentation-only, or formatting changes.
license: MIT
metadata:
  author: Flint
  homepage: https://flint.ps
  version: "0.1.0"
---

# Bug Hunter

Attackers do not read code the way its author wrote it. They look for the one request the author never imagined: someone else's ID, a negative quantity, a webhook sent twice, a profile picture URL that points at the cloud metadata service. This skill makes you look for that request while you build, when the fix is one line, instead of after release, when it is an incident.

## 1. Decide how much security work the change needs

Classify the change before anything else. Proportionality matters. Security noise on trivial changes trains people to ignore it and wastes their tokens.

| Level | The change touches | What you do |
|---|---|---|
| 0 | Styling, copy, docs, formatting, tests only, refactors with no behavior change | Nothing from this skill. Do the task. |
| 1 | User input or rendering, but none of the sensitive surfaces below | Apply the secure defaults in section 3. No report. |
| 2 | Any sensitive surface: authentication, authorization, sessions or tokens, money, credits or quotas, file upload, download or paths, server-side URL fetching or webhooks, SQL, NoSQL, shell or template execution, deserialization, secrets or crypto, multi-tenant data, admin features, new dependencies, LLM or agent features | Full workflow in section 2, then a short report |

When unsure between two levels, pick the higher one. Once code exists, the triage script lists the sensitive surfaces a change touches and the references worth reading. Run it from the project root (the script path is relative to this skill's directory):

```bash
python scripts/triage_diff.py --git                    # working tree vs HEAD, new untracked files included
git diff main...HEAD | python scripts/triage_diff.py - # a branch or any other diff
```

It is a regex triage. Use it to avoid missing a surface, not to decide that a change is safe.

## 2. Level 2 workflow

### Step 1: Map the surface in a few lines

Name the assets (data, money, accounts, compute), the actors (anonymous visitor, normal user, user of another tenant, admin, and content the system ingests from outside such as webhook payloads, uploaded files, or web pages an LLM reads), the entry points this change adds or modifies, and the trust boundaries the data crosses. Details in `references/threat-model.md`.

### Step 2: Write abuse cases before writing code

Write 3 to 8 one-line abuse cases in the form "As <actor>, I <action> to <impact>." Rank them by likelihood times impact. Be concrete: a route, a parameter, a value.

Good: "As a logged-in user, I change `/invoices/1043/download` to `/invoices/1044/download` to read another customer's invoice."
Weak: "Attackers might access unauthorized data."

Then read only the references that match your abuse cases (map in section 5).

### Step 3: Build with secure defaults

Implement the feature so each abuse case is closed by design, using section 3 and the framework notes for the stack. Prefer controls that still hold when one layer fails. Scope the query to the owner and also check the policy.

### Step 4: Attack your own diff

Re-read the diff as the attacker. For every input the change accepts, ask what happens if it is someone else's identifier; missing, empty, null, or the wrong type; negative, zero, huge, or a float where an integer is expected; duplicated, replayed, or sent twice at the same moment; a path with `../`; a URL pointing at `127.0.0.1`, `169.254.169.254`, or an internal hostname; HTML or script; text instructing an LLM to ignore its rules. Follow each input to its sink: query, file system, HTTP client, template, model, shell. The full checklist is in `references/self-attack.md`.

Prove the important ones. For each high-risk abuse case, add at least one test that fails when the protection is removed, for example "user A gets 404 when requesting user B's invoice." A test is evidence. A sentence saying the code is secure is not.

### Step 5: Report briefly

End your answer with the format in `references/report-format.md`. State what you checked, what is mitigated and how it is proven, and what risk remains. Never claim the code is "secure".

## 3. Secure defaults (levels 1 and 2)

Each default is here because it is a common real finding. Broken access control is #1 in the OWASP Top 10:2025.

- **Authorize at the data layer.** Fetch objects through the current principal (`$user->invoices()->findOrFail($id)`, `WHERE owner_id = ?`) and check the policy too. Authentication middleware alone proves who the user is, not what they may touch.
- **Never trust client-supplied ownership, role, price, quantity, discount, or status.** Look them up or recompute them on the server. Allowlist fields for mass assignment.
- **Parameterize every query and command.** No SQL, shell, or template source built from user data. Dynamic column names come from an allowlist.
- **Encode output by default.** Avoid raw HTML sinks (`{!! !!}`, `dangerouslySetInnerHTML`, `v-html`, `|safe`) unless the content passes a maintained sanitizer.
- **Fetch user-supplied URLs carefully.** Allowlist schemes and hosts, resolve DNS and block private, loopback, link-local and metadata ranges, re-validate every redirect, set timeouts and size limits.
- **Verify webhooks.** Check the signature over the raw body with a constant-time comparison, enforce a timestamp tolerance, and process each event ID once.
- **Handle files defensively.** Validate type by content, cap size, generate server-side names, keep files in private storage, never build paths from user input, and serve downloads through an authorization check.
- **Keep secrets server-side.** Read them from the environment or a secret manager. Never put them in client bundles (`NEXT_PUBLIC_`, `VITE_`, `REACT_APP_`, `EXPO_PUBLIC_` variables are shipped to the browser), logs, error messages, URLs, or commits.
- **Rate-limit what attackers repeat.** Login, OTP, password reset, signup, invitations, expensive queries, and anything that spends money or LLM tokens.
- **Fail closed.** When auth, payment, or validation code errors out, deny. Users get a generic message, logs get the details without secrets.
- **Vet before adding a dependency.** Prefer the standard library or an existing dependency. See `references/dependencies.md`.
- **Treat LLM output as untrusted input.** Give tools the least privilege, require human confirmation for irreversible or external actions, and keep secrets out of prompts. See `references/ai-features.md`.

## 4. Framework notes

Read only the file for the stack in front of you:

- `references/frameworks/laravel.md`
- `references/frameworks/node.md` (Express, Next.js, Prisma, Mongoose)
- `references/frameworks/python.md` (Django, DRF, FastAPI, Flask)
- `references/frameworks/supabase-firebase.md`

## 5. Reference map

| The change involves | Read |
|---|---|
| Mapping the surface, writing abuse cases | `references/threat-model.md` |
| Login, sessions, tokens, roles, ownership, tenants, admin | `references/access-control.md` |
| SQL, NoSQL, shell, templates, HTML rendering, deserialization | `references/injection.md` |
| Fetching URLs, webhooks, redirects, third-party APIs | `references/outbound-and-webhooks.md` |
| Uploads, downloads, file processing, paths | `references/files.md` |
| Payments, credits, coupons, quotas, races, rate limits | `references/business-logic.md` |
| Secrets, password hashing, randomness, encryption, JWT | `references/secrets-and-crypto.md` |
| CORS, debug mode, headers, error handling, logging | `references/config-and-errors.md` |
| New or updated packages | `references/dependencies.md` |
| LLM calls, agents, tools, RAG | `references/ai-features.md` |
| Reviewing the diff as an attacker | `references/self-attack.md` |
| The final report | `references/report-format.md` |

## 6. Boundaries

- This skill is defensive. Test only the user's own code, locally or in their test suite. Do not write exploits for third-party systems and do not send attack traffic to hosts the user does not own.
- Every finding needs a concrete request, path, and impact. Do not pad the report with theoretical issues.
- If a protection needs infrastructure you cannot add here (a rate limiter service, a WAF rule, a secret manager), list it as residual risk instead of pretending it exists.
