# Vibe Island for Linux 产品需求文档

英文版：`docs/PRD.md`

维护说明：以后只要本文件或英文版发生变更，必须同步更新中英文两个版本。

## 目标

先面向 Arch / EndeavourOS 做出一个 Linux 原生的「Agent 灵动岛」，随后再扩展到更广泛的 Linux 桌面环境。

产品应该让用户能够：

- 在一个地方同时观察多个 AI 编程 Agent
- 及时知道哪个 Agent 被阻塞、完成了任务，或者正在等待用户回答
- 以最低摩擦跳回正确的终端或工作区
- 保持数据完全本地流转，并尽量降低空闲资源占用

本项目灵感来自原版 Vibe Island，并参考其公开功能描述：

- 官方网站：https://vibeisland.app/
- Claude Island 参考仓库：https://github.com/farouqaldori/claude-island

## 产品原则

- 本地优先：事件、状态、动作都尽量只在本机完成
- 低打扰：默认只突出真正重要的时刻
- 快速恢复上下文：一旦需要注意力，尽快把用户带回正确会话
- Linux 原生：优先为 Wayland + KDE 优化，并在其他环境优雅降级
- Agent 无关核心：不同工具走不同适配层，但共享统一会话模型

## 当前状态快照

截至 2026-04-05，项目已经越过最初骨架期，正在从“核心链路跑通”转向“产品感和可用性深化”。

已经可用的内容：

- Rust daemon，本地 Unix socket，SQLite 会话与事件存储
- daemon 到 Qt/QML 浮动壳层的实时订阅
- 重开后自动重新扫描正在运行的 Claude / Codex 会话
- 可拖拽且能记忆位置的浮动灵动岛
- Claude Code 与 Codex CLI 的 hook 接入
- Claude / Codex 核心审批与提问可在岛内完成
- 第三个选项支持在卡片内直接输入补充回复
- 乐观 UI 反馈，点击审批后卡片会尽快收起
- KDE Wayland / Konsole 下较可靠的 Jump 回原终端
- 紧急与完成事件的本地音效提示
- daemon 与 shell 中的 stuck detection
- shell 中的 Replay 时间线
- Quiet Mode 与 Focus Mode
- 面向任务的会话命名，同目录多开更容易区分
- 标题抽取优先保留真实任务意图，而不是 `agent-turn-complete` 这类运行噪音
- Codex 会话的任务意图记忆，不会被探测命令和完成提示污染
- 像 `Codex @ ...` 这样的通用回退标题不会再覆盖真实任务名
- Claude / Codex 的审批卡已经能显示 review 信息，包括命令、说明、风险和工作区提示
- 基于 Agent 本地工件恢复 live 标题已经成为当前主方向
- mini terminal peek 和 usage HUD 已进入正式产品方向，而不再只是“可选增强”
- Telegram bridge 设置现在会跨重启保留，而不再被当作一次性运行态配置
- 折叠态 notch 正在转向更小的 `sleeping` 闲置呈现，而不是总是硬塞一张压缩会话卡
- 展开态 shell 的几何尺寸现在应当作为用户偏好被持久化，重开时要以合理大小恢复，而不是继续向接近全屏的尺寸漂移
- 展开态 shell 正在转向支持用户直接用鼠标缩放，以适配不同桌面布局，同时不破坏内部信息层级
- 由于 Wayland 下 pin 仍受 compositor 策略影响，托盘召回现在已经成为正式支持的交互路径
- 统一启动器和桌面入口已经成为发布就绪的一部分，公开版用户不应该再手动分别启动 daemon 与 shell
- 首个 GitHub 公开版范围固定为 `vibeisland-linux` 本体；Claude + Codex 协作运行时继续作为本地 / 私有路线独立维护

当前只做到一部分的内容：

