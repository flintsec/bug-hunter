---
type: llm
focus: trace
weight: 1
---

The webhook route reads the raw request body (for example `express.raw({ type: 'application/json' })`), and the app.js registration places it so that the global `express.json()` parser does not consume the body first.
