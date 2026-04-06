# Vibe Island for Linux

English version: [`README.md`](./README.md)

`Vibe Island for Linux` 是一个本地优先的 Linux “Agent 灵动岛”。它可以持续观察 Claude Code 和 Codex 的实时会话状态，在真正需要你介入审批或回答时把注意力拉回来，并且帮你跳回正确的终端。

## 当前发布状态

当前公开首发版本目标：`0.1.0-beta.1`

这次第一次 GitHub 开源发布已经可以承担真实本地工作流，但仍然会对开发和测试时使用的环境有明显优化倾向。

## 它是干什么的

- 在一个浮动壳层里同时监控多个 Claude Code / Codex 会话
- 遇到真正的审批和提问时自动展开
- 支持岛内审批、回复、mini terminal peek 和 jump 回原终端
- 提供 usage HUD、replay 时间线、idle/sleep 折叠态，以及可选的 Telegram 远程审批
- 整体采用本地架构：Rust daemon、Unix socket、SQLite、PyQt6/QML shell

## 当前一等支持环境

当前的一等支持环境是：

- Arch Linux / EndeavourOS
- KDE Plasma
- Wayland
- Konsole

其他 Linux 桌面和终端目前仍然按 best-effort 处理。

## 运行要求

- Python 3.12 或更高版本
- 带 `cargo` 的 Rust 工具链
- Python 环境中可用的 PyQt6
- 本地已安装 Claude Code 和 / 或 Codex CLI
- 如果你想获得当前最稳的体验，建议环境为 Arch Linux / KDE Plasma / Wayland / Konsole

## 快速开始

1. 先安装 Claude Code / Codex 的桥接 hooks：

```bash
cd /path/to/vibeisland-linux
python tools/vibeisland.py install all
```

2. 用一条命令启动灵动岛：

```bash
cd /path/to/vibeisland-linux
python tools/vibeisland.py launch
```

3. 可选：安装桌面启动入口：

```bash
cd /path/to/vibeisland-linux
python tools/vibeisland.py install-desktop
```

之后你可以直接使用：

```bash
vibeisland
vibeisland status
vibeisland stop
```

## beta1 已包含的重点能力

- 一条命令同时拉起 daemon 和 shell
- 通过 `install-desktop` 安装桌面入口
- Claude Code + Codex hooks bridge
- 核心审批与回复可在岛内完成
- Jump 回原终端和 mini terminal peek
- Telegram 远程审批桥接
- provider usage HUD、replay 时间线和 idle/sleep 呈现

## 配置注意点

- Claude Code 配置文件：`~/.claude/settings.json`
- Codex 配置文件：`~/.codex/config.toml` 与 `~/.codex/hooks.json`
- Claude 在 OAuth 和 API key 模式之间切换时，不能把 `hooks` 和 `statusLine` 删掉
- Codex 需要保留 `approval_policy = "never"`、`notify` 与 `features.codex_hooks = true`
- Telegram 是可选功能，绝不能成为灵动岛运行的前提

详细配置说明见：

- [`docs/INTEGRATION_SETUP.md`](./docs/INTEGRATION_SETUP.md)
- [`docs/INTEGRATION_SETUP.zh-CN.md`](./docs/INTEGRATION_SETUP.zh-CN.md)

## 文档入口

- [`docs/README.md`](./docs/README.md)
- [`docs/README.zh-CN.md`](./docs/README.zh-CN.md)
- [`docs/PRD.zh-CN.md`](./docs/PRD.zh-CN.md)
- [`docs/TECHNICAL_DESIGN.zh-CN.md`](./docs/TECHNICAL_DESIGN.zh-CN.md)
- [`CHANGELOG.md`](./CHANGELOG.md)
- [`CONTRIBUTING.md`](./CONTRIBUTING.md)
- [`SECURITY.md`](./SECURITY.md)

## 媒体资源

- 截图和演示素材建议统一放在 [`media/`](./media/)

## 公开版边界

这个仓库将整理成公开的 `vibeisland-linux` 项目。

本地的 Claude + Codex 协作运行时会继续作为另一个独立项目存在，不进入灵动岛当前公开版承诺。也就是说，即便没有安装协作运行时，灵动岛本体也必须能独立正常工作。

## 当前 beta 已知限制

- 当前一等体验仍然主要围绕 KDE Plasma + Wayland + Konsole
- Wayland 下的 pin / always-on-top 仍然是 best-effort
- 测试环境之外的终端 Jump 精准度还在继续提高
- UI 质感已经能满足日常使用，但仍不是最终完成态

## 许可证

MIT，见 [`LICENSE`](./LICENSE)。
