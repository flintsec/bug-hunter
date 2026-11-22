# Secrets, passwords, randomness, encryption

Most crypto bugs in application code are not broken math. They are the wrong primitive, a secret in the wrong place, or a comparison that leaks timing.

## Secrets

- Read secrets from the environment or a secret manager. Commit `.env.example` with placeholders, never `.env`.
- Client-side variables are public. Anything prefixed `NEXT_PUBLIC_`, `VITE_`, `REACT_APP_`, `EXPO_PUBLIC_`, or `PUBLIC_` (SvelteKit, Astro) is compiled into the browser bundle. Only publishable keys belong there.
- Never log secrets. Redact `Authorization` headers, cookies, tokens, passwords, and full request bodies of auth endpoints.
- Never put secrets in URLs. Query strings end up in logs, browser history, and `Referer` headers.
- A leaked secret must be rotated. Deleting the commit is not enough, because history, forks, CI caches, and bots already have it.
- Separate keys per environment and per purpose. The key that signs sessions should not also sign webhooks.
- Scan before pushing: `gitleaks` or `trufflehog` in a pre-commit hook or CI.

## Passwords

| Use | Never |
|---|---|
| The framework hasher: Laravel `Hash::make` (bcrypt or Argon2id), Django default PBKDF2 or Argon2, `argon2` or `bcrypt` packages in Node, `argon2-cffi` or `bcrypt` in Python | MD5, SHA-1, SHA-256, or any fast hash, with or without salt |
| `password_verify`, `Hash::check`, `check_password` for verification | String comparison of hashes |

Rehash on login when the algorithm or cost changes. Check new passwords against a breached-password list when the product allows it.

## Randomness for tokens and IDs

| Language | Secure | Not for security |
|---|---|---|
| PHP | `random_bytes(32)`, `bin2hex(random_bytes(32))`, `Str::random(40)`, `random_int` | `rand`, `mt_rand`, `uniqid`, `lcg_value`, `str_shuffle` |
| Python | `secrets.token_urlsafe(32)`, `secrets.token_hex(32)`, `secrets.randbelow` | `random.*`, `uuid1` |
| Node | `crypto.randomBytes(32).toString('hex')`, `crypto.randomUUID()` | `Math.random`, `Date.now()` based IDs |

Use at least 128 bits of entropy for anything that grants access: reset tokens, invite codes, API keys, session IDs. Store reset tokens and API keys hashed, like passwords.

## Comparing secrets

Compare signatures, tokens, and HMACs in constant time:

- PHP: `hash_equals($known, $user)`
- Python: `hmac.compare_digest(a, b)`
- Node: `crypto.timingSafeEqual(a, b)` (both buffers must have the same length, so check the length first and return false when it differs)

## Integrity and signatures

- HMAC-SHA256 with a long random key for signing data you will verify later (webhooks, signed URLs, unsubscribe links).
- Include an expiry and a purpose in what you sign, so a token for one action cannot be replayed for another.
- SHA-256 alone is a checksum, not a signature. Anyone can recompute it.

## Encryption

- Prefer high-level APIs: Laravel `Crypt` and the `encrypted` cast, libsodium (`sodium_crypto_secretbox`), Python `cryptography` (`Fernet` or `AESGCM`).
- With low-level APIs use an AEAD mode such as AES-256-GCM with a random 12-byte nonce per message, and never reuse a nonce with the same key.
- Never ECB, never DES or RC4, never Node's deprecated `crypto.createCipher` (it derives keys from passwords badly).
- Never invent a scheme. If you are combining primitives by hand, stop and use a library construction.
- Encrypted columns cannot be searched. When lookup is needed, store a keyed hash (HMAC) of the value next to the ciphertext.

## TLS

Never disable certificate verification in code that ships: `verify=False` (requests, httpx), `rejectUnauthorized: false` (Node), `CURLOPT_SSL_VERIFYPEER => false` (PHP), `NODE_TLS_REJECT_UNAUTHORIZED=0`. Fix the trust store instead.

## JWT in one paragraph

Pin the algorithm when verifying, reject `none`, verify `exp`, `iss`, and `aud`, keep access tokens short-lived, and use a long random secret for HMAC algorithms. The payload is only base64-encoded, so anyone holding the token can read it. Details in `access-control.md`.

## Tests to write

- The production client bundle does not contain server secrets (build, then search the output for the secret's variable name or a known prefix like `sk_live_`).
- New users have password hashes that start with the expected algorithm prefix (`$2y$`, `$argon2id$`, `pbkdf2_sha256$`).
- A reset token works once and fails the second time and after expiry.
- A webhook or signed URL with one changed byte in the signature is rejected.
