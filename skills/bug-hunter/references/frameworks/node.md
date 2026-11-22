# Node notes: Express, Next.js, Prisma, Mongoose

## Express

- Body limits: `app.use(express.json({ limit: '100kb' }))`.
- Headers: `app.use(helmet())`.
- CORS: `cors({ origin: ['https://app.example.com'], credentials: true })`. Never `origin: true` together with `credentials: true` on routes that read user data.
- Behind a proxy, set `app.set('trust proxy', 1)` (the number of proxies). Wrong values let clients spoof `X-Forwarded-For` and bypass IP rate limits.
- Rate limits: `express-rate-limit` on login, OTP, reset, signup, and costly routes: `rateLimit({ windowMs: 15 * 60 * 1000, limit: 10 })`.
- Files: `res.sendFile(name, { root: '/srv/uploads' })` refuses paths that escape `root`. Without `root`, resolve and check containment yourself.
- Redirects: `res.redirect(req.query.next)` is an open redirect. Accept only relative paths starting with a single `/`.
- Errors: a final error handler that logs details and returns a generic message.

### Webhooks in Express

Register the raw body parser on the webhook route before the global JSON parser touches it:

```js
app.post('/webhooks/stripe', express.raw({ type: 'application/json' }), async (req, res) => {
  let event;
  try {
    event = stripe.webhooks.constructEvent(req.body, req.headers['stripe-signature'], process.env.STRIPE_WEBHOOK_SECRET);
  } catch {
    return res.status(400).send('invalid signature');
  }
  const firstTime = await recordEventOnce(event.id); // unique index on event_id
  if (firstTime) await queue.add('stripe-event', { id: event.id });
  res.sendStatus(200);
});
app.use(express.json());
```

## Next.js

- Route handlers (`app/**/route.ts`) and Server Actions are public HTTP endpoints. Authenticate and authorize inside each one, even if the page that calls it is protected.
- Do not rely on middleware alone for authorization. CVE-2025-29927 let attackers skip Next.js middleware with a crafted `x-middleware-subrequest` header. Keep Next.js patched and check access again where the data is read.
- `NEXT_PUBLIC_*` values are inlined into the browser bundle. Server secrets have no prefix and live in server-only modules. Add `import 'server-only'` to modules that must never reach the client.
- Props passed from Server Components to Client Components are serialized to the browser. Pass DTOs, not database rows with hashes and tokens.
- `images.remotePatterns` controls which hosts the image optimizer fetches. A wildcard host makes `/_next/image` an open fetch proxy.
- `dangerouslySetInnerHTML` needs DOMPurify (`isomorphic-dompurify` on the server).

## Validation with zod

```js
const UpdateProfile = z.object({ name: z.string().min(1).max(80), bio: z.string().max(500).optional() }).strict();
const data = UpdateProfile.parse(req.body); // unknown keys like role throw
```

## Prisma

- Tagged `$queryRaw` and `$executeRaw` are parameterized. `$queryRawUnsafe` and `$executeRawUnsafe` are not.
- Scope by owner: `prisma.invoice.findFirst({ where: { id, userId: session.user.id } })`. `findUnique` only accepts unique fields, so ownership needs `findFirst` or a compound unique key.
- Limit returned fields with `select`. Never `data: req.body`.

## Mongoose

- `mongoose.set('sanitizeFilter', true)` wraps operator-looking values so `{ "$ne": null }` cannot change a query.
- Cast inputs: `String(req.body.email)`.
- Scope: `Invoice.findOne({ _id: id, owner: req.user.id })`, not `findById(id)`.
- Hide sensitive fields with `select: false` in the schema.

## JWT

- `jsonwebtoken`: `jwt.verify(token, key, { algorithms: ['HS256'], issuer, audience })`.
- `jose`: `jwtVerify(token, key, { algorithms: ['RS256'], issuer, audience })`.

## Processes

`execFile(cmd, args)` or `spawn(cmd, args)` without `shell: true`. `exec(string)` always runs a shell.

## Outbound HTTP and SSRF

- Resolve with `dns.promises.lookup(host, { all: true })` and check every address with `ipaddr.js`: run `ipaddr.process(addr)` (converts IPv4-mapped IPv6) and allow only `range() === 'unicast'`.
- Connect to the address you checked by passing a custom `lookup` to the HTTP agent, or use a filtering agent such as `request-filtering-agent` after confirming it covers your HTTP client.
- `fetch` follows redirects by default. Use `redirect: 'manual'` and validate each `Location`.
- Always pass `AbortSignal.timeout(5000)` or an equivalent timeout.

## Prototype pollution

Never deep-merge request bodies into objects (`lodash.merge(config, req.body)`). Reject `__proto__`, `constructor`, and `prototype` keys, or use `Map` and `Object.create(null)`.

## Tests (Vitest or Jest with supertest)

```js
it('returns 404 for another user\'s invoice', async () => {
  const res = await request(app).get(`/invoices/${invoiceOfA.id}`).set('Cookie', cookieOfB);
  expect(res.status).toBe(404);
});

it('processes a duplicated webhook once', async () => {
  await sendSignedEvent(evt);
  await sendSignedEvent(evt);
  expect(await countOrdersMarkedPaid(evt)).toBe(1);
});
```
