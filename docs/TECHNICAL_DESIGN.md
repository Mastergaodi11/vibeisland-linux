# Vibe Island for Linux Technical Design

Chinese version: `docs/TECHNICAL_DESIGN.zh-CN.md`

Maintenance note: keep the English and Chinese editions in sync whenever this document changes.

## Verified Local Context

- workspace target: `/path/to/vibeisland-linux`
- OS: EndeavourOS (Arch-based)
- session type: Wayland
- desktop environment: KDE Plasma
- local Claude config exists at `~/.claude/settings.json`
- local Codex config exists at `~/.codex/config.toml`
- operator setup reference: `docs/INTEGRATION_SETUP.md`

## External Reference

The original public product page describes these core behaviors:

- monitor multiple agents in one view
- react to approvals and questions
- jump back to the correct terminal
- use a local Unix socket / local-only model

Source:

- https://vibeisland.app/
- https://github.com/farouqaldori/claude-island

`claude-island` is the closest public UI reference for this project. The most useful ideas to borrow are:

- a compact collapsed notch with one stable activity signal
- dense list rows instead of oversized dashboard cards
- restrained dark surfaces with semantic accents
- inline approvals and tiny secondary icon actions
- low-jitter layout with stable widths and heights

## Implemented Status

As of 2026-04-04, the Linux build already covers a meaningful subset of the intended design.

Implemented now:

- `vibeislandd` Rust daemon with Unix socket IPC
- SQLite-backed event and session persistence
- realtime snapshot subscription from daemon to shell
- live process re-scan so already-running Claude/Codex sessions reappear after reopen
- hook-based adapters for Claude Code and Codex CLI
- managed in-island approval handling for core Claude/Codex flows
- draggable Qt/QML floating shell with inline response cards
- optimistic response updates so approval cards clear quickly after click
- KDE Wayland / Konsole-friendly jump behavior with KWin + DBus fallback logic
- basic sound cues through system sound backends
- derived stuck detection in daemon snapshots and shell session health
- replay timeline surfaced from the event store into the shell
- quiet mode / focus mode presentation controls in the shell
- persisted per-terminal task labels so live re-scan can recover more useful task-first titles
- intent-priority title selection so operational hook labels and review headlines do not overwrite the underlying task goal
- Codex history-backed task intent recovery so `PreToolUse` / `notify` events can keep the original user task title during long-running work
- generic approval-response titles like `Codex @ ...` are treated as low-signal so they cannot poison persisted task labels or block later recovery
- review data attached to approval events and rendered in the shell
- live title recovery should now favor agent-local artifacts whenever a session is still running and the daemon only knows a generic runtime label
- usage HUD and terminal peek are now first-class product goals rather than future polish
- session list scroll position is preserved across realtime refreshes so browsing deep stacks does not snap back to the top
- manual collapse now overrides automatic expansion until the user explicitly re-expands the island
- shell preferences now persist across close/reopen without deleting Telegram bridge settings
- the collapsed notch is being refit around a narrower width and a dedicated idle/sleep presentation
- the expanded notch header is moving to a single-line task/status layout so pills and title do not overlap at user-sized widths
- prompt attention can now be configured as an explicit shell preference; when enabled, new approval states both expand and request foreground attention
- a tray-based summon path is being added because Wayland compositor policies may still override "always on top" in edge cases
- shell audio playback now prefers lightweight system audio players for bundled 8-bit cues, so startup should not depend on Qt multimedia hardware-decoder probing
- expanded shell geometry is moving from content-driven sizing to persisted and clamped window sizing with direct mouse resize affordances
- collapsed dragging is being widened to most of the notch body while explicit controls stay reserved for click actions
- a launcher layer in `tools/vibeisland.py` now owns daemon/socket/shell orchestration so public startup becomes one command plus an optional desktop entry
- public export is now an explicit build concern: the repo can remain a local superset, while `export-public` emits a collaboration-free `vibeisland-linux` tree for GitHub release

Partially implemented:

- tmux-aware jump metadata and tmux send-keys fallback
- generic app activation by PID / title / KWin window matching
- ask-user / approval coverage across varied prompt shapes
- richer review summaries beyond command/detail/risk/workspace hint
- artifact-backed live title recovery for reopened sessions
- terminal peek in the island with a short follow-up input path
- 30s orange and 75s red overdue escalation in both collapsed and expanded states

