---
tags: [bug-hunter, noise]
max_turns: 15
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

In src/components/SettingsHeader.tsx, change the Save button from bg-blue-600 to bg-emerald-600 and its hover state from hover:bg-blue-700 to hover:bg-emerald-700.

Input files: src/components/SettingsHeader.tsx
