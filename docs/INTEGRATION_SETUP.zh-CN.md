# Vibe Island 集成配置说明

英文版：`docs/INTEGRATION_SETUP.md`

维护说明：以后只要本文件或英文版发生变更，必须同步更新中英文两个版本。

本文档说明：在另一台 Linux 机器上，要让 `Vibe Island` 正常与 `Claude Code` 和 `Codex` 联动，需要哪些本地 CLI 配置。

## 目标

要让灵动岛正常工作，至少需要两类集成：

- `Claude Code` 需要通过 `~/.claude/settings.json` 把生命周期和审批事件转发出来
- 如果希望灵动岛显示 Claude 的 5 小时 / 7 天剩余额度，还需要通过 `statusLine` 暴露 `rate_limits`
- `Codex` 需要通过 `~/.codex/config.toml` 和 `~/.codex/hooks.json` 把生命周期事件转发出来

本项目已经提供了一键安装器：

```bash
cd /path/to/vibeisland-linux
python tools/vibeisland.py install all
```

如果你更想手动配置，可以按下面的方式做。

## Claude Code

配置文件：

- `~/.claude/settings.json`

### 浏览器 OAuth 登录

如果你希望 `Claude Code` 使用官方浏览器登录，而不是 API key 或自定义 token 模式：

- 不要在 `settings.json` 中设置 `ANTHROPIC_AUTH_TOKEN`
- 不要在 `settings.json` 中设置 `ANTHROPIC_BASE_URL`
- 建议设置：

```json
"forceLoginMethod": "claudeai"
```

推荐的认证相关片段如下：

```json
{
  "env": {
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"
  },
  "forceLoginMethod": "claudeai"
}
```

完成后，重新打开 `claude`，按照浏览器流程登录即可。

### Vibe Island 必需的 hooks

下面这些 hook 事件都应该调用：

```bash
/usr/bin/python "/path/to/vibeisland-linux/tools/vibeisland.py" claude-hook
```

当前项目会安装这些 Claude 事件：

- `SessionStart`
- `UserPromptSubmit`
- `PreToolUse`
- `PermissionRequest`
- `Notification`
- `Elicitation`
- `Stop`
- `PostToolUse`
- `PostToolUseFailure`

示例结构：

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

重要说明：

- 即便切换 Claude 的登录方式，也必须保留 `hooks` 段
- 浏览器 OAuth 与 hooks 是两套独立能力，切换登录方式不应该删除 hooks

### Claude 配额 HUD 必需的 `statusLine`

如果你希望灵动岛显示 Claude OAuth 的剩余额度百分比，还需要让 `Claude Code` 调用：

```bash
/usr/bin/python "/path/to/vibeisland-linux/tools/vibeisland.py" claude-statusline
```

示例结构：

```json
{
  "statusLine": {
    "type": "command",
    "command": "/usr/bin/python '/path/to/vibeisland-linux/tools/vibeisland.py' claude-statusline"
  }
}
```

说明：

- 这和 `hooks` 是分开的
- `hooks` 负责生命周期与审批事件
- `statusLine` 负责把 Claude 的 `rate_limits` 提供给灵动岛，以显示 5 小时和 7 天剩余额度
- 新增或修改 `statusLine` 后，必须重启一次 `claude`

## Codex

配置文件：

- `~/.codex/config.toml`
- `~/.codex/hooks.json`

### 必需的 `config.toml`

当前 `Vibe Island` 依赖这些键：

```toml
approval_policy = "never"
notify = ["/usr/bin/python", "/path/to/vibeisland-linux/tools/vibeisland.py", "codex-notify"]

[features]
codex_hooks = true
```

说明：

- `approval_policy = "never"` 是因为审批体验由灵动岛接管
- `notify` 让灵动岛能观察完成和通知类事件
- `codex_hooks = true` 用来开启 hook 系统

### 必需的 `hooks.json`

下面这些事件应该调用：

```bash
/usr/bin/python "/path/to/vibeisland-linux/tools/vibeisland.py" codex-hook
```

当前项目会安装这些 Codex 事件：

- `SessionStart`
- `UserPromptSubmit`
- `PreToolUse`
- `PermissionRequest`
- `PermissionDenied`
- `PostToolUse`
- `PostToolUseFailure`
- `Stop`
- `StopFailure`

示例结构：

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

## 在新机器上的推荐配置流程

1. 克隆或复制 `vibeisland-linux`
2. 把文档示例中的绝对路径替换为本机真实路径
3. 执行：

```bash
cd /path/to/vibeisland-linux
python tools/vibeisland.py install all
```

