# Vibe Island for Linux PRD

Chinese version: `docs/PRD.zh-CN.md`

Maintenance note: keep the English and Chinese editions in sync whenever this document changes.

## Goal

Build a Linux-native "agent island" for vibe coding on Arch/EndeavourOS first, then expand to broader Linux desktops.

The product should let users:

- monitor multiple AI coding agents in one place
- know exactly when an agent is blocked, done, or asking a question
- jump back to the right terminal or workspace with minimal friction
- keep local-only data flow and low idle resource usage

This project is inspired by the original Vibe Island product and uses its public feature description as reference:

- official site: https://vibeisland.app/
- Claude Island reference repo: https://github.com/farouqaldori/claude-island

## Product Principles

- Local-first: all events, state, and actions stay on the machine
- Low interruption: surface only important moments by default
- Fast recovery: when attention is needed, bring the user back to the correct session quickly
- Linux-native: optimize for Wayland + KDE first, then degrade gracefully elsewhere
- Agent-agnostic core: adapters per tool, one unified session model

## Current Status Snapshot

As of 2026-04-05, the project is beyond the initial skeleton stage and is shifting from core plumbing to product polish and usability depth.

What works now:

- Rust daemon with local Unix socket and SQLite-backed session/event store
- realtime subscription from daemon to floating Qt/QML shell
- live process re-scan on reopen so already-running Claude/Codex sessions reappear
- draggable floating island with persistent position during runtime
- Claude Code and Codex CLI hook integration
- in-island approval / ask-user interaction for core Claude/Codex flows
- inline third-option follow-up text entry inside the session card
- optimistic UI response state so approval cards close quickly after click
- best-effort jump back to existing terminals, with KDE Wayland / Konsole working well
- local sound cues for urgent and completed events
- stuck detection surfaced in the daemon and shell
- replay timeline surfaced in the shell
- quiet mode and focus mode controls in the shell for lower-noise operation
- task-first session naming with persisted per-terminal labels, so same-directory sessions are easier to distinguish
- intent-first title extraction, so `agent-turn-complete` / review strings do not replace the actual task goal
- session intent memory for Codex, so runtime probe commands and completion notifications keep the original task title instead of replacing it
- generic fallback titles like `Codex @ ...` no longer overwrite a session's saved task intent after approvals or optimistic UI updates
- review-before-approve data surface for Claude/Codex approvals, including command, detail, risk, and workspace hint
- artifact-backed live title recovery is now the next priority, so titles come from agent-local session artifacts rather than noisy runtime labels
- terminal peek and usage HUD are now part of the product direction, not just nice-to-have extras
- Telegram bridge settings now persist across restarts instead of being treated like disposable runtime state
- the collapsed notch is moving toward a smaller "sleeping" idle presentation rather than always mirroring a full session card
- expanded shell geometry now needs to persist as a user preference and reopen at a clamped, reasonable size instead of stretching toward full screen
- the expanded shell is moving toward direct mouse resizing so users can tune it to their desktop layout without breaking the internal hierarchy
- tray summon is now part of the supported Wayland UX because pinning remains best-effort under compositor policy
- a unified launcher and desktop entry are now part of release-readiness, so public users should not need separate daemon and shell terminals
- the first public GitHub release is scoped to `vibeisland-linux` only; Claude+Codex collaboration runtime remains a separate local/private track

What is only partial today:

- terminal jump precision outside KDE / Konsole / tmux
- support for ask-user and approval edge cases across every tool and prompt shape
- UI fidelity compared with the original Mac app, even though the information hierarchy is now much improved
- always-on-top behavior is still partly compositor-dependent, so pinning needs best-effort engineering plus a graceful fallback story
- the expanded shell still needs adaptive header compaction so task titles and state pills stay readable across user-resized widths
- multi-agent coverage beyond Claude/Codex
- title recovery for every live session still needs deeper artifact parsing for nonstandard transcripts and future adapters

What is not shipped yet:

- full Markdown plan review
- batch approvals
- token / runtime / cost HUD
- settings UI, tray UI, and advanced notification controls
- Cursor / OpenCode / Droid / Gemini production adapters

## User Problems

When multiple agents are running in parallel, users lose track of:

- which agent is still working
- which agent is blocked on approval
- which agent already finished
- which terminal or pane belongs to which task

System notifications alone are not enough because they do not preserve session context or provide reliable return paths.

## Primary Users

- CLI-heavy AI coding users on Linux
- tmux users with parallel agent sessions
- users who switch frequently between editor, terminal, and browser

## MVP Scope

### Target platform

