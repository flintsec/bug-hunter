"""Tests for triage_diff.py. Run: python -m unittest discover -s scripts -v"""

from __future__ import annotations

import base64
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import triage_diff as td  # noqa: E402


def run(diff: str) -> dict:
    return td.triage(td.parse_unified_diff(diff))


def categories(result: dict) -> set:
    return {c["id"] for c in result["categories"]}


def fake_jwt(payload: dict) -> str:
    def enc(data: dict) -> str:
        raw = json.dumps(data).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return f"{enc({'alg': 'HS256', 'typ': 'JWT'})}.{enc(payload)}.c2lnbmF0dXJlLXBsYWNlaG9sZGVy"


LARAVEL_DOWNLOAD = """\
diff --git a/routes/web.php b/routes/web.php
index 1111111..2222222 100644
--- a/routes/web.php
+++ b/routes/web.php
@@ -10,3 +10,4 @@ Route::middleware('auth')->group(function () {
     Route::get('/dashboard', DashboardController::class);
+    Route::get('/invoices/{id}/download', [InvoiceController::class, 'download'])->name('invoices.download');
 });
diff --git a/app/Http/Controllers/InvoiceController.php b/app/Http/Controllers/InvoiceController.php
new file mode 100644
index 0000000..3333333
--- /dev/null
+++ b/app/Http/Controllers/InvoiceController.php
@@ -0,0 +1,14 @@
+<?php
+
+namespace App\\Http\\Controllers;
+
+use App\\Models\\Invoice;
+use Illuminate\\Support\\Facades\\Storage;
+
+class InvoiceController extends Controller
+{
+    public function download(int $id)
+    {
+        $invoice = Invoice::findOrFail($id);
+        return Storage::download($invoice->path);
+    }
"""


class ParserTests(unittest.TestCase):
    def test_line_numbers_follow_hunks(self):
        diff = """\
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -3,4 +3,5 @@ import os
 a = 1
-b = 2
+b = 3
+c = 4
 d = 5
 e = 6
"""
        [change] = td.parse_unified_diff(diff)
        self.assertEqual([(l.number, l.text) for l in change.added], [(4, "b = 3"), (5, "c = 4")])
        self.assertEqual([(l.number, l.text) for l in change.removed], [(4, "b = 2")])

    def test_triple_plus_inside_hunk_is_an_added_line(self):
        diff = """\
diff --git a/loop.js b/loop.js
--- a/loop.js
+++ b/loop.js
@@ -1,2 +1,3 @@
 let i = 0;
+++i;
 console.log(i);
"""
        [change] = td.parse_unified_diff(diff)
        self.assertEqual(change.path, "loop.js")
        self.assertEqual([l.text for l in change.added], ["++i;"])

    def test_new_and_deleted_files(self):
        diff = """\
diff --git a/new.txt b/new.txt
new file mode 100644
--- /dev/null
+++ b/new.txt
@@ -0,0 +1 @@
+hello
diff --git a/old.txt b/old.txt
deleted file mode 100644
--- a/old.txt
+++ /dev/null
@@ -1 +0,0 @@
-bye
"""
        new, old = td.parse_unified_diff(diff)
        self.assertEqual((new.path, new.status), ("new.txt", "added"))
        self.assertEqual((old.path, old.status), ("old.txt", "deleted"))
        self.assertEqual([l.text for l in old.removed], ["bye"])

    def test_plain_diff_u_without_git_header(self):
        diff = """\
--- views.py\t2026-11-01 10:00:00
+++ views.py\t2026-11-02 10:00:00
@@ -1 +1,2 @@
 import os
+os.system(cmd)
"""
        result = run(diff)
        self.assertIn("command-exec", categories(result))
        self.assertEqual(result["files"][0]["path"], "views.py")


