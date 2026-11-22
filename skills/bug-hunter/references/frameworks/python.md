# Python notes: Django, DRF, FastAPI, Flask

## Django

- Scope lookups: `get_object_or_404(Invoice, pk=pk, owner=request.user)`, and in class-based views override `get_queryset()` to filter by the user.
- The ORM binds values. `.raw(sql, params)` and `cursor.execute(sql, params)` are safe only with the params argument. Avoid `.extra()`.
- Templates escape by default. `|safe` and `mark_safe()` need sanitized input. Build HTML fragments with `format_html()`.
- `@csrf_exempt` only on webhook views that verify a signature.
- Production: `DEBUG = False`, explicit `ALLOWED_HOSTS`, `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`. Run `python manage.py check --deploy`.
- Password reset: Django's views respond the same way whether or not the email exists. Keep that behavior in custom flows.

## Django REST Framework

- Set a safe default: `DEFAULT_PERMISSION_CLASSES = ['rest_framework.permissions.IsAuthenticated']`.
- `has_object_permission` only runs when the view calls `get_object()`. List views and custom queries skip it, so filter `get_queryset()` by the user as well.
- `ModelViewSet` with `queryset = Invoice.objects.all()` and no filtered `get_queryset()` is an IDOR.
- Serializers: list `fields` explicitly and set `read_only_fields` for `owner`, `role`, `status`, `price`. `fields = '__all__'` exposes and accepts everything.
- Throttling: `DEFAULT_THROTTLE_CLASSES` and `ScopedRateThrottle` for login, OTP, and costly endpoints.

## FastAPI

- Auth as a dependency (`user = Depends(get_current_user)`), then scope every query by `user.id`.
- Input models reject unknown keys: `model_config = ConfigDict(extra='forbid')`. Output models (`response_model=InvoiceOut`) stop fields like `password_hash` from leaking.
- Uploads: `UploadFile` has no size limit by default. Enforce a limit at the proxy (`client_max_body_size`) and while reading in chunks.
- Webhooks: verify over `await request.body()` before parsing JSON.
- CORS: `CORSMiddleware(allow_origins=['https://app.example.com'], allow_credentials=True)` with exact origins.

## Flask

- Never run with `debug=True` on a reachable host. The Werkzeug debugger is an interactive Python console.
- `render_template_string(user_input)` is template injection. Render templates from files and pass values as variables.
- The default session cookie is signed, not encrypted. Users can read it, so keep secrets out of `session`.
- Files: `send_from_directory(directory, name)` contains paths; `werkzeug.utils.secure_filename` cleans upload names.
- `SECRET_KEY` from the environment, long and random.

## SQLAlchemy

```python
session.execute(text("SELECT * FROM invoices WHERE id = :id AND owner_id = :owner"), {"id": invoice_id, "owner": user.id})
```

Never f-strings or `%` formatting in `text()`.

## HTTP clients

- `requests` has no default timeout. Always pass `timeout=(3, 10)`. `httpx` defaults to 5 seconds.
- `requests` follows redirects (`allow_redirects=False` to stop it). `httpx` does not follow them unless `follow_redirects=True`.
- Never `verify=False`.

## SSRF address check

```python
import ipaddress, socket

def is_public_address(addr: str) -> bool:
    ip = ipaddress.ip_address(addr)
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast and not ip.is_reserved

def resolve_public(host: str, port: int) -> list[str]:
    addrs = {info[4][0] for info in socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)}
    if not addrs or not all(is_public_address(a) for a in addrs):
        raise ValueError("destination not allowed")
    return sorted(addrs)
```

Connect to an address you checked (or route through an egress proxy). Checking first and letting the client resolve again allows DNS rebinding.

## Other sinks

- `subprocess.run([...], shell=False)`. `shlex.quote` only when a shell is unavoidable.
- `yaml.safe_load`, never `yaml.load` with the full loader. Never `pickle` or `marshal` on untrusted data.
- XML through `defusedxml`.
- Tokens from `secrets`, comparisons with `hmac.compare_digest`.

## Tests (pytest)

```python
def test_user_cannot_read_other_users_invoice(client, user_a, user_b, invoice_of_a):
    client.force_login(user_b)
    response = client.get(f"/invoices/{invoice_of_a.id}/download")
    assert response.status_code == 404

def test_avatar_url_cannot_reach_metadata(api_client, user):
    api_client.force_authenticate(user)
    response = api_client.post("/me/avatar-from-url", {"url": "http://169.254.169.254/latest/meta-data/"})
    assert response.status_code == 400
```
