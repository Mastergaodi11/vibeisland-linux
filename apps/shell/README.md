# Shell UI

This directory contains the floating shell UI for `Vibe Island for Linux`.

For normal usage, start the product from the unified launcher instead of launching the shell by hand:

```bash
python tools/vibeisland.py launch
```

If you specifically want to run only the shell for development, use:

```bash
python -m apps.shell
```

If `vibeislandd` is running, the shell connects to `VIBEISLAND_SOCKET`, prefers the live
subscription stream, and runs a lightweight live-process reconcile on startup so already-running
Claude/Codex terminals reappear quickly after reopening. If streaming is unavailable, it falls back
to one-shot snapshot reads.

If the daemon is not running, the shell falls back to `sample_snapshot.json` for development/demo use.

The floating island remembers local UI preferences in `~/.config/vibeisland-shell/state.json`,
including position, expanded size, Telegram settings, and other shell-side presentation state.

Useful flags:

```bash
python -m apps.shell --state apps/shell/sample_snapshot.json
python -m apps.shell --socket /tmp/vibeisland.sock
```
