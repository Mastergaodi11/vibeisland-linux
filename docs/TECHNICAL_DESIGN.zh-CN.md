# Vibe Island for Linux 技术设计

英文版：`docs/TECHNICAL_DESIGN.md`

维护说明：以后只要本文件或英文版发生变更，必须同步更新中英文两个版本。

## 已确认的本地环境

- 工作目录：`/path/to/vibeisland-linux`
- 操作系统：EndeavourOS（基于 Arch）
- 会话类型：Wayland
- 桌面环境：KDE Plasma
- 本地 Claude 配置文件：`~/.claude/settings.json`
- 本地 Codex 配置文件：`~/.codex/config.toml`
- 操作配置参考：`docs/INTEGRATION_SETUP.md`

## 外部参考

原始产品公开描述了这些核心行为：

- 在一个视图里监控多个 Agent
- 对审批和提问快速反应
- 跳回正确终端
- 使用本地 Unix socket / 本地优先模型

参考来源：

- https://vibeisland.app/
- https://github.com/farouqaldori/claude-island

`claude-island` 是当前最接近的公开 UI 参考。最值得借鉴的是：

- 紧凑、稳定的折叠态 notch
- 列表式高密度任务行，而不是 oversized dashboard card
- 克制的深色表面和语义化强调色
- 审批控件内嵌在所属会话行内
- 宽高变化小、视觉抖动低的布局

## 当前已实现状态

截至 2026-04-04，Linux 版已经覆盖了目标设计中相当有价值的一部分。

目前已完成：

- `vibeislandd` Rust daemon 与 Unix socket IPC
- 基于 SQLite 的事件和会话持久化
- daemon 到 shell 的实时快照订阅
- 重开后重新扫描 live 进程，让仍在运行的 Claude / Codex 会话回到岛上
- Claude Code 与 Codex CLI 的 hook 适配
- Claude / Codex 核心审批的岛内处理
- 可拖拽的 Qt/QML 浮动壳层
- 审批点击后的乐观更新
- KDE Wayland / Konsole 下基于 KWin + DBus 的 Jump
- 基础音效接入
- stuck detection 已在 daemon 和 shell 中可见
- Replay timeline 已从事件存储送到 shell
- Quiet Mode / Focus Mode 已接入 shell
- 按终端持久化任务标签，便于 live 重扫后恢复任务名
- 标题选择优先保留任务意图，而不是 runtime hook 文本
- Codex 任务标题可从历史 / transcript 中恢复，避免被探测命令污染
- `Codex @ ...` 这类通用标题被降为低信号，不能再污染真正的任务标签
- 审批事件上已经附带 review 信息，并可在 shell 中渲染
- live 标题恢复开始优先使用 Agent 本地工件，而不是 daemon 当前仅有的通用标题
- usage HUD 与 terminal peek 已成为正式目标，而不再只是附加项
- 会话列表会在实时刷新后保留滚动位置，避免用户下拉浏览时又被弹回顶部
- 手动折叠现在会覆盖自动展开；在用户再次主动展开前，岛不会因为后台事件而自己弹开
- shell 偏好现在会跨关闭/重开保留，不再在退出时删除 Telegram bridge 设置
- 折叠态 notch 正在围绕更窄的宽度和专门的 idle/sleep 呈现做重构
- 展开态顶部正改为单行任务/状态标题，避免用户常用宽度下标题和状态 pill 重叠
- prompt attention 现在是一个显式 shell 偏好；启用后，新审批会同时触发展开和前台注意力请求
- 由于 Wayland compositor 仍可能覆盖极端场景下的 always-on-top，系统托盘召回路径也已纳入设计
- shell 音效现在优先走更轻量的系统音频播放器来播放内置 8-bit 提示音，从而避免启动阶段依赖 Qt 多媒体硬件解码探测
- 展开态 shell 正在从内容驱动尺寸转向“持久化 + 钳制”的窗口尺寸模型，并支持用户直接用鼠标缩放
- 折叠态拖拽热区正在扩展到 notch 的大部分主体区域，而显式操作控件仍保留给点击交互
- `tools/vibeisland.py` 里新增了一层 launcher，负责统一编排 daemon / socket / shell，让公开版启动收敛为一条命令，并支持桌面入口
- 公开导出现在成为明确的构建边界：本地仓库可以继续保留私有协作实验，但 `export-public` 导出的 `vibeisland-linux` 必须默认不带 collaboration 运行时依赖

