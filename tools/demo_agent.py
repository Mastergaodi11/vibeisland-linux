#!/usr/bin/env python
import sys
import time
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.vibeisland import make_event, publish_event


if __name__ == "__main__":
    timeline = [
        make_event(
            source="claude",
            session_id="claude-auth-fix",
            kind="session_started",
            state="running",
            title="Fix auth middleware",
            summary="Claude started digging into auth guards",
            terminal="tmux",
            tmux_session="work",
            tmux_window="1",
            tmux_pane="%2",
        ),
        make_event(
            source="codex",
            session_id="codex-ui-shell",
            kind="session_updated",
            state="running",
            title="Polish shell prototype",
            summary="Codex is shaping the floating shell",
            terminal="kitty",
            tmux_session="work",
            tmux_window="2",
            tmux_pane="%3",
        ),
        make_event(
            source="claude",
            session_id="claude-auth-fix",
            kind="needs_approval",
            state="blocked",
            title="Fix auth middleware",
            summary="Needs approval to edit src/auth/middleware.ts",
            terminal="tmux",
            approval_type="file_edit",
            tmux_session="work",
            tmux_window="1",
            tmux_pane="%2",
        ),
        make_event(
            source="codex",
            session_id="codex-ui-shell",
            kind="completed",
            state="completed",
            title="Polish shell prototype",
            summary="Prototype card stack finished",
            terminal="kitty",
            tmux_session="work",
            tmux_window="2",
            tmux_pane="%3",
        ),
    ]

    for item in timeline:
        print(publish_event(item))
        time.sleep(1.2)
