# Release Notes: 0.1.0-beta.1

## Vibe Island for Linux beta1

This is the first public beta release of `Vibe Island for Linux`.

## Highlights

- local-first floating island for Claude Code and Codex
- one-command startup through `python tools/vibeisland.py launch`
- optional desktop launcher installation through `python tools/vibeisland.py install-desktop`
- in-island approvals, replies, jump-back, and mini terminal peek
- usage HUD, replay timeline, idle/sleep collapsed state
- optional Telegram remote approval bridge

## First-Class Environment

- Arch Linux / EndeavourOS
- KDE Plasma
- Wayland
- Konsole

Other Linux desktops and terminals are currently best-effort.

## Important Configuration Notes

- Claude Code configuration lives in `~/.claude/settings.json`
- Codex configuration lives in `~/.codex/config.toml` and `~/.codex/hooks.json`
- Switching Claude between OAuth and API key modes must not remove `hooks` or `statusLine`
- Codex should keep `approval_policy = "never"`, `notify`, and `features.codex_hooks = true`

See:

- `README.md`
- `docs/INTEGRATION_SETUP.md`
- `docs/INTEGRATION_SETUP.zh-CN.md`

## Public Boundary

This beta release is for the standalone island only.

The local/private Claude+Codex collaboration runtime is intentionally excluded from this public release.

## Known Beta Limitations

- best experience is still centered on KDE Plasma + Wayland + Konsole
- always-on-top / pin remains best-effort under Wayland compositor policy
- jump precision outside the tested environment is still improving
- UI polish is strong enough for daily use, but not final