部分实现：

- tmux 感知的 Jump 元数据与 tmux send-keys 回退
- 通用 PID / 标题 / KWin 窗口激活
- ask-user / approval 在更多 prompt 形态下的覆盖
- 比 command / detail / risk / workspace 更丰富的 review 摘要
- 基于工件的重开后 live 标题恢复
- terminal peek 与简短 follow-up 输入
- 30 秒橙色、75 秒红色的超时升级提示

尚未实现：

- 托盘 / 设置界面
- 完整 plan diff review
- 批量审批
- kitty / wezterm / IDE 终端的精准 provider
- Claude / Codex 之外的正式生产级适配器

## 当前需要优先补的缺口

目前最主要的正确性问题是：重开后如何为 live session 恢复正确身份。

现状问题：

- hook 事件不总是能给出可用的 `tty`
- daemon 在无法把 live 进程重新绑定到旧任务元数据时，会回退到通用标题
- shell 虽然能恢复部分标题，但 live 身份本身仍然需要更多来自本地工件而不是只来自 `tty`
- 当有更具体的工件标题可用时，通用标题不应该继续粘住

因此，下一执行切片应继续推进基于工件的恢复。

## 架构概览

采用双进程桌面架构。

### 1. `vibeislandd`

Rust daemon 负责：

- 接收适配器输入
- 做事件归一化
- 维护会话状态机
- 负责 SQLite 持久化
- 提供 Unix socket / 本地 API
- 维护 jump target 注册表
- 执行通知策略
- 派发音效事件

### 2. `vibeisland-shell`

Qt 6 / QML 壳层负责：

- 折叠态灵动岛 UI
- 展开态会话面板
- 可缩放的展开态浮动窗口
- 轻量交互动作
- 托盘图标
- 通知表现
- 动画和音效提示


## 为什么选这套技术栈

### Rust daemon

- 适合长期运行的本地系统服务
- 擅长 Unix socket、DBus 和进程层工具能力
- 便于最终打包为单个原生二进制

### Qt 6 / QML 壳层

- 最适合做精致、带动画的浮动表面
- 与 KDE 集成良好
- 在这个 use case 上，比 web shell 更适合处理 Wayland 浮窗
- 更容易实现透明、顶部锚定、始终置顶的界面

### 为什么不把 Tauri 作为主壳层

Tauri 很适合做设置页，但第一版在 Wayland 上的浮层行为不如原生 Qt 稳定。后续如果需要非 overlay 工具界面，仍然可以再引入 Tauri。

## 显示策略

### Wayland

- 优先尝试 layer-shell 风格的顶部居中 overlay
- 尽量以非激活方式呈现
- 避免粗暴抢焦点

### X11 回退

- 无边框、置顶、透明窗口
- 复用同一数据契约，只在表现层简化

## 组件地图

### A. Adapters

每个 Agent 都有自己的适配边界。

例如：

- `adapter-claude`
- `adapter-codex`
- 未来的 `adapter-gemini`

适配器职责：

- 接收原始 Agent 信号
- 映射到公共 schema
- 附加 session 与 jump 元数据
- 把归一化后的事件发送给 daemon

### B. Session Aggregator

职责：

- 创建和合并 session 记录
- 维护最新状态
- 记录 heartbeat 时间戳
- 标记 stale session
- 计算 attention score

### C. Event Store

SQLite 用于保存：

- 事件日志
- 当前 session 表
- jump target 表
- replay timeline 查询
- 以 `source + tty` 为键的任务身份缓存
- 以 `source + pid` 为键的 live 工件缓存

### D. Jump Providers

单独的 provider 层用于处理：

- tmux
- kitty
- wezterm
- VS Code 扩展桥接
- 通用回退 provider

`Jump` 应始终是精准动作。`Peek` 是另外一个动作，不应该强制夺走原终端焦点。

### E. Action Router

接收来自 UI 的动作，并决定能否：

- 跳转到目标
- 回答问题
- 允许 / 拒绝审批
- 回退为“打开所属终端”
- 打开 terminal peek 抽屉，展示 transcript 预览并提供简短输入

### F. Session Artifact Resolver