Not implemented yet:

- tray/settings surface
- full plan diff review
- batch approval grouping
- precision providers for kitty / wezterm / IDE terminals
- production adapters beyond Claude/Codex

## Current Gaps To Close Next

The main remaining correctness gap is live-session identity after reopen:

- hook events do not always carry a usable `tty`
- daemon live scan currently falls back to generic titles when it cannot reconnect a running process to prior task metadata
- shell display logic can recover some titles, but live process identity needs to come from session artifacts instead of only `tty`
- generic fallback titles should not stick when a more specific artifact-backed title is available

The next implementation slice therefore shifts to artifact-backed recovery.

## Architecture Summary

Use a two-process desktop architecture.

### 1. `vibeislandd`

Rust daemon responsible for:

- adapter intake
- event normalization
- session state machine
- SQLite persistence
- Unix socket / local API
- jump target registry
- notification policy
- sound event dispatch

### 2. `vibeisland-shell`

Qt 6 / QML floating shell responsible for:

- collapsed island UI
- expanded session panel
- user-resizable expanded floating window
- lightweight actions
- tray icon
- notification affordances
- animation and sound cues


## Why This Stack

### Rust daemon

- strong fit for long-running local system service
- good Unix socket, DBus, and process tooling
- easy to ship as a single native binary

### Qt 6 / QML shell

- best fit for polished animated floating surfaces
- strong KDE integration
- better Wayland desktop ergonomics than a web shell for this use case
- easier to do transparent, top-anchored, always-on-top UI

### Why not Tauri as the primary shell

Tauri is appealing for settings screens, but first-version floating overlay behavior on Wayland is more brittle than a native Qt shell. We can still revisit Tauri later for non-overlay tooling if needed.

## Display Strategy

### Wayland

- first try layer-shell-style top-center overlay behavior
- prefer non-activating presentation when possible
- avoid focus stealing

### X11 fallback

- borderless always-on-top transparent window
- same data contract, simpler presentation

## Component Map

### A. Adapters

Each agent gets its own adapter boundary.

Examples:

- `adapter-claude`
- `adapter-codex`
- later `adapter-gemini`

Adapter responsibilities:

- receive raw agent-specific signals
- map them to common schema
- attach session and jump metadata
- send normalized events to daemon

### B. Session Aggregator

Responsibilities:

- create and merge session records
- maintain latest state
- keep heartbeat timestamps
- mark sessions stale
- compute attention score

### C. Event Store

Use SQLite for:

- event log
- current session table
- jump target table
- replay timeline queries
- cached task identity records keyed by `source + tty`
- cached live-session artifact records keyed by `source + pid`

### D. Jump Providers

Separate provider layer for:

- tmux
- kitty
- wezterm
- VS Code extension bridge
- generic fallback provider

`Jump` should remain the precision action. `Peek` is a separate action and should not steal focus from the original terminal.

### E. Action Router

Receives user action from UI and decides whether it can:

- jump to target
- answer question
- approve or deny
- fall back to "open owning terminal"
- open a terminal peek drawer with transcript preview and short inline input

### F. Session Artifact Resolver

Add a resolver layer that can inspect live local process artifacts without waiting for fresh hook events.

Responsibilities:

- map a live Codex PID to its `.codex/sessions/...jsonl` transcript file via `/proc/<pid>/fd/*`
- map a live Claude PID to `~/.claude/sessions/<pid>.json`, then to the matching project transcript
- recover stable `backend_session_id`, transcript path, thread name, last user task, and usage metadata
- expose transcript-backed peek content for the shell
- recover Codex titles from `~/.codex/state_5.sqlite` when `cwd` matches but hook text is generic
- recover Claude titles from session/project artifacts and ignore boilerplate assistant replies

### G. Shell View-State Guard

The shell keeps a tiny local view-state layer outside daemon snapshots so operator intent survives rapid refresh cycles.

Responsibilities:

- remember `ListView.contentY` across session model updates
- restore scroll position after refresh and after a manual re-expand
- treat manual collapse as an explicit user preference and suppress automatic re-expansion until the user opens the island again

## Recommended Event Flow