4. 如果使用 Claude 浏览器登录，确认 `~/.claude/settings.json` 中不包含：

- `ANTHROPIC_AUTH_TOKEN`
- `ANTHROPIC_BASE_URL`

5. 增加或保留：

```json
"forceLoginMethod": "claudeai"
```

6. 重启 `claude` 和 `codex`
7. 通过统一启动器启动 Vibe Island：

```bash
cd /path/to/vibeisland-linux
python tools/vibeisland.py launch
```

Shell 行为说明：

- Telegram bot token 和自动学到的 `chat_id` 会保存在 `~/.config/vibeisland-shell/state.json`
- 展开态 shell 的宽高也会保存在这个文件里，并在下次启动时以被钳制后的合理尺寸恢复
- 在 KDE Wayland 下，`pin` 是“尽量保证”的行为；真正可靠的手动唤回路径是托盘里的 `Summon Island`
- 如果你还想安装桌面入口和 `vibeisland` 终端命令，可执行：

```bash
cd /path/to/vibeisland-linux
python tools/vibeisland.py install-desktop
```

之后就可以直接使用：

```bash
vibeisland
vibeisland status
vibeisland stop
```

## 故障排查

### Claude 仍然要求 token / API 登录

检查 `~/.claude/settings.json`，删除：

- `ANTHROPIC_AUTH_TOKEN`
- `ANTHROPIC_BASE_URL`

然后重新打开 `claude`。

### Shell 重开后尺寸过大或位置异常

检查：

- `~/.config/vibeisland-shell/state.json`

shell 现在会把展开态尺寸和位置持久化到这里。如果这个文件里保留了更早版本遗留的旧几何尺寸，新的实现应该会自动钳制；如果仍有异常，可以先手动删除一次这个文件，再重新启动 shell。

### 灵动岛看不到 Claude 或 Codex 事件

检查：

- `~/.claude/settings.json` 里是否还保留 `hooks`
- 如果你希望看到 Claude 配额百分比，`~/.claude/settings.json` 里是否还保留 `statusLine`
- `~/.codex/config.toml` 是否仍有 `notify` 和 `features.codex_hooks = true`
- `~/.codex/hooks.json` 是否仍包含 Vibe Island 的命令

### Claude 事件正常，但额度仍显示 unavailable

请检查：

- `~/.claude/settings.json` 是否包含 `statusLine`
- 增加 `statusLine` 后是否重启过 `claude`
- 打开 Claude 时，`~/.local/state/vibeisland/claude_statusline.json` 是否会被更新

### 项目路径变化后 hooks 失效

hook 命令使用的是绝对路径。如果项目路径改变，请重新执行：

```bash
cd /new/path/to/vibeisland-linux
python tools/vibeisland.py install all
```


## 可选的 Telegram 远程审批配置

Telegram 是可选能力。即便完全不配置 Telegram，Vibe Island 也必须保持可正常使用。

1. 通过 BotFather 创建 bot，并复制 bot token。
2. 点击 shell 右上角的 settings 按钮打开设置面板。
3. 粘贴 bot token，开启 Telegram 开关并保存。
4. 在 Telegram 中打开这个 bot，先发送一次 `/start`，让 shell 学会你的 `chat_id`。
5. 使用内置的 `TEST` 按钮确认 bot 已能把消息发到你的手机。

bot token、自动学到的 `chat_id` 和最近一次处理过的 Telegram update id 都会写入 shell 偏好文件，因此下次启动时 bridge 会自动恢复连接。

启用后，审批既可以在桌面灵动岛上处理，也可以从 Telegram 处理。`reply / deny` 路径会提示你再发一条文本消息，这条文本会被转发成 agent 的选项 3 式 follow-up 回复。
当 Telegram 上的审批按钮成功送达 agent 后，shell 现在也会反向给 Telegram 一个简短成功回执，帮助用户确认选择已经生效。

Telegram 推送应保持克制：

- 只转发真正面向用户的 live 审批 / 提问
- 协作状态噪音和 bridge/runtime 诊断信息应保留在桌面，不应刷到手机
- 对于完全相同、仍未解决的审批，请求应去重，不应反复提醒

## 可选的前台提醒行为

shell 设置面板现在提供 `AUTO FRONT ON APPROVAL`。

- 开启后，新的审批 / 提问会自动展开灵动岛，并请求桌面把它带到前台。
- 普通的 live 会话波动不应触发这条路径；shell 现在会把它保留给真正可操作的审批 / 提问。
- 关闭后，灵动岛会更安静；用户可以改用系统托盘图标手动召回。
