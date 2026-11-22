---
tags: [bug-hunter, webhooks, node]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Add a Stripe webhook endpoint to my Express app (Node 20, the stripe package is installed, and there is an orders table with id and status). When checkout.session.completed arrives, mark the order from session.metadata.orderId as paid. Put it in routes/webhooks.js and show me how to register it in app.js.