加入一个 resolver 层，在不等待新 hook 事件的情况下读取本地 live 工件。

职责：

- 通过 `/proc/<pid>/fd/*` 把 live Codex PID 映射回 `.codex/sessions/...jsonl`
- 把 live Claude PID 映射到 `~/.claude/sessions/<pid>.json`，再对应到 project transcript
- 恢复稳定的 `backend_session_id`、transcript 路径、线程名、最后用户任务和 usage 元数据
- 为 shell 提供基于 transcript 的 peek 内容
- 当 `cwd` 一致但 hook 文本过于通用时，从 `~/.codex/state_5.sqlite` 恢复 Codex 标题
- 从 Claude session / project 工件中恢复标题，并忽略模板化助手废话

### G. Shell 视图状态保护层

shell 会在 daemon 快照之外额外维护一层很小的本地视图状态，用来保证高频刷新时仍然尊重操作员的浏览意图。

职责：

- 记住 `ListView.contentY`，避免 session model 刷新后滚动位置丢失
- 在刷新后以及手动重新展开后恢复滚动位置
- 把“手动折叠”视为明确的用户偏好，在用户再次主动展开前抑制自动展开

## 推荐事件流

1. Agent 发出 hook 或 wrapper 事件
2. 适配器转为公共 schema
3. 适配器把事件发送给 `vibeislandd`
4. daemon 更新 session 和持久化数据
5. daemon 把状态变化发送给 shell
6. shell 更新 UI，并按需播放音效 / 显示通知

对于重开后的 live session，shell 与 daemon 还可以额外做一次本地工件刷新：

1. 发现 live 进程
2. 检查进程 fd / session 元数据
3. 恢复 backend session id、transcript 路径和 usage
4. 从 session 工件推导稳定任务标题
5. 把工件结果合并回展示身份

如果 daemon 只知道一个通用 runtime 标题，shell 应该在渲染前先尝试从本地工件刷新。

## 按 Agent 的集成策略

### Claude Code

当前路径：

- 配置注入 + hooks
- 在支持的 flow 中，在 `PreToolUse` 阶段等待本地托管审批

当前说明：

- 当前岛内已经优先使用本地审批决策，而不是伪造终端按键
- 更丰富的 review 展示和更多 prompt 形态覆盖仍是后续工作
- 对 live 运行会话来说，基于工件的标题恢复应成为真相源
- token 使用量在可用时应从本地 Agent 工件中提取

### Codex CLI

当前路径：

- hook 集成
- notify bridge
- 通过 hook 拦截 + 本地决策状态来托管审批流

当前说明：

- 核心审批 flow 已能在岛内处理
- app-server 以及更丰富的结构化输出仍值得后续接入
- live Codex 任务在重开后应通过 transcript fd 发现恢复 thread name 与 token / rate-limit 数据
- 若 Codex 走 API key 计费，应显示自灵动岛启动以来的累计 token，而不是伪造额度
- 当 live Codex 只有通用 runtime hook 文本时，`~/.codex/state_5.sqlite` 是最重要的本地标题来源

### Gemini CLI

初始计划：

- 未来加入时走 wrapper-based adapter

## 统一 Session Schema

使用版本化事件模型。

```json
{
  "schema": "v1",
  "event_id": "uuid",
  "ts": "2026-04-03T08:12:52.250Z",
  "source": "codex",
  "adapter": "codex-wrapper",
  "session": {
    "id": "session-id",
    "title": "Fix auth middleware",
    "workspace": "/path/to/repo",
    "cwd": "/path/to/repo",
    "task_label": "Fix auth middleware",
    "artifact_session_id": "optional-backend-id",
    "peek_supported": true
  },
  "kind": "needs_approval",
  "state": "blocked",
  "summary": "Waiting for shell approval",
  "progress": {
    "phase": "editing",
    "pct": null
  },
  "usage": {
    "provider": "codex",
    "billing_mode": "subscription",
    "window_5h_remaining_percent": 34,
    "window_7d_remaining_percent": 67,
    "session_total_tokens": 37601
  },
  "interaction": {
    "question": null,
    "choices": []
  },
  "jump_target": {
    "terminal": "tmux",
    "tty": "/dev/pts/3",
    "pid": 12345,
    "tmux_session": "work",
    "tmux_window": "2",
    "tmux_pane": "%7"
  },
  "raw": {},
  "session_artifact": {
    "backend_session_id": "real-provider-session-id",
    "transcript_path": "/home/user/.codex/sessions/...jsonl",
    "thread_name": "Build 贪吃蛇游戏",
    "peek_available": true
  }
}
```

