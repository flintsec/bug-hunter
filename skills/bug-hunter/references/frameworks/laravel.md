# Laravel notes

Covers Laravel 10 to 13 and the common add-ons (Sanctum, Livewire, Inertia, Filament, Cashier). Check the project's `composer.json` for the version before relying on version-specific APIs.

## Authorization

- Scope lookups through the user: `$request->user()->invoices()->findOrFail($id)`. A plain `Invoice::findOrFail($id)` or implicit route model binding `{invoice}` checks nothing about ownership.
- Add a policy as well and enforce it: `Gate::authorize('view', $invoice)` works in every version. Since Laravel 11 the base controller has no traits, so `$this->authorize()` only exists if the controller uses `AuthorizesRequests`.
- Route level: `->can('view', 'invoice')` on the route, or `->middleware('can:view,invoice')`.
- Nested resources: `Route::scopeBindings()` makes `/projects/{project}/tasks/{task}` resolve only tasks of that project. It does not check that the project belongs to the user.
- FormRequest `authorize()` is a good place for ownership checks on writes. Returning `true` there is a decision, not a default.
- Livewire: every public method is callable from the browser and public properties can be changed by the client. Authorize inside each action, and mark IDs that must not change with `#[Locked]`.
- Inertia: page props are embedded in the HTML. Pass API Resources or `->only([...])`, never whole models.
- Filament: implement `canAccessPanel()` on the user model and policies for each resource.

## Mass assignment

- Use `$fillable`. Avoid `$guarded = []` and `Model::unguard()`.
- Write with `$request->validated()` or `$request->safe()->only([...])`, never `$request->all()`.
- In development, `Model::shouldBeStrict()` in `AppServiceProvider` surfaces silently discarded attributes and lazy loading.
- `forceFill()` and `forceCreate()` skip the allowlist. Use them only with server-built data.

## Queries

- Eloquent and the query builder bind values. The raw methods only bind what you pass as the second argument: `whereRaw('total > ?', [$min])`.
- Never concatenate into `DB::raw`, `selectRaw`, `orderByRaw`, `havingRaw`, `DB::statement`, or `DB::select`.
- Map sort columns and directions through an allowlist. Do the same for JSON paths (`where('meta->'.$key, ...)`) and table names.

## Blade and output

- `{{ $value }}` escapes. `{!! $value !!}` does not, so it needs content sanitized with HTML Purifier (for example `mews/purifier`).
- Pass data to JavaScript with `Js::from($data)` or `@json($data)`, not string concatenation into `<script>`.
- Markdown: `Str::markdown($text, ['html_input' => 'strip', 'allow_unsafe_links' => false])`.

## Files

- Validate: `'invoice' => ['required', 'file', 'mimes:pdf', 'max:10240']` (`max` is in kilobytes; `mimes` checks the detected type, add `extensions:pdf` to check the name too).
- Store on a private disk: `$path = $request->file('invoice')->store('invoices');` uses the `local` disk, which is private. `public` and `storage:link` are for files anyone may download.
- Serve after authorization: `return Storage::download($invoice->path, "invoice-{$invoice->number}.pdf");`
- S3: `Storage::temporaryUrl($path, now()->addMinutes(5))` after the policy check.

## Authentication

- Starter kits (Breeze, Jetstream, Fortify) include login throttling. Keep it. Custom login: `RateLimiter::for('login', fn (Request $r) => Limit::perMinute(5)->by($r->input('email').'|'.$r->ip()));` plus `throttle:login`.
- `Password::defaults()` in a service provider for consistent password rules.
- Sanctum tokens: give abilities (`createToken('cli', ['invoices:read'])`) and check them with `$request->user()->tokenCan('invoices:read')`.
- Sanctum SPA auth depends on `SANCTUM_STATEFUL_DOMAINS` and session domain settings. Wrong values either break login or widen trust.

## CSRF and webhooks

- Laravel 11+: exclude webhook routes in `bootstrap/app.php` with `$middleware->validateCsrfTokens(except: ['webhooks/*'])`. Older versions: `$except` in `VerifyCsrfToken`.
- An excluded route must verify the provider signature over `$request->getContent()`. With the Stripe SDK: `\Stripe\Webhook::constructEvent($request->getContent(), $request->header('Stripe-Signature'), config('services.stripe.webhook_secret'))`.
- Laravel Cashier verifies Stripe signatures automatically when `STRIPE_WEBHOOK_SECRET` is set. Check that it is set in production.
- Deduplicate on the event ID with a unique index, inside the same transaction as the side effect.

## Outbound HTTP

```php
$response = Http::timeout(5)
    ->connectTimeout(3)
    ->withoutRedirecting()
    ->withOptions(['curl' => [CURLOPT_RESOLVE => ["{$host}:443:{$checkedIp}"]]])
    ->get($url);
```

- Check every resolved address before connecting. PHP 8.2+: `filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_GLOBAL_RANGE)` rejects private and reserved ranges. Older PHP: combine `FILTER_FLAG_NO_PRIV_RANGE | FILTER_FLAG_NO_RES_RANGE` and also block `100.64.0.0/10`.
- `CURLOPT_RESOLVE` pins the connection to the address you checked, which stops DNS rebinding.
- `gethostbynamel()` returns IPv4 only. Use `dns_get_record($host, DNS_A | DNS_AAAA)` to see both families.

## Configuration

- `APP_DEBUG=false` and `APP_ENV=production` in production. Ignition error pages leak environment details.
- Gate Telescope and Horizon (`viewTelescope`, `viewHorizon` gates) and keep Debugbar out of production.
- `APP_KEY` is a secret. Rotating it invalidates sessions and encrypted values, so plan it.
- Sensitive columns: the `encrypted` cast. Tokens: `Str::random(40)` (backed by `random_bytes`).

## Queues

- Jobs run later, possibly after permissions changed. Carry the acting user and tenant explicitly and re-check access in `handle()` when it matters.
- `SerializesModels` re-fetches models by ID. A deleted or moved record can change what the job touches.

## Tests (Pest)

```php
it('does not let a user download another user\'s invoice', function () {
    $owner = User::factory()->create();
    $other = User::factory()->create();
    $invoice = Invoice::factory()->for($owner)->create();

    $this->actingAs($other)
        ->get(route('invoices.download', $invoice))
        ->assertNotFound();
});

it('ignores role on profile update', function () {
    $user = User::factory()->create(['role' => 'member']);

    $this->actingAs($user)
        ->patchJson('/api/profile', ['name' => 'Sam', 'role' => 'admin'])
        ->assertOk();

    expect($user->fresh()->role)->toBe('member');
});
```
