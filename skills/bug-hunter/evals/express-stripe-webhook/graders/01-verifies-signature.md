---
type: llm
focus: trace
weight: 1
---

The handler verifies the Stripe-Signature header with `stripe.webhooks.constructEvent` (or an equivalent HMAC check with a timestamp tolerance) and responds with a 4xx status, without changing any order, when verification fails.