## 本阶段的 UI 方向

可借鉴 Claude Island 的这些模式，并改造成 Linux 版：

- 紧凑暗色胶囊，强调色克制使用
- 展开态更像高密度列表，不像 oversized dashboard card
- 审批控件内嵌在所属任务行中
- 小型次级图标动作放在任务行右侧
- 折叠态用一行展示当前状态和当前项目标题
- 折叠态应保持文本宽度稳定，避免标签抖动
- 整体配色应以石墨色系为主，把色彩留给状态，而不是装饰

Linux 适配说明：

- 因为没有物理刘海约束，要保留可拖拽行为
- 第一阶段优先做 transcript-backed peek，而不是完整 chat 渲染
- 保留 `Jump` 作为精准动作，并新增 terminal-peek 作为轻量动作
- 在 `Jump` 旁边增加一个紧凑终端图标按钮，点击后打开岛内 peek 抽屉

## Usage 收集计划

Claude usage：

- 解析活跃 project session `.jsonl` 中的 usage block
- 如果可用，直接消费 Claude `statusLine` 里的 `rate_limits`，展示 OAuth 的 5 小时 / 7 天剩余额度
- 如果最近没有新的 `statusLine` 快照，则回退为 transcript 推导的 token 统计

Codex usage：

- 解析活跃 session `.jsonl` 中的 `token_count` 事件
- 从 `rate_limits` 展示 5 小时 / 7 天剩余额度
- 如果处于 API key 计费模式，则回退为自灵动岛启动以来的累计 token

Claude artifact usage：

- 解析 `message.usage` 和最近 project transcript 工件里的 token 总量
- 把最好的本地状态以 `available`、`unavailable` 或 `api-key` 的形式对外暴露

### 核心事件种类

- `session_started`
- `session_heartbeat`
- `session_updated`
- `plan_updated`
- `needs_approval`
- `ask_user`
- `completed`
- `failed`
- `cancelled`

### Session 状态

- `running`
- `blocked`
- `waiting_user`
- `completed`
- `failed`
- `stale`

## 终端 Jump 策略

按能力分层：

### Tier 1：精准

- tmux
- KDE Wayland / Konsole（通过 KWin + DBus）

### Tier 1.5：当前已部分可用

- 基于 PID 的应用激活
- 捕获 tmux 元数据，并在可用时使用 tmux send-keys 回退

### Tier 2：高概率正确

- 通过 PID / cwd / title 匹配激活通用终端窗口

### Tier 3：兜底

- 打开 workspace
- 展示 session 元数据
- 告诉用户应查看哪个终端宿主

## 审批策略

当前设计选择：

对支持的 Claude / Codex 审批流，优先使用明确的本地决策状态，而不是依赖伪造终端输入。

原因：

- Linux 终端与 Wayland 输入路径并不一致
- 直接键盘注入会带来权限和信任摩擦
- 只要 Agent 暴露了安全拦截点，本地 hook 托管决策会更可靠

含义：

- 支持的审批应在岛内完整闭环
- 对不支持的工具和未来 Agent，在暴露安全动作通道前，仍可能需要回退行为

## 建议仓库结构

```text
docs/
  PRD.md
  PRD.zh-CN.md
  TECHNICAL_DESIGN.md
  TECHNICAL_DESIGN.zh-CN.md
  INTEGRATION_SETUP.md
  INTEGRATION_SETUP.zh-CN.md
apps/
  shell/
crates/
  daemon/
  common/
  adapter-claude/
  adapter-codex/
  jump-tmux/
  jump-kitty/
tools/
  launcher/
```

## Subagent 执行计划

后续实现应该继续按 ownership 明确拆给 subagent 并行推进。

### Subagent 1：Core / Daemon

负责：

- `crates/common`
- `crates/daemon`

任务：

- 事件 schema
- 本地 socket server
- session aggregator
- SQLite 存储

### Subagent 2：Shell / UX

负责：

- `apps/shell`

任务：

- 浮动灵动岛
- 卡片布局
- 动画
- 托盘
- 通知
- 音效接线

