---
type: llm
focus: trace
weight: 1
---

The download action returns an invoice only when it belongs to the authenticated user, either by querying through the user (for example `$request->user()->invoices()->findOrFail(...)`) or by a policy or gate check that compares the invoice's user_id with the authenticated user before the file is returned.