class LevelTests(unittest.TestCase):
    def test_docs_and_styles_only_is_level_zero(self):
        diff = """\
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1,2 @@
 # App
+Never call exec() with user input.
diff --git a/public/app.css b/public/app.css
--- a/public/app.css
+++ b/public/app.css
@@ -1 +1 @@
-.btn { color: blue; }
+.btn { color: green; }
"""
        result = run(diff)
        self.assertEqual(result["level"], 0)
        self.assertEqual(result["findings"], [])

    def test_tests_only_is_level_zero(self):
        diff = """\
diff --git a/tests/test_search.py b/tests/test_search.py
--- a/tests/test_search.py
+++ b/tests/test_search.py
@@ -1 +1,2 @@
 import pytest
+PAYLOAD = "' OR '1'='1"
"""
        self.assertEqual(run(diff)["level"], 0)

    def test_style_change_in_component_is_level_one_without_findings(self):
        diff = """\
diff --git a/src/components/SaveButton.tsx b/src/components/SaveButton.tsx
--- a/src/components/SaveButton.tsx
+++ b/src/components/SaveButton.tsx
@@ -1,3 +1,3 @@
 export function SaveButton() {
-  return <button role="button" className="bg-blue-600">Save</button>;
+  return <button role="button" className="bg-emerald-600">Save</button>;
 }
"""
        result = run(diff)
        self.assertEqual(result["level"], 1)
        self.assertEqual(result["findings"], [])

    def test_laravel_invoice_download_is_level_two(self):
        result = run(LARAVEL_DOWNLOAD)
        self.assertEqual(result["level"], 2)
        self.assertTrue({"entry-point", "object-access", "files"} <= categories(result))
        refs = result["references"]
        for expected in (
            "references/threat-model.md",
            "references/access-control.md",
            "references/files.md",
            "references/self-attack.md",
            "references/report-format.md",
            "references/frameworks/laravel.md",
        ):
            self.assertIn(expected, refs)
        lookup = [f for f in result["findings"] if f["category"] == "object-access"]
        self.assertEqual(lookup[0]["line"], 12)
        self.assertEqual(lookup[0]["path"], "app/Http/Controllers/InvoiceController.php")


