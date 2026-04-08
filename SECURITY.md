# Security Policy

## Supported Versions

We accept security reports for the latest commit on the `main` branch.
Older releases are not separately maintained.

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Report security issues by emailing the maintainers privately. Include:

- A description of the vulnerability and its potential impact
- Steps to reproduce or a proof-of-concept (if safe to share)
- Any suggested fixes or mitigations

We will acknowledge your report within 72 hours and aim to release a fix within
14 days for critical issues.

## Scope

In scope:

- Authentication and authorisation bypass
- SQL injection or data exfiltration
- Server-side request forgery (SSRF)
- Cross-site scripting (XSS) via stored content
- Secrets or API keys exposed via API responses or logs

Out of scope:

- Denial-of-service attacks requiring authenticated access and significant resources
- Issues only reproducible on unsupported or non-default configurations
- Social engineering

## Disclosure Policy

We follow a coordinated disclosure model. Please allow us reasonable time to
remediate before any public disclosure. We will credit reporters in release
notes unless anonymity is requested.
