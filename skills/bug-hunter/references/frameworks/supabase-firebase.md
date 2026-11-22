# Supabase and Firebase notes

With a backend-as-a-service the browser talks to the database directly. The rules are the backend. A missing rule is not a missing feature, it is public read and write access.

## Supabase

### The model

- The anon key is public by design. It ships in the client and anyone can call the REST API (PostgREST) with it.
- Row Level Security (RLS) decides what each request can see and change. A table in an exposed schema (usually `public`) without RLS is readable and writable by anyone with the anon key.
- The service role key bypasses RLS. It belongs on the server only. A `NEXT_PUBLIC_` or `VITE_` variable holding it gives every visitor full database access.

### Policies

```sql
alter table invoices enable row level security;

create policy "owners read invoices" on invoices
  for select to authenticated
  using ((select auth.uid()) = user_id);

create policy "owners insert invoices" on invoices
  for insert to authenticated
  with check ((select auth.uid()) = user_id);
```

- `using` filters existing rows (select, update, delete). `with check` validates new values (insert, update). Updates usually need both.
- Wrapping `auth.uid()` in `(select ...)` lets Postgres evaluate it once per query, which Supabase recommends for performance.
- Never authorize with `user_metadata` (`raw_user_meta_data`). Users can edit it. Roles belong in `app_metadata` or in a table only the server writes.
- Views run with the owner's rights and skip RLS unless created `with (security_invoker = true)` (Postgres 15+).
- `security definer` functions also skip RLS. Set `search_path = ''`, check `auth.uid()` inside, and revoke execute from roles that should not call them.
- Column-level exposure: RLS works on rows. Hide sensitive columns with a view, a separate table, or column privileges.

### Storage

- Buckets marked public are readable by anyone with the URL.
- Private buckets need policies on `storage.objects`, for example limiting each user to their own folder: `(storage.foldername(name))[1] = (select auth.uid())::text`.

### Edge Functions

JWT verification is on by default. If you turn it off for a webhook, verify the provider signature instead. Use the service role key inside the function only after your own authorization check.

### Check it

- The dashboard's Security Advisor flags tables without RLS and risky functions.
- Test with the anon key from a script, logged in as user B, and try to select, update, and delete user A's rows. Expect empty results or errors.

## Firebase

### The model

- The web config (including `apiKey`) identifies the project. It is not a secret. Security Rules are the access control. Restrict the key in the console and enable App Check to slow down scripted abuse.
- The Admin SDK bypasses rules and runs only on servers.
- Test mode rules (`allow read, write: if true;` or a date-based expiry) must never reach production.

### Firestore rules

```text
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /invoices/{invoiceId} {
      allow read: if request.auth != null
                  && resource.data.ownerId == request.auth.uid;
      allow create: if request.auth != null
                    && request.resource.data.ownerId == request.auth.uid
                    && request.resource.data.keys().hasOnly(['ownerId', 'amount', 'createdAt']);
      allow update, delete: if false;
    }
  }
}
```

- Rules are not filters. A query must include the same constraint the rule checks (`where('ownerId', '==', uid)`), or it fails.
- Validate the shape of writes with `keys().hasOnly()` and type checks, or users can add fields like `role` or `paid`.
- Roles come from custom claims set with the Admin SDK (`request.auth.token.admin == true`), never from a field in a user-writable document.

### Storage rules

Check owner, size, and type: `request.auth.uid == userId && request.resource.size < 5 * 1024 * 1024 && request.resource.contentType.matches('image/.*')`.

### Cloud Functions

Callable functions must check `request.auth` and authorize the specific action. HTTP functions are public URLs and need their own authentication.

### Check it

Write rule tests with the Emulator Suite and `@firebase/rules-unit-testing`: an unauthenticated read fails, user B reading user A's document fails, a create with an extra `role` field fails.
