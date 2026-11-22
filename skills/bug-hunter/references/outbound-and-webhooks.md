# Outbound requests, SSRF, redirects, webhooks, third-party APIs

## Server-side request forgery (SSRF)

SSRF appears whenever the server fetches a URL that a user influences: avatar or image from URL, link previews and unfurling, "import from URL", PDF or screenshot generators that load remote resources, outgoing webhooks to user-configured endpoints, OIDC discovery, and LLM tools that browse.

What an attacker reaches through it: cloud metadata (`169.254.169.254`, `metadata.google.internal`) and the credentials it serves, admin panels on `localhost`, databases and caches on private addresses, internal APIs that trust the network.

### Defenses, in order

1. **Avoid it.** Let the browser upload the file instead of the server fetching a URL.
2. **Allowlist.** If the feature only needs a few hosts, allow exactly those.
3. **Parse strictly.** Use the language's URL parser, allow only `http` and `https`, reject credentials in the URL (`user:pass@`), restrict ports to 80 and 443.
4. **Resolve, check, connect to the checked IP.** Resolve the hostname yourself, reject any address in the blocked ranges below, then connect to that exact IP (with the original `Host` header). Checking the name and then letting the HTTP client resolve it again allows DNS rebinding.
5. **Handle redirects.** Disable automatic redirects, or re-run the full check on every hop.
6. **Bound the request.** Connect and read timeouts, maximum response size, maximum redirects, expected content type.
7. **Do not reflect.** Never return the raw response body or detailed network errors to the user. That turns blind SSRF into full SSRF.
8. **Infrastructure.** Route user-URL fetching through an egress proxy that enforces the same rules (Stripe's open source Smokescreen is one), apply network policies to fetcher workers, and require IMDSv2 on AWS. This is the most robust option when the feature is central to the product. It complements the checks above.

### Blocked address ranges

```text
IPv4: 0.0.0.0/8, 10.0.0.0/8, 100.64.0.0/10, 127.0.0.0/8, 169.254.0.0/16,
      172.16.0.0/12, 192.0.0.0/24, 192.168.0.0/16, 198.18.0.0/15,
      224.0.0.0/4, 240.0.0.0/4, 255.255.255.255/32
IPv6: ::/128, ::1/128, fc00::/7, fe80::/10, ff00::/8,
      ::ffff:0:0/96 (IPv4-mapped: check the embedded IPv4 too)
```

Most languages offer a helper (`ipaddress` in Python with `is_private`, `is_loopback`, `is_link_local`, `is_reserved`, `is_multicast`; the `ipaddr.js` or `ip-address` packages in Node). Remember alternate encodings like `0x7f000001`, `2130706433`, and `127.1`. Parsing through the IP library and checking the resulting address handles them.

## Open redirects

- Prefer named routes or relative paths you control.
- If a `next` or `return_to` parameter is needed, accept only relative paths that start with a single `/` and reject `//`, `/\`, and anything with a scheme. Or keep an allowlist of exact destinations.
- Open redirects matter more than they look: they upgrade phishing and can leak OAuth codes.

## Receiving webhooks

1. **Verify the signature over the raw request body.** Frameworks that parse JSON first change the bytes. Use the raw body (`express.raw` on that route, `$request->getContent()` in Laravel, `await request.body()` in FastAPI) and the provider's SDK when one exists (`stripe.webhooks.constructEvent`).
2. **Compare in constant time.** `hash_equals`, `crypto.timingSafeEqual`, `hmac.compare_digest`.
3. **Check the timestamp.** Reject events outside a tolerance window, often five minutes, to limit replay.
4. **Process each event once.** Store the provider's event ID under a unique constraint, inside the same transaction as the side effect. Duplicate deliveries are normal behavior for providers, not an attack.
5. **Do not trust amounts or statuses in the payload for money decisions.** Re-fetch the object from the provider's API, or compare against your own order record.
6. **Respond fast, work later.** Return 2xx after verification and persistence, then process in a queue. Slow handlers cause retries and duplicates.
7. **Expect any order.** Events can arrive out of order. Use state machines with allowed transitions instead of "last event wins".
8. **CSRF exemption is fine** for webhook routes only when the signature check replaces it.

## Sending webhooks to user-configured URLs

- Treat the destination as an SSRF sink with every rule above.
- Sign your payloads (HMAC with a per-endpoint secret, include a timestamp) so receivers can verify.
- Retry with exponential backoff and jitter, cap attempts, and disable endpoints that keep failing.
- Keep secrets and personal data out of payloads unless the receiver needs them.

## Calling third-party APIs

- Set timeouts on every call. Many default HTTP clients wait forever.
- Retry only idempotent operations, or send an idempotency key for writes (payments, orders, emails).
- Validate and type the response before using it. A compromised or buggy upstream is outside content.
- Use the narrowest API key scope, store keys server-side, rotate them.
- Log request IDs, never full tokens or authorization headers.

## Tests to write

- Avatar URL `http://169.254.169.254/latest/meta-data/` is rejected.
- A URL on an allowed host that redirects to `http://127.0.0.1:6379/` is rejected at the redirect.
- `http://0x7f000001/` and `http://[::ffff:127.0.0.1]/` are rejected.
- A webhook with an invalid signature returns 400 and changes nothing.
- The same valid webhook delivered twice produces one side effect.
- `?next=//evil.example` redirects to the default page, not off-site.
