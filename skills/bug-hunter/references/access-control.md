# Access control: authentication, authorization, sessions, tenants

Broken access control is #1 in the OWASP Top 10:2025, and the 2025 edition folds SSRF into it. Agents usually get authentication right and authorization wrong: the route requires login, but nothing checks that the object belongs to the caller.

## Contents
1. Authorization layers
2. Multi-tenant data
3. Mass assignment and response leaks
4. Authentication flows
5. Sessions and tokens
6. Tests to write
7. Mistakes agents make

## 1. Authorization layers

Check all three for every route the change touches.

| Layer | Question | Typical bug | Defense |
|---|---|---|---|
| Function | May this role call this endpoint at all? | Admin route protected only in the UI (BFLA) | Server-side role or permission check on the route or controller |
| Object | May this principal touch this specific object? | `/orders/{id}` returns any order (IDOR / BOLA) | Query through the principal, plus a policy check |
| Property | May this principal read or write this field? | User sets `role`, response includes `password_hash` (BOPLA) | Input allowlist, output DTOs or resources |

Deny by default. A new route without an explicit rule should fail closed.

Scope the query, do not filter afterwards:

```text
good:  invoice = current_user.invoices.find(id)          -> 404 for others
risky: invoice = Invoice.find(id); if invoice.user_id != current_user.id: deny
```

Both can be correct, but the first cannot be forgotten in a later code path. Return 404 rather than 403 for objects the caller should not know exist.

Unguessable IDs (UUIDs) make enumeration harder. They are not authorization. Links get shared, logged, and leaked.

## 2. Multi-tenant data

- Take the tenant from the authenticated session, never from a request parameter or header the client controls.
- Apply tenant scoping centrally (global scopes, row level security, repository base class) and also in raw queries, background jobs, exports, search indexes, caches, and file storage paths.
- Unique constraints and lookups should include the tenant (`UNIQUE(tenant_id, slug)`).
- Cache keys must include the tenant and, for per-user data, the user.
- Background jobs carry the tenant and acting user explicitly and re-check access when they run.
- Vector stores and search indexes need the same filter. RAG over all tenants' documents is a data leak waiting for the right question.

## 3. Mass assignment and response leaks

- Allowlist writable fields (`$fillable`, DTOs, Pydantic or Zod schemas, serializer `fields`). Never pass the whole request body to `create` or `update`.
- Fields like `role`, `is_admin`, `owner_id`, `tenant_id`, `balance`, `email_verified_at`, `status`, `price` are server-controlled.
- Return explicit response shapes. Serializing the whole model leaks password hashes, tokens, internal flags, and other users' data in nested relations.

## 4. Authentication flows

**Passwords.** Use the framework's hasher (bcrypt or Argon2id). Never MD5, SHA-1, or a plain SHA-256. Do not set maximum lengths so low that passphrases fail, and remember bcrypt ignores input past 72 bytes.

**Login.** Same response and similar timing for unknown user and wrong password. Rate-limit per account and per IP. Regenerate the session ID after login.

**Password reset.** Random single-use token from a CSPRNG, short expiry (minutes to an hour), stored hashed, invalidated after use and when the password changes. The response does not reveal whether the email exists. Never build the reset link from the request's `Host` header.

**OTP and 2FA.** Limit attempts per code and per account, expire codes quickly, compare in constant time, bind the code to the specific login attempt.

**Email change.** Confirm on the new address and notify the old one. Require re-authentication for email, password, and 2FA changes.

**OAuth and OIDC.** Use and check `state`, use PKCE, match `redirect_uri` exactly against a registered list, validate the ID token signature, issuer, audience, and expiry. Link accounts by verified email only.

**Invites and magic links.** Random, expiring, single-use, scoped to one resource and one role.

## 5. Sessions and tokens

- Cookies: `HttpOnly`, `Secure`, `SameSite=Lax` or `Strict`, narrow path and domain.
- Logout and password change invalidate sessions on the server.
- CSRF protection for cookie-authenticated state-changing requests. Routes exempted from CSRF (webhooks) need another proof of origin, such as a signature.
- JWT: pin the algorithm on verification, reject `none`, verify signature, `exp`, `iss`, and `aud`, keep lifetimes short, rotate refresh tokens and detect reuse. Ignore `jku`, `x5u`, and attacker-controlled `kid` lookups. A JWT payload is readable by anyone, so keep secrets out of it.
- API keys: show once, store hashed, scope them, allow rotation, and log their use.

## 6. Tests to write

Create two users in two tenants in your fixtures. Then, for every route the change adds:

- User B requests user A's object by ID. Expect 404 or 403 and no data in the body.
- User B tries to update or delete user A's object. Expect denial and an unchanged database row.
- A normal user calls the admin function directly. Expect 403.
- The request body includes a server-controlled field (`role`, `owner_id`, `price`). Expect it to be ignored or rejected.
- Logged-out request. Expect 401 or a redirect, never data.

## 7. Mistakes agents make

- Adding `auth` middleware and treating the route as protected.
- Trusting `user_id`, `tenant_id`, or `role` from the request body or a header.
- Checking ownership in the `show` action but not in `update`, `delete`, `export`, or the download route.
- Returning `model.toJSON()` or `fields = '__all__'`.
- Hiding the admin button in the frontend instead of checking the role on the server.
- Using the incrementing ID in a public URL and calling it fine because "you need to be logged in".
