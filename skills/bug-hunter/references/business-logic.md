# Business logic: money, credits, coupons, races, limits

Scanners rarely find these bugs because the code is "correct". The logic is wrong. Bounty hunters love them for the same reason.

## Money and quantities

- Prices, totals, discounts, tax, and shipping come from the server, never from the request.
- Store money as integers in the smallest unit (cents) or as decimals, never floats.
- Validate ranges: quantity is a positive integer with a sensible maximum; amounts are positive; percentages stay in 0 to 100.
- Re-validate the cart at checkout. Prices and stock change between page load and payment.
- Currency is part of the amount. Do not compare amounts across currencies.

## Coupons, credits, gift cards, trials

- Single-use means enforced by the database (unique constraint on redemption, or an atomic update), not by an `if` before the insert.
- Define stacking rules explicitly and enforce them server-side.
- Check expiry, per-user limits, eligible products, and minimum totals at redemption time.
- Trials and referral rewards attract multi-account abuse. Tie rewards to verified actions and add rate limits.

## Race conditions

Two requests that each check then act will both pass the check.

| Pattern | Example | Fix |
|---|---|---|
| Check then update | `if balance >= amount: balance -= amount` | Atomic update: `UPDATE accounts SET balance = balance - :amt WHERE id = :id AND balance >= :amt`, then check rows affected |
| Read then insert | Redeem coupon if not redeemed | Unique constraint plus handling the duplicate error |
| Multi-step state | Order paid, then shipped | Transaction with row lock (`SELECT ... FOR UPDATE`, `lockForUpdate()`, `select_for_update()`) and a state machine |
| Retries from clients | Double-click on "Pay" | Idempotency key per operation, stored with a unique constraint |

Test races for real: send the same request concurrently (10 to 50 parallel calls) and assert exactly one success.

## Workflow bypass

- Model multi-step flows as server-side state machines. A request may only move an object from an allowed state to an allowed next state.
- Confirm payment with the provider (or a verified webhook) before fulfilling. A redirect to `/success` proves nothing.
- Check every step on the server even if the UI only shows the next button after the previous step.

## Limits and abuse

- Rate-limit by account, by IP, and by target resource: login, OTP, password reset, signup, invitations, contact forms, SMS and email sending, search, exports, and AI endpoints.
- Cap page sizes, query depth and complexity (GraphQL), export sizes, and upload counts.
- Account enumeration: login, signup, and reset should not reveal whether an email exists through different messages, status codes, or timing.
- Denial of wallet: anything that costs you money per call (SMS, email, LLM tokens, third-party APIs) needs per-user quotas and global spend alerts.

## Sharing and invitations

- Share links: random tokens, expiry, revocation, scoped to one resource and permission level.
- Invitations: bind to the invited email, single use, and do not let the accepting user pick a higher role than offered.

## Tests to write

- Quantity `-1`, `0`, `1.5`, and `1000000` are rejected or clamped.
- A tampered price in the request body is ignored.
- Ten parallel redemptions of one single-use coupon produce exactly one success.
- Calling the "ship" endpoint on an unpaid order fails.
- The eleventh OTP attempt within the window is blocked.