1. agent emits a hook or wrapper event
2. adapter converts it to common schema
3. adapter sends event to `vibeislandd`
4. daemon updates session and persistence
5. daemon emits state change to shell
6. shell updates UI and optionally plays sound / shows notification

For reopened live sessions, the shell and daemon may also do a local artifact refresh:

1. discover live process
2. inspect process fd/session metadata
3. recover backend session id + transcript path + usage
4. derive stable task title from session artifact
5. merge artifact result into displayed session identity

If the daemon only has a generic runtime label, the shell should refresh from local artifacts before the row is rendered.

## Integration Strategy by Agent

### Claude Code

Current path:

- config injection + hooks
- managed approval wait inside `PreToolUse` for supported flows

Current notes:

- the island now resolves core approval decisions locally instead of depending on synthetic terminal input
- richer review surfaces and more prompt-shape coverage are still future work
- artifact-backed title recovery should be the default source of truth for live running sessions
- token usage should come from local agent artifacts when available

### Codex CLI

Current path:

- hook-based integration
- notify bridge
- managed approval flow using hook interception plus local decision state

Current notes:

- core approval flows now work from the island
- app-server and richer structured outputs remain promising future integration points
- live running Codex tasks should use transcript fd discovery to recover thread names and token/rate-limit data after reopen
- if Codex is using API-key billing, surface cumulative token usage since island launch rather than guessing quota
- `~/.codex/state_5.sqlite` is the most useful local title source when live Codex sessions have only generic runtime hooks

### Gemini CLI

Initial plan:

- wrapper-based adapter when added later

## Unified Session Schema

Use a versioned event model.

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

## UI Direction For This Slice

Borrow these patterns from the Claude Island reference and adapt them to Linux:

- compact dark capsule with restrained accent usage
- opened view behaves like a dense list, not oversized dashboard cards
- inline approval controls live inside the owning row
- small secondary icon actions sit to the right of the task row
- collapsed state shows current activity plus current project title in one line
- collapsed state should keep its text width stable so labels do not jitter as content changes
- the color system should stay mostly graphite and reserve color for state, not decoration

Linux adaptation notes:

- preserve drag-anywhere behavior because there is no physical notch constraint
- use transcript-backed peek instead of full chat rendering at first
- keep `Jump` as the precision action and add terminal-peek as the inline lightweight action
- add a compact terminal icon button next to `Jump`, and make that icon open the in-island peek drawer

## Usage Collection Plan

Claude usage:

- parse active project session `.jsonl` usage blocks for token totals
- consume Claude `statusLine` `rate_limits` snapshots for OAuth 5-hour / 7-day remaining quota when available
- fall back to transcript-based token totals when no recent `statusLine` snapshot exists

Codex:

- parse active session `.jsonl` `token_count` events
- show 5-hour / 7-day remaining percentages from `rate_limits`
- if running in API-key billing mode, fall back to cumulative token totals since island startup

Claude artifact usage:

- parse `message.usage` and recent project transcript artifacts for token totals
- surface the best available provider state as `available`, `unavailable`, or `api-key`

### Core event kinds

- `session_started`
- `session_heartbeat`
- `session_updated`
- `plan_updated`
- `needs_approval`
- `ask_user`
- `completed`
- `failed`
- `cancelled`

### Session states

- `running`
- `blocked`
- `waiting_user`
- `completed`
- `failed`
- `stale`

## Terminal Jump Strategy

Use capability tiers.

### Tier 1: precise

- tmux
- KDE Wayland / Konsole via KWin + DBus activation

### Tier 1.5: partially working today

- generic PID-based app activation
- tmux metadata capture and tmux send-keys fallback where available

### Tier 2: likely-correct

- generic terminal window activation by PID / cwd / title matching

### Tier 3: fallback

- open workspace
- reveal session metadata
- tell the user which terminal host to look at

## Approval Strategy

Current design choice:

Use explicit local decision state for supported Claude/Codex approval flows instead of relying on synthetic terminal input.

Reason:

- Linux terminals and Wayland input paths are inconsistent
- direct keyboard injection creates trust and permission friction
- hook-managed local decisions are more reliable where the agent exposes a safe interception point

Implication:

- supported approvals should resolve fully inside the island
- unsupported tools and future agents may still need fallback behavior until they expose a safe action channel

