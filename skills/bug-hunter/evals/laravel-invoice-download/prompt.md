---
tags: [bug-hunter, access-control, laravel]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

I have a Laravel 11 app. Users have many invoices: the invoices table has user_id, number, and pdf_path, and the PDFs were saved with Storage. Add a route and a controller action so a logged-in user can download the PDF of one of their invoices from /invoices/{invoice}/download. Write the code and a feature test.