- Arch/EndeavourOS
- Wayland first
- KDE Plasma first
- X11 best-effort fallback

### Supported agents in MVP

- Claude Code
- Codex CLI

### Supported states in MVP

- running
- needs approval
- asks user a question
- completed
- failed
- stale

### Supported user actions in MVP

- expand island when attention is required
- see all active sessions in one panel
- preview short plan/status summary
- play event sound
- issue desktop notification
- jump back to the most likely terminal/workspace
- answer supported approval / ask-user prompts from the island for Claude/Codex

### Explicitly not in MVP

- perfect 1:1 Mac notch visual recreation
- full in-island approval execution for every future agent/terminal combination
- full support for all AI agents on day one
- perfect precision jump for every Linux terminal emulator
- cloud sync or remote accounts

## Differentiating Linux Features

These are good additions beyond the original concept and should be designed in from the start.

### 1. Attention Score

Rank sessions by urgency instead of simple recency.

Inputs:

- blocked duration
- whether approval is needed
- whether user input is needed
- token burn rate if available
- repeated failures

### 2. Stuck Detection

Detect sessions that appear trapped.

Signals:

- no heartbeat for too long
- repeated identical tool failures
- repeated reads with no edits
- same plan step repeated too many times

### 3. Replay Timeline

Show a short timeline of what happened while the user was away.

Examples:

- started task
- edited file
- requested approval
- resumed
- completed

### 4. Workspace Binding

Bind sessions to repo, branch, cwd, terminal, and tmux pane for better jump accuracy.

### 5. Quiet Hours / Focus Mode

Only expand for high-priority events while still counting background state changes.

### 6. Cost and Time HUD

Show compact runtime metrics where available.

Examples:

- duration
- token count
- tool calls
- last activity age

### 7. Attention Aging

If a blocked or waiting session goes unanswered, it should visibly age.

Rules:

- after 30 seconds, warn in orange
- after 75 seconds, escalate to red
- show the aging cue in both collapsed and expanded states

### 8. Artifact-Backed Title Recovery

Recover the user-task title from local agent artifacts, not from transient hook text.

Goals:

- prefer the original user task over probe commands, runtime hook labels, and boilerplate replies
- keep a stable title even if the same session emits `agent-turn-complete`, review text, or command probes later
- use Codex thread data and Claude session/project artifacts to recover titles after reopen
- treat generic labels like `Codex @ workspace` as fallback-only values

Examples of good titles:

- `Create 1.txt on Desktop`
- `Build Tetris game`
- `Build Snake game`
- `Fix auth bug`

### 9. Mini Terminal Peek

Add a compact in-island peek surface for fast follow-up work.

Goals:

- keep `Jump` for exact terminal focus
- add a mini terminal icon action for in-island context viewing and short task continuation
- show a lightweight transcript preview and a small input composer
- avoid building a full terminal emulator in the island itself

### 10. Batch Approvals

Group similar requests to reduce interruption frequency.

### 11. Plan Diff Review

When plan text changes, show what changed instead of dumping the whole plan again.

## UX Outline

### Collapsed state

- top-center floating capsule
- left side should communicate state at a glance
- right side should show the current highest-priority project title without opening the island
- chip palette must stay legible on dark backgrounds and avoid high-glare yellow fills
- pulse only for important events
- collapsed state should borrow the spirit of `claude-island`: small, stable, information-dense, and not dashboard-like

### Collapsed state priority rules

- if any session is blocked, show the oldest blocked session title
- else if any session is waiting for user input, show the oldest unattended question title
- else show the most recently active running task title
- if no useful task title is available, fall back to a compact source + workspace label

### Expanded state

- stacked session cards
- per-card title, agent icon, state, elapsed time, short summary
- primary action is Jump
- secondary actions depend on capability
- each card should also expose a compact terminal-peek action
- approval or question controls should stay inside the owning session card
- card layout should look like a compact list row, not a neon game panel

### Session card requirements

- card title must represent the user task, not runtime noise such as `agent-turn-complete`, approval headlines, or probe commands
- long summaries must wrap or truncate inside the card bounds with no overlap
- approval controls should live inside the same card that owns the request
- visual density should resemble a compact list, not large neon game cards
- task labels should stay stable across the life of the session and should recover from agent-local artifacts when the daemon has only generic fallback text
- when a session goes unanswered for more than 30 seconds it should become orange, and after 75 seconds it should become red
- the collapsed island should continue to surface the top-priority task name without requiring expansion

### Attention aging