- KDE / Konsole / tmux 之外的终端 Jump 精准度
- 各种 ask-user / approval 边界场景覆盖
- 与原版 Mac 产品相比，UI 质感仍有差距
- 置顶行为仍部分受 compositor 限制，因此 pin 功能还需要“尽量保证 + 友好回退”两手准备
- 展开态 shell 仍需要更强的自适应头部压缩策略，以保证用户缩放后标题和状态 pill 不会互相重叠
- Claude / Codex 之外的多 Agent 覆盖
- 对非标准 transcript 和未来适配器的标题恢复还需要更深层解析

尚未交付：

- 完整 Markdown plan review
- 批量审批
- 完整 token / runtime / cost HUD
- 设置界面、托盘界面和高级通知设置
- Cursor / OpenCode / Droid / Gemini 的正式生产级适配

## 用户问题

当多个 Agent 并行运行时，用户很容易丢失以下上下文：

- 哪个 Agent 还在工作
- 哪个 Agent 正在等待审批
- 哪个 Agent 已经完成
- 哪个终端或 pane 对应哪个任务

单纯系统通知不够，因为通知本身不会保留会话上下文，也不提供可靠的回跳路径。

## 主要用户

- 大量使用 CLI 的 Linux AI 编程用户
- 使用 tmux 并同时跑多个 Agent 会话的用户
- 经常在编辑器、终端、浏览器之间切换的用户

## MVP 范围

### 目标平台

- Arch / EndeavourOS
- Wayland 优先
- KDE Plasma 优先
- X11 尽力兼容

### MVP 支持的 Agent

- Claude Code
- Codex CLI

### MVP 支持的状态

- running
- needs approval
- asks user a question
- completed
- failed
- stale

### MVP 支持的用户动作

- 在需要注意力时自动展开灵动岛
- 在一个面板里查看所有活跃会话
- 预览简短计划 / 状态摘要
- 播放事件音效
- 发出桌面通知
- 跳回最可能正确的终端 / 工作区
- 在岛内直接回答 Claude / Codex 支持的审批与提问

### 明确不属于 MVP 的内容

- 对 Mac 刘海形态做 1:1 完全复刻
- 第一天就支持所有 AI Agent
- 所有 Linux 终端模拟器都做到完美 Jump
- 所有未来 Agent / 终端组合都能做到完美岛内审批执行
- 云同步或远程账户体系

## Linux 版差异化功能

### 1. Attention Score

按紧急程度给会话排序，而不是只按最近更新时间排序。

输入信号包括：

- 被阻塞的时长
- 是否在等待审批
- 是否在等待用户输入
- 如果可获得，则参考 token 消耗速率
- 是否出现重复失败

### 2. Stuck Detection

识别那些看起来“卡住了”的会话。

信号包括：

- 心跳长时间没有更新
- 相同工具失败反复发生
- 一直在读文件但没有产出编辑
- 同一个计划步骤重复太多次

### 3. Replay Timeline

展示用户离开期间都发生了什么。

例如：

- 开始任务
- 编辑文件
- 请求审批
- 恢复执行
- 完成任务

### 4. Workspace Binding

将会话绑定到 repo、branch、cwd、terminal 和 tmux pane，以提升 Jump 准确率。

### 5. Quiet Hours / Focus Mode

仅在高优先级事件发生时自动展开，同时仍然统计后台状态变化。

### 6. Cost and Time HUD

在可用时显示紧凑的运行指标，例如：

- 时长
- token 数量
- 工具调用次数
- 距离上次活动的时间

### 7. Attention Aging

如果一个 blocked 或 waiting 会话一直没有被处理，它应该显著“老化”。

规则：

- 超过 30 秒变橙色
- 超过 75 秒变红色
- 折叠态和展开态都要显示这种老化提示

### 8. 基于工件的标题恢复

标题应该从本地 Agent 工件里恢复，而不是直接使用瞬时 hook 文本。

目标：

- 优先保留原始用户任务，而不是 probe command、runtime hook label 或模板化回复
- 即便同一会话后来发出了 `agent-turn-complete`、review 文本或命令探测，标题也要保持稳定
- 重开后使用 Codex 线程数据和 Claude session / project 工件恢复标题
- `Codex @ workspace` 之类的通用标题只能作为回退值使用