### Subagent 3：Agent Adapters

负责：

- `crates/adapter-claude`
- `crates/adapter-codex`
- `tools/launcher`

任务：

- hook 配置管理
- wrapper launcher
- 适配器事件翻译

### Subagent 4：Jump Integrations

负责：

- `crates/jump-tmux`
- `crates/jump-kitty`
- 未来 jump provider

任务：

- 终端映射
- Jump 执行
- best-effort fallback 逻辑

## 构建顺序

1. 搭出 workspace 与共享 schema
2. 实现带测试夹具输入的 daemon
3. 实现 Claude 与 Codex 适配器
4. 实现订阅 mock event 的最小 shell
5. 把真实 socket 链路串起来
6. 增加 tmux jump provider
7. 做以 KDE 为中心的 shell 打磨

## 下一阶段设计优先级

1. 审批前 Review

- 在卡片里展示精确命令、文件影响摘要和风险原因
- 让审批变成“看懂了再批”，而不是盲批

2. 导航置信度

- 为 kitty、wezterm、VS Code、Cursor 增加专用 Jump provider
- 当结果只是 best-effort 时，也要明确告诉用户

3. 注意力质量

- 增加 quiet mode、批量处理和更好的优先级规则，让灵动岛少打扰

4. 恢复能力与记忆

- 增加 replay timeline、session search 以及 stale / stuck detection

5. 日常使用人体工学

- 设置界面、音效包选择、密度控制、按工具规则和更强的视觉精修

6. 基于工件的身份恢复

- 即便 runtime hook 很吵，也要让标题保持任务优先
- 重开后从本地工件恢复 `Build Snake game` / `Create 1.txt` 这类标签

7. Usage 与超时老化

- 展示 provider usage
- 让 30 秒无人处理的审批变橙色，75 秒变红色

## 必须尊重的难题

- Wayland 的焦点与 overlay 行为
- 不稳定的私有 Agent 内部实现
- 终端控制 API 质量参差不齐
- 审批动作本身的安全性

## 推荐实现原则

第一版优先保证可靠的会话可见性和 Jump 准确度，而不是追求华丽但脆弱的跨进程控制。

## 下一执行切片

建议按以下顺序推进：

1. stuck detection
2. replay timeline
3. quiet mode

原因：

- 这几项用最小风险换来最大的上下文恢复与注意力收益
- 它们可以复用现有 daemon 事件存储、session 摘要和 shell 订阅模型
- 也能为后续更深的 review-before-approve 打好基础

推荐实现形态：

- 扩展 `SessionSummary` 的派生 attention 元数据，而不是再发明一套独立状态系统
- 从持久化事件日志或 session 本地 recent event cache 中推导 replay 项
- quiet mode 先做展示层策略，后续再考虑 daemon 侧通知策略

本切片完成标准：

- 一个会话能够以显式理由显示为 stuck，而不只是看起来仍然是 running
- 用户能在 shell 中看到近期时间线，而不需要打开终端
- 低优先级噪音可以被压制，但紧急审批仍然会展开灵动岛


## 2026-04-06 Shell 运行时补充

- `WindowStaysOnTopHint` 现在由 shell 侧的 `pinned` 状态控制，而不是永久开启。
- replay 的展开/收起已经成为持久化的 shell 偏好；默认展开，但可以在不关闭 timeline 来源的情况下折叠。
- Terminal Peek 现在支持 live preview override，在不强制重建整份 session 列表的前提下，也能从本地最新 transcript 刷新 peek 面板。
- shell 现已具备可选的 Telegram bot 循环：
  - 在 shell 偏好中保存 bot token / 已配对 chat id
  - 轮询 `getUpdates`
  - 对待处理审批发送内联按钮
  - 通过等待用户下一条 Telegram 文本消息，实现类似选项 3 的 follow-up 回复
  - 过滤协作 / system 噪音，并对内容未变化的审批提示做去重
  - Telegram 回调会优先解析到底层托管审批 request，因此 Claude 和 Codex 都能更稳地穿过 session id 漂移
- 音效优先使用本地 8-bit wave 资源；不可用时再回退到桌面系统提示音 / beep。
- 像素 sprite 使用 QML Canvas 动态渲染，因此 Linux 版 shell 不依赖外部 GIF 解码器也能保持自包含。