- if a blocked or waiting session remains unanswered for more than 30 seconds, mark it orange
- if it remains unanswered for more than 75 seconds, mark it red
- the aging cue must be visible in both collapsed and expanded states

### Usage HUD

- show Claude and Codex separately
- for subscription-backed sessions, show 5-hour and 7-day remaining percentages when available
- for API-key backed sessions, show the total token usage accumulated since the island was opened
- missing provider data should degrade gracefully to `unavailable` instead of lying
- if a provider cannot expose a reliable quota number locally, the UI should say `unavailable` instead of guessing

### Terminal peek

- each session card keeps `Jump`
- each session card also gets a compact terminal icon action
- terminal icon opens an embedded peek panel inside the island
- the peek panel should show recent useful transcript lines and support a short follow-up input
- the peek panel should be smaller and calmer than the main session card, closer to a quick context drawer than a full terminal
- the peek panel shows recent transcript / session output for that session
- the peek panel includes a compact input field for quick follow-up prompts
- quick follow-up should prefer direct session-aware delivery, then best-effort terminal injection only as fallback

### Notification rules

- expand immediately for approval or ask-user
- soft expand or pulse for completion
- stay silent for low-signal progress churn unless user opts in

## Technical Direction

- daemon core in Rust
- floating shell in Qt 6 / QML
- local Unix socket as event bus
- SQLite event store and session cache
- per-agent adapters for normalization

More detail lives in `docs/TECHNICAL_DESIGN.md`.

## Next Execution Slice

The next slice should ship these items together:

1. artifact-backed live session identity
2. task-title recovery from real session files, not only hook events
3. collapsed-state redesign based on compact notch references
4. overdue approval coloring
5. per-agent usage HUD
6. transcript-backed terminal peek panel

## Delivery Phases

### Phase 0: Design and scaffolding

- write PRD
- write technical design
- define event schema
- define repo layout

### Phase 1: Core observability MVP

- daemon
- Unix socket
- session store
- Claude adapter
- Codex adapter
- minimal floating shell
- tray + notification + sound

### Phase 2: Better navigation

- tmux provider
- kitty / wezterm providers
- workspace binding
- stronger stale detection

### Phase 3: Rich interactions

- ask-user response UI
- plan diff UI
- replay timeline
- attention scoring

### Phase 4: More adapters

- Gemini CLI
- VS Code terminal extension
- long-tail terminal integrations

## Success Criteria

- user can see all active Claude/Codex sessions at a glance
- blocked sessions become visible within 1 second of event arrival
- user can jump back to the right terminal in common workflows
- idle footprint remains lightweight
- the system remains fully local-only

## Key Risks

- Wayland overlay behavior varies by compositor
- terminal jump precision is uneven across Linux terminals
- some agent clients expose stable hooks, some do not
- approval execution is much harder than approval awareness

## Recommended Next Step

Move from "core working prototype" to "daily-driver Linux utility" by prioritizing:

- higher-confidence jump providers beyond Konsole
- richer review surfaces before approval
- lower-noise attention management
- UI polish and settings for everyday use

## Next Execution Plan

The next implementation sequence should optimize for daily usefulness first, not breadth.

### Iteration A: Daily Driver Phase 1

Priority order:

1. stuck detection
2. replay timeline
3. quiet mode

Why this order:

- these three features directly reduce the "I lost track of what is happening" problem
- they improve everyday value even before more agent adapters ship
- they build on the current daemon/session model with relatively low architecture risk

Expected user outcome:

- users can tell which sessions are truly active versus merely lingering
- users can recover context after stepping away
- users can keep the island visible all day without it becoming noisy

### Iteration B: Review Before Approve

Status:

- core review data is now present in approval cards for Claude/Codex

Still to deepen:

- richer plan diff and file impact summaries
- clearer trust cues for why the agent is asking now
- broader coverage for long-tail prompt shapes and agents

### Iteration C: Navigation Expansion

- add more precise jump providers for kitty, wezterm, VS Code, and Cursor
- expose whether a jump is exact or best-effort

### Iteration D: Product Polish

- stronger motion, sound, density controls, settings surface, and visual refinement

### Iteration E: Solo Shell Refresh

- remove `focus` from the main shell surface and replace it with clearer replay, settings, quiet, and pin controls
- enlarge typography and flatten the shell/list visual language so it reads closer to the original Vibe Island references
- replace static provider icons with animated pixel sprites and add multiple 8-bit sound cues for approvals, completion, send, and shell toggles
- shrink the collapsed notch so it acts like a glanceable status strip rather than a wide toolbar
- add optional Telegram bot routing for remote approvals and option-3 text replies