好标题示例：

- `Create 1.txt on Desktop`
- `Build Tetris game`
- `Build Snake game`
- `Fix auth bug`

### 9. Mini Terminal Peek

在岛内增加一个紧凑的终端 Peek 面板，用于快速追上下文和补发短指令。

目标：

- 保留 `Jump` 作为精准跳回动作
- 另加一个 mini terminal 图标，在岛内查看上下文并继续轻量任务
- 展示轻量 transcript 预览和一个小型输入框
- 不在岛内实现完整终端模拟器

### 10. Batch Approvals

把相似审批请求合并，减少频繁打断。

### 11. Plan Diff Review

当计划变化时，显示“变了什么”，而不是重新整段倾倒完整计划文本。

## 体验设计概要

### 折叠态

- 顶部居中的浮动胶囊
- 左侧负责传达状态
- 右侧直接显示当前最高优先级项目标题，无需展开即可知道在跑什么
- 深色背景上要保持高可读性，避免大面积刺眼黄底
- 只在重要事件时做轻微脉冲
- 折叠态要借鉴 `claude-island` 的精神：小、稳、信息密度高，而不是做成一个面板缩略图

### 折叠态优先级规则

- 若存在 blocked 会话，显示最老的 blocked 会话标题
- 否则若存在等待用户输入的会话，显示最老的未处理问题标题
- 否则显示最近活跃的 running 任务标题
- 如果没有高质量任务标题，再退回到 source + workspace 的紧凑标签

### 展开态

- 堆叠的会话卡片
- 每张卡展示标题、Agent 图标、状态、耗时和摘要
- 主动作是 Jump
- 次动作按能力暴露
- 每张卡都应有一个紧凑 terminal-peek 动作
- 审批和提问控件必须留在所属会话卡内
- 卡片布局应像高密度任务列表，而不是霓虹游戏面板

### 会话卡要求

- 标题必须表达用户任务，而不是 `agent-turn-complete`、审批 headline、probe command 这类运行噪音
- 长摘要必须在卡片内部安全换行或截断，不能溢出
- 审批控件必须和所属请求在同一张卡内
- 视觉密度应接近紧凑列表，而不是 oversized neon card
- 任务标签在整个会话生命周期内都应保持稳定，并在 daemon 只剩通用回退文本时从 Agent 本地工件恢复
- 如果 blocked 或 waiting 超过 30 秒，要变成橙色；超过 75 秒，要变成红色
- 折叠态也必须持续显示当前最高优先级任务名

### Attention Aging

- 超过 30 秒未处理：橙色
- 超过 75 秒未处理：红色
- 这一提示在折叠态和展开态都必须可见

### Usage HUD

- Claude 和 Codex 分开展示
- 若是订阅额度模式，则显示 5 小时和 7 天剩余额度百分比
- 若是 API key 计费模式，则显示本次灵动岛开启以来累计消耗的 token
- 如果拿不到可靠数据，必须诚实显示 `unavailable`
- 某供应商若本地无法暴露剩余额度，不要瞎猜

### Terminal Peek

- 每张卡保留 `Jump`
- 每张卡再增加一个紧凑终端图标动作
- 点击终端图标后，在岛内打开嵌入式 peek 面板
- Peek 面板展示最近相关 transcript 行，并支持短输入
- Peek 面板应该更小、更安静，更像 context drawer，而不是完整终端
- Peek 面板展示该会话最近 transcript / session 输出
- Peek 面板带一个紧凑输入框，用于快速 follow-up
- follow-up 优先走会话感知的直连路径，只有失败时才回退到终端注入

### 通知规则

- 遇到审批或 ask-user：立即展开
- 任务完成：轻度展开或脉冲提示
- 低信号的进度抖动默认保持静默，除非用户主动开启

## 技术方向

