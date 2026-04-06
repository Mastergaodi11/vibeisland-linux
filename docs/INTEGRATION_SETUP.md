# Vibe Island Integration Setup

Chinese version: `docs/INTEGRATION_SETUP.zh-CN.md`

Maintenance note: keep the English and Chinese editions in sync whenever this document changes.

This document explains the local CLI configuration required for `Vibe Island` to work correctly with `Claude Code` and `Codex` on another Linux machine.

## Goal

To make the island work normally, two integrations must exist:

- `Claude Code` must forward lifecycle and approval events through `~/.claude/settings.json`
- `Claude Code` must also expose `rate_limits` through `statusLine` if you want the Claude 5-hour / 7-day quota HUD
- `Codex` must forward lifecycle events through `~/.codex/config.toml` and `~/.codex/hooks.json`

This project already provides an installer:

```bash
cd /path/to/vibeisland-linux
python tools/vibeisland.py install all
```

If you prefer to configure things manually, use the sections below.

## Claude Code

Config file:

- `~/.claude/settings.json`

### Browser OAuth login

If you want `Claude Code` to log in through the official browser flow instead of API key or custom token mode:

- Do not set `ANTHROPIC_AUTH_TOKEN` in `settings.json`
- Do not set `ANTHROPIC_BASE_URL` in `settings.json`
- Set:

```json
"forceLoginMethod": "claudeai"
```

Recommended auth-related portion:

```json
{
  "env": {
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"
  },
  "forceLoginMethod": "claudeai"
}
```

After this, reopen `claude` and complete the browser login flow.

### Required Vibe Island hooks

The following hook events should call:

```bash
/usr/bin/python "/path/to/vibeisland-linux/tools/vibeisland.py" claude-hook
```

This project currently installs these Claude events:

- `SessionStart`
- `UserPromptSubmit`
- `PreToolUse`
- `PermissionRequest`
- `Notification`
- `Elicitation`
- `Stop`
- `PostToolUse`
- `PostToolUseFailure`

Example shape:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume",
        "hooks": [
          {
            "type": "command",
            "command": "/usr/bin/python '/path/to/vibeisland-linux/tools/vibeisland.py' claude-hook",
            "timeout": 8
          }
        ]
      }
    ]
  }
}
```

Important:

- Keep the `hooks` section even if you switch Claude authentication mode
- Browser OAuth and hooks are independent; changing login mode should not remove hooks

### Required `statusLine` for Claude quota HUD

If you want the island to show Claude OAuth remaining quota percentages, `Claude Code` must also call:

```bash
/usr/bin/python "/path/to/vibeisland-linux/tools/vibeisland.py" claude-statusline
```

Example shape:

```json
{
  "statusLine": {
    "type": "command",
    "command": "/usr/bin/python '/path/to/vibeisland-linux/tools/vibeisland.py' claude-statusline"
  }
}
```

Notes:

- This is separate from `hooks`
- `hooks` drive lifecycle / approval events
- `statusLine` supplies Claude `rate_limits` so the island can show 5-hour and 7-day remaining quota percentages
- After adding or changing `statusLine`, restart `claude`

## Codex

Config files:

- `~/.codex/config.toml`
- `~/.codex/hooks.json`

### Required `config.toml`

`Vibe Island` currently expects these keys:

```toml
approval_policy = "never"
notify = ["/usr/bin/python", "/path/to/vibeisland-linux/tools/vibeisland.py", "codex-notify"]

[features]
codex_hooks = true
```

Notes:

- `approval_policy = "never"` is used because the island manages approval UX itself
- `notify` lets the island observe completion/notification-style events
- `codex_hooks = true` enables the hook system

### Required `hooks.json`

The following events should call:

```bash
/usr/bin/python "/path/to/vibeisland-linux/tools/vibeisland.py" codex-hook
```

This project currently installs these Codex events:

- `SessionStart`
- `UserPromptSubmit`
- `PreToolUse`
- `PermissionRequest`
- `PermissionDenied`
- `PostToolUse`
- `PostToolUseFailure`
- `Stop`
- `StopFailure`

Example shape:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume",
        "hooks": [
          {
            "type": "command",
            "command": "/usr/bin/python '/path/to/vibeisland-linux/tools/vibeisland.py' codex-hook"
          }
        ]
      }
    ]
  }
}
```

