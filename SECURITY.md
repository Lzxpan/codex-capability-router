# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| `v0.2.0-beta.1` | Yes, public pre-release |

## Reporting a vulnerability

Please do not put secrets, credentials, private capability inventory, tokens,
or personal data in a public issue. Use GitHub's private vulnerability
reporting or Security Advisories for this repository when available.

If private reporting is unavailable, open a minimal public issue that contains
no sensitive details and asks for a private reporting channel. Do not attach
logs or files that contain local absolute paths, account information, or
authentication material.

## Scope and release boundary

This project is local-first, read-only, and advisory-only. It does not execute
capabilities, install Plugins, modify permissions, perform network discovery,
or persist private inventory. The public repository intentionally excludes
private registries, credentials, local evaluation state, internal planning
notes, and machine-specific artifacts.

Security reports are evaluated against the released behavior and documented
boundaries. The beta does not promise a response-time SLA or stable API.