- daemon 核心使用 Rust
- 浮动壳层使用 Qt 6 / QML
- 使用本地 Unix socket 作为事件总线
- 使用 SQLite 做事件存储和会话缓存
- 每种 Agent 走各自适配器做归一化

更详细内容见 `docs/TECHNICAL_DESIGN.md`。

## 下一执行切片

下一轮应整体交付以下几项：

1. 基于工件的 live 会话身份恢复
2. 从真实 session 文件恢复任务标题，而不仅依赖 hook 事件
3. 参考紧凑 notch 的折叠态重做
4. 超时审批的橙 / 红提示
5. 分 Agent 的 usage HUD
6. 基于 transcript 的 terminal peek

## 交付阶段

### Phase 0：设计与搭建

- 编写 PRD
- 编写技术设计文档
- 定义事件 schema
- 定义仓库结构

### Phase 1：核心可观察性 MVP

- daemon
- Unix socket
- session store
- Claude adapter
- Codex adapter
- 最小浮动壳层
- 托盘 + 通知 + 音效

### Phase 2：更好的导航

- tmux provider
- kitty / wezterm provider
- workspace binding
- 更强的 stale detection

### Phase 3：更丰富的交互

- ask-user 回复 UI
- plan diff UI
- replay timeline
- attention scoring

### Phase 4：更多适配器

- Gemini CLI
- VS Code terminal 扩展
- 长尾终端集成

## 成功标准

- 用户能一眼看到所有活跃的 Claude / Codex 会话
- 被阻塞的会话在事件到达后 1 秒内变得可见
- 在常见工作流中，用户能跳回正确终端
- 空闲时资源占用保持轻量
- 系统保持完全本地化

## 关键风险

- Wayland overlay 行为在不同 compositor 上差异很大
- Linux 终端 Jump 精准度不一致
- 有些 Agent 客户端暴露稳定 hooks，有些没有
- “执行审批”远比“知道要审批”更难

## 推荐下一步

把项目从“核心原型可运行”推进到“每天能挂着用的 Linux 小工具”，优先级建议为：

- 在 Konsole 之外补更高置信度的 jump provider
- 审批前展示更丰富的 review 信息
- 更低噪声的 attention 管理
- 适合日常使用的 UI 和设置项打磨

## 下一轮执行计划

下一阶段应该优先追求日常可用性，而不是盲目扩展支持面。

### Iteration A：Daily Driver 第一阶段

优先顺序：

1. stuck detection
2. replay timeline
3. quiet mode

为什么这样排：

- 这三项最直接缓解“我不知道现在发生了什么”的问题
- 即使新适配器还没上线，它们也能先提升日常价值
- 它们都能建立在现有 daemon / session 模型上，架构风险较低

预期结果：

- 用户能分清哪些会话是真的在工作，哪些只是挂着
- 离开后能快速恢复上下文
- 灵动岛可以全天开着而不至于太吵

### Iteration B：审批前 Review

当前状态：

- Claude / Codex 的审批卡已经具备基础 review 数据

仍需加深：

- 更丰富的 plan diff 和文件影响摘要
- 更明确的“为什么现在向你请求审批”
- 覆盖更多长尾 prompt 形态和 Agent

### Iteration C：导航扩展

- 为 kitty、wezterm、VS Code、Cursor 添加更精准 jump provider
- 明确告诉用户这次 jump 是“精准命中”还是“尽力而为”

### Iteration D：产品打磨

- 更强的动画、音效、密度控制、设置界面和视觉精修

### Iteration E：单机 Shell 重构

- 从主 shell 交互中移除 `focus`，改用更清晰的 replay、settings、quiet 和 pin 控件
- 放大字体，进一步压平 shell / 列表的视觉语言，让它更贴近原始 Vibe Island 参考图
- 用像素动图 sprite 替换静态 provider 图标，并补上审批、完成、发送、折叠切换等多组 8-bit 音效
- 缩小折叠态 notch，让它更像“可一眼扫过”的状态条，而不是宽大的工具栏
- 加入可选的 Telegram Bot 远程审批与选项 3 文本回复能力
