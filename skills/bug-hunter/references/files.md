# Files: uploads, downloads, processing, storage

## Uploads

| Check | Why |
|---|---|
| Size limit at the app and at the proxy | Disk and memory exhaustion |
| Type by content (magic bytes) and an extension allowlist | Attackers rename `shell.php` to `cat.jpg` |
| Server-generated file name | User names carry `../`, control characters, and executable extensions |
| Private storage or outside the web root | A stored `.php` or `.html` file must never execute or render from your origin |
| Re-encode images | Strips polyglot payloads and EXIF location data |
| Pixel and frame limits before decoding | Image bombs: a small file that decodes to gigabytes |
| Archive limits | Zip slip (entries named `../../app/config`) and zip bombs (huge ratio). Validate each entry path, cap total size and file count. |
| Scan when the business needs it | Antivirus for files other users will download |

### Dangerous types

- **SVG** is XML that can contain scripts. Either reject it, sanitize it with an SVG-aware sanitizer, or serve it as an attachment from a separate domain.
- **HTML, XHTML, JS, and anything browsers may sniff as HTML.** Serve user files with `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff`, ideally from a separate cookieless domain.
- **Office documents and PDFs** are fine to store. Processing them server-side needs updated libraries and sandboxing.

## Downloads

- Authorize every download against the current user, the same way as any other object access.
- Look files up by database ID, then read the stored path. Never accept a path or file name from the request.
- For object storage, issue short-lived signed URLs after the authorization check.
- Sanitize the name in `Content-Disposition` (strip quotes, CR, LF) or let the framework build the header.

## Paths

When a path must be built, resolve it and confirm it stays inside the base directory:

```text
base = realpath(STORAGE_DIR)
full = realpath(join(base, name))
if not (full == base or full.startswith(base + os.sep)): reject
```

## Storage configuration

- Buckets private by default. Public read only for intentionally public assets.
- Per-tenant prefixes help organization. They do not replace authorization checks.
- No directory listing on any web server.

## Processing

- Run heavy processing (images, video, PDF, archives) in a queue with timeouts and memory limits.
- Keep processing libraries updated. ImageMagick, Ghostscript, and PDF libraries have a long history of remote code execution bugs.
- Prefer library calls over shell commands. See `injection.md` for shell rules.

## Tests to write

- Uploading `shell.php` renamed to `image.jpg` is rejected by content check.
- Uploading an SVG with `<script>` is rejected or served as an attachment.
- A file name like `../../evil.txt` does not escape the storage directory.
- User B requesting user A's file ID gets 404.
- An oversized file is rejected before the whole body is read.
