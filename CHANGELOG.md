# Changelog

All notable changes to `Vibe Island for Linux` should be documented in this file.

The format is intentionally lightweight for the beta stage.

## Unreleased

Post-beta fixes currently staged for the next public update:

- collaboration cards are no longer injected into the island unless collaboration is explicitly re-enabled
- pending approval requests are now overlaid into the shell session model so blocked prompts remain visible in the island even when Telegram already sees them
- session dedupe now also merges on stable session id aliases, which reduces duplicate cards for the same live terminal

## 0.1.0-beta.1 - 2026-04-06

First public GitHub-ready beta release of the Linux island.

Highlights:

- one-command launcher through `python tools/vibeisland.py launch`
- desktop launcher installation through `python tools/vibeisland.py install-desktop`
- Claude Code and Codex CLI hook integration
- in-island approval and reply UX for core flows
- terminal jump-back and mini terminal peek
- Telegram remote approval bridge
- provider usage HUD, replay timeline, idle/sleep collapsed state
- public export flow through `python tools/vibeisland.py export-public --output <dir>`

Known limits:

- first-class environment is still Arch Linux / KDE Plasma / Wayland / Konsole
- always-on-top / pin behavior remains best-effort under Wayland compositor policy
- the private Claude+Codex collaboration runtime is intentionally excluded from this public release
