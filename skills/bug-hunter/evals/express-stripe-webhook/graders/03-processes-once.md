---
type: llm
focus: trace
weight: 1
---

The code prevents the same event from being processed twice, for example by recording the Stripe event ID under a unique constraint or by updating only orders that are not already paid.
