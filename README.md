# Vibe Island for Linux

中文说明：[`README.zh-CN.md`](./README.zh-CN.md)

Vibe Island for Linux is a local-first floating “agent island” for Linux desktops. It watches live Claude Code and Codex sessions, pulls urgent approvals back into view, lets you jump to the right terminal, and keeps the core workflow on your own machine.

## Release Status

Current public release target: `0.1.0-beta.1`

This first GitHub release is a usable beta for real local workflows, but it is still opinionated toward the environment used during development and testing.

## What It Does

- monitors multiple Claude Code / Codex sessions in one floating shell
- expands for real approvals and user questions
- supports in-island approval, reply, mini terminal peek, and jump-back actions
- shows provider usage HUD, replay timeline, idle/sleep states, and Telegram remote approval as optional extras
- keeps event flow local through a Rust daemon, Unix socket, SQLite state, and a PyQt6/QML shell

## First-Class Environment

Current first-class support is:

- Arch Linux / EndeavourOS
- KDE Plasma
- Wayland
- Konsole

Other Linux desktops and terminals are still best-effort.

## Requirements

- Python 3.12 or newer
- Rust toolchain with `cargo`
- PyQt6 available in your Python environment
- Claude Code and/or Codex CLI installed locally
- Arch Linux / KDE Plasma / Wayland / Konsole if you want the most tested path

## Quick Start

1. Install the Claude Code / Codex bridge hooks:

```bash
cd /path/to/vibeisland-linux
python tools/vibeisland.py install all
```

2. Start the island with one command:

```bash
cd /path/to/vibeisland-linux
python tools/vibeisland.py launch
```

3. Optional: install the desktop launcher:

```bash
cd /path/to/vibeisland-linux
python tools/vibeisland.py install-desktop
```

After that you can use:

```bash
vibeisland
vibeisland status
vibeisland stop
```

## Beta 1 Highlights

- one-command launcher for daemon + shell
- desktop launcher installation through `install-desktop`
- Claude Code + Codex hooks bridge
- in-island approvals and replies for core flows
- jump-back and mini terminal peek
- Telegram remote approval bridge
- provider usage HUD, replay timeline, and idle/sleep presentation

## Configuration Notes

- Claude Code config lives in `~/.claude/settings.json`
- Codex config lives in `~/.codex/config.toml` and `~/.codex/hooks.json`
- Switching Claude between OAuth and API key modes must not remove the `hooks` or `statusLine` sections
- Codex must keep `approval_policy = "never"`, `notify`, and `features.codex_hooks = true`
- Telegram is optional and should never be required for the island to run

Detailed setup instructions:

- [`docs/INTEGRATION_SETUP.md`](./docs/INTEGRATION_SETUP.md)
- [`docs/INTEGRATION_SETUP.zh-CN.md`](./docs/INTEGRATION_SETUP.zh-CN.md)

## Documentation

- [`docs/README.md`](./docs/README.md)
- [`docs/README.zh-CN.md`](./docs/README.zh-CN.md)
- [`docs/PRD.md`](./docs/PRD.md)
- [`docs/TECHNICAL_DESIGN.md`](./docs/TECHNICAL_DESIGN.md)
- [`CHANGELOG.md`](./CHANGELOG.md)
- [`CONTRIBUTING.md`](./CONTRIBUTING.md)
- [`SECURITY.md`](./SECURITY.md)

## Media

- Screenshots and release/demo assets should live under [`media/`](./media/)

## Public Open-Source Boundary

This repository is being prepared as the public `vibeisland-linux` project.

The local Claude+Codex collaboration runtime remains a separate private/local project and is not part of the public release promise for the island itself. The island must keep working even when that collaboration runtime is not installed.

## Known Beta Limitations

- first-class behavior is still tuned for KDE Plasma + Wayland + Konsole
- pin / always-on-top remains best-effort under Wayland compositor policy
- terminal jump precision outside the tested environment is still improving
- UI polish is already strong enough for daily use, but not final

## License

MIT, see [`LICENSE`](./LICENSE).
