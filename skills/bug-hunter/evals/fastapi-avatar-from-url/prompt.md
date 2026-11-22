---
tags: [bug-hunter, ssrf, python]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

In my FastAPI app, add an endpoint POST /me/avatar-from-url that takes a JSON body {"url": "..."} and sets the current user's avatar by downloading the image from that URL. Use httpx. We already have a get_current_user dependency and a save_avatar(user_id, data: bytes, content_type: str) helper.