## Recommended setup flow on a new machine

1. Clone or copy `vibeisland-linux`
2. Adjust the absolute path in the examples to the real local path
3. Run:

```bash
cd /path/to/vibeisland-linux
python tools/vibeisland.py install all
```

4. If using Claude browser login, ensure `~/.claude/settings.json` does not contain:

- `ANTHROPIC_AUTH_TOKEN`
- `ANTHROPIC_BASE_URL`

5. Add or keep:

```json
"forceLoginMethod": "claudeai"
```

6. Restart both `claude` and `codex`
7. Start Vibe Island with the unified launcher:

```bash
cd /path/to/vibeisland-linux
python tools/vibeisland.py launch
```

Shell behavior notes:

- Telegram bot token and learned `chat_id` are stored in `~/.config/vibeisland-shell/state.json`
- expanded shell width and height are also stored there and should reopen at a clamped, reasonable size
- under KDE Wayland, `pin` is best-effort; the tray `Summon Island` action is the reliable manual recall path
- if you want a desktop launcher and a `vibeisland` terminal command, run:

```bash
cd /path/to/vibeisland-linux
python tools/vibeisland.py install-desktop
```

Then you can use:

```bash
vibeisland
vibeisland status
vibeisland stop
```

## Troubleshooting

### Claude still asks for token/API login

Check `~/.claude/settings.json` and remove:

- `ANTHROPIC_AUTH_TOKEN`
- `ANTHROPIC_BASE_URL`

Then reopen `claude`.

### Shell reopens too large or in a strange position

Check:

- `~/.config/vibeisland-shell/state.json`

The shell now persists expanded size and position there. If an old geometry was saved from a previous build, reopening should clamp it automatically; if not, remove that file once and relaunch the shell.

### Island shows no Claude or Codex events

Check:

- `~/.claude/settings.json` has the `hooks` section
- `~/.claude/settings.json` has the `statusLine` command if you expect Claude quota percentages
- `~/.codex/config.toml` still has `notify` and `features.codex_hooks = true`
- `~/.codex/hooks.json` still contains the Vibe Island commands

### Claude events work but quota still shows unavailable

Check:

- `~/.claude/settings.json` includes the `statusLine` command
- `claude` was restarted after adding `statusLine`
- `~/.local/state/vibeisland/claude_statusline.json` is being updated while Claude is open

### Hooks broke after changing machine path

The hook commands use absolute paths. If the project moved, rerun:

```bash
cd /new/path/to/vibeisland-linux
python tools/vibeisland.py install all
```


## Optional Telegram Remote Approval Setup

Telegram is optional. Vibe Island must keep working without it.

1. Create a bot with BotFather and copy the bot token.
2. Open the shell settings panel from the top-right settings button.
3. Paste the bot token, enable Telegram, and save.
4. Open the bot in Telegram and send `/start` once so the shell can learn your `chat_id`.
5. Use the built-in `TEST` button to confirm that the bot can reach your phone.

The bot token, learned `chat_id`, and last processed Telegram update id are persisted in the shell preferences so the bridge reconnects automatically on the next launch.

When enabled, approvals can be answered either on desktop or from Telegram. The "reply / deny" path asks for a follow-up text message and then forwards that message as the agent's option-3 style reply.
When Telegram approvals are answered successfully, the shell now sends a small success follow-up back to Telegram so the user gets confirmation that the decision reached the agent.

Telegram delivery should stay selective:

- only live user-facing approvals / asks should be forwarded
- collaboration status noise and bridge/runtime diagnostics should stay on desktop
- repeated reminders for the exact same unresolved approval should be deduplicated

## Optional Foreground Attention Behavior

The shell settings panel now includes `AUTO FRONT ON APPROVAL`.

- When enabled, a fresh approval/question expands the island and asks the desktop to bring it forward.
- Routine live-session churn should not trigger this path; the shell now reserves it for real actionable approvals/questions.
- When disabled, the island stays quieter and can be recalled manually from the tray icon instead.
