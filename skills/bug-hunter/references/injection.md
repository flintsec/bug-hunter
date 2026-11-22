# Injection: SQL, NoSQL, shell, templates, HTML, deserialization

Injection happens when data crosses into a place where it is interpreted as code. The fix is always the same idea: keep data and code in separate channels.

## SQL

- Use the ORM or query builder with bound parameters. Prepared statements fix values, not identifiers.
- Raw escape hatches are where agents slip: Laravel `DB::raw`, `whereRaw`, `orderByRaw`, `selectRaw`, `DB::statement`; Sequelize `literal` and `query`; Knex `raw`; Prisma `$queryRawUnsafe` and `$executeRawUnsafe`; SQLAlchemy `text()` built with f-strings; Django `.extra()` and `.raw()` with string formatting. Each of these is fine only with bound parameters.
- Column names, sort direction, and table names cannot be bound. Map user input through an allowlist:

```text
sort = {"newest": "created_at", "price": "price_cents"}.get(input, "created_at")
direction = "desc" if input_dir == "desc" else "asc"
```

- `LIKE` patterns: escape `%` and `_` when the user should not control wildcards.
- Batch `IN` lists: bind each element, cap the list length.

## NoSQL

- MongoDB operator injection: a JSON body like `{"password": {"$ne": null}}` turns an equality check into "any value". Cast inputs to the expected type, reject keys starting with `$` or containing `.`, enable Mongoose `sanitizeFilter`.
- Never pass user input to `$where`, `mapReduce`, or server-side JavaScript.

## Shell and processes

- Avoid the shell. Call the program with an argument array (`spawn("convert", [input, output])`, `subprocess.run([...], shell=False)`, Symfony `Process` with an array).
- Never interpolate input into a command string, even "escaped". `escapeshellarg` is a last resort.
- Watch option injection: a filename like `--output=/etc/passwd` is parsed as a flag. Put `--` before positional arguments.
- Prefer a library over shelling out (image processing, archives, PDF).

## Templates (SSTI)

- Never render user input as a template: Jinja2 `Template(user_input)` or `render_template_string(user_input)`, Blade `Blade::render($userString)`, Twig `createTemplate`, Handlebars `compile(userInput)`.
- User content goes into templates as variables, never as template source.

## Cross-site scripting (XSS)

- Rely on framework auto-escaping (`{{ }}` in Blade, Jinja, Vue, JSX).
- Raw sinks need a sanitizer: Blade `{!! !!}`, React `dangerouslySetInnerHTML`, Vue `v-html`, Jinja `|safe`, Django `mark_safe`, DOM `innerHTML`, `insertAdjacentHTML`, `document.write`. Sanitize with a maintained library (DOMPurify, HTML Purifier, nh3). Bleach is deprecated.
- Markdown renderers often allow raw HTML and `javascript:` links by default. Disable raw HTML or sanitize the rendered output.
- Attributes: user URLs in `href` and `src` need a scheme allowlist (`http`, `https`, `mailto`). `javascript:` and `data:` are XSS.
- Inline script blocks: JSON-encode with a safe encoder, never string-concatenate into `<script>`.
- SVG and HTML uploads served from your origin are stored XSS. See `files.md`.
- Add a Content Security Policy as a second layer, not as the fix.

## Path traversal

- Resolve the final path and confirm it stays inside the base directory:

```text
full = realpath(join(base, name))
assert full == base or full.startswith(base + separator)
```

- Better: never take paths from users. Store files under generated IDs and look them up in the database.
- Watch encodings: `..%2f`, `%2e%2e/`, backslashes on Windows, absolute paths, null bytes in older runtimes.

## Header and log injection

- Strip `\r` and `\n` from values placed in headers (`Content-Disposition` filenames, redirect locations).
- Encode user data in logs so a value cannot forge a new log line.

## CSV and spreadsheet injection

Exports opened in Excel or Sheets execute cells starting with `=`, `+`, `-`, `@`, tab, or carriage return. Prefix such cells with a single quote when exporting user content.

## Deserialization and dynamic code

- Never deserialize untrusted data with PHP `unserialize`, Python `pickle` or `marshal`, Java `ObjectInputStream`, or YAML full loaders. Use JSON, or `yaml.safe_load`.
- No `eval`, `new Function`, `vm.runInContext`, or `exec` on user data.
- XML: disable external entities (`defusedxml` in Python, secure parser settings elsewhere) to prevent XXE.

## Regular expressions (ReDoS)

User input against nested quantifiers like `(a+)+$` can hang a worker. Bound input length, avoid nested quantifiers, or use a linear-time engine (RE2) for user-supplied patterns.

## Safe test strings for your own test suite

Use these against the user's own code, in tests, to prove the defense works.

| Class | Test value | Expected |
|---|---|---|
| SQL | `' OR '1'='1` | Treated as a literal, no extra rows |
| NoSQL | `{"$ne": null}` in a string field | Rejected with 400 |
| Shell | `; id` or `$(id)` in a filename | Treated as a literal filename |
| Template | `{{7*7}}` | Rendered as text, not `49` |
| XSS | `<img src=x onerror=alert(1)>` | Escaped in output |
| Path | `../../etc/passwd` | Rejected |
| URL scheme | `javascript:alert(1)` | Rejected or neutralized |
| CSV | `=HYPERLINK("http://example.com")` | Exported with a leading quote |