class RuleTests(unittest.TestCase):
    def test_removed_authorization_is_flagged(self):
        diff = """\
diff --git a/app/Http/Controllers/InvoiceController.php b/app/Http/Controllers/InvoiceController.php
--- a/app/Http/Controllers/InvoiceController.php
+++ b/app/Http/Controllers/InvoiceController.php
@@ -20,4 +20,3 @@ class InvoiceController extends Controller
     public function show(Invoice $invoice)
     {
-        Gate::authorize('view', $invoice);
         return view('invoices.show', compact('invoice'));
"""
        result = run(diff)
        self.assertEqual(result["level"], 2)
        [finding] = [f for f in result["findings"] if f["category"] == "removed-control"]
        self.assertEqual((finding["side"], finding["line"]), ("removed", 22))

    def test_express_webhook(self):
        diff = """\
diff --git a/server/routes/billing.js b/server/routes/billing.js
--- a/server/routes/billing.js
+++ b/server/routes/billing.js
@@ -1 +1,3 @@
 const router = express.Router();
+router.post('/webhooks/stripe', express.json(), async (req, res) => {
+  await markOrderPaid(req.body.data.object.metadata.orderId);
"""
        found = categories(run(diff))
        self.assertTrue({"entry-point", "webhook"} <= found)

    def test_python_ssrf_versus_fixed_url(self):
        diff = """\
diff --git a/app/avatars.py b/app/avatars.py
--- a/app/avatars.py
+++ b/app/avatars.py
@@ -1 +1,3 @@
 import requests
+resp = requests.get(payload.avatar_url, timeout=5)
+health = requests.get(f"{settings.API_BASE}/health", timeout=5)
"""
        result = run(diff)
        ssrf = [f for f in result["findings"] if f["category"] == "ssrf"]
        self.assertEqual([f["line"] for f in ssrf], [2])
        self.assertIn("outbound-http", categories(result))

    def test_browser_fetch_is_not_ssrf(self):
        diff = """\
diff --git a/src/components/Preview.jsx b/src/components/Preview.jsx
--- a/src/components/Preview.jsx
+++ b/src/components/Preview.jsx
@@ -1 +1,2 @@
 export default function Preview({ url }) {
+  useEffect(() => { fetch(url).then(setData); }, [url]);
"""
        self.assertNotIn("ssrf", categories(run(diff)))

    def test_dependency_manifest(self):
        diff = """\
diff --git a/package.json b/package.json
--- a/package.json
+++ b/package.json
@@ -5,3 +5,4 @@
   "dependencies": {
+    "left-pad-pro": "^1.0.0",
     "react": "^19.0.0"
"""
        result = run(diff)
        self.assertEqual(result["level"], 2)
        self.assertIn("dependencies", categories(result))

    def test_llm_feature(self):
        diff = """\
diff --git a/app/assistant.ts b/app/assistant.ts
--- a/app/assistant.ts
+++ b/app/assistant.ts
@@ -1 +1,2 @@
 import { z } from "zod";
+import Anthropic from "@anthropic-ai/sdk";
"""
        self.assertIn("llm", categories(run(diff)))

    def test_aria_role_is_not_authorization(self):
        diff = """\
diff --git a/src/pages/Settings.tsx b/src/pages/Settings.tsx
--- a/src/pages/Settings.tsx
+++ b/src/pages/Settings.tsx
@@ -1 +1,2 @@
 <section>
+<div role="dialog" aria-modal="true">
"""
        self.assertNotIn("authz", categories(run(diff)))

    def test_mass_assignment_and_sql(self):
        diff = """\
diff --git a/app/Http/Controllers/ProfileController.php b/app/Http/Controllers/ProfileController.php
--- a/app/Http/Controllers/ProfileController.php
+++ b/app/Http/Controllers/ProfileController.php
@@ -1 +1,3 @@
 <?php
+$user->update($request->all());
+$rows = DB::select("SELECT * FROM users WHERE name = '" . $name . "'");
"""
        found = categories(run(diff))
        self.assertTrue({"mass-assignment", "sql"} <= found)

    def test_sql_built_by_plain_concatenation(self):
        # The query fragment quotes the value, so the string ends with '" just
        # before the + operator. One of the most common injection shapes.
        diff = """\
diff --git a/db/search.py b/db/search.py
--- a/db/search.py
+++ b/db/search.py
@@ -0,0 +1,2 @@
+def search(name):
+    q = "SELECT * FROM users WHERE name = '" + name + "'"
"""
        self.assertIn("sql", categories(run(diff)))

    def test_plain_string_concatenation_is_not_sql(self):
        # A concatenated string with no SQL keyword must not trip the rule.
        diff = """\
diff --git a/ui/toast.js b/ui/toast.js
--- a/ui/toast.js
+++ b/ui/toast.js
@@ -0,0 +1 @@
+const greeting = "Hello " + name + ", welcome back!";
"""
        self.assertNotIn("sql", categories(run(diff)))

    def test_open_with_concatenated_path_is_flagged(self):
        # A file path built from a literal prefix plus user input: classic LFI.
        diff = """\
diff --git a/api/download.py b/api/download.py
--- a/api/download.py
+++ b/api/download.py
@@ -0,0 +1,2 @@
+def download(request):
+    return open("/data/" + request.args["name"]).read()
"""
        self.assertIn("files", categories(run(diff)))

    def test_open_of_static_file_is_not_flagged(self):
        # A constant path with no concatenation should not trip the files rule.
        diff = """\
diff --git a/app/config.py b/app/config.py
--- a/app/config.py
+++ b/app/config.py
@@ -0,0 +1 @@
+settings = open("config.json").read()
"""
        self.assertNotIn("files", categories(run(diff)))

    def test_php_variable_interpolated_into_sql(self):
        diff = """\
diff --git a/sqli.php b/sqli.php
--- a/sqli.php
+++ b/sqli.php
@@ -0,0 +1,2 @@
+$id = $_GET['id'];
+$query = "SELECT first_name, last_name FROM users WHERE user_id = '$id';";
"""
        self.assertIn("sql", categories(run(diff)))

    def test_ruby_interpolated_where_clause(self):
        diff = """\
diff --git a/app/models/user.rb b/app/models/user.rb
--- a/app/models/user.rb
+++ b/app/models/user.rb
@@ -0,0 +1 @@
+  User.where("name = '#{name}'")
"""
        self.assertIn("sql", categories(run(diff)))

    def test_numbered_placeholder_is_not_sql(self):
        # Postgres positional parameters are the safe, parameterised form.
        diff = """\
diff --git a/db.py b/db.py
--- a/db.py
+++ b/db.py
@@ -0,0 +1 @@
+cur.execute("SELECT * FROM users WHERE id = $1 AND org = $2", [uid, org])
"""
        self.assertNotIn("sql", categories(run(diff)))

    def test_ui_string_with_keyword_is_not_sql(self):
        # A user-facing message that merely contains an uppercase keyword.
        diff = """\
diff --git a/ui/banner.js b/ui/banner.js
--- a/ui/banner.js
+++ b/ui/banner.js
@@ -0,0 +1 @@
+const msg = `UPDATE available in ${version}, please refresh`;
"""
        self.assertNotIn("sql", categories(run(diff)))

    def test_safe_where_without_interpolation_is_not_sql(self):
        diff = """\
diff --git a/app/models/post.rb b/app/models/post.rb
--- a/app/models/post.rb
+++ b/app/models/post.rb
@@ -0,0 +1 @@
+  Post.where("status = 'active'").order(:created_at)
"""
        self.assertNotIn("sql", categories(run(diff)))


