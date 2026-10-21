# Temporary npm development-tool exception

Reviewed 2026-10-12; expires **2026-10-26**. Owner: Stash maintainers.

[GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)
affects braces 3.0.3. There is no published patched release. Next's supported
ESLint plugin still depends on it through fast-glob and micromatch. npm's
suggested remediation downgrades eslint-config-next to 14.2.35; this project
uses Next 16 and retains its matching lint configuration.

The reviewed dependency chain is eslint-config-next 16.3.8 →
@next/eslint-plugin-next 16.3.8 → fast-glob 3.3.1 → micromatch 4.0.8 → braces 3.0.3.
Every installed node in this chain is marked development-only in both lockfiles.
The plugin's only glob invocation is
[get-root-dirs](https://raw.githubusercontent.com/vercel/next.js/v16.3.8/packages/eslint-plugin-next/src/utils/get-root-dirs.ts),
which accepts the developer's `settings.next.rootDir`. Both current lint configs
omit that setting, taking the plain working-directory path instead. Reassess
this exception if the configs introduce rootDir globs or other consumers.

The audit runner retains the raw npm report and emits a visible warning. It
exempts only this advisory and exact reviewed versions, and requires every
installed instance to be dev-only. New advisories, production copies, different
versions, unknown dependency chains, audit errors and expiry still fail CI.
Any change to npm's reviewed 14.2.35 downgrade suggestion also ends the exception.
Production npm audits
currently report zero vulnerabilities. This exception is not an upstream fix.

Before expiry, update to a patched supported dependency and remove the exception,
or explicitly repeat the exposure review. No automatic renewal is implemented.
