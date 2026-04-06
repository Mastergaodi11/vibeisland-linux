# Security Policy

## Supported Release Line

Current public release line:

- `0.1.0-beta.1`

## Reporting a Vulnerability

If you believe you found a security issue, please avoid posting exploit details in a public GitHub issue first.

Preferred report content:

- affected version
- affected environment
- reproduction steps
- impact summary
- whether the issue exposes local secrets, approvals, tokens, or remote control paths

If private reporting infrastructure is added later, this document should be updated with a dedicated contact path.

## Project-Specific Notes

Areas that deserve extra care:

- local approval handling
- Telegram bridge token handling
- Claude Code / Codex hook integration
- shell-to-terminal reply / jump behavior
- persistence files under `~/.config` and `~/.local/state`
