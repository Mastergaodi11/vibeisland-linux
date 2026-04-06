# Contributing

Thanks for your interest in improving `Vibe Island for Linux`.

## Scope

This repository is for the public island itself:

- Rust daemon
- shell UI
- Claude Code / Codex integration hooks
- local notifications, replay, usage HUD, Telegram bridge

The private/local Claude+Codex collaboration runtime is intentionally out of scope for public contributions in this repository.

## Before Opening an Issue

Please include:

- distro and desktop environment
- X11 or Wayland
- terminal emulator
- whether you use Claude Code, Codex, or both
- exact reproduction steps
- relevant terminal output or screenshots

For UI issues, screenshots are especially helpful.

## Before Opening a Pull Request

Please keep changes focused and mention:

- what user-visible problem you are solving
- what environment you tested on
- whether behavior changed for KDE Wayland / Konsole

If you touch docs, update English and Chinese docs together.

## Development Notes

- prefer `rg` for search
- use `python tools/vibeisland.py launch` for the normal local run path
- use `python tools/vibeisland.py status` to inspect launcher state
- use `python tools/vibeisland.py export-public --output <dir>` to verify the public, collaboration-free export

## Code and UX Expectations

- local-first behavior is preferred over cloud coupling
- avoid breaking the first-class Arch / KDE Plasma / Wayland / Konsole path
- keep approvals and jump-back flows fast and legible
- preserve the collaboration-free public boundary
