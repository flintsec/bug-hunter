# Configuration, error handling, logging

Three OWASP Top 10:2025 categories live here: A02 Security Misconfiguration, A09 Security Logging and Alerting Failures, and A10 Mishandling of Exceptional Conditions.

## Debug and admin surfaces

- Production runs with debug off: `APP_DEBUG=false` (Laravel), `DEBUG = False` (Django), no `debug=True` in Flask (the Werkzeug debugger executes code), `NODE_ENV=production`.
- Development dashboards are gated or disabled in production: Laravel Telescope, Horizon, Debugbar, Django admin on a guessable path with weak accounts, Swagger or GraphQL playgrounds for internal APIs.
- No default credentials, no sample accounts, no seeded admin with a known password.
- Nothing sensitive under the web root: `.env`, `.git/`, database dumps, backups, `phpinfo()` pages, logs. Disable directory listing.

## CORS

- CORS relaxes the browser's same-origin policy. It does not protect your API from non-browser clients.
- With credentials (cookies) allowed, list exact origins. Reflecting whatever `Origin` arrives together with `Access-Control-Allow-Credentials: true` lets any website read your users' data.
- Never allow the `null` origin. Sandboxed iframes and local files send it.
- Origin checks compare the full origin. A check like `origin.endsWith('example.com')` accepts `evilexample.com`.

## Security headers

Set them once in middleware (helmet in Express, `SecurityMiddleware` in Django, a middleware in Laravel):

| Header | Purpose |
|---|---|
| `Strict-Transport-Security` | Forces HTTPS on later visits |
| `Content-Security-Policy` | Second layer against XSS, controls framing with `frame-ancestors` |
| `X-Content-Type-Options: nosniff` | Stops browsers from treating uploads as HTML or script |
| `Referrer-Policy: strict-origin-when-cross-origin` | Keeps tokens in URLs from leaking to other sites |

## Cloud and storage

- Buckets private by default, public only for intentionally public assets.
- IAM roles with least privilege, no wildcard actions on production data.
- On AWS, require IMDSv2 on instances so a simple SSRF cannot read credentials.

## Exceptional conditions (A10)

- **Fail closed.** If an authorization check, payment verification, or signature validation throws, the request is denied. A `catch` that logs and continues is a bypass.
- **Deny by default in branches.** A `switch` or `match` on role, plan, or status ends with a branch that denies.
- **Handle missing values explicitly.** `if (user.role !== 'admin') deny()` is correct; `if (user.role === 'guest') deny()` lets `undefined` through.
- **Decide what timeouts mean.** When the fraud check or the payment provider times out, the order is not approved.
- **Roll back.** Multi-step changes to money, permissions, or inventory run in a transaction.
- **Generic errors outside, details in logs.** No stack traces, SQL, file paths, or internal hostnames in responses.

## Logging and alerting (A09)

Log security-relevant events with user ID, tenant, IP, and request ID:

- login success and failure, logout, password and email changes, 2FA changes
- password reset requests and completions
- authorization failures (403s and 404s on owned resources in bulk are a scraping signal)
- role and permission changes, API key creation and revocation
- payment events, refunds, webhook signature failures
- rate-limit hits

Rules: never log secrets, tokens, or full card numbers; encode user input so it cannot forge log lines; send logs somewhere an attacker on the app server cannot edit; alert on spikes, not only on single events.

## Tests to write

- Production config has debug disabled (a test that boots with production settings and asserts the flag).
- A request with `Origin: https://evil.example` does not receive `Access-Control-Allow-Origin` for credentialed routes.
- A forced exception in the authorization path results in denial, not success.
- Error responses for a broken query do not include stack traces or SQL.
