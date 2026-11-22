#!/usr/bin/env python3
"""Map a code change to the bug-hunter security level and references.

Reads a unified diff (``git diff`` output), finds the security-sensitive
surfaces that the added and removed lines touch, and prints:

* the level from SKILL.md (0 = skip, 1 = secure defaults, 2 = full workflow)
* the matching lines, grouped by category
* the reference files worth reading next

This is a regex triage. It points at code worth reviewing. It cannot prove
that code is safe or vulnerable, and it will miss things a human would see.

Usage (run from the project root):
    python path/to/scripts/triage_diff.py --git            # working tree vs HEAD, plus untracked files
    git diff main...HEAD | python path/to/scripts/triage_diff.py -
    python path/to/scripts/triage_diff.py changes.diff --format json
    python path/to/scripts/triage_diff.py --git --fail-level 2   # exit 1 in CI when level 2

Standard library only. Python 3.9 or newer.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional, Pattern, Sequence, Tuple

__version__ = "0.1.0"

# ---------------------------------------------------------------------------
# Diff parsing
# ---------------------------------------------------------------------------


@dataclass
class DiffLine:
    number: int  # line number in the new file (added) or the old file (removed)
    text: str


@dataclass
class FileChange:
    path: str
    old_path: Optional[str] = None
    status: str = "modified"  # added | deleted | modified | renamed | binary
    added: List[DiffLine] = field(default_factory=list)
    removed: List[DiffLine] = field(default_factory=list)
    has_plus_header: bool = False


HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
GIT_HEADER_RE = re.compile(r'^diff --git "?a/(.+?)"? "?b/(.+?)"?$')


def _clean_path(raw: str) -> Optional[str]:
    path = raw.split("\t", 1)[0].strip()
    if len(path) >= 2 and path.startswith('"') and path.endswith('"'):
        path = path[1:-1]
    if path == "/dev/null":
        return None
    if path.startswith(("a/", "b/")):
        path = path[2:]
    return path


def parse_unified_diff(text: str) -> List[FileChange]:
    """Parse git or plain unified diff text into file changes.

    Hunk line counts are tracked, so an added line such as ``++i`` (shown as
    ``+++i`` in the diff) is never mistaken for a file header.
    """
    files: List[FileChange] = []
    current: Optional[FileChange] = None
    old_no = new_no = 0
    old_left = new_left = 0
    old_header: Optional[str] = None
    old_header_seen = False

    for raw in text.splitlines():
        if current is not None and (old_left > 0 or new_left > 0):
            if raw.startswith("\\"):  # "\ No newline at end of file"
                continue
            tag, body = raw[:1], raw[1:]
            if tag == "+":
                current.added.append(DiffLine(new_no, body))
                new_no += 1
                new_left -= 1
                continue
            if tag == "-":
                current.removed.append(DiffLine(old_no, body))
                old_no += 1
                old_left -= 1
                continue
            if tag == " " or raw == "":
                old_no += 1
                new_no += 1
                old_left -= 1
                new_left -= 1
                continue
            old_left = new_left = 0  # malformed hunk, fall back to header parsing

        if raw.startswith("diff --git "):
            match = GIT_HEADER_RE.match(raw)
            if match:
                current = FileChange(path=match.group(2), old_path=match.group(1))
            else:
                current = FileChange(path=raw[len("diff --git "):].strip())
            files.append(current)
            old_header_seen = False
            continue
        if raw.startswith("--- "):
            old_header = _clean_path(raw[4:])
            old_header_seen = True
            continue
        if raw.startswith("+++ ") and old_header_seen:
            new_path = _clean_path(raw[4:])
            if current is None or current.has_plus_header:
                current = FileChange(path=new_path or old_header or "")
                files.append(current)
            current.has_plus_header = True
            current.old_path = old_header
            if new_path is None:
                current.status = "deleted"
                current.path = old_header or current.path
            else:
                current.path = new_path
                if old_header is None:
                    current.status = "added"
            old_header_seen = False
            continue
        if current is None:
            continue
        match = HUNK_RE.match(raw)
        if match:
            old_no = int(match.group(1))
            old_left = int(match.group(2)) if match.group(2) is not None else 1
            new_no = int(match.group(3))
            new_left = int(match.group(4)) if match.group(4) is not None else 1
            continue
        if raw.startswith("new file mode"):
            current.status = "added"
        elif raw.startswith("deleted file mode"):
            current.status = "deleted"
        elif raw.startswith("rename from "):
            current.old_path = raw[len("rename from "):].strip()
        elif raw.startswith("rename to "):
            current.status = "renamed"
            current.path = raw[len("rename to "):].strip()
        elif raw.startswith(("Binary files ", "GIT binary patch")):
            current.status = "binary"
    return files


def _run_git(args: Sequence[str], cwd: Optional[str]) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, check=True
    )
    return completed.stdout.decode("utf-8", errors="replace")


def collect_git_changes(base: str = "HEAD", cwd: Optional[str] = None) -> List[FileChange]:
    """Working tree changes against ``base`` plus untracked files.

    ``git diff`` alone misses new files that were never added, which is
    exactly what coding agents create, so untracked files are read too.
    """
    try:
        diff_text = _run_git(["diff", base, "--no-color", "--no-ext-diff"], cwd)
    except subprocess.CalledProcessError:
        # Repository without commits: compare the index and the working tree instead.
        diff_text = _run_git(["diff", "--cached", "--no-color", "--no-ext-diff"], cwd)
        diff_text += _run_git(["diff", "--no-color", "--no-ext-diff"], cwd)
    files = parse_unified_diff(diff_text)

    root = Path(cwd) if cwd else Path.cwd()
    listing = _run_git(["ls-files", "--others", "--exclude-standard", "-z"], cwd)
    for rel in filter(None, listing.split("\0")):
        target = root / rel
        try:
            if target.stat().st_size > 1_000_000:
                continue
            data = target.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:8192]:
            files.append(FileChange(path=rel, status="binary"))
            continue
        lines = data.decode("utf-8", errors="replace").splitlines()
        files.append(
            FileChange(
                path=rel,
                status="added",
                added=[DiffLine(i + 1, text) for i, text in enumerate(lines)],
            )
        )
    return files


# ---------------------------------------------------------------------------
# File classification
# ---------------------------------------------------------------------------

DOC_EXTS = {".md", ".mdx", ".markdown", ".txt", ".rst", ".adoc"}
STYLE_EXTS = {".css", ".scss", ".sass", ".less", ".styl", ".pcss"}
ASSET_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".ico", ".svg", ".bmp",
    ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp3", ".mp4", ".webm", ".pdf",
}
MANIFESTS = {
    "package.json", "package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml",
    "yarn.lock", "bun.lock", "bun.lockb", "composer.json", "composer.lock",
    "pyproject.toml", "poetry.lock", "uv.lock", "Pipfile", "Pipfile.lock",
    "setup.py", "setup.cfg", "go.mod", "go.sum", "Cargo.toml", "Cargo.lock",
    "Gemfile", "Gemfile.lock",
}
TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs", "testing", "e2e", "cypress", "playwright"}
TEST_NAME_RE = re.compile(
    r"(^test_.*\.py$|_test\.(py|go)$|\.(test|spec)\.[cm]?[jt]sx?$|Test\.php$|_spec\.rb$|^conftest\.py$)"
)
ENV_FILE_RE = re.compile(r"^\.env(\.[\w-]+)?$")
ENV_TEMPLATE_RE = re.compile(r"\.(example|sample|template|dist|defaults?)$", re.IGNORECASE)
JS_EXTS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte", ".astro"}


def classify(path: str) -> str:
    """Return one of: manifest, ci, test, docs, style, asset, code."""
    pure = PurePosixPath(path)
    name = pure.name
    lower = name.lower()
    suffix = pure.suffix.lower()
    parents = {part.lower() for part in pure.parts[:-1]}
    if name in MANIFESTS or (lower.startswith("requirements") and suffix in {".txt", ".in"}):
        return "manifest"
    if (
        path.startswith(".github/workflows/")
        or path.startswith(".circleci/")
        or name in {".gitlab-ci.yml", "Jenkinsfile", "bitbucket-pipelines.yml", "azure-pipelines.yml"}
    ):
        return "ci"
    if TEST_NAME_RE.search(name) or parents & TEST_DIRS:
        return "test"
    if suffix in DOC_EXTS or lower in {"license", "licence", "changelog", "authors", "notice"}:
        return "docs"
    if suffix in STYLE_EXTS:
        return "style"
    if suffix in ASSET_EXTS:
        return "asset"
    return "code"


def is_env_file(path: str) -> bool:
    name = PurePosixPath(path).name
    return bool(ENV_FILE_RE.match(name)) and not ENV_TEMPLATE_RE.search(name)


# ---------------------------------------------------------------------------
# Categories and rules
# ---------------------------------------------------------------------------

# id -> (level, description, references)
CATEGORIES: Dict[str, Tuple[int, str, Tuple[str, ...]]] = {
    "entry-point": (2, "new or changed route, handler, or server action", ("threat-model.md", "access-control.md")),
    "object-access": (2, "object lookup by identifier", ("access-control.md",)),
    "authz": (2, "roles, ownership, tenants, policies, middleware", ("access-control.md",)),
    "auth-session": (2, "login, passwords, sessions, cookies, tokens, OAuth", ("access-control.md", "secrets-and-crypto.md")),
    "mass-assignment": (2, "bulk assignment from request data", ("access-control.md",)),
    "sql": (2, "raw or concatenated SQL", ("injection.md",)),
    "nosql": (2, "NoSQL query built from request data", ("injection.md",)),
    "command-exec": (2, "shell or process execution", ("injection.md",)),
    "xss-sink": (2, "raw HTML rendering", ("injection.md",)),
    "dynamic-code": (2, "templates or code built at runtime", ("injection.md",)),
    "deserialization": (2, "unsafe deserialization or XML parsing", ("injection.md",)),
    "files": (2, "uploads, downloads, file system paths, archives", ("files.md",)),
    "ssrf": (2, "server fetches a URL that may come from a user", ("outbound-and-webhooks.md",)),
    "outbound-http": (1, "outbound HTTP call (timeouts, errors)", ("outbound-and-webhooks.md",)),
    "redirect": (2, "redirect to a destination from the request", ("outbound-and-webhooks.md",)),
    "webhook": (2, "webhooks and signatures", ("outbound-and-webhooks.md",)),
    "money": (2, "prices, credits, coupons, payments, quotas", ("business-logic.md",)),
    "secret": (2, "secret or credential in the change", ("secrets-and-crypto.md",)),
    "public-env-secret": (2, "secret-looking variable with a client-side prefix", ("secrets-and-crypto.md",)),
    "env-file": (2, "environment file committed", ("secrets-and-crypto.md",)),
    "weak-crypto": (2, "weak hashing, disabled TLS checks, unverified JWT", ("secrets-and-crypto.md",)),
    "weak-random": (1, "non-cryptographic randomness", ("secrets-and-crypto.md",)),
    "config": (2, "CORS, CSRF, debug mode, cookies, headers, admin tools", ("config-and-errors.md",)),
    "llm": (2, "LLM, agent, embeddings, or MCP feature", ("ai-features.md",)),
    "dependencies": (2, "dependency manifest or lockfile changed", ("dependencies.md",)),
    "ci-risk": (2, "risky CI pattern", ("dependencies.md",)),
    "ci": (1, "CI pipeline changed", ("dependencies.md",)),
    "removed-control": (2, "a security control was removed", ("access-control.md", "self-attack.md")),
}

REFERENCE_ORDER = [
    "threat-model.md", "access-control.md", "injection.md", "outbound-and-webhooks.md",
    "files.md", "business-logic.md", "secrets-and-crypto.md", "config-and-errors.md",
    "dependencies.md", "ai-features.md", "self-attack.md", "report-format.md",
]


@dataclass(frozen=True)
class Rule:
    category: str
    pattern: Pattern[str]
    side: str = "added"  # added | removed
    kinds: Tuple[str, ...] = ("code",)
    exts: Optional[Tuple[str, ...]] = None  # limit to these file suffixes
    exclude: Optional[Pattern[str]] = None  # skip files whose path matches


def _rx(pattern: str, ignore_case: bool = False) -> Pattern[str]:
    return re.compile(pattern, re.IGNORECASE if ignore_case else 0)


# Browser code cannot cause SSRF, so URL fetching there is not flagged as such.
CLIENT_SIDE_PATH = re.compile(r"(^|/)(components|hooks|composables|client|frontend)/|\.(jsx|vue|svelte)$")

URLISH = r"(url|uri|href|link|endpoint|webhook|callback|target|src|source|image|img|avatar|feed|remote|website|domain|host)"

RULES: List[Rule] = [
    Rule("entry-point", _rx(
        r"Route::(get|post|put|patch|delete|any|match|resource|apiResource|resources|apiResources)\b"
        r"|\b(router|app|server|api|fastify|routes)\.(get|post|put|patch|delete|all|route)\s*\("
        r"|@(app|router|bp|blueprint|api)\.(get|post|put|patch|delete|route|api_route)\s*\("
        r"|\b(re_)?path\s*\(\s*r?['\"]"
        r"|export\s+(async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE)\b"
        r"|['\"]use server['\"]"
        r"|\bon(Call|Request)\s*\("
        r"|#\[Route\("
    )),
    Rule("object-access", _rx(
        r"\b(findOrFail|firstOrFail|findById|findByPk|findUnique|findUniqueOrThrow|findFirst|get_object_or_404)\s*\("
        r"|::find\s*\(|\.objects\.(get|filter)\s*\(|\bsession\.get\s*\(\s*\w+\s*,|\.findOne\s*\(\s*\{\s*_?id\b"
    )),
    Rule("authz", _rx(
        r"\bauthorize\s*\(|Gate::|->can(not)?\s*\(|@can\b|\bpolicies\b|\b\w+Policy\b|permission_classes"
        r"|has_(object_)?permission|login_required|permission_required|\bis_?[Aa]dmin\b|\bis_(staff|superuser)\b"
        r"|\broles?\b(?!\s*=\s*[\"'{])|\b(tenant|owner|user)(_id|Id)\b|->middleware\s*\(|\bcan\s*\(\s*['\"]"
    )),
    Rule("auth-session", _rx(
        r"\b(login|logout|log_in|log_out|sign_?in|sign_?up|signin|signup|password|passwd|reset[_-]?token"
        r"|remember[_-]?token|otp|totp|2fa|mfa|two[_-]?factor|magic[_-]?link|cookies?|jwt|jsonwebtoken|bearer"
        r"|oauth2?|oidc|openid|sanctum|passport|fortify|csrf|xsrf|api[_-]?keys?)\b"
        r"|\b(req|request)\.session\b|\$request->session\(|Session::|session_start\s*\(|\bsession\s*\[|\bsession\(\)->"
        r"|\bSESSION_[A-Z_]+",
        ignore_case=True,
    )),
    Rule("mass-assignment", _rx(
        r"\$fillable|\$guarded|\$request->(all|input)\(\s*\)|request\(\)->all\(\)|::unguard\(|\bforce(Fill|Create)\s*\("
        r"|fields\s*=\s*['\"]__all__['\"]|\*\*request\.(data|json|form|POST|get_json\(\))"
        r"|Object\.assign\(\s*\w+\s*,\s*req\.body|\bdata\s*:\s*req\.body\b|\.(create|update|insert)\w*\(\s*req\.body\b"
        r"|\{\s*\.\.\.req\.body"
    )),
    Rule("sql", _rx(
        r"DB::(raw|statement|select|insert|update|delete|unprepared)\s*\("
        r"|\b(where|orWhere|having|orderBy|select|groupBy|from|join)Raw\s*\("
        r"|\$(query|execute)Raw(Unsafe)?\b|\bsequelize\.(query|literal)\s*\(|\bknex\.raw\s*\(|\.raw\s*\(|\.extra\s*\("
        r"|\bcursor\.execute\s*\(|\bmysqli_query\s*\(|\bpg_query\s*\("
        r"|\btext\s*\(\s*f['\"]|\bf['\"]\s*(SELECT|INSERT|UPDATE|DELETE|WITH)\b"
        r"|`\s*(SELECT|INSERT|UPDATE|DELETE)\b[^`]*\$\{"
        r"|(SELECT|INSERT INTO|UPDATE|DELETE FROM)\b[^\"'\n]*[\"']\s*(\+|\.|%)\s*\$?\w"
    )),
    Rule("nosql", _rx(
        r"\$where\b|\$regex\b|\$ne\b|\$expr\b|\bmapReduce\s*\(|\.find(One)?\s*\(\s*req\.(body|query|params)"
        r"|\bwhere\s*\(\s*req\.|sanitizeFilter"
    ), exts=(".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".py")),
    Rule("command-exec", _rx(
        r"(?<![.\w$])(exec|shell_exec|system|passthru|proc_open|popen|pcntl_exec)\s*\("
        r"|\bsubprocess\.(run|call|Popen|check_output|check_call)\s*\(|\bos\.(system|popen|exec\w*|spawn\w*)\s*\("
        r"|\bchild_process\b|\b(execSync|execFile|execFileSync|spawnSync)\s*\(|(?<![.\w])spawn\s*\("
        r"|\bProcess::(run|start|pipe|fromShellCommandline)\b|new\s+Process\s*\(|\bshell\s*=\s*True|\bshell\s*:\s*true"
    )),
    Rule("xss-sink", _rx(
        r"\{!!|dangerouslySetInnerHTML|\bv-html\b|\|\s*safe\b|\bmark_safe\s*\(|\b(inner|outer)HTML\s*\+?="
        r"|insertAdjacentHTML\s*\(|document\.write(ln)?\s*\(|\bsrcdoc\b|\{\{\{|\bnew\s+HtmlString\b|\bMarkup\s*\("
        r"|\{@html\b|bypassSecurityTrust\w*\s*\("
    )),
    Rule("dynamic-code", _rx(
        r"render_template_string\s*\(|Blade::render\s*\(|createTemplate\s*\(|Handlebars\.compile\s*\("
        r"|\bnew\s+Function\s*\(|(?<![.\w])eval\s*\(|\bvm\.(runIn\w+|Script)\b|set(Timeout|Interval)\s*\(\s*['\"`]"
        r"|\bcreate_function\s*\(|\bassert\s*\(\s*\$_"
    )),
    Rule("deserialization", _rx(
        r"\bunserialize\s*\(|\bpickle\.loads?\s*\(|\bcPickle\b|\bmarshal\.loads?\s*\(|\byaml\.(unsafe_)?load\s*\((?![^)]*SafeLoader)"
        r"|\bjsonpickle\.decode\s*\(|ObjectInputStream|\bnode-serialize\b|\betree\.(parse|fromstring)\s*\("
        r"|xml\.dom\.minidom|simplexml_load_(string|file)\s*\(|LIBXML_NOENT|\bnew\s+DOMDocument\b"
    )),
    Rule("files", _rx(
        r"\$request->(file|hasFile)\s*\(|\bUploadedFile\b|move_uploaded_file\s*\(|\$_FILES\b"
        r"|->store(As|Publicly|PubliclyAs)?\s*\(|Storage::|\bmulter\b|\bformidable\b|\bbusboy\b|request\.files\b"
        r"|\bUploadFile\b|\b(File|Image)Field\b|\bsend_(file|from_directory)\s*\(|\bFileResponse\s*\("
        r"|\bres\.(sendFile|download|attachment)\s*\(|\bfs(\.promises)?\.(readFile|createReadStream|writeFile|unlink|rm|rename|copyFile)\w*\s*\("
        r"|\bfile_(get|put)_contents\s*\(|\bfopen\s*\(|(?<![.\w])unlink\s*\(|\breadfile\s*\("
        r"|(?<![.\w])open\s*\(\s*(os\.path\.join|f['\"]|request|req|user|path|filename|file_?path)"
        r"|\bZipArchive\b|\bzipfile\b|\btarfile\b|\bextractall\s*\(|\bpath\.(join|resolve)\s*\([^)]*\breq\."
    )),
    Rule("ssrf", _rx(
        r"(\bfetch|\baxios(\.\w+)?|\bgot(\.\w+)?|\brequests\.\w+|\bhttpx\.\w+|\burlopen|Http::\w+|\bcurl_init"
        r"|\bfile_get_contents|\bhttps?\.(get|request)|\bky(\.\w+)?)\s*\(\s*(?=[^)'\"`\s])[^)]*\b" + URLISH + r"\w*",
        ignore_case=True,
    ), exclude=CLIENT_SIDE_PATH),
    Rule("outbound-http", _rx(
        r"\bHttp::(get|post|put|patch|delete|send|withOptions|timeout|withHeaders|acceptJson|asForm|withToken)\b"
        r"|\bGuzzleHttp\b|\bcurl_(init|exec)\s*\(|\brequests\.(get|post|put|patch|delete|head|request|Session)\b"
        r"|\bhttpx\.(get|post|put|patch|delete|request|Client|AsyncClient)\b|\burllib\.request\b|\burlopen\s*\("
        r"|\baiohttp\b|(?<![.\w])fetch\s*\(|\baxios(\.\w+)?\s*\(|\bgot(\.\w+)?\s*\(|\bhttps?\.(get|request)\s*\(|\bundici\b"
    )),
    Rule("redirect", _rx(
        r"(\bredirect(_to|To)?|\bres\.redirect|Redirect::to|redirect\(\)->(to|away)|\bRedirectResponse)\s*\(\s*(?=[^)'\"`\s])[^)]*"
        r"\b(next|return\w*|redirect\w*|continue|callback|url|to|dest\w*|target|back_?url)\b|->away\s*\(",
        ignore_case=True,
    )),
    Rule("webhook", _rx(
        r"webhook|stripe[-_]?signature|x-hub-signature|x-signature|\bsvix\b|constructEvent\s*\(|verify_?signature"
        r"|\bhmac\b|x-shopify-hmac|x-slack-signature|x-paystack-signature",
        ignore_case=True,
    )),
    Rule("money", _rx(
        r"\b(price|prices|amount|discount|coupons?|vouchers?|promo_?codes?|credits?|balance|quantity|qty|refunds?"
        r"|wallets?|quota|checkout|payments?|charges?|payouts?|subscriptions?|billing|stripe|paypal|paddle"
        r"|lemon_?squeezy|gift_?cards?|cart)\b",
        ignore_case=True,
    )),
    Rule("public-env-secret", _rx(
        r"\b(NEXT_PUBLIC|VITE|REACT_APP|EXPO_PUBLIC|PUBLIC)_[A-Z0-9_]*(SECRET|PRIVATE|SERVICE_ROLE|PASSWORD|ADMIN)[A-Z0-9_]*"
    ), kinds=("code", "ci")),
    Rule("weak-crypto", _rx(
        r"(?<![.\w])(md5|sha1)\s*\(|hashlib\.(md5|sha1)\b|createHash\s*\(\s*['\"](md5|sha1)['\"]|\bcreateCipher\s*\("
        r"|MODE_ECB|-ecb['\"]|\bverify\s*=\s*False|rejectUnauthorized\s*:\s*false|CURLOPT_SSL_VERIFY(PEER|HOST)\s*(,|=>)\s*(false|0)"
        r"|NODE_TLS_REJECT_UNAUTHORIZED|algorithms\s*[=:]\s*\[\s*['\"]none['\"]|['\"]alg['\"]\s*:\s*['\"]none['\"]"
        r"|verify_signature['\"]?\s*:\s*False|ignoreExpiration\s*:\s*true|\bjwt\.decode\s*\(\s*\w+\s*\)"
    )),
    Rule("weak-random", _rx(
        r"\bMath\.random\s*\(|(?<![.\w])(mt_)?rand\s*\(|\buniqid\s*\(|\brandom\.(random|randint|choice|choices|randrange)\s*\("
    )),
    Rule("config", _rx(
        r"APP_DEBUG\s*=\s*true|\bDEBUG\s*=\s*True|\bdebug\s*=\s*True|Access-Control-Allow-(Origin|Credentials)"
        r"|allow_origins\s*=\s*\[\s*['\"]\*['\"]|\borigin\s*:\s*(true|['\"]\*['\"])|\bcredentials\s*:\s*true"
        r"|allow_credentials\s*=\s*True|supports_credentials|CORS_(ALLOW_ALL_ORIGINS|ORIGIN_ALLOW_ALL)"
        r"|ALLOWED_HOSTS\s*=\s*\[\s*['\"]\*['\"]|validateCsrfTokens|VerifyCsrfToken|csrf_exempt|WTF_CSRF_ENABLED"
        r"|(SESSION|CSRF)_COOKIE_SECURE\s*=\s*False|\bhttpOnly\s*:\s*false|\bsecure\s*:\s*false|sameSite\s*:\s*['\"]none['\"]"
        r"|X-Frame-Options|Content-Security-Policy|\bhelmet\s*\(|trust\s*proxy|phpinfo\s*\(|view(Telescope|Horizon)"
        r"|Horizon::auth|\bremotePatterns\b|\bcors\s*\("
    ), kinds=("code", "ci")),
    Rule("llm", _rx(
        r"\bopenai\b|\banthropic\b|@ai-sdk/|\b(generate|stream)(Text|Object)\s*\(|chat\.completions|messages\.create\s*\("
        r"|responses\.create\s*\(|\blangchain\b|\bllama_?index\b|\bollama\b|google[-.]genai|\bmistralai\b"
        r"|\btool_choice\b|\bfunction_call\b|\bsystem_?prompt\b|\bembeddings?\b|\bvector_?stores?\b|\bpinecone\b"
        r"|\bchromadb\b|\bqdrant\b|\bweaviate\b|\bpgvector\b|\bMcpServer\b|modelcontextprotocol",
        ignore_case=True,
    )),
    Rule("ci-risk", _rx(
        r"pull_request_target|workflow_run|permissions\s*:\s*write-all|curl[^|\n]*\|\s*(sudo\s+)?(ba)?sh\b"
    ), kinds=("ci",)),
    Rule("removed-control", _rx(
        r"\bauthorize\s*\(|Gate::|->can\s*\(|->middleware\s*\(|login_required|permission_classes|has_object_permission"
        r"|Depends\s*\(\s*get_current\w*|\brequireAuth\b|\bensureAuthenticated\b|\bisAuthenticated\b|\bthrottle\b"
        r"|\brateLimit\b|RateLimiter|csrf|hash_equals|timingSafeEqual|compare_digest|constructEvent|verify\w*Signature"
        r"|['\"](user_id|owner_id|tenant_id)['\"]|\b(user|owner|tenant)(_id|Id)\s*[:=]|\bescape\w*\s*\(|sanitiz\w*"
        r"|DOMPurify|htmlspecialchars|\bPolicy\b|\$fillable|read_only_fields|sanitizeFilter|withoutRedirecting"
    ), side="removed", kinds=("code",)),
]

# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------

VENDOR_SECRETS: List[Tuple[str, Pattern[str]]] = [
    ("AWS access key ID", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("private key block", re.compile(r"-----BEGIN (RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY-----")),
    ("Stripe secret key", re.compile(r"\b(sk|rk)_(live|test)_[0-9a-zA-Z]{10,}")),
    ("Stripe webhook secret", re.compile(r"\bwhsec_[0-9a-zA-Z]{10,}")),
    ("GitHub token", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}")),
    ("Anthropic API key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("OpenAI-style API key", re.compile(r"\bsk-(proj-|svcacct-)?[A-Za-z0-9_\-]{20,}")),
    ("SendGrid API key", re.compile(r"\bSG\.[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,}")),
    ("Supabase secret key", re.compile(r"\bsb_secret_[A-Za-z0-9_\-]{10,}")),
]
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")
ASSIGNED_SECRET_RE = re.compile(
    r"\b(api[_-]?key|secret([_-]?key)?|client[_-]?secret|password|passwd|auth[_-]?token|access[_-]?token"
    r"|refresh[_-]?token|private[_-]?key)\b[\"']?\s*(=>|:=|[:=])\s*[\"']([^\"'\s]{8,})[\"']",
    re.IGNORECASE,
)
PLACEHOLDER_HINTS = (
    "your", "example", "xxx", "changeme", "change_me", "placeholder", "dummy", "sample", "<", "${", "{{",
    "****", "redacted", "process.env", "env(", "getenv", "secret_here", "todo", "fake", "test",
)


def _jwt_role(token: str) -> Optional[str]:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8"))
    except (ValueError, IndexError, UnicodeDecodeError):
        return None
    role = data.get("role") if isinstance(data, dict) else None
    return role if isinstance(role, str) else None


def redact(text: str, secret: str) -> str:
    shown = secret[:4]
    return text.replace(secret, f"{shown}...[redacted {len(secret)} chars]")


def scan_secrets(line: str, kind: str) -> List[Tuple[str, str]]:
    """Return (label, matched secret) pairs found in one line."""
    hits: List[Tuple[str, str]] = []
    for label, pattern in VENDOR_SECRETS:
        for match in pattern.finditer(line):
            hits.append((label, match.group(0)))
    for match in JWT_RE.finditer(line):
        role = _jwt_role(match.group(0))
        if role == "anon":
            continue  # Supabase anon key: public by design, protected by RLS
        label = "Supabase service_role key (bypasses RLS)" if role == "service_role" else "JWT"
        hits.append((label, match.group(0)))
    if kind in ("code", "ci"):
        for match in ASSIGNED_SECRET_RE.finditer(line):
            value = match.group(4)
            if any(hint in value.lower() for hint in PLACEHOLDER_HINTS):
                continue
            if any(value in found for _, found in hits):
                continue
            hits.append((f"hardcoded {match.group(1).lower()}", value))
    return hits


# ---------------------------------------------------------------------------
# Triage
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    category: str
    path: str
    line: int
    side: str
    snippet: str
    detail: str = ""


def _snippet(text: str, limit: int = 140) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 3] + "..."


def detect_framework_refs(files: Sequence[FileChange], kinds: Dict[str, str]) -> List[str]:
    suffixes = {PurePosixPath(f.path).suffix.lower() for f in files if kinds[f.path] != "docs"}
    names = {PurePosixPath(f.path).name for f in files}
    sample = " ".join(f.path for f in files) + " " + " ".join(
        line.text for f in files if kinds[f.path] in ("code", "manifest") for line in f.added[:300]
    )
    refs: List[str] = []
    if ".php" in suffixes or "composer.json" in names:
        refs.append("frameworks/laravel.md")
    if suffixes & JS_EXTS or "package.json" in names:
        refs.append("frameworks/node.md")
    if ".py" in suffixes or names & {"pyproject.toml", "requirements.txt", "Pipfile"}:
        refs.append("frameworks/python.md")
    if re.search(r"supabase|firebase|firestore|row level security|create policy", sample, re.IGNORECASE) or any(
        name.endswith(".rules") for name in names
    ):
        refs.append("frameworks/supabase-firebase.md")
    return refs


def triage(files: Sequence[FileChange]) -> dict:
    kinds = {f.path: classify(f.path) for f in files}
    findings: List[Finding] = []
    seen = set()

    def add(category: str, change: FileChange, line: int, side: str, snippet: str, detail: str = "") -> None:
        key = (category, change.path, line, side)
        if key in seen:
            return
        seen.add(key)
        findings.append(Finding(category, change.path, line, side, _snippet(snippet), detail))

    for change in files:
        kind = kinds[change.path]
        suffix = PurePosixPath(change.path).suffix.lower()
        if change.status != "deleted":
            if kind == "manifest":
                first = change.added[0].number if change.added else 0
                add("dependencies", change, first, "added", change.path)
            if kind == "ci":
                first = change.added[0].number if change.added else 0
                add("ci", change, first, "added", change.path)
            if is_env_file(change.path):
                add("env-file", change, 0, "added", change.path, "commit .env.example with placeholders instead")
        for line in change.added:
            for label, secret in scan_secrets(line.text, kind):
                add("secret", change, line.number, "added", redact(line.text, secret), label)
            for rule in RULES:
                if rule.side != "added" or kind not in rule.kinds:
                    continue
                if rule.exts and suffix not in rule.exts:
                    continue
                if rule.exclude and rule.exclude.search(change.path):
                    continue
                if rule.pattern.search(line.text):
                    add(rule.category, change, line.number, "added", line.text)
        if kind == "code":
            for line in change.removed:
                for rule in RULES:
                    if rule.side == "removed" and rule.pattern.search(line.text):
                        add(rule.category, change, line.number, "removed", line.text)

    code_like = [p for p, k in kinds.items() if k in ("code", "ci", "manifest")]
    if findings:
        level = max(CATEGORIES[f.category][0] for f in findings)
    else:
        level = 1 if code_like else 0

    by_category: Dict[str, List[Finding]] = {}
    for finding in findings:
        by_category.setdefault(finding.category, []).append(finding)

    refs = set()
    for category in by_category:
        refs.update(CATEGORIES[category][2])
    if level == 2:
        refs.update({"threat-model.md", "self-attack.md", "report-format.md"})
    ordered = [r for r in REFERENCE_ORDER if r in refs]
    if level >= 1:
        ordered += detect_framework_refs(files, kinds)

    notes: List[str] = []
    if not files:
        notes.append("Empty diff. Nothing to triage.")
    elif level == 0:
        notes.append("Only documentation, styles, assets, or tests changed. Level 0: no security pass needed.")
    elif not findings:
        notes.append("Code changed but no sensitive surface matched. Level 1: apply the secure defaults, no report.")
    if any(f.side == "removed" for f in findings):
        notes.append("Removed lines contained security controls. Confirm each removal is intended and still covered.")
    notes.append("Regex triage, not analysis. It points at code to review and proves nothing.")

    category_order = sorted(by_category, key=lambda c: (-CATEGORIES[c][0], c))
    return {
        "tool": "bug-hunter/triage_diff",
        "version": __version__,
        "level": level,
        "files": [
            {
                "path": f.path,
                "status": f.status,
                "kind": kinds[f.path],
                "added": len(f.added),
                "removed": len(f.removed),
            }
            for f in files
        ],
        "categories": [
            {
                "id": c,
                "level": CATEGORIES[c][0],
                "description": CATEGORIES[c][1],
                "hits": len(by_category[c]),
                "references": [f"references/{r}" for r in CATEGORIES[c][2]],
            }
            for c in category_order
        ],
        "findings": [
            {
                "category": f.category,
                "path": f.path,
                "line": f.line,
                "side": f.side,
                "snippet": f.snippet,
                **({"detail": f.detail} if f.detail else {}),
            }
            for c in category_order
            for f in by_category[c]
        ],
        "references": [f"references/{r}" for r in ordered],
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def render_text(result: dict, max_lines: int = 5) -> str:
    out: List[str] = [f"bug-hunter triage: level {result['level']}", ""]
    if result["categories"]:
        out.append("Sensitive surfaces:")
        width = max(len(c["id"]) for c in result["categories"])
        for category in result["categories"]:
            hits = category["hits"]
            out.append(
                f"  {category['id'].ljust(width)}  {hits} hit{'s' if hits != 1 else ''}"
                f"  ({category['description']})"
            )
            shown = [f for f in result["findings"] if f["category"] == category["id"]][:max_lines]
            for finding in shown:
                where = f"{finding['path']}:{finding['line']}" if finding["line"] else finding["path"]
                prefix = "removed " if finding["side"] == "removed" else ""
                detail = f" [{finding['detail']}]" if finding.get("detail") else ""
                out.append(f"      {prefix}{where}  {finding['snippet']}{detail}")
            if hits > len(shown):
                out.append(f"      ... {hits - len(shown)} more")
        out.append("")
    if result["references"]:
        out.append("Read next:")
        out.extend(f"  {ref}" for ref in result["references"])
        out.append("")
    counts: Dict[str, int] = {}
    for entry in result["files"]:
        counts[entry["kind"]] = counts.get(entry["kind"], 0) + 1
    summary = ", ".join(f"{n} {kind}" for kind, n in sorted(counts.items()))
    out.append(f"Files: {len(result['files'])} ({summary})" if summary else "Files: 0")
    out.extend(f"Note: {note}" for note in result["notes"])
    return "\n".join(out)


def render_json(result: dict) -> str:
    return json.dumps(result, indent=2, ensure_ascii=False)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Triage a code change for the bug-hunter skill: security level, hot spots, references.",
    )
    parser.add_argument("diff", nargs="?", default="-", help="unified diff file, or - for stdin (default)")
    parser.add_argument("--git", nargs="?", const="HEAD", metavar="BASE",
                        help="read changes from git: working tree vs BASE (default HEAD) plus untracked files")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--max-lines", type=int, default=5, help="lines shown per category in text output")
    parser.add_argument("--fail-level", type=int, choices=(1, 2),
                        help="exit with status 1 when the level is at least this value (for CI)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    try:
        if args.git is not None:
            files = collect_git_changes(args.git)
        elif args.diff == "-":
            if sys.stdin.isatty():
                parser.print_help(sys.stderr)
                return 2
            data = sys.stdin.buffer.read() if hasattr(sys.stdin, "buffer") else sys.stdin.read().encode("utf-8")
            files = parse_unified_diff(data.decode("utf-8", errors="replace"))
        else:
            files = parse_unified_diff(Path(args.diff).read_text(encoding="utf-8", errors="replace"))
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"triage_diff: {exc}", file=sys.stderr)
        return 2

    result = triage(files)
    output = render_json(result) if args.format == "json" else render_text(result, args.max_lines)
    try:
        sys.stdout.reconfigure(errors="replace")  # type: ignore[attr-defined]
    except AttributeError:
        pass
    print(output)
    if args.fail_level is not None and result["level"] >= args.fail_level:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