class SecretTests(unittest.TestCase):
    def test_vendor_secret_is_redacted(self):
        key = "sk_live_" + "51HxQz" + "A9b8C7d6E5f4G3h2"
        diff = f"""\
diff --git a/config/billing.php b/config/billing.php
--- a/config/billing.php
+++ b/config/billing.php
@@ -1 +1,2 @@
 <?php
+return ['stripe_key' => '{key}'];
"""
        result = run(diff)
        self.assertIn("secret", categories(result))
        rendered = td.render_text(result) + td.render_json(result)
        self.assertNotIn(key, rendered)
        self.assertIn("redacted", rendered)

    def test_supabase_anon_key_ignored_service_role_flagged(self):
        anon = fake_jwt({"iss": "supabase", "role": "anon"})
        service = fake_jwt({"iss": "supabase", "role": "service_role"})
        diff = f"""\
diff --git a/src/lib/supabase.ts b/src/lib/supabase.ts
--- a/src/lib/supabase.ts
+++ b/src/lib/supabase.ts
@@ -1 +1,3 @@
 import {{ createClient }} from "@supabase/supabase-js";
+const anon = "{anon}";
+const admin = "{service}";
"""
        result = run(diff)
        secrets = [f for f in result["findings"] if f["category"] == "secret"]
        self.assertEqual([f["line"] for f in secrets], [3])
        self.assertIn("service_role", secrets[0]["detail"])

    def test_placeholder_password_is_ignored(self):
        diff = """\
diff --git a/config/db.js b/config/db.js
--- a/config/db.js
+++ b/config/db.js
@@ -1 +1,2 @@
 module.exports = {
+  password: "your-password-here",
"""
        self.assertNotIn("secret", categories(run(diff)))

    def test_env_file_committed(self):
        diff = """\
diff --git a/.env b/.env
new file mode 100644
--- /dev/null
+++ b/.env
@@ -0,0 +1 @@
+APP_KEY=base64:abc
"""
        self.assertIn("env-file", categories(run(diff)))

    def test_env_example_is_fine(self):
        diff = """\
diff --git a/.env.example b/.env.example
--- a/.env.example
+++ b/.env.example
@@ -0,0 +1 @@
+APP_KEY=
"""
        self.assertNotIn("env-file", categories(run(diff)))


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.diff_path = os.path.join(self.tmp, "change.diff")
        Path(self.diff_path).write_text(LARAVEL_DOWNLOAD, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_json_output_parses(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = td.main([self.diff_path, "--format", "json"])
        self.assertEqual(code, 0)
        data = json.loads(buffer.getvalue())
        self.assertEqual(data["level"], 2)

    def test_fail_level(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(td.main([self.diff_path, "--fail-level", "2"]), 1)

    def test_stdin(self):
        script = str(Path(td.__file__).resolve())
        completed = subprocess.run(
            [sys.executable, script, "-"], input=LARAVEL_DOWNLOAD.encode("utf-8"), capture_output=True, check=False
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("level 2", completed.stdout.decode("utf-8"))

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_git_mode_includes_untracked_files(self):
        repo = os.path.join(self.tmp, "repo")
        os.makedirs(repo)
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
               "GIT_COMMITTER_EMAIL": "t@t"}
        def git(*args):
            subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, env=env)
        git("init", "-q")
        Path(repo, "README.md").write_text("# demo\n", encoding="utf-8")
        git("add", ".")
        git("commit", "-q", "-m", "init")
        Path(repo, "upload.py").write_text("f = request.files['doc']\n", encoding="utf-8")
        files = td.collect_git_changes("HEAD", cwd=repo)
        result = td.triage(files)
        self.assertIn("files", categories(result))
        self.assertEqual(result["files"][0]["status"], "added")


def _one_file_diff(path: str, code: str) -> str:
    lines = code.split("\n")
    return (f"diff --git a/{path} b/{path}\n--- /dev/null\n+++ b/{path}\n"
            f"@@ -0,0 +1,{len(lines)} @@\n") + "".join("+" + ln + "\n" for ln in lines)


class CrossLanguageTests(unittest.TestCase):
    """Go / Java / C# / Ruby idioms that older PHP/Node/Python-centric rules missed."""

    POSITIVE = [
        # SQL built by a format helper or C# interpolation.
        ("sql", "a.go",   r'db.Query(fmt.Sprintf("SELECT * FROM users WHERE id = %s", id))'),
        ("sql", "a.java", r'stmt.executeQuery(String.format("SELECT * FROM users WHERE id = %s", id));'),
        ("sql", "a.cs",   r'cmd.CommandText = $"SELECT * FROM Users WHERE Id = {id}";'),
        # real WebGoat shape: an inner 'literal' sits before the concatenation point.
        ("sql", "a.java", r'''query = "SELECT * FROM user_data WHERE last_name = '" + accountName + "'";'''),
        # command execution.
        ("command-exec", "a.go",   r'exec.Command("sh", "-c", userCmd).Run()'),
        ("command-exec", "a.java", r'Runtime.getRuntime().exec("ping " + host);'),
        ("command-exec", "a.java", r'new ProcessBuilder("sh", "-c", cmd).start();'),
        ("command-exec", "a.cs",   r'Process.Start("cmd.exe", "/c " + input);'),
        ("command-exec", "a.rb",   r'out = `ls #{dir}`'),
        ("command-exec", "a.rb",   r'%x(cat #{f})'),
        # outbound HTTP / SSRF surface.
        ("outbound-http", "a.go",   r'resp, _ := http.Get(userURL)'),
        ("outbound-http", "a.java", r'InputStream in = new URL(userUrl).openStream();'),
        ("outbound-http", "a.cs",   r'var resp = await httpClient.GetAsync(userUrl);'),
        ("outbound-http", "a.php",  r"curl_setopt($ch, CURLOPT_URL, $_GET['url']);"),
        # deserialization.
        ("deserialization", "a.java", r'Object o = new XMLDecoder(in).readObject();'),
        ("deserialization", "a.rb",   r'obj = Marshal.load(data)'),
        ("deserialization", "a.cs",   r'var o = new BinaryFormatter().Deserialize(stream);'),
        # weak crypto.
        ("weak-crypto", "a.java", r'MessageDigest md = MessageDigest.getInstance("MD5");'),
        ("weak-crypto", "a.java", r'Cipher c = Cipher.getInstance("AES/ECB/PKCS5Padding");'),
        # files / path traversal and open redirect in languages we had missed.
        ("files", "a.java",  r'File f = new File(baseDir, request.getParameter("name"));'),
        ("redirect", "a.php", 'header("Location: " . $_GET[\'url\']);'),
        ("xss-sink", "a.js",  r'$("#out").html(userInput);'),
        # hardcoded secret in a prefixed variable name.
        ("secret", "a.rb",    r'db_password = "pR0dPassw0rd9xQ"'),
    ]

    NEGATIVE = [  # (forbidden category, file, safe code)
        ("sql", "a.java", r'PreparedStatement ps = conn.prepareStatement("SELECT * FROM u WHERE id = ?");'),
        ("sql", "a.php",  r'$stmt = $pdo->prepare("SELECT * FROM u WHERE id = ?"); $stmt->execute([$id]);'),
        ("sql", "a.go",   r'db.Query("SELECT * FROM users WHERE id = $1", id)'),
        ("sql", "a.cs",   r'cmd.CommandText = "SELECT * FROM Users WHERE Id = @id";'),
        ("sql", "a.js",   r'const msg = `UPDATE available in ${version}, please refresh`;'),
        ("deserialization", "a.cs", r'var o = JsonSerializer.Deserialize<Dto>(s);'),
        ("secret", "a.py",          r'update_password_url = "https://acme.io/reset-flow-page"'),
    ]

    def test_positives(self):
        for want, path, code in self.POSITIVE:
            with self.subTest(want=want, code=code):
                self.assertIn(want, categories(run(_one_file_diff(path, code))))

    def test_negatives(self):
        for forbid, path, code in self.NEGATIVE:
            with self.subTest(forbid=forbid, code=code):
                self.assertNotIn(forbid, categories(run(_one_file_diff(path, code))))


if __name__ == "__main__":
    unittest.main()