## Repository Layout Proposal

```text
docs/
  PRD.md
  TECHNICAL_DESIGN.md
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

## Subagent Execution Plan

Future implementation should be parallelized with subagents across disjoint ownership areas.

### Subagent 1: Core / Daemon

Owns:

- `crates/common`
- `crates/daemon`

Tasks:

- event schema
- local socket server
- session aggregator
- SQLite store

### Subagent 2: Shell / UX

Owns:

- `apps/shell`

Tasks:

- floating island shell
- card layout
- animations
- tray
- notifications
- sound wiring

### Subagent 3: Agent Adapters

Owns:

- `crates/adapter-claude`
- `crates/adapter-codex`
- `tools/launcher`

Tasks:

- hook config management
- wrapper launcher
- adapter event translation

### Subagent 4: Jump Integrations

Owns:

- `crates/jump-tmux`
- `crates/jump-kitty`
- future jump providers

Tasks:

- terminal mapping
- jump execution
- best-effort fallback logic

## Build Order

1. scaffold workspace and shared schema
2. implement daemon with test fixture ingestion
3. implement Claude and Codex adapters
4. implement minimal shell subscribed to mock events
5. connect real socket flow end to end
6. add tmux jump provider
7. add KDE-focused shell behavior polish

## Next Design Priorities

1. Review before approve

- show exact command, file diff summary, and risk reason inside the card
- make approval feel informed rather than blind

2. Navigation confidence

- ship dedicated kitty / wezterm / VS Code / Cursor jump providers
- surface jump confidence when the result is only best-effort

3. Attention quality

- add quiet mode, batching, and better prioritization so the island interrupts less often

4. Recovery and memory

- add replay timeline, session search, and stale/stuck detection

5. Daily-driver ergonomics

- settings UI, sound pack selection, density controls, per-tool rules, and stronger visual polish

6. Artifact-backed identity

- keep titles task-first even when runtime hooks become noisy
- recover `Build Snake game` / `Create 1.txt` style labels from local artifacts after reopen

7. Usage and aging

- show provider usage and make unattended approvals turn orange at 30s and red at 75s

## Hard Problems To Respect

- Wayland focus and overlay behavior
- unstable private agent internals
- mixed quality of terminal control APIs
- action safety for approvals

## Recommended Implementation Rule

Prefer reliable session visibility and jump accuracy over flashy cross-process control in the first release.

## Next Execution Slice

Implement the next slice in this order:

1. stuck detection
2. replay timeline
3. quiet mode

Reasoning:

- these capabilities improve attention quality and context recovery with the highest user impact per unit of implementation risk
- they reuse the existing daemon event store, session summaries, and shell subscription model
- they create a better base for later review-before-approve work because users can trust what the island is surfacing

Recommended technical shape:

- extend `SessionSummary` with derived attention metadata rather than inventing a second status system
- derive replay items from the persisted event log or session-local recent event cache
- treat quiet mode as presentation policy first, with optional future daemon-side notification policy

Exit criteria for this slice:

- a session can surface as stuck with an explicit reason instead of only appearing "running"
- users can see a short recent timeline in the shell without opening the terminal
- low-priority churn can be suppressed while urgent approvals still expand the island


## 2026-04-06 Shell Runtime Additions

- `WindowStaysOnTopHint` is now controlled by a shell-side `pinned` flag instead of being permanently enabled.
- Replay visibility is a persisted shell preference; the replay band defaults to expanded but can now collapse without disabling the timeline source.
- Terminal Peek now supports live preview overrides so the open peek panel can refresh from the latest local transcript without waiting for a full session-list rebuild.
- The shell now owns an optional Telegram bot loop:
  - stores bot token / paired chat id in shell prefs
  - polls `getUpdates`
  - sends inline approval keyboards for pending requests
  - supports an option-3 style follow-up by waiting for the user's next Telegram message
  - filters out collaboration/system noise and deduplicates unchanged approval prompts
  - resolves Telegram approval callbacks against the underlying managed approval request so Claude and Codex both survive session-id drift
- Audio playback now prefers local 8-bit wave assets and falls back to desktop sound/beep when needed.
- Pixel sprites are rendered as QML canvas-driven animated icons so the shell stays self-contained on Linux and does not depend on external GIF decoders.
