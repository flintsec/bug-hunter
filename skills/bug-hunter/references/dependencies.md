# Dependencies and supply chain

Software Supply Chain Failures is A03 in the OWASP Top 10:2025. Coding agents add a new risk on top of the classic ones: they sometimes invent package names that sound right. Attackers register those names and wait. This is often called slopsquatting.

## Before adding a package

1. **Do you need it?** Prefer the standard library, the framework, or a dependency the project already has. Ten lines of code you understand beat a package for one function.
2. **Is it the package you think it is?** Confirm the exact name on the registry (npm, Packagist, PyPI) and that it links to the expected source repository. Watch for typos and lookalikes (`reqeusts`, `python-dateutils`, `laravel-permision`).
3. **Is it alive?** Recent releases, more than one maintainer for critical packages, issues that get answers, a security policy.
4. **What does it run on install?** npm `preinstall` and `postinstall` scripts and Python build hooks execute code on your machine and in CI.
5. **What does it pull in?** Check the transitive tree size and licenses.

If you cannot verify a package from here, say so in the report and let the user confirm it. Do not guess.

## Pin and lock

- Commit lockfiles: `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `bun.lock`, `composer.lock`, `poetry.lock`, `uv.lock`.
- In CI install from the lockfile: `npm ci`, `pnpm install --frozen-lockfile`, `composer install` (not `update`), `pip install -r requirements.txt --require-hashes` or `uv sync --locked`.
- Avoid floating versions for tools that run with secrets (`latest` Docker tags, unpinned GitHub Actions). Pin GitHub Actions to a full commit SHA.

## Audit

- `npm audit`, `composer audit`, `pip-audit`, or `osv-scanner` across ecosystems.
- Enable Dependabot or Renovate so updates arrive as small reviewed pull requests.
- Read the changelog of security releases. A patch that changes defaults (for example a stricter cookie setting) can break flows.

## CI and build pipeline

- Give workflows the least `permissions:` they need. The default token should not be able to write to the repository unless the job requires it.
- Be careful with `pull_request_target` and `workflow_run`. They run with secrets in the context of the base repository, so they must never check out and execute code from the fork.
- Never pipe a remote script into a shell (`curl ... | bash`) in build steps without a pinned version and checksum.
- Keep build secrets out of build logs and artifacts.

## MCP servers, agent tools, and skills

Treat them like dependencies with extra reach. They run with your credentials and their tool descriptions enter the model's context, where hidden instructions can steer it. Install from known sources, pin versions, review what tools they expose, and give them the narrowest tokens possible.

## Report line

When the change adds or updates a dependency, include one line in the report: the package, the version, why it was needed, and what you verified (name, source repository, maintenance, install scripts).
