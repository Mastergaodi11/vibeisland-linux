import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_FFMPEG_DECODING_HW_DEVICE_TYPES", "")

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot, QUrl
from PyQt6.QtGui import QAction, QGuiApplication, QIcon, QPainter, QPixmap, QColor
from PyQt6.QtQml import QQmlApplicationEngine
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

try:
    from apps.shell.collab_adapter import collaboration_raw_sessions as _collaboration_raw_sessions
except Exception:
    def _collaboration_raw_sessions() -> list[dict[str, Any]]:
        return []


def collaboration_raw_sessions() -> list[dict[str, Any]]:
    flag = str(os.environ.get("VIBEISLAND_ENABLE_COLLAB", "") or "").strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return []
    return _collaboration_raw_sessions()


ROOT = Path(__file__).resolve().parent
DEFAULT_SOCKET = os.environ.get("VIBEISLAND_SOCKET", "/tmp/vibeisland.sock")
DEFAULT_STATE = ROOT / "sample_snapshot.json"
DEFAULT_PREFS = Path.home() / ".config" / "vibeisland-shell" / "state.json"
SOUND_ASSET_DIR = ROOT / "assets" / "sounds"
APPROVAL_REQUESTS_DIR = Path.home() / ".local" / "state" / "vibeisland" / "approval_requests"
TOOLS_BRIDGE = ROOT.parent.parent / "tools" / "vibeisland.py"
COLLAB_BRIDGE = ROOT.parent.parent / "tools" / "agent_collab.py"
CODEX_STATE_DB = Path.home() / ".codex" / "state_5.sqlite"
CODEX_SESSIONS_DIR = Path.home() / ".codex" / "sessions"
CODEX_HISTORY_PATH = Path.home() / ".codex" / "history.jsonl"
CODEX_SESSION_INDEX_PATH = Path.home() / ".codex" / "session_index.jsonl"
CLAUDE_SESSIONS_DIR = Path.home() / ".claude" / "sessions"
CLAUDE_STATUSLINE_PATH = Path.home() / ".local" / "state" / "vibeisland" / "claude_statusline.json"
CODEX_AUTH_PATH = Path.home() / ".codex" / "auth.json"
CLAUDE_HISTORY_PATH = Path.home() / ".claude" / "history.jsonl"
CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
CODEX_SESSION_PATH_RE = re.compile(r"([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")
URL_RE = re.compile(r"https?://([^/\s`]+)")
COMMAND_INTENT_RE = re.compile(
    r"(?is)(?:use\s+bash\s+to\s+run(?:\s+command)?|run(?:\s+the)?(?:\s+bash)?\s+command|execute(?:\s+the)?\s+command|bash(?:\s+to\s+run)?(?:\s+command)?|shell(?:\s+command)?(?:\s+to\s+run)?)\s+(.+)"
)
BOILERPLATE_REPLY_HINTS = (
    "i'm ready to help",
    "im ready to help",
    "i’m ready to help",
    "i'll run that",
    "i’ll run that",
    "i will run that",
    "i can help with that",
    "i can help",
    "i see you've provided",
    "i see you’ve provided",
    "i see you have provided",
    "what would you like me to help with",
    "what would you like me to do",
    "please clarify what you'd like me to do",
    "please clarify what you’d like me to do",
    "let me know what you'd like",
    "let me know what you’d like",
    "i don't see a specific task",
    "i do not see a specific task",
    "agent-turn-complete",
    "command execution review",
    "network access review",
    "workspace write review",
    "read-only review",
    "review before approve",
    "task review",
    "question to answer",
)
FILE_PATH_RE = re.compile(
    r"([A-Za-z0-9_\-./\u4e00-\u9fff]+(?:\.[A-Za-z0-9]{1,8}))"
)
NAMED_FILE_RE = re.compile(
    r"名为\s*[\"“]?([A-Za-z0-9_\-\u4e00-\u9fff]+?)[\"”]?\s*(?:的)?\s*"
    r"(txt|md|json|yaml|yml|toml|py|js|ts|tsx|jsx|html|css|csv|ini|conf|sh|rs|cpp|c|h|hpp|java|kt|go|php|rb|swift)\s*文件",
    re.I,
)
LOW_SIGNAL_LABEL_PREFIXES = (
    "agent-turn-complete",
    "command execution review",
    "network access review",
    "workspace write review",
    "read-only review",
    "review before approve",
    "task review",
    "question to answer",
    "sessionstart hook",
    "userpromptsubmit hook",
    "pretooluse hook",
    "posttooluse hook",
    "stop hook",
)
COMMAND_PROGRAM_ALIASES = {
    "bash": "Run shell command",
    "sh": "Run shell command",
    "zsh": "Run shell command",
    "curl": "Fetch",
    "wget": "Fetch",
    "git": "Run git",
    "npm": "Run npm",
    "pnpm": "Run pnpm",
    "yarn": "Run yarn",
    "python": "Run Python",
    "python3": "Run Python",
    "uv": "Run uv",
    "make": "Run make",
}
OPERATIONAL_LABEL_PREFIXES = (
    "pwd",
    "pwd &&",
    "ls",
    "ls -",
    "find ",
    "rg --files",
    "command -v ",
    "which ",
    "test -f ",
    "test -e ",
    "sed -n ",
    "cat progress.md",
    "cat skill.md",
    "read skill.md",
    "read progress.md",
    "explored",
    "list ",
    "ran pwd",
    "ran ls",
    "ran find ",
    "ran command -v ",
    "ran test -f ",
    "node -v",
    "npm -v",
    "pnpm -v",
)
_LOCAL_SESSION_CACHE: dict[str, Any] = {"expires_at": 0.0, "codex": [], "claude": []}
USAGE_REFRESH_INTERVAL_SECONDS = 4.0
TELEGRAM_POLL_INTERVAL_SECONDS = 2.2
TELEGRAM_NOTIFICATION_COOLDOWN_SECONDS = 30.0
PREVIEW_NOISE_HINTS = (
    "<local-command-caveat>",
    "codex-companion.mjs",
    "setup --json",
    "running sessionstart hook",
    "running userpromptsubmit hook",
    "running pretooluse hook",
    "running posttooluse hook",
    "sessionstart hook (completed)",
    "userpromptsubmit hook (completed)",
    "pretooluse hook (completed)",
    "posttooluse hook (completed)",
    "claude needs your permission to use bash",
    "needs your permission to use bash",
    "press up to edit queued messages",
    "esc to interrupt",
)

EXPANDED_DEFAULT_WIDTH = 728
EXPANDED_DEFAULT_HEIGHT = 628
EXPANDED_MIN_WIDTH = 600
EXPANDED_MIN_HEIGHT = 420
EXPANDED_MAX_WIDTH = 960
EXPANDED_MAX_HEIGHT = 820
COLLAPSED_DEFAULT_WIDTH = 304
COLLAPSED_MIN_WIDTH = 284
COLLAPSED_MAX_WIDTH = 320


def age_label(updated_at: str) -> str:
    from datetime import datetime, timezone

    try:
        normalized = updated_at.replace("Z", "+00:00")
        stamp = datetime.fromisoformat(normalized)
        now = datetime.now(timezone.utc)
        delta = now - stamp.astimezone(timezone.utc)
        seconds = max(int(delta.total_seconds()), 0)
    except Exception:
        return "now"

    if seconds >= 3600:
        return f"{seconds // 3600}h"
    if seconds >= 60:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def age_seconds(updated_at: str) -> int | None:
    from datetime import datetime, timezone

    try:
        normalized = updated_at.replace("Z", "+00:00")
        stamp = datetime.fromisoformat(normalized)
        now = datetime.now(timezone.utc)
        delta = now - stamp.astimezone(timezone.utc)
        return max(int(delta.total_seconds()), 0)
    except Exception:
        return None


def parse_iso_timestamp(value: str | None) -> float | None:
    from datetime import datetime, timezone

    text = normalize_text(value)
    if not text:
        return None
    try:
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return stamp.astimezone(timezone.utc).timestamp()
    except Exception:
        return None


def read_recent_jsonl(path: Path, limit: int = 200) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    items: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    continue
                if isinstance(payload, dict):
                    items.append(payload)
    except Exception:
        return []
    if limit <= 0 or len(items) <= limit:
        return items
    return items[-limit:]


def resolve_collab_bridge_command() -> list[str] | None:
    override = normalize_text(os.environ.get("VIBE_COLLAB_BIN"))
    candidates: list[list[str]] = []
    if override:
        candidates.append(shlex.split(override))
    which_collab = shutil.which("vibe-collab")
    if which_collab:
        candidates.append([which_collab])
    if COLLAB_BRIDGE.exists():
        candidates.append([sys.executable, str(COLLAB_BRIDGE)])
    for candidate in candidates:
        if not candidate:
            continue
        executable = candidate[0]
        if executable == sys.executable:
            return candidate
        if Path(executable).exists() or shutil.which(executable):
            return candidate
    return None


def timeline_label_for_kind(kind: str) -> str:
    normalized = str(kind or "").strip().lower()
    mapping = {
        "needs_approval": "Approval needed",
        "session_updated": "Updated",
        "completed": "Completed",
        "failed": "Failed",
        "ask_user": "Question",
        "stale": "Stale",
        "stuck": "Stuck",
        "started": "Started",
        "resumed": "Resumed",
        "approval": "Approval needed",
    }
    return mapping.get(normalized, normalized.replace("_", " ").title() or "Update")


def timeline_accent_for_kind(kind: str) -> str:
    normalized = str(kind or "").strip().lower()
    if normalized in {"needs_approval", "approval", "failed", "stale"}:
        return "#ff8e9d"
    if normalized in {"completed"}:
        return "#8ef8cb"
    if normalized in {"stuck"}:
        return "#ff9c71"
    return "#7dd8ff"


def fallback_response_choices(source: str, approval_type: str, summary: str) -> list[str]:
    lowered_source = str(source or "").strip().lower()
    lowered_summary = str(summary or "").strip().lower()
    lowered_approval = str(approval_type or "").strip().lower()

    if lowered_source == "claude":
        if lowered_approval == "bash" or "bash" in lowered_summary:
            return [
                "Yes",
                "Yes, and don't ask again for Bash",
                "No, tell Claude what to do differently",
            ]
        return [
            "Allow once",
            "Allow for this Claude session",
            "No, tell Claude what to do differently",
        ]

    if lowered_source == "codex":
        return [
            "Yes, proceed",
            "Yes, and don't ask again",
            "No, tell Codex what to do differently",
        ]

    return []


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text


def truncate(value: Any, limit: int = 88) -> str:
    text = normalize_text(value)
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)].rstrip() + "…"


def first_text(*values: Any) -> str:
    for value in values:
        text = normalize_text(value)
        if text:
            return text
    return ""


def workspace_name(path_value: str | None) -> str:
    text = normalize_text(path_value)
    if not text:
        return ""
    name = Path(text).name
    return name or text


def match_workspace_path(candidate: str | None, cwd: str | None) -> bool:
    left = normalize_text(candidate)
    right = normalize_text(cwd)
    if not left or not right:
        return False
    if left == right:
        return True
    try:
        return Path(left).resolve() == Path(right).resolve()
    except Exception:
        return left == right


def read_json_file_maybe(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def percent_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return max(0, min(100, int(round(float(value)))))
    except Exception:
        return None


def rate_limit_window(rate_limits: dict[str, Any], kind: str) -> dict[str, Any]:
    if not isinstance(rate_limits, dict):
        return {}

    normalized_map: dict[str, dict[str, Any]] = {}
    for key, value in rate_limits.items():
        if not isinstance(value, dict):
            continue
        normalized_key = str(key).strip().lower().replace("-", "").replace("_", "")
        normalized_map[normalized_key] = value

    if kind == "5h":
        candidates = ("primary", "fivehour", "5h", "shortterm", "hourly")
    else:
        candidates = ("secondary", "sevenday", "7d", "longterm", "weekly")

    for candidate in candidates:
        value = normalized_map.get(candidate)
        if value:
            return value

    for normalized_key, value in normalized_map.items():
        if kind == "5h" and ("5" in normalized_key or "five" in normalized_key or "hour" in normalized_key):
            return value
        if kind == "7d" and ("7" in normalized_key or "seven" in normalized_key or "week" in normalized_key or "day" in normalized_key):
            return value

    return {}


def remaining_percent_from_window(window: dict[str, Any]) -> int | None:
    if not isinstance(window, dict):
        return None
    for key in ("remaining_percentage", "remaining_percent", "remainingPercent"):
        value = percent_int(window.get(key))
        if value is not None:
            return value
    for key in ("used_percentage", "used_percent", "usedPercent", "utilization", "percentage"):
        value = percent_int(window.get(key))
        if value is not None:
            return max(0, 100 - value)
    return None


def load_claude_statusline_snapshot() -> dict[str, Any]:
    snapshot = read_json_file_maybe(CLAUDE_STATUSLINE_PATH)
    if not snapshot:
        return {}
    updated_at = parse_iso_timestamp(str(snapshot.get("updated_at") or ""))
    if updated_at is not None and (time.time() - updated_at) > 14 * 24 * 3600:
        return {}
    return snapshot


def append_preview_line(lines: list[str], text: str | None, *, prefix: str = "", limit: int = 132) -> None:
    content = normalize_text(text)
    if not content:
        return
    if is_boilerplate_reply(content):
        return
    lowered = content.lower()
    if any(hint in lowered for hint in PREVIEW_NOISE_HINTS):
        return
    value = truncate(f"{prefix}{content}" if prefix else content, limit)
    if value not in lines:
        lines.append(value)


def is_preview_noise(text: str | None) -> bool:
    content = normalize_text(text).lower()
    if not content:
        return True
    if is_boilerplate_reply(content):
        return True
    return any(hint in content for hint in PREVIEW_NOISE_HINTS)


def recent_meaningful_lines(lines: list[str] | None, limit: int = 6) -> list[str]:
    ordered: list[str] = []
    for item in lines or []:
        text = truncate(item, 132)
        if not text or is_preview_noise(text):
            continue
        if text not in ordered:
            ordered.append(text)
    if limit > 0 and len(ordered) > limit:
        return ordered[-limit:]
    return ordered


def read_proc_fd_targets(pid: int | None) -> list[str]:
    if not pid:
        return []
    fd_dir = Path("/proc") / str(int(pid)) / "fd"
    if not fd_dir.exists():
        return []
    targets: list[str] = []
    try:
        for entry in fd_dir.iterdir():
            try:
                target = os.readlink(entry)
            except Exception:
                continue
            if target:
                targets.append(target)
    except Exception:
        return []
    return targets


def extract_session_id_from_path(path_value: str | None) -> str:
    text = normalize_text(path_value)
    if not text:
        return ""
    match = re.search(r"([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})", text, re.I)
    return normalize_text(match.group(1)) if match else ""


def extract_live_process_pid(session_id: str | None) -> int | None:
    text = normalize_text(session_id)
    match = re.match(r"live::[a-z0-9_]+::(\d+)$", text, re.I)
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def find_codex_session_file_for_pid(pid: int | None) -> Path | None:
    for target in read_proc_fd_targets(pid):
        if "/.codex/sessions/" not in target or not target.endswith(".jsonl"):
            continue
        path = Path(target)
        if path.exists():
            return path
    return None


def find_claude_session_meta_for_pid(pid: int | None) -> dict[str, Any]:
    if not pid:
        return {}
    return read_json_file_maybe(CLAUDE_SESSIONS_DIR / f"{int(pid)}.json")


def find_claude_project_file(session_id: str | None) -> Path | None:
    normalized = normalize_text(session_id)
    if not normalized or not CLAUDE_PROJECTS_DIR.exists():
        return None
    matches = sorted(
        CLAUDE_PROJECTS_DIR.rglob(f"{normalized}.jsonl"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return matches[0] if matches else None


def load_codex_thread_row(*, session_id: str | None = None, cwd: str | None = None) -> dict[str, Any]:
    if not CODEX_STATE_DB.exists():
        return {}

    normalized_session_id = normalize_text(session_id)
    normalized_cwd = normalize_text(cwd)
    try:
        with sqlite3.connect(CODEX_STATE_DB) as connection:
            connection.row_factory = sqlite3.Row
            if normalized_session_id:
                row = connection.execute(
                    """
                    SELECT id, cwd, title, first_user_message, updated_at, tokens_used
                    FROM threads
                    WHERE id = ?
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (normalized_session_id,),
                ).fetchone()
                if row:
                    return dict(row)
            if normalized_cwd:
                row = connection.execute(
                    """
                    SELECT id, cwd, title, first_user_message, updated_at, tokens_used
                    FROM threads
                    WHERE cwd = ?
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (normalized_cwd,),
                ).fetchone()
                if row:
                    return dict(row)
    except Exception:
        return {}
    return {}


def codex_preview_from_session_file(path: Path | None) -> tuple[list[str], dict[str, Any]]:
    if path is None or not path.exists():
        return [], {}

    items = read_recent_jsonl(path, limit=320)
    lines: list[str] = []
    rate_limits: dict[str, Any] = {}

    for item in items:
        item_type = normalize_text(item.get("type"))
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}

        if item_type == "user_input":
            append_preview_line(lines, payload.get("text") or payload.get("content"), prefix="You: ")
            continue

        if item_type == "assistant_message":
            append_preview_line(lines, payload.get("text") or payload.get("content"))
            continue

        if item_type == "event_msg":
            payload_type = normalize_text(payload.get("type"))
            if payload_type == "token_count" and isinstance(payload.get("rate_limits"), dict):
                rate_limits = payload.get("rate_limits")
            elif payload_type == "agent_message":
                append_preview_line(lines, payload.get("message"))
            elif payload_type == "exec_command_end":
                command = payload.get("command")
                if isinstance(command, list):
                    append_preview_line(lines, " ".join(str(part) for part in command[:6]), prefix="$ ")
            continue

        if item_type == "response_item":
            response_payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            if normalize_text(response_payload.get("type")) != "message":
                continue
            for block in response_payload.get("content") or []:
                if not isinstance(block, dict):
                    continue
                append_preview_line(
                    lines,
                    block.get("text") or block.get("output_text"),
                )

    return recent_meaningful_lines(lines, limit=6), rate_limits


def codex_rate_limit_candidates_from_session_file(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []

    items = read_recent_jsonl(path, limit=320)
    candidates: list[dict[str, Any]] = []
    file_mtime = path.stat().st_mtime

    for item in items:
        item_type = normalize_text(item.get("type"))
        if item_type != "event_msg":
            continue
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        if normalize_text(payload.get("type")) != "token_count":
            continue
        rate_limits = payload.get("rate_limits") if isinstance(payload.get("rate_limits"), dict) else {}
        if not rate_limits:
            continue
        candidates.append(
            {
                "timestamp": parse_iso_timestamp(item.get("timestamp")) or file_mtime,
                "file_mtime": file_mtime,
                "rate_limits": rate_limits,
                "limit_id": normalize_text(rate_limits.get("limit_id")).lower(),
                "has_primary": bool(rate_limits.get("primary")),
                "has_secondary": bool(rate_limits.get("secondary")),
                "path": str(path),
            }
        )

    return candidates


def freshest_codex_rate_limits(active_records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    candidate_paths: list[Path] = []
    seen_paths: set[str] = set()

    def add_path(path_text: str | None) -> None:
        path_str = normalize_text(path_text)
        if not path_str or path_str in seen_paths:
            return
        path = Path(path_str)
        if not path.exists():
            return
        seen_paths.add(path_str)
        candidate_paths.append(path)

    for record in active_records or []:
        add_path(record.get("transcript_path"))

    if CODEX_SESSIONS_DIR.exists():
        for path in sorted(CODEX_SESSIONS_DIR.rglob("*.jsonl"), key=lambda item: item.stat().st_mtime, reverse=True)[:24]:
            add_path(str(path))

    generic_candidates: list[dict[str, Any]] = []
    fallback_candidates: list[dict[str, Any]] = []

    for path in candidate_paths:
        for candidate in codex_rate_limit_candidates_from_session_file(path):
            if candidate.get("limit_id") == "codex":
                generic_candidates.append(candidate)
            elif candidate.get("has_primary") or candidate.get("has_secondary"):
                fallback_candidates.append(candidate)

    if generic_candidates:
        generic_candidates.sort(
            key=lambda item: (
                item.get("timestamp", 0.0),
                item.get("file_mtime", 0.0),
            ),
            reverse=True,
        )
        return generic_candidates[0].get("rate_limits") or {}
    if fallback_candidates:
        fallback_candidates.sort(
            key=lambda item: (
                1 if item.get("has_primary") else 0,
                1 if item.get("has_secondary") else 0,
                item.get("timestamp", 0.0),
                item.get("file_mtime", 0.0),
            ),
            reverse=True,
        )
        return fallback_candidates[0].get("rate_limits") or {}
    return {}


def load_live_codex_context(pid: int | None, cwd: str | None) -> dict[str, Any]:
    session_path = find_codex_session_file_for_pid(pid)
    session_id = extract_session_id_from_path(str(session_path)) if session_path else ""
    thread_row = load_codex_thread_row(session_id=session_id, cwd=cwd)
    if not thread_row and not session_path:
        return {}

    preview_lines, rate_limits = codex_preview_from_session_file(session_path)
    prompt = first_text(
        thread_row.get("first_user_message") if thread_row else "",
        thread_row.get("title") if thread_row else "",
    )
    label_seed = first_text(
        thread_row.get("first_user_message") if thread_row else "",
        thread_row.get("title") if thread_row else "",
        prompt,
    )
    label = normalize_task_label_candidate(label_seed) or truncate(label_seed, 52)

    return {
        "session_id": first_text(thread_row.get("id") if thread_row else "", session_id),
        "cwd": first_text(thread_row.get("cwd") if thread_row else "", cwd),
        "prompt": prompt,
        "thread_name": normalize_text(thread_row.get("title") if thread_row else ""),
        "label": label,
        "preview_lines": recent_meaningful_lines(preview_lines or ([truncate(prompt, 120)] if prompt else []), limit=6),
        "rate_limits": rate_limits or {},
        "tokens_total": int(thread_row.get("tokens_used") or 0) if thread_row else 0,
        "mtime": session_path.stat().st_mtime if session_path and session_path.exists() else 0.0,
        "transcript_path": str(session_path) if session_path else "",
    }


def claude_preview_from_project_file(path: Path | None) -> tuple[list[str], int, int, int]:
    if path is None or not path.exists():
        return [], 0, 0, 0

    items = read_recent_jsonl(path, limit=240)
    lines: list[str] = []
    tokens_5h = 0
    tokens_7d = 0
    tokens_total = 0
    now = time.time()

    for item in items:
        message = item.get("message") if isinstance(item.get("message"), dict) else {}
        usage = message.get("usage") if isinstance(message.get("usage"), dict) else {}
        total_tokens = (
            int(usage.get("input_tokens") or 0)
            + int(usage.get("output_tokens") or 0)
            + int(usage.get("cache_creation_input_tokens") or 0)
            + int(usage.get("cache_read_input_tokens") or 0)
        )
        if total_tokens:
            tokens_total += total_tokens
            stamp = parse_iso_timestamp(str(item.get("timestamp") or ""))
            if stamp is not None:
                age = max(now - stamp, 0)
                if age <= 5 * 3600:
                    tokens_5h += total_tokens
                if age <= 7 * 24 * 3600:
                    tokens_7d += total_tokens

        item_type = normalize_text(item.get("type"))
        if item_type not in {"user", "assistant"}:
            continue
        content = message.get("content")
        if isinstance(content, str):
            append_preview_line(lines, content, prefix="You: " if item_type == "user" else "")
            continue
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            text = block.get("text")
            if not text and block.get("type") == "tool_use":
                text = block.get("name")
            append_preview_line(lines, text, prefix="You: " if item_type == "user" else "")

    return recent_meaningful_lines(lines, limit=6), tokens_5h, tokens_7d, tokens_total


def load_live_claude_context(pid: int | None, cwd: str | None) -> dict[str, Any]:
    meta = find_claude_session_meta_for_pid(pid)
    session_id = normalize_text(meta.get("sessionId"))
    if not session_id and not normalize_text(cwd):
        return {}

    project_path = find_claude_project_file(session_id) if session_id else None
    preview_lines, usage_5h, usage_7d, tokens_total = claude_preview_from_project_file(project_path)
    statusline_snapshot = load_claude_statusline_snapshot()
    rate_limits = statusline_snapshot.get("rate_limits") if isinstance(statusline_snapshot.get("rate_limits"), dict) else {}
    prompt = ""
    for item in reversed(read_recent_jsonl(CLAUDE_HISTORY_PATH, limit=400)):
        if normalize_text(item.get("sessionId")) != session_id:
            continue
        prompt = normalize_text(item.get("display"))
        if prompt:
            break

    label_seed = first_text(prompt, session_id)
    label = normalize_task_label_candidate(label_seed) or truncate(label_seed, 52)
    resolved_cwd = first_text(meta.get("cwd"), cwd)

    return {
        "session_id": session_id,
        "cwd": resolved_cwd,
        "prompt": prompt,
        "label": label,
        "preview_lines": recent_meaningful_lines(preview_lines or ([truncate(prompt, 120)] if prompt else []), limit=6),
        "rate_limits": rate_limits or {},
        "usage_5h": usage_5h,
        "usage_7d": usage_7d,
        "tokens_total": tokens_total,
        "mtime": project_path.stat().st_mtime if project_path and project_path.exists() else 0.0,
        "transcript_path": str(project_path) if project_path else "",
    }


def scan_recent_codex_records(limit_files: int = 80) -> list[dict[str, Any]]:
    thread_rows: list[dict[str, Any]] = []
    if CODEX_STATE_DB.exists():
        try:
            with sqlite3.connect(CODEX_STATE_DB) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    """
                    SELECT id, cwd, title, first_user_message, updated_at, tokens_used
                    FROM threads
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (limit_files,),
                ).fetchall()
                thread_rows = [dict(row) for row in rows]
        except Exception:
            thread_rows = []

    session_files: dict[str, Path] = {}
    if CODEX_SESSIONS_DIR.exists():
        for path in sorted(CODEX_SESSIONS_DIR.rglob("*.jsonl"), key=lambda item: item.stat().st_mtime, reverse=True)[: max(limit_files * 2, 80)]:
            session_id = extract_session_id_from_path(str(path))
            if session_id and session_id not in session_files:
                session_files[session_id] = path

    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in thread_rows:
        session_id = normalize_text(row.get("id"))
        if not session_id or session_id in seen:
            continue
        seen.add(session_id)
        session_path = session_files.get(session_id)
        preview_lines, rate_limits = codex_preview_from_session_file(session_path)
        prompt = first_text(row.get("first_user_message"), row.get("title"))
        label_seed = first_text(row.get("first_user_message"), row.get("title"))
        label = normalize_task_label_candidate(label_seed) or truncate(label_seed, 52)
        records.append(
            {
                "session_id": session_id,
                "cwd": normalize_text(row.get("cwd")),
                "prompt": prompt,
                "thread_name": normalize_text(row.get("title")),
                "label": label,
                "preview_lines": recent_meaningful_lines(preview_lines or ([truncate(prompt, 120)] if prompt else []), limit=6),
                "rate_limits": rate_limits or {},
                "tokens_total": int(row.get("tokens_used") or 0),
                "mtime": session_path.stat().st_mtime if session_path and session_path.exists() else float(row.get("updated_at") or 0),
                "transcript_path": str(session_path) if session_path else "",
            }
        )

    records.sort(key=lambda item: item.get("mtime", 0), reverse=True)
    return records


def scan_recent_claude_records(limit_items: int = 400) -> list[dict[str, Any]]:
    prompt_by_session: dict[str, str] = {}
    statusline_snapshot = load_claude_statusline_snapshot()
    rate_limits = statusline_snapshot.get("rate_limits") if isinstance(statusline_snapshot.get("rate_limits"), dict) else {}
    for item in read_recent_jsonl(CLAUDE_HISTORY_PATH, limit=limit_items):
        session_id = normalize_text(item.get("sessionId"))
        prompt = normalize_text(item.get("display"))
        if session_id and prompt:
            prompt_by_session[session_id] = prompt

    records: list[dict[str, Any]] = []
    if not CLAUDE_PROJECTS_DIR.exists():
        return records

    for path in sorted(CLAUDE_PROJECTS_DIR.rglob("*.jsonl"), key=lambda item: item.stat().st_mtime, reverse=True)[:120]:
        session_id = normalize_text(path.stem)
        if not session_id:
            continue
        preview_lines, usage_5h, usage_7d, tokens_total = claude_preview_from_project_file(path)
        prompt = prompt_by_session.get(session_id, "")
        label_seed = prompt or (preview_lines[0] if preview_lines else "")
        label = normalize_task_label_candidate(label_seed) or truncate(label_seed, 52)
        cwd = ""
        for item in read_recent_jsonl(path, limit=50):
            cwd = normalize_text(item.get("cwd"))
            if cwd:
                break
        records.append(
            {
                "session_id": session_id,
                "cwd": cwd,
                "prompt": prompt,
                "label": label,
                "preview_lines": recent_meaningful_lines(preview_lines or ([truncate(prompt, 120)] if prompt else []), limit=6),
                "rate_limits": rate_limits or {},
                "usage_5h": usage_5h,
                "usage_7d": usage_7d,
                "tokens_total": tokens_total,
                "mtime": path.stat().st_mtime,
                "transcript_path": str(path),
            }
        )

    records.sort(key=lambda item: item.get("mtime", 0), reverse=True)
    return records


def local_session_records() -> dict[str, list[dict[str, Any]]]:
    now = time.time()
    if _LOCAL_SESSION_CACHE["expires_at"] > now:
        return {"codex": _LOCAL_SESSION_CACHE["codex"], "claude": _LOCAL_SESSION_CACHE["claude"]}
    codex_records = scan_recent_codex_records()
    claude_records = scan_recent_claude_records()
    _LOCAL_SESSION_CACHE.update({
        "expires_at": now + 5.0,
        "codex": codex_records,
        "claude": claude_records,
    })
    return {"codex": codex_records, "claude": claude_records}


def recover_local_session_hint(source: str, cwd: str | None, *, pid: int | None = None) -> dict[str, Any]:
    normalized_source = normalize_text(source).lower()
    normalized_cwd = normalize_text(cwd)
    if normalized_source not in {"codex", "claude"}:
        return {}
    if normalized_source == "codex":
        exact = load_live_codex_context(pid, normalized_cwd)
    else:
        exact = load_live_claude_context(pid, normalized_cwd)
    if exact:
        return exact
    if not normalized_cwd:
        return {}
    records = local_session_records().get(normalized_source, [])
    for record in records:
        if match_workspace_path(record.get("cwd"), normalized_cwd):
            return record
    return {}


def is_generic_title(title: str, source: str, cwd: str | None) -> bool:
    text = normalize_text(title).lower()
    if not text:
        return True

    source_name = normalize_text(source).lower()
    cwd_name = workspace_name(cwd).lower()

    generic_targets = {source_name, f"{source_name} session", f"{source_name} in {cwd_name}"}
    if cwd_name:
        generic_targets.add(f"{source_name} @ {cwd_name}")
        generic_targets.add(cwd_name)

    if text in generic_targets:
        return True
    if text.startswith("detected live "):
        return True
    if text.startswith("working normally") or text.startswith("still working"):
        return True
    if text.startswith("ready to jump back") or text.startswith("all tests passed"):
        return True
    if any(text.startswith(prefix) for prefix in OPERATIONAL_LABEL_PREFIXES):
        return True
    if "&& node -v" in text or "&& npm -v" in text or "&& pnpm -v" in text:
        return True
    if any(hint in text for hint in BOILERPLATE_REPLY_HINTS):
        return True
    if any(text.startswith(prefix) for prefix in LOW_SIGNAL_LABEL_PREFIXES):
        return True
    if text.startswith("review before approve") or text.startswith("task review") or text.startswith("question to answer"):
        return True
    if text in {"agent-turn-complete", "completed", "updated", "running", "done", "finished"}:
        return True
    if text in {"startup", "booting", "booting island", "initializing", "initialising", "starting up"}:
        return True
    if text.startswith("session started") or text.startswith("session start"):
        return True
    return False


def strip_label_noise(text: str) -> str:
    cleaned = normalize_text(text)
    if not cleaned:
        return ""

    lowered = cleaned.lower()
    prefixes = (
        "bash wants approval:",
        "allow network access to ",
        "allow this shell command to modify files?",
        "allow this shell command?",
        "claude needs your permission to use ",
        "needs approval for ",
        "detected live ",
        "approval needed for ",
        "permission denied:",
        "completed:",
        "i'm ready to help",
        "im ready to help",
        "i’ll run that",
        "i'll run that",
        "i will run that",
        "i can help",
        "i see you've provided",
        "i see you’ve provided",
        "i see you have provided",
        "what would you like me to help with",
        "what would you like me to do",
        "please clarify what you'd like me to do",
        "please clarify what you’d like me to do",
    )
    for prefix in prefixes:
        if lowered.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip(" :-—")
            lowered = cleaned.lower()
            break

    if cleaned.startswith("`") and cleaned.endswith("`"):
        cleaned = cleaned[1:-1].strip()

    return cleaned


def is_boilerplate_reply(text: str | None) -> bool:
    lowered = normalize_text(text).lower()
    if not lowered:
        return False
    return any(hint in lowered for hint in BOILERPLATE_REPLY_HINTS)


def first_sentence_fragment(text: str | None) -> str:
    content = normalize_text(text)
    if not content:
        return ""
    fragment = re.split(r"[\n。！？!?；;]", content, maxsplit=1)[0]
    return normalize_text(fragment)


def summarize_command_label(command: str | None) -> str:
    content = normalize_text(command)
    if not content:
        return ""
    if is_generic_title(content, "", None):
        return ""

    if content.lower().startswith("bash(") and content.endswith(")"):
        content = content[content.find("(") + 1 : -1].strip()
    if content.startswith("$ "):
        content = content[2:].strip()
    if content.startswith("`") and content.endswith("`"):
        content = content[1:-1].strip()

    if not content:
        return ""

    try:
        tokens = shlex.split(content, posix=True)
    except ValueError:
        tokens = content.split()
    if not tokens:
        return ""

    program = Path(tokens[0].strip('"')).name.lower()
    host_match = URL_RE.search(content)
    host = host_match.group(1) if host_match else ""

    if program == "curl":
        if host:
            if any(flag in tokens for flag in ("-I", "--head")):
                return truncate(f"Fetch {host} headers", 52)
            if any(flag in tokens for flag in ("-L", "--location")):
                return truncate(f"Follow redirects from {host}", 52)
            return truncate(f"Fetch {host}", 52)
        return "Fetch URL"

    if program == "wget":
        if host:
            return truncate(f"Fetch {host}", 52)
        return "Fetch URL"

    if program == "git" and len(tokens) > 1:
        subcommand = tokens[1].lower()
        git_labels = {
            "status": "Check git status",
            "diff": "Review git diff",
            "log": "Review git log",
            "show": "Review git show",
            "pull": "Run git pull",
            "push": "Run git push",
            "fetch": "Run git fetch",
            "clone": "Run git clone",
        }
        if subcommand in git_labels:
            return truncate(git_labels[subcommand], 52)

    if program in {"npm", "pnpm", "yarn"}:
        if len(tokens) > 1 and not tokens[1].startswith("-"):
            subcommand = tokens[1].lower()
            if subcommand in {"install", "add", "test", "run", "build", "start", "dev", "publish"}:
                return truncate(f"Run {program} {subcommand}", 52)
        return truncate(f"Run {program}", 52)

    if program in {"python", "python3", "uv"}:
        if len(tokens) > 1 and not tokens[1].startswith("-"):
            return truncate(f"Run {program} {Path(tokens[1]).name}", 52)
        return truncate(f"Run {program}", 52)

    if program in {"bash", "sh", "zsh"}:
        if len(tokens) >= 3 and tokens[1] in {"-lc", "-c"}:
            nested = summarize_command_label(" ".join(tokens[2:]))
            if nested:
                return nested
        return "Run shell command"

    if program in COMMAND_PROGRAM_ALIASES:
        label = COMMAND_PROGRAM_ALIASES[program]
        if host and label == "Fetch":
            return truncate(f"{label} {host}", 52)
        return truncate(label, 52)

    if host:
        return truncate(f"Check {host}", 52)

    if len(content) <= 52 and "\n" not in content:
        return truncate(content, 52)

    return ""


def summarize_file_task_label(text: str | None, limit: int = 52) -> str:
    content = normalize_text(text)
    if not content:
        return ""

    lowered = content.lower()
    create_hint = any(token in lowered for token in ("create", "created", "write", "wrote", "add ", "added", "创建", "新建", "生成", "写入", "已创建", "添加"))
    update_hint = any(token in lowered for token in ("edit", "update", "updated", "modify", "modified", "rewrite", "改", "修改", "更新", "重写"))
    if not create_hint and not update_hint:
        return ""

    target = ""
    named_file = NAMED_FILE_RE.search(content)
    if named_file:
        filename = named_file.group(1)
        extension = named_file.group(2).lower()
        target = f"{filename}.{extension}"
        if "桌面" in content:
            target = f"桌面/{target}"
        elif "desktop" in lowered:
            target = f"Desktop/{target}"
    else:
        paths = [match.group(1) for match in FILE_PATH_RE.finditer(content)]
        paths = [path.strip("`\"'.,:;()[]{}") for path in paths if "." in path]
        if paths:
            target = max(paths, key=len)

    if not target:
        return ""

    action = "Create" if create_hint and not update_hint else "Update"
    return truncate(f"{action} {target}", limit)


def clean_goal_target(text: str) -> str:
    candidate = normalize_text(text)
    if not candidate:
        return ""
    candidate = re.sub(
        r"^(?:please\s+|帮我(?:们)?|请你|请|我想让你|我希望你|现在需要你|麻烦你|可以帮我|请帮我|帮忙)\s*",
        "",
        candidate,
        flags=re.I,
    )
    candidate = re.sub(
        r"^(?:一个|一款|一套|一份|一个简易的|一个简单的|简易的|简单的|独立的)\s*",
        "",
        candidate,
    )
    return candidate.strip(" \"'`，。,:;")


def summarize_goal_task_label(text: str | None, limit: int = 52) -> str:
    content = first_sentence_fragment(text)
    if not content:
        return ""

    lowered = content.lower()
    if "俄罗斯方块" in content or "tetris" in lowered:
        return truncate("Build Tetris game", limit)

    for action, pattern in (
        ("Fix", r"(?:fix|修复)\s+(.+)"),
        ("Optimize", r"(?:optimize|优化)\s+(.+)"),
        ("Refactor", r"(?:refactor|重构)\s+(.+)"),
    ):
        match = re.search(pattern, content, flags=re.I)
        if not match:
            continue
        target = clean_goal_target(match.group(1))
        if target:
            return truncate(f"{action} {target}", limit)

    build_match = re.search(
        r"(?:build|make|create|implement|develop|做|制作|实现|开发|搭建|做成|完成)\s*"
        r"(?:一个|一款|一套|一份|一个简易的|一个简单的|简易的|简单的|独立的)?\s*(.+)",
        content,
        flags=re.I,
    )
    if build_match:
        target = clean_goal_target(build_match.group(1))
        target = re.sub(r"(?:来测试.*|用于测试.*|方便测试.*)$", "", target, flags=re.I).strip()
        if target:
            return truncate(f"Build {target}", limit)

    return ""


def normalize_task_label_candidate(text: str | None) -> str:
    candidate = strip_label_noise(normalize_text(text))
    if not candidate or is_generic_title(candidate, "", None):
        return ""

    command_hint = extract_command_hint(candidate)
    if command_hint:
        command_label = summarize_command_label(command_hint)
        if command_label:
            return command_label

    command_label = summarize_command_label(candidate)
    if command_label:
        return command_label

    file_label = summarize_file_task_label(candidate)
    if file_label:
        return file_label

    goal_label = summarize_goal_task_label(candidate)
    if goal_label:
        return goal_label

    return candidate


def extract_command_hint(*values: Any) -> str:
    for value in values:
        text = normalize_text(value)
        if not text:
            continue

        lines = text.splitlines()
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("$ "):
                return truncate(stripped[2:].strip(), 120)
            if stripped.startswith("`") and stripped.endswith("`"):
                candidate = stripped[1:-1].strip()
                if candidate:
                    return truncate(candidate, 120)
            if stripped.lower().startswith("bash(") and stripped.endswith(")"):
                candidate = stripped[stripped.find("(") + 1 : -1].strip()
                if candidate:
                    return truncate(candidate, 120)

        code_match = re.search(r"`([^`]+)`", text)
        if code_match:
            candidate = normalize_text(code_match.group(1))
            if candidate:
                return truncate(candidate, 120)

        command_match = COMMAND_INTENT_RE.search(text)
        if command_match:
            candidate = normalize_text(command_match.group(1)).rstrip(" .!?，。；;")
            if candidate:
                return truncate(candidate, 120)

        if ":" in text:
            tail = normalize_text(text.split(":", 1)[1])
            if len(tail.split()) >= 2:
                return truncate(tail, 120)

        if re.search(r"\b(curl|wget|git|bash|python|pnpm|npm|uv|make|sed|tee|rm|mv|cp)\b", text, re.I):
            return truncate(text, 120)

    return ""


def review_risk_label(approval_type: str, command_hint: str, summary: str) -> str:
    lowered = " ".join([normalize_text(approval_type), normalize_text(command_hint), normalize_text(summary)]).lower()
    if not lowered:
        return ""
    if any(token in lowered for token in ("http://", "https://", "curl ", "wget ", "ssh ", "scp ", "rsync ", "ping ")):
        return "Network access"
    if any(token in lowered for token in ("rm ", "mv ", "cp ", "tee ", "touch ", "mkdir ", "chmod ", "chown ", "sed -i", "python -c")):
        return "File changes"
    if "bash" in lowered:
        return "Shell command"
    if normalize_text(approval_type):
        return normalize_text(approval_type).replace("_", " ").title()
    return "Review"


def derive_session_task_label(
    *,
    source: str,
    title: str,
    summary: str,
    question: str,
    approval_type: str,
    cwd: str | None,
    display_title: str | None = None,
    task_label: str | None = None,
    review_title: str | None = None,
    recovered_hint: dict[str, Any] | None = None,
) -> str:
    source_name = normalize_text(source).title() or "Agent"
    cwd_name = workspace_name(cwd)
    recovered = recovered_hint or recover_local_session_hint(source, cwd)
    command_hint = extract_command_hint(
        question,
        summary,
        title,
        display_title,
        task_label,
        review_title,
    )

    candidates = [
        recovered.get("label"),
        recovered.get("prompt"),
        display_title,
        task_label,
        command_hint,
        question,
        review_title,
        summary,
        title,
    ]

    for candidate in candidates:
        text = normalize_task_label_candidate(candidate)
        if not text or is_generic_title(text, source_name, cwd_name):
            continue
        return truncate(strip_label_noise(text), 52)

    if approval_type:
        approval = normalize_text(approval_type).replace("_", " ").strip().title()
        if approval:
            return truncate(f"{source_name} · {approval}", 52)

    if cwd_name:
        return truncate(f"{source_name} · {cwd_name}", 52)

    return truncate(f"{source_name} session", 52)


def derive_context_label(source: str, cwd: str | None, terminal: str | None, tty: str | None) -> str:
    parts: list[str] = []
    source_name = normalize_text(source).title()
    if source_name:
        parts.append(source_name)

    terminal_name = normalize_text(terminal)
    if terminal_name:
        parts.append(terminal_name)
    elif tty:
        tty_name = normalize_text(tty)
        if tty_name.startswith("/dev/"):
            tty_name = tty_name.replace("/dev/", "", 1)
        tty_name = normalize_text(tty_name)
        if tty_name:
            parts.append(tty_name)
    else:
        workspace = workspace_name(cwd)
        if workspace:
            parts.append(workspace)

    return " · ".join(parts[:3])


def normalize_tty_key(value: str | None) -> str:
    tty_name = normalize_text(value)
    if tty_name.startswith("/dev/"):
        tty_name = tty_name.replace("/dev/", "", 1)
    return normalize_text(tty_name)


def peek_send_supported(jump_target: dict[str, Any] | None) -> bool:
    target = jump_target if isinstance(jump_target, dict) else {}
    terminal_name = normalize_text(target.get("terminal")).lower()
    if target.get("tmux_pane") or target.get("tmux_window"):
        return True
    if terminal_name == "konsole":
        return True
    if os.environ.get("DISPLAY") and shutil.which("xdotool"):
        return True
    return False


def display_session_aliases(session: dict[str, Any]) -> set[str]:
    source = normalize_text(session.get("source")).lower()
    if not source:
        return set()

    aliases: set[str] = set()
    session_id = normalize_text(session.get("id"))
    artifact_session = normalize_text(session.get("artifactSessionId"))
    tty_name = normalize_tty_key(session.get("jumpTty"))
    jump_pid = normalize_text(session.get("jumpPid"))
    live_pid = normalize_text(extract_live_process_pid(session.get("id")))
    title = normalize_text(session.get("taskLabel") or session.get("displayTitle") or session.get("rawTitle") or session.get("title"))
    workspace = normalize_text(session.get("workspaceLabel") or session.get("contextLabel"))

    if session_id:
        aliases.add(f"{source}|id|{session_id}")
    if artifact_session:
        aliases.add(f"{source}|artifact|{artifact_session}")
    if tty_name:
        aliases.add(f"{source}|tty|{tty_name}")
    if jump_pid:
        aliases.add(f"{source}|pid|{jump_pid}")
    if live_pid:
        aliases.add(f"{source}|pid|{live_pid}")

    if workspace and title:
        aliases.add(f"{source}|task|{workspace}|{title}")

    if not aliases and (workspace or title):
        aliases.add(f"{source}|fallback|{workspace}|{title}")

    return aliases


def display_session_priority(session: dict[str, Any]) -> tuple[int, int, int, int, int, int, str]:
    state = normalize_text(session.get("state")).lower()
    needs_response = bool(session.get("needsResponse"))
    if needs_response:
        state_score = 600
    elif state == "running":
        state_score = 500
    elif state == "failed":
        state_score = 400
    elif state == "stale":
        state_score = 350
    elif state == "completed":
        state_score = 300
    else:
        state_score = 200

    title = normalize_text(session.get("title"))
    source_name = normalize_text(session.get("source"))
    workspace = normalize_text(session.get("workspaceLabel") or session.get("contextLabel"))
    title_quality = 0 if is_generic_title(title, source_name, workspace) else 1
    artifact_quality = 1 if normalize_text(session.get("artifactSessionId")) else 0
    jump_identity_quality = 1 if normalize_text(session.get("jumpPid")) or normalize_tty_key(session.get("jumpTty")) else 0
    live_quality = 1 if normalize_text(session.get("id")).startswith("live::") else 0
    peek_quality = 1 if session.get("peekLines") else 0
    attention = int(session.get("attention", 0) or 0)
    updated_at = normalize_text(session.get("updatedAt"))
    return (
        state_score,
        title_quality,
        artifact_quality,
        jump_identity_quality,
        live_quality,
        peek_quality + attention,
        updated_at,
    )


def dedupe_display_sessions(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []

    for session in sessions:
        aliases = display_session_aliases(session)
        if not aliases:
            groups.append({"session": session, "aliases": set()})
            continue

        matched_indices = [index for index, group in enumerate(groups) if aliases & group["aliases"]]
        if not matched_indices:
            groups.append({"session": session, "aliases": set(aliases)})
            continue

        keeper_index = matched_indices[0]
        keeper_group = groups[keeper_index]
        if display_session_priority(session) > display_session_priority(keeper_group["session"]):
            keeper_group["session"] = session
        keeper_group["aliases"].update(aliases)

        for merge_index in reversed(matched_indices[1:]):
            merge_group = groups[merge_index]
            keeper_group["aliases"].update(merge_group["aliases"])
            if display_session_priority(merge_group["session"]) > display_session_priority(keeper_group["session"]):
                keeper_group["session"] = merge_group["session"]
            groups.pop(merge_index)

    return [group["session"] for group in groups]


def derive_review_fields(
    *,
    source: str,
    approval_type: str,
    question: str,
    summary: str,
    title: str,
    cwd: str | None,
    workspace: str | None,
    state_text: str,
    review_payload: dict[str, Any] | None = None,
) -> dict[str, str]:
    payload = review_payload or {}
    review_title = first_text(payload.get("headline"), payload.get("title"))
    command_hint = first_text(
        payload.get("command"),
        payload.get("detail"),
        payload.get("reason"),
        extract_command_hint(question, summary, title),
    )
    reason_hint = first_text(payload.get("reason"), question, summary)
    scope_hint = first_text(payload.get("scope"), workspace_name(workspace) or workspace_name(cwd))
    risk_hint = first_text(payload.get("risk"), review_risk_label(approval_type, command_hint, summary))

    if not review_title:
        if state_text in {"Blocked", "Waiting User"}:
            review_title = "REVIEW BEFORE APPROVE"
        elif question:
            review_title = "QUESTION TO ANSWER"
        else:
            review_title = "TASK REVIEW"

    return {
        "reviewHeadline": truncate(review_title, 48),
        "reviewCommand": truncate(command_hint, 120),
        "reviewReason": truncate(reason_hint, 120),
        "reviewScope": truncate(scope_hint, 64),
        "reviewRisk": truncate(risk_hint, 40),
    }


def codex_auth_mode() -> str:
    payload = read_json_file_maybe(CODEX_AUTH_PATH)
    return normalize_text(payload.get("auth_mode")).lower()


def collect_usage_totals() -> dict[str, int]:
    records = local_session_records()
    codex_total = sum(int(item.get("tokens_total") or 0) for item in records.get("codex", []))
    claude_total = sum(int(item.get("tokens_total") or 0) for item in records.get("claude", []))
    return {"codex": codex_total, "claude": claude_total}


def usage_display_snapshot(
    started_at: float,
    sessions: list[dict[str, Any]] | None = None,
    baseline: dict[str, int] | None = None,
) -> dict[str, dict[str, Any]]:
    del started_at
    baseline_totals = baseline or {}
    current_totals = collect_usage_totals()
    active_records: dict[str, list[dict[str, Any]]] = {"codex": [], "claude": []}
    seen: set[tuple[str, str]] = set()

    for session in sessions or []:
        source = normalize_text(session.get("source")).lower()
        if source not in active_records:
            continue
        jump_target = session.get("jump_target") if isinstance(session.get("jump_target"), dict) else {}
        pid_value = extract_live_process_pid(str(session.get("id") or "")) or jump_target.get("pid")
        try:
            pid = int(pid_value) if pid_value is not None else None
        except Exception:
            pid = None
        hint = recover_local_session_hint(
            source,
            str(session.get("cwd") or session.get("workspace") or ""),
            pid=pid,
        )
        if not hint:
            continue
        identity = normalize_text(hint.get("session_id")) or str(session.get("id") or "")
        key = (source, identity)
        if key in seen:
            continue
        seen.add(key)
        active_records[source].append(hint)

    codex_rate_limits = freshest_codex_rate_limits(active_records["codex"])
    if not codex_rate_limits:
        for item in active_records["codex"]:
            if isinstance(item.get("rate_limits"), dict) and item.get("rate_limits"):
                codex_rate_limits = item.get("rate_limits")
                break

    primary = codex_rate_limits.get("primary") if isinstance(codex_rate_limits, dict) else {}
    secondary = codex_rate_limits.get("secondary") if isinstance(codex_rate_limits, dict) else {}
    codex_delta = max(0, current_totals.get("codex", 0) - baseline_totals.get("codex", 0))
    claude_delta = max(0, current_totals.get("claude", 0) - baseline_totals.get("claude", 0))
    claude_tokens_5h = sum(int(item.get("usage_5h") or 0) for item in active_records["claude"])
    claude_tokens_7d = sum(int(item.get("usage_7d") or 0) for item in active_records["claude"])
    codex_mode = "tokens" if codex_auth_mode() == "api_key" else "quota"
    claude_statusline = load_claude_statusline_snapshot()
    claude_rate_limits = claude_statusline.get("rate_limits") if isinstance(claude_statusline.get("rate_limits"), dict) else {}
    if not claude_rate_limits:
        for item in active_records["claude"]:
            if isinstance(item.get("rate_limits"), dict) and item.get("rate_limits"):
                claude_rate_limits = item.get("rate_limits")
                break
    claude_five_hour_remaining = remaining_percent_from_window(rate_limit_window(claude_rate_limits, "5h"))
    claude_seven_day_remaining = remaining_percent_from_window(rate_limit_window(claude_rate_limits, "7d"))
    claude_mode = "quota" if claude_five_hour_remaining is not None or claude_seven_day_remaining is not None else "estimate"

    return {
        "codex": {
            "label": "Codex",
            "mode": codex_mode,
            "fiveHour": f"{max(0, 100 - int(primary.get('used_percent') or 0))}% left" if primary and codex_mode == "quota" else "unavailable",
            "sevenDay": f"{max(0, 100 - int(secondary.get('used_percent') or 0))}% left" if secondary and codex_mode == "quota" else "unavailable",
            "sessionTokens": codex_delta,
            "detail": "ChatGPT quota" if codex_mode == "quota" else "API key usage",
        },
        "claude": {
            "label": "Claude",
            "mode": claude_mode,
            "fiveHour": f"{claude_five_hour_remaining}% left" if claude_five_hour_remaining is not None else "unavailable",
            "sevenDay": f"{claude_seven_day_remaining}% left" if claude_seven_day_remaining is not None else "unavailable",
            "sessionTokens": claude_delta,
            "detail": "Claude.ai quota" if claude_mode == "quota" else f"5h used {claude_tokens_5h:,} / 7d used {claude_tokens_7d:,}",
        },
    }


def build_peek_lines(
    *,
    source: str,
    cwd: str | None,
    summary: str,
    question: str,
    review_command: str,
    review_reason: str,
    recovered_hint: dict[str, Any] | None = None,
) -> list[str]:
    lines: list[str] = []
    recovered = recovered_hint or recover_local_session_hint(source, cwd)
    preview_lines = recent_meaningful_lines(recovered.get("preview_lines", []), limit=6)
    for candidate in preview_lines:
        text = truncate(candidate, 132)
        if text and text not in lines:
            lines.append(text)

    if len(lines) < 3:
        for candidate in [question, review_command, review_reason, summary]:
            text = truncate(candidate, 132)
            if text and not is_preview_noise(text) and text not in lines:
                lines.append(text)

    return lines[:6]


def compact_timeline_signature(timeline: list[dict[str, Any]] | None) -> tuple[Any, ...]:
    items: list[Any] = []
    for entry in timeline or []:
        if not isinstance(entry, dict):
            continue
        items.append(
            (
                normalize_text(entry.get("session_id")),
                normalize_text(entry.get("type")),
                normalize_text(entry.get("label")),
                normalize_text(entry.get("title")),
                normalize_text(entry.get("summary")),
            )
        )
    return tuple(items)


def compact_session_signature(session: dict[str, Any]) -> tuple[Any, ...]:
    interaction = session.get("interaction") if isinstance(session.get("interaction"), dict) else {}
    review = session.get("review") if isinstance(session.get("review"), dict) else {}
    jump_target = session.get("jump_target") if isinstance(session.get("jump_target"), dict) else {}
    stuck = session.get("stuck") if isinstance(session.get("stuck"), dict) else {}
    peek = session.get("peek") if isinstance(session.get("peek"), dict) else {}
    collaboration = session.get("collaboration") if isinstance(session.get("collaboration"), dict) else {}
    preview_lines = tuple(normalize_text(line) for line in (peek.get("preview_lines") or []) if normalize_text(line))[:6]
    choices = tuple(normalize_text(choice) for choice in (interaction.get("choices") or []) if normalize_text(choice))
    return (
        normalize_text(session.get("id")),
        normalize_text(session.get("source")),
        normalize_text(session.get("state")),
        normalize_text(session.get("title")),
        normalize_text(session.get("task_label")),
        normalize_text(session.get("collapsed_headline")),
        normalize_text(session.get("summary")),
        int(session.get("attention_score", 0) or 0),
        normalize_text(session.get("cwd")),
        normalize_text(session.get("workspace")),
        normalize_text(interaction.get("question")),
        normalize_text(interaction.get("approval_type")),
        choices,
        normalize_text(review.get("headline")),
        normalize_text(review.get("command")),
        normalize_text(review.get("reason")),
        normalize_text(review.get("scope")),
        normalize_text(review.get("risk")),
        bool(stuck.get("is_stuck", False)),
        int(stuck.get("score", 0) or 0),
        normalize_text(stuck.get("reason")),
        int(stuck.get("stalled_for_seconds", 0) or 0),
        preview_lines,
        normalize_text(jump_target.get("pid")),
        normalize_text(jump_target.get("terminal")),
        normalize_text(jump_target.get("tmux_session")),
        normalize_text(jump_target.get("tmux_window")),
        normalize_text(jump_target.get("tmux_pane")),
        normalize_text(collaboration.get("session_name")),
        normalize_text(collaboration.get("strategy")),
        normalize_text(collaboration.get("status")),
        normalize_text(collaboration.get("current_phase")),
        normalize_text(collaboration.get("current_actor")),
        normalize_text(collaboration.get("next_actor")),
        normalize_text(collaboration.get("next_action")),
        normalize_text(((collaboration.get("claude") or {}).get("status"))),
        normalize_text(((collaboration.get("codex") or {}).get("status"))),
    )


def snapshot_signature(snapshot: dict[str, Any], sessions: list[dict[str, Any]]) -> tuple[Any, ...]:
    quiet_mode = snapshot.get("quiet_mode") if isinstance(snapshot.get("quiet_mode"), dict) else {}
    approval_requests = snapshot.get("pending_approval_requests") if isinstance(snapshot.get("pending_approval_requests"), list) else []
    return (
        bool(quiet_mode.get("enabled", False)),
        int(snapshot.get("active_count", 0) or 0),
        int(snapshot.get("blocked_count", 0) or 0),
        tuple(compact_session_signature(session) for session in sessions if isinstance(session, dict)),
        compact_timeline_signature(snapshot.get("timeline") if isinstance(snapshot.get("timeline"), list) else []),
        tuple(
            (
                normalize_text(item.get("source")),
                normalize_text(item.get("session_id")),
                normalize_text(item.get("ui_session_id")),
                normalize_text(item.get("question")),
                tuple(normalize_text(choice) for choice in (item.get("choices") or []) if normalize_text(choice)),
            )
            for item in approval_requests
            if isinstance(item, dict)
        ),
    )


class Backend(QObject):
    snapshotReady = pyqtSignal(object)
    usageSnapshotReady = pyqtSignal(object)
    peekPreviewReady = pyqtSignal(str, object)
    snapshotChanged = pyqtSignal()
    sessionsChanged = pyqtSignal()
    timelineChanged = pyqtSignal()
    responseFinished = pyqtSignal(str, bool, str)
    headlineChanged = pyqtSignal()
    countsChanged = pyqtSignal()
    expandedChanged = pyqtSignal()
    replayExpandedChanged = pyqtSignal()
    quietModeChanged = pyqtSignal()
    focusModeChanged = pyqtSignal()
    pinnedChanged = pyqtSignal()
    promptAttentionChanged = pyqtSignal()
    connectedChanged = pyqtSignal()
    geometryChanged = pyqtSignal()
    usageChanged = pyqtSignal()
    telegramChanged = pyqtSignal()
    attentionRequested = pyqtSignal()
    summonRequested = pyqtSignal()

    def __init__(self, socket_path: str, state_path: Path):
        super().__init__()
        self._socket_path = socket_path
        self._state_path = state_path
        self._prefs_path = self._resolve_prefs_path()
        self._snapshot_signature = None
        self._raw_sessions = []
        self._sessions = []
        self._timeline = []
        self._prompt_session = {}
        self._suppressed_prompt_key = ""
        self._headline = "Booting island"
        self._active_count = 0
        self._blocked_count = 0
        self._expanded = True
        self._replay_expanded = True
        self._auto_expand_allowed = True
        self._quiet_mode = False
        self._focus_mode = False
        self._pinned = False
        self._prompt_attention_enabled = True
        self._connected = False
        self._window_x = -1
        self._window_y = 18
        self._window_width = EXPANDED_DEFAULT_WIDTH
        self._window_height = EXPANDED_DEFAULT_HEIGHT
        self._collapsed_width = COLLAPSED_DEFAULT_WIDTH
        self._started_at = time.time()
        self._usage_baseline = collect_usage_totals()
        self._usage = usage_display_snapshot(self._started_at, [], self._usage_baseline)
        self._last_usage_refresh_at = 0.0
        self._shutdown_called = False
        self._last_sound_at = 0.0
        self._previous_states = {}
        self._sound_effects: dict[str, str] = {}
        self._sound_effects_initialized = False
        self._sound_player: list[str] | None = None
        self._telegram_enabled = False
        self._telegram_bot_token = ""
        self._telegram_chat_id = ""
        self._telegram_status = "Telegram notifications are off"
        self._telegram_last_update_id = 0
        self._telegram_notified_sessions: dict[str, dict[str, Any]] = {}
        self._telegram_reply_targets: dict[str, str] = {}
        self._telegram_response_feedback: dict[str, tuple[str, str, str]] = {}
        self._loaded_prefs = self._load_prefs()
        self._apply_loaded_prefs()
        self.snapshotReady.connect(self._apply_snapshot)
        self.usageSnapshotReady.connect(self._apply_usage_snapshot)
        self.responseFinished.connect(self._handle_response_finished_feedback)
        self._stop_event = threading.Event()
        self._worker = threading.Thread(target=self._poll_loop, daemon=True)
        self._worker.start()
        self._telegram_worker = threading.Thread(target=self._telegram_loop, daemon=True)
        self._telegram_worker.start()
        self.refresh()
        if self._quiet_mode:
            self._send_quiet_mode()

    @pyqtProperty("QVariantList", notify=sessionsChanged)
    def sessions(self):
        return self._sessions

    @pyqtProperty("QVariantList", notify=timelineChanged)
    def timeline(self):
        return self._timeline

    @pyqtProperty("QVariantMap", notify=sessionsChanged)
    def promptSession(self):
        return self._prompt_session

    @pyqtProperty(bool, notify=sessionsChanged)
    def hasPromptSession(self):
        return bool(self._prompt_session)

    @pyqtProperty(int, notify=sessionsChanged)
    def promptChoiceCount(self):
        return len(self._prompt_session.get("choices", []))

    @pyqtProperty(str, notify=headlineChanged)
    def headline(self):
        return self._headline

    @pyqtProperty(int, notify=countsChanged)
    def activeCount(self):
        return self._active_count

    @pyqtProperty(int, notify=countsChanged)
    def blockedCount(self):
        return self._blocked_count

    @pyqtProperty(bool, notify=expandedChanged)
    def expanded(self):
        return self._expanded

    @pyqtProperty(bool, notify=replayExpandedChanged)
    def replayExpanded(self):
        return self._replay_expanded

    @pyqtProperty(bool, notify=quietModeChanged)
    def quietMode(self):
        return self._quiet_mode

    @pyqtProperty(bool, notify=focusModeChanged)
    def focusMode(self):
        return self._focus_mode

    @pyqtProperty(bool, notify=connectedChanged)
    def connected(self):
        return self._connected

    @pyqtProperty(bool, notify=pinnedChanged)
    def pinned(self):
        return self._pinned

    @pyqtProperty(bool, notify=promptAttentionChanged)
    def promptAttentionEnabled(self):
        return self._prompt_attention_enabled

    @pyqtProperty("QVariantMap", notify=usageChanged)
    def usage(self):
        return self._usage

    @pyqtProperty(str, constant=True)
    def socketPath(self):
        return self._socket_path

    @pyqtProperty(int, notify=geometryChanged)
    def windowX(self):
        return self._window_x

    @pyqtProperty(int, notify=geometryChanged)
    def windowY(self):
        return self._window_y

    @pyqtProperty(int, notify=geometryChanged)
    def windowWidth(self):
        return self._window_width

    @pyqtProperty(int, notify=geometryChanged)
    def collapsedWidth(self):
        return self._collapsed_width

    @pyqtProperty(int, notify=geometryChanged)
    def windowHeight(self):
        return self._window_height

    @pyqtProperty(bool, notify=geometryChanged)
    def hasStoredGeometry(self):
        return self._loaded_prefs is not None and self._window_x >= 0

    @pyqtProperty(bool, notify=telegramChanged)
    def telegramEnabled(self):
        return self._telegram_enabled

    @pyqtProperty(str, notify=telegramChanged)
    def telegramBotToken(self):
        return self._telegram_bot_token

    @pyqtProperty(str, notify=telegramChanged)
    def telegramChatId(self):
        return self._telegram_chat_id

    @pyqtProperty(str, notify=telegramChanged)
    def telegramStatus(self):
        return self._telegram_status

    @pyqtSlot()
    def toggleExpanded(self):
        self._expanded = not self._expanded
        self._auto_expand_allowed = self._expanded
        current_prompt_key = self._prompt_key_for_session(self._prompt_session)
        if not self._expanded and current_prompt_key:
            self._suppressed_prompt_key = current_prompt_key
        elif self._expanded and current_prompt_key and self._suppressed_prompt_key == current_prompt_key:
            self._suppressed_prompt_key = ""
        self.expandedChanged.emit()
        self._write_view_prefs()
        self._play_sound("toggle")

    @pyqtSlot()
    def toggleReplayExpanded(self):
        self._replay_expanded = not self._replay_expanded
        self.replayExpandedChanged.emit()
        self._write_view_prefs()
        self._play_sound("toggle")

    @pyqtSlot()
    def toggleQuietMode(self):
        self._quiet_mode = not self._quiet_mode
        self.quietModeChanged.emit()
        self._write_view_prefs()
        self._send_quiet_mode()
        self._play_sound("toggle")

    @pyqtSlot()
    def togglePinned(self):
        self._pinned = not self._pinned
        self.pinnedChanged.emit()
        self._write_view_prefs()
        self._play_sound("toggle")

    @pyqtSlot()
    def togglePromptAttention(self):
        self._prompt_attention_enabled = not self._prompt_attention_enabled
        self.promptAttentionChanged.emit()
        self._write_view_prefs()
        self._play_sound("toggle")

    @pyqtSlot()
    def summonWindow(self):
        self.summonRequested.emit()

    @pyqtSlot()
    def toggleFocusMode(self):
        self._focus_mode = not self._focus_mode
        self.focusModeChanged.emit()
        self._write_view_prefs()

    @pyqtSlot(str)
    def refreshPeekPreview(self, session_id: str):
        session = self._find_raw_session(session_id)
        if not session:
            self.peekPreviewReady.emit(str(session_id or ""), [])
            return
        self.peekPreviewReady.emit(str(session_id or ""), self._build_peek_preview(session))

    @pyqtSlot(str, bool, str)
    def saveTelegramSettings(self, bot_token: str, enabled: bool, chat_id: str):
        normalized_token = str(bot_token or "").strip()
        normalized_chat = str(chat_id or "").strip()
        changed = (
            normalized_token != self._telegram_bot_token
            or normalized_chat != self._telegram_chat_id
            or bool(enabled) != self._telegram_enabled
        )
        self._telegram_bot_token = normalized_token
        self._telegram_chat_id = normalized_chat
        self._telegram_enabled = bool(enabled and normalized_token)
        if not normalized_token:
            self._telegram_status = "Paste a BotFather token to enable Telegram"
            self._telegram_enabled = False
        elif self._telegram_chat_id:
            self._telegram_status = f"Telegram paired and saved with {self._telegram_chat_id}"
        else:
            self._telegram_status = "Token saved. Send /start to the bot from Telegram to pair this machine."
        if changed:
            self._write_view_prefs()
            self.telegramChanged.emit()

    @pyqtSlot()
    def sendTelegramTest(self):
        if not self._telegram_bot_token:
            self._telegram_status = "Paste a BotFather token first"
            self.telegramChanged.emit()
            return
        if not self._telegram_chat_id:
            self._telegram_status = "Open your bot in Telegram and send /start to pair it first"
            self.telegramChanged.emit()
            return
        ok = self._telegram_send_message(
            self._telegram_chat_id,
            "Vibe Island test ping.\nIf you received this, remote approval notifications are ready.",
        )
        self._telegram_status = "Telegram test sent" if ok else "Telegram test failed"
        self.telegramChanged.emit()

    @pyqtSlot(str)
    def jumpToSession(self, session_id: str):
        for session in self._raw_sessions:
            if session["id"] != session_id:
                continue

            collaboration = session.get("collaboration") if isinstance(session.get("collaboration"), dict) else {}
            if collaboration:
                preferred_agent = normalize_text(collaboration.get("current_actor")).lower()
                if preferred_agent not in {"claude", "codex"}:
                    preferred_agent = normalize_text(collaboration.get("next_actor")).lower()
                if preferred_agent not in {"claude", "codex"}:
                    preferred_agent = "codex"
                self.openCollabAgent(session_id, preferred_agent)
                print(f"Collaboration jump requested for {session_id}: {preferred_agent}")
                return

            command = [sys.executable, str(TOOLS_BRIDGE), "jump", "--session-json", json.dumps(session, ensure_ascii=False)]

            def run_jump():
                result = subprocess.run(
                    command,
                    cwd=ROOT.parent.parent,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if result.stdout.strip():
                    print(result.stdout.strip())
                if result.stderr.strip():
                    print(result.stderr.strip(), file=sys.stderr)
                if result.returncode != 0:
                    print(
                        f"Jump failed for {session_id} with exit code {result.returncode}",
                        file=sys.stderr,
                    )

            threading.Thread(target=run_jump, daemon=True).start()
            print(f"Jump requested for {session_id}: {session.get('title', 'Untitled')}")
            return

    @pyqtSlot(str, str)
    def openCollabAgent(self, session_id: str, agent_name: str):
        normalized_agent = normalize_text(agent_name).lower()
        if normalized_agent not in {"claude", "codex"}:
            return
        bridge_command = resolve_collab_bridge_command()
        if not bridge_command:
            print("No collaboration runtime found in PATH and no local fallback available.", file=sys.stderr)
            return
        for session in self._raw_sessions:
            if session["id"] != session_id:
                continue
            collaboration = session.get("collaboration") if isinstance(session.get("collaboration"), dict) else {}
            if not collaboration:
                continue
            workspace = normalize_text(collaboration.get("workspace")) or normalize_text(session.get("cwd") or session.get("workspace"))
            collab_session = normalize_text(collaboration.get("session_name"))
            if not workspace or not collab_session:
                return
            command = [
                *bridge_command,
                "open",
                "--workspace",
                workspace,
                "--session",
                collab_session,
                "--agent",
                normalized_agent,
                "--launch",
            ]

            def run_open():
                result = subprocess.run(
                    command,
                    cwd=ROOT.parent.parent,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if result.stdout.strip():
                    print(result.stdout.strip())
                if result.stderr.strip():
                    print(result.stderr.strip(), file=sys.stderr)
                if result.returncode != 0:
                    print(
                        f"Open collab agent failed for {session_id} with exit code {result.returncode}",
                        file=sys.stderr,
                    )

            threading.Thread(target=run_open, daemon=True).start()
            print(f"Open collab agent requested for {session_id}: {normalized_agent}")
            return

    @pyqtSlot(str, int, str)
    def respondToSession(self, session_id: str, choice_index: int, choice_text: str):
        session = self._find_raw_session(session_id)
        if not session:
            return
        self._dispatch_response(session, choice_index=choice_index, choice_text=choice_text)
        print(f"Respond requested for {session_id}: {choice_text or choice_index}")

    @pyqtSlot(str, int, str)
    def respondToSessionWithFollowup(self, session_id: str, choice_index: int, followup_text: str):
        followup = str(followup_text or "").strip()
        if not followup:
            print(f"Follow-up text missing for {session_id}", file=sys.stderr)
            return

        session = self._find_raw_session(session_id)
        if not session:
            return
        self._dispatch_response(session, choice_index=choice_index, followup_text=followup)
        print(f"Respond with follow-up requested for {session_id}: {followup}")

    @pyqtSlot(str, str)
    def sendPeekMessage(self, session_id: str, message_text: str):
        text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", str(message_text or ""))
        text = re.sub(r"\r?\n+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            print(f"Peek message missing for {session_id}", file=sys.stderr)
            return

        session = self._find_raw_session(session_id)
        if not session:
            return
        self._dispatch_peek_message(session, text)
        self._play_sound("peek-send")
        print(f"Peek send requested for {session_id}: {text}")

    @pyqtSlot()
    def shutdown(self):
        if self._shutdown_called:
            return
        self._shutdown_called = True
        self._stop_event.set()
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(0.5)
                client.connect(self._socket_path)
                client.sendall(b'{"type":"clear"}\n')
        except Exception:
            pass
        self._write_view_prefs()

    @pyqtSlot(int, int, int, int, bool)
    def saveWindowState(self, x: int, y: int, width: int, height: int, expanded: bool):
        self._window_x = max(int(x), -1)
        self._window_y = max(int(y), 0)
        if expanded:
            self._window_width, self._window_height = self._clamp_expanded_size(width, height)
            self._window_x, self._window_y = self._clamp_window_position(
                self._window_x,
                self._window_y,
                self._window_width,
                self._window_height,
            )
        else:
            self._collapsed_width = self._clamp_collapsed_width(width)
            self._window_x, self._window_y = self._clamp_window_position(
                self._window_x,
                self._window_y,
                self._collapsed_width,
                58,
            )
        self._expanded = bool(expanded)
        self._auto_expand_allowed = self._expanded
        current_prompt_key = self._prompt_key_for_session(self._prompt_session)
        if not self._expanded and current_prompt_key:
            self._suppressed_prompt_key = current_prompt_key
        elif self._expanded and current_prompt_key and self._suppressed_prompt_key == current_prompt_key:
            self._suppressed_prompt_key = ""
        self._write_view_prefs()
        self.geometryChanged.emit()
        self.expandedChanged.emit()

    def _find_raw_session(self, session_id: str) -> dict[str, Any] | None:
        normalized = normalize_text(session_id)
        if not normalized:
            return None
        for session in self._raw_sessions:
            if normalize_text(session.get("id")) == normalized:
                return session
        return None

    def _approval_request_files(self) -> list[Path]:
        if not APPROVAL_REQUESTS_DIR.exists():
            return []
        return sorted(APPROVAL_REQUESTS_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)

    def _pending_approval_requests(self) -> list[dict[str, Any]]:
        pending: list[dict[str, Any]] = []
        for request_path in self._approval_request_files():
            request = self._read_json_file_maybe(request_path)
            if not request or normalize_text(request.get("source")) == "":
                continue
            decision = request.get("decision") if isinstance(request.get("decision"), dict) else {}
            if normalize_text(decision.get("action")):
                continue
            pending.append(request)
        return pending

    def _approval_request_token(self, request: dict[str, Any]) -> str:
        source = normalize_text(request.get("source")).lower() or "agent"
        jump_target = request.get("jump_target") if isinstance(request.get("jump_target"), dict) else {}
        anchor = first_text(
            request.get("ui_session_id"),
            request.get("session_id"),
            jump_target.get("pid"),
            jump_target.get("tty"),
            request.get("cwd"),
            request.get("question"),
            "pending",
        )
        digest = hashlib.sha1(f"{source}:{anchor}".encode("utf-8")).hexdigest()
        return digest[:10]

    def _read_json_file_maybe(self, path: Path) -> dict[str, Any] | None:
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def _session_matches_approval_request(self, session: dict[str, Any], request: dict[str, Any]) -> bool:
        source = normalize_text(request.get("source")).lower()
        session_source = normalize_text(session.get("source")).lower()
        if source and session_source and session_source != source:
            return False

        session_id = normalize_text(session.get("id"))
        candidate_ids = {
            normalize_text(request.get("session_id")),
            normalize_text(request.get("ui_session_id")),
        }
        candidate_ids.discard("")
        if session_id and session_id in candidate_ids:
            return True

        request_jump = request.get("jump_target") if isinstance(request.get("jump_target"), dict) else {}
        session_jump = session.get("jump_target") if isinstance(session.get("jump_target"), dict) else {}
        request_pid = normalize_text(request_jump.get("pid"))
        session_pid = normalize_text(session_jump.get("pid"))
        if request_pid and session_pid and request_pid == session_pid:
            return True

        request_tty = normalize_text(request_jump.get("tty"))
        session_tty = normalize_text(session_jump.get("tty"))
        if request_tty and session_tty and request_tty == session_tty:
            return True

        request_cwd = normalize_text(request.get("cwd"))
        session_cwd = normalize_text(session.get("cwd") or session.get("workspace"))
        if request_cwd and session_cwd and request_cwd == session_cwd:
            return True

        request_question = normalize_text(request.get("question"))
        session_question = normalize_text((session.get("interaction") or {}).get("question") if isinstance(session.get("interaction"), dict) else session.get("question"))
        if request_question and session_question and request_question == session_question:
            return True

        return False

    def _approval_request_for_session(self, session: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(session, dict):
            return None
        raw = self._find_raw_session(normalize_text(session.get("id")))
        candidates: list[dict[str, Any]] = []
        if raw:
            candidates.append(raw)
        candidates.append(session)
        for request in self._pending_approval_requests():
            for candidate in candidates:
                if self._session_matches_approval_request(candidate, request):
                    return request
            session_source = normalize_text(session.get("source")).lower()
            request_source = normalize_text(request.get("source")).lower()
            if session_source and request_source and session_source == request_source:
                session_cwd = normalize_text(session.get("cwd") or session.get("workspace"))
                request_cwd = normalize_text(request.get("cwd"))
                session_question = normalize_text(session.get("question"))
                request_question = normalize_text(request.get("question"))
                session_approval = normalize_text(session.get("approvalType"))
                request_approval = normalize_text(request.get("approval_type"))
                if session_cwd and request_cwd and session_cwd == request_cwd:
                    if session_question and request_question and session_question == request_question:
                        return request
                    if session_approval and request_approval and session_approval == request_approval:
                        return request
        return None

    def _prompt_key_for_session(self, session: dict[str, Any] | None) -> str:
        if not isinstance(session, dict):
            return ""
        request = self._approval_request_for_session(session)
        if request:
            return self._approval_request_token(request)
        parts = [
            normalize_text(session.get("source")).lower(),
            normalize_text(session.get("id")),
            normalize_text(session.get("question")),
            normalize_text(session.get("approvalType")),
            normalize_text(session.get("reviewCommand")),
            "|".join(str(item).strip() for item in (session.get("choices") or []) if str(item).strip()),
        ]
        payload = "||".join(parts)
        if not payload.strip("|"):
            return ""
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]

    def _session_from_approval_request(self, request: dict[str, Any], token: str) -> dict[str, Any] | None:
        source = normalize_text(request.get("source")).lower()
        if not source:
            return None

        for candidate_id in (
            normalize_text(request.get("ui_session_id")),
            normalize_text(request.get("session_id")),
        ):
            raw = self._find_raw_session(candidate_id)
            if raw:
                return raw

        for raw in self._raw_sessions:
            if self._session_matches_approval_request(raw, request):
                return raw

        session_id = normalize_text(request.get("ui_session_id")) or normalize_text(request.get("session_id"))
        if not session_id:
            session_id = f"telegram::{source}::{token}"
        jump_target = request.get("jump_target") if isinstance(request.get("jump_target"), dict) else {}
        return {
            "id": session_id,
            "source": source,
            "cwd": normalize_text(request.get("cwd")),
            "workspace": normalize_text(request.get("cwd")),
            "jump_target": jump_target,
            "interaction": {
                "question": normalize_text(request.get("question")),
                "approval_type": normalize_text(request.get("approval_type")),
                "choices": request.get("choices") if isinstance(request.get("choices"), list) else [],
            },
            "title": normalize_text(request.get("title")) or normalize_text(request.get("task_label")) or "Approval needed",
            "summary": normalize_text(request.get("summary")) or normalize_text(request.get("question")) or "Approval needed",
        }

    def _session_with_pending_approval(self, request: dict[str, Any]) -> dict[str, Any] | None:
        token = self._approval_request_token(request)
        base = self._session_from_approval_request(request, token)
        if not isinstance(base, dict):
            return None

        session = dict(base)
        interaction = dict(session.get("interaction")) if isinstance(session.get("interaction"), dict) else {}
        request_choices = [str(choice) for choice in request.get("choices") or [] if str(choice).strip()]
        interaction["question"] = normalize_text(request.get("question")) or normalize_text(interaction.get("question"))
        interaction["approval_type"] = normalize_text(request.get("approval_type")) or normalize_text(interaction.get("approval_type"))
        interaction["choices"] = request_choices or [str(choice) for choice in interaction.get("choices") or [] if str(choice).strip()]
        session["interaction"] = interaction
        session["source"] = normalize_text(request.get("source")) or normalize_text(session.get("source"))
        session["state"] = "blocked"
        session["summary"] = normalize_text(request.get("summary")) or normalize_text(session.get("summary")) or "Approval needed"
        session["title"] = normalize_text(request.get("title")) or normalize_text(session.get("title")) or "Approval needed"
        session["task_label"] = (
            normalize_text(request.get("task_label"))
            or normalize_text(session.get("task_label"))
            or normalize_text(session.get("title"))
            or normalize_text(request.get("title"))
        )
        session["updated_at"] = normalize_text(request.get("updated_at")) or normalize_text(session.get("updated_at"))
        session["created_at"] = normalize_text(request.get("created_at")) or normalize_text(session.get("created_at"))
        session["cwd"] = normalize_text(request.get("cwd")) or normalize_text(session.get("cwd")) or normalize_text(session.get("workspace"))
        session["workspace"] = normalize_text(session.get("workspace")) or normalize_text(session.get("cwd")) or normalize_text(request.get("cwd"))
        request_jump = request.get("jump_target") if isinstance(request.get("jump_target"), dict) else {}
        base_jump = session.get("jump_target") if isinstance(session.get("jump_target"), dict) else {}
        if request_jump:
            session["jump_target"] = {
                **base_jump,
                **{key: value for key, value in request_jump.items() if value not in (None, "", [])},
            }
        return session

    def _build_peek_preview(self, session: dict[str, Any]) -> list[str]:
        collaboration = session.get("collaboration") if isinstance(session.get("collaboration"), dict) else {}
        if collaboration:
            raw_lines = (session.get("peek") or {}).get("preview_lines") or []
            return recent_meaningful_lines([str(line) for line in raw_lines], limit=8)

        raw_source = str(session.get("source") or "")
        jump_target = session.get("jump_target") if isinstance(session.get("jump_target"), dict) else {}
        jump_pid = extract_live_process_pid(str(session.get("id") or "")) or jump_target.get("pid")
        try:
            jump_pid = int(jump_pid) if jump_pid is not None else None
        except Exception:
            jump_pid = None

        recovered_hint = recover_local_session_hint(
            raw_source,
            str(session.get("cwd") or session.get("workspace") or ""),
            pid=jump_pid,
        )
        interaction = session.get("interaction") or {}
        review_payload = session.get("review") if isinstance(session.get("review"), dict) else {}
        state_text = str(session.get("state") or "running").replace("_", " ").title()
        display_summary = normalize_text(session.get("summary") or "")
        if is_generic_title(display_summary, raw_source, str(session.get("cwd") or session.get("workspace") or "")):
            preview_lines = recent_meaningful_lines(recovered_hint.get("preview_lines", []), limit=6)
            if preview_lines:
                display_summary = preview_lines[-1]
        review_fields = derive_review_fields(
            source=raw_source,
            approval_type=str(interaction.get("approval_type") or ""),
            question=str(interaction.get("question") or ""),
            summary=str(session.get("summary") or ""),
            title=str(session.get("title") or ""),
            cwd=str(session.get("cwd") or ""),
            workspace=str(session.get("workspace") or ""),
            state_text=state_text,
            review_payload=review_payload,
        )
        return build_peek_lines(
            source=raw_source,
            cwd=str(session.get("cwd") or ""),
            summary=display_summary or str(session.get("summary") or ""),
            question=str(interaction.get("question") or ""),
            review_command=review_fields["reviewCommand"],
            review_reason=review_fields["reviewReason"],
            recovered_hint=recovered_hint,
        )

    def _dispatch_command(self, command: list[str], session_id: str, *, label: str) -> None:
        def run_command():
            result = subprocess.run(
                command,
                cwd=ROOT.parent.parent,
                check=False,
                capture_output=True,
                text=True,
            )
            if result.stdout.strip():
                print(result.stdout.strip())
            if result.stderr.strip():
                print(result.stderr.strip(), file=sys.stderr)
            if result.returncode != 0:
                print(f"{label} failed for {session_id} with exit code {result.returncode}", file=sys.stderr)
            message = result.stdout.strip() or result.stderr.strip()
            self.responseFinished.emit(session_id, result.returncode == 0, message)

        threading.Thread(target=run_command, daemon=True).start()

    def _dispatch_response(self, session: dict[str, Any], *, choice_index: int = 0, choice_text: str = "", followup_text: str = "") -> None:
        session_id = str(session.get("id") or "")
        command = [
            sys.executable,
            str(TOOLS_BRIDGE),
            "respond",
            "--session-json",
            json.dumps(session, ensure_ascii=False),
        ]
        if followup_text.strip():
            command.extend(["--choice-index", str(choice_index or 3), "--followup-text", followup_text.strip()])
        elif choice_index > 0:
            command.extend(["--choice-index", str(choice_index)])
        elif choice_text.strip():
            command.extend(["--text", choice_text.strip()])
        self._dispatch_command(command, session_id, label="Respond")

    def _queue_telegram_response_feedback(self, session_id: str, chat_id: str, success_text: str, failure_text: str) -> None:
        normalized_session = normalize_text(session_id)
        normalized_chat = normalize_text(chat_id)
        if not normalized_session or not normalized_chat:
            return
        self._telegram_response_feedback[normalized_session] = (
            normalized_chat,
            success_text,
            failure_text,
        )

    def _handle_response_finished_feedback(self, session_id: str, ok: bool, message: str) -> None:
        normalized_session = normalize_text(session_id)
        feedback = self._telegram_response_feedback.pop(normalized_session, None)
        if not feedback:
            return
        chat_id, success_text, failure_text = feedback
        if not chat_id:
            return
        if ok:
            self._telegram_send_message(chat_id, success_text)
            return
        detail = normalize_text(message)
        payload = failure_text
        if detail:
            payload = f"{failure_text}\n{truncate(detail, 180)}"
        self._telegram_send_message(chat_id, payload)

    def _dispatch_peek_message(self, session: dict[str, Any], message_text: str) -> None:
        session_id = str(session.get("id") or "")
        command = [
            sys.executable,
            str(TOOLS_BRIDGE),
            "send-peek",
            "--session-json",
            json.dumps(session, ensure_ascii=False),
            "--text",
            re.sub(r"\s+", " ", str(message_text or "")).strip(),
            "--return-focus-pid",
            str(os.getpid()),
        ]
        self._dispatch_command(command, session_id, label="Peek send")

    def _init_sound_effects(self) -> None:
        if self._sound_effects_initialized:
            return
        self._sound_effects_initialized = True
        if not SOUND_ASSET_DIR.exists():
            return
        for player in (
            ["pw-play"],
            ["paplay"],
            ["aplay", "-q"],
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error"],
        ):
            if shutil.which(player[0]):
                self._sound_player = player
                break
        for sound_id, filename in {
            "approval": "approval.wav",
            "completed": "completed.wav",
            "peek-send": "peek-send.wav",
            "toggle": "toggle.wav",
        }.items():
            sound_path = SOUND_ASSET_DIR / filename
            if not sound_path.exists():
                continue
            self._sound_effects[sound_id] = str(sound_path)

    def _set_connected(self, connected: bool):
        if self._connected != connected:
            self._connected = connected
            self.connectedChanged.emit()

    def refresh(self):
        snapshot = self.fetch_snapshot_once()
        self._apply_snapshot(snapshot)

    def _build_usage_snapshot(self, sessions: list[dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
        return usage_display_snapshot(
            self._started_at,
            self._raw_sessions if sessions is None else sessions,
            self._usage_baseline,
        )

    def _refresh_usage_snapshot(self, force: bool = False, sessions: list[dict[str, Any]] | None = None) -> None:
        now = time.monotonic()
        if not force and now - self._last_usage_refresh_at < USAGE_REFRESH_INTERVAL_SECONDS:
            return
        self._last_usage_refresh_at = now
        self.usageSnapshotReady.emit(self._build_usage_snapshot(sessions))

    def _apply_usage_snapshot(self, updated_usage: dict[str, dict[str, Any]]) -> None:
        if updated_usage == self._usage:
            return
        self._usage = updated_usage
        self.usageChanged.emit()

    def _apply_snapshot(self, snapshot):
        collab_sessions = collaboration_raw_sessions()
        snapshot_sessions = snapshot.get("sessions", [])
        pending_approval_requests = self._pending_approval_requests()
        approval_sessions = [
            session
            for session in (
                self._session_with_pending_approval(request)
                for request in pending_approval_requests
            )
            if isinstance(session, dict)
        ]
        sessions = snapshot_sessions + collab_sessions + approval_sessions
        enriched_snapshot = dict(snapshot)
        enriched_snapshot["sessions"] = sessions
        enriched_snapshot["pending_approval_requests"] = pending_approval_requests
        enriched_snapshot["active_count"] = int(snapshot.get("active_count", len(snapshot_sessions))) + len(
            [session for session in collab_sessions if normalize_text(session.get("state")).lower() != "completed"]
        )
        enriched_snapshot["blocked_count"] = int(snapshot.get("blocked_count", 0)) + len(
            [session for session in collab_sessions if normalize_text(session.get("state")).lower() in {"waiting_user", "blocked"}]
        ) + len(approval_sessions)
        enriched_snapshot["active_count"] += len(
            [session for session in approval_sessions if normalize_text(session.get("state")).lower() != "completed"]
        )
        previous_raw_sessions = self._raw_sessions
        self._raw_sessions = sessions
        self._refresh_usage_snapshot(sessions=sessions)
        signature = snapshot_signature(enriched_snapshot, sessions)
        if signature == self._snapshot_signature:
            return
        previous_sessions = {session["id"]: session for session in previous_raw_sessions}
        self._snapshot_signature = signature

        snapshot_quiet = snapshot.get("quiet_mode")
        if self._loaded_prefs is None and isinstance(snapshot_quiet, dict):
            quiet_enabled = bool(snapshot_quiet.get("enabled", self._quiet_mode))
            if quiet_enabled != self._quiet_mode:
                self._quiet_mode = quiet_enabled
                self.quietModeChanged.emit()

        pretty_sessions = []
        prompt_session = {}
        timeline_entries = []
        for session in sessions:
            collaboration = session.get("collaboration") if isinstance(session.get("collaboration"), dict) else {}
            if collaboration:
                updated_at = str(session.get("updated_at") or snapshot.get("generated_at") or "")
                seconds_since_update = age_seconds(updated_at)
                state_text = str(session.get("state") or "running").replace("_", " ").title()
                pretty = {
                    "id": session["id"],
                    "title": normalize_text(session.get("title")) or "Collaboration",
                    "rawTitle": normalize_text(session.get("title")),
                    "displayTitle": normalize_text(session.get("title")) or "Collaboration",
                    "taskLabel": normalize_text(session.get("task_label")) or normalize_text(session.get("title")) or "Collaboration",
                    "contextLabel": first_text(
                        f"Collab · {workspace_name(collaboration.get('workspace'))}",
                        workspace_name(collaboration.get("workspace")),
                    ),
                    "workspaceLabel": workspace_name(collaboration.get("workspace")),
                    "terminalLabel": "",
                    "source": "Collab",
                    "state": state_text,
                    "summary": normalize_text(session.get("summary")) or "Collaboration ready",
                    "attention": int(session.get("attention_score", 0)),
                    "updated": age_label(updated_at),
                    "updatedAt": updated_at,
                    "ageSeconds": seconds_since_update if seconds_since_update is not None else -1,
                    "jumpable": True,
                    "peekable": bool((session.get("peek") or {}).get("preview_lines")),
                    "peekSendable": False,
                    "question": "",
                    "choices": [],
                    "approvalType": "",
                    "responseAgeSeconds": -1,
                    "responseUrgency": "none",
                    "stuck": False,
                    "stale": False,
                    "healthKind": "collab",
                    "healthLabel": normalize_text(collaboration.get("current_phase")).replace("_", " ").title() or "Collab",
                    "healthDetail": normalize_text(collaboration.get("next_action")) or normalize_text(session.get("summary")),
                    "reviewHeadline": normalize_text(collaboration.get("strategy")).replace("_", " ").title() or "Bridge",
                    "reviewCommand": normalize_text(collaboration.get("current_actor")).title() or "Multi-agent",
                    "reviewReason": normalize_text(collaboration.get("next_action")),
                    "reviewScope": workspace_name(collaboration.get("workspace")),
                    "reviewRisk": normalize_text(collaboration.get("strategy")).replace("_", " "),
                    "peekLines": [str(line) for line in (session.get("peek") or {}).get("preview_lines") or [] if normalize_text(line)],
                    "artifactSessionId": normalize_text(collaboration.get("session_name")),
                    "needsResponse": state_text in {"Blocked", "Waiting User"},
                    "isCollabSession": True,
                    "collabSessionName": normalize_text(collaboration.get("session_name")),
                    "collabPhase": normalize_text(collaboration.get("current_phase")),
                    "collabStrategy": normalize_text(collaboration.get("strategy")),
                    "collabCurrentActor": normalize_text(collaboration.get("current_actor")),
                    "collabNextActor": normalize_text(collaboration.get("next_actor")),
                    "collabNextAction": normalize_text(collaboration.get("next_action")),
                    "collabClaudeStatus": normalize_text(((collaboration.get("claude") or {}).get("status"))),
                    "collabCodexStatus": normalize_text(((collaboration.get("codex") or {}).get("status"))),
                    "collabClaudeMode": normalize_text(((collaboration.get("claude") or {}).get("mode"))),
                    "collabCodexMode": normalize_text(((collaboration.get("codex") or {}).get("mode"))),
                }
                pretty_sessions.append(pretty)
                previous = previous_sessions.get(pretty["id"])
                if previous is None or previous.get("summary") != pretty["summary"] or previous.get("state") != pretty["state"]:
                    timeline_entries.append(
                        self._timeline_entry(
                            pretty,
                            "updated",
                            "Collab",
                            pretty["summary"],
                        )
                    )
                continue

            raw_source = str(session.get("source") or "")
            jump_target = session.get("jump_target") if isinstance(session.get("jump_target"), dict) else {}
            jump_pid = extract_live_process_pid(str(session.get("id") or "")) or jump_target.get("pid")
            try:
                jump_pid = int(jump_pid) if jump_pid is not None else None
            except Exception:
                jump_pid = None
            recovered_hint = recover_local_session_hint(
                raw_source,
                str(session.get("cwd") or session.get("workspace") or ""),
                pid=jump_pid,
            )
            artifacts_payload = session.get("artifacts") if isinstance(session.get("artifacts"), dict) else {}
            interaction = session.get("interaction") or {}
            review_payload = session.get("review") if isinstance(session.get("review"), dict) else {}
            choices = [str(choice) for choice in interaction.get("choices") or [] if str(choice).strip()]
            approval_type = str(interaction.get("approval_type") or "").strip()
            updated_at = str(session.get("updated_at") or snapshot.get("generated_at") or "")
            seconds_since_update = age_seconds(updated_at)
            state_text = str(session["state"]).replace("_", " ").title()
            stuck_payload = session.get("stuck") if isinstance(session.get("stuck"), dict) else {}
            stuck = bool(stuck_payload.get("is_stuck", False))
            stale = False
            health_kind = "running"
            health_label = "Active"
            health_detail = session["summary"]
            if state_text == "Blocked" or state_text == "Waiting User":
                health_kind = "blocked"
                health_label = "Needs approval"
                health_detail = "Waiting for your decision"
                if stuck:
                    health_detail = str(stuck_payload.get("reason") or "Waiting for approval for too long")
            elif state_text == "Failed":
                health_kind = "failed"
                health_label = "Failed"
                health_detail = "Needs a restart or a closer look"
            elif state_text == "Completed":
                health_kind = "done"
                health_label = "Completed"
                health_detail = "Ready to jump back"
            elif state_text == "Stale":
                health_kind = "stale"
                health_label = "Stale"
                stale = True
                health_detail = "No heartbeat is coming through"
            elif stuck:
                health_kind = "stuck"
                health_label = "Possibly stuck"
                health_detail = str(stuck_payload.get("reason") or f"No progress for {stuck_payload.get('stalled_for_seconds', 'a while')}s")
            elif seconds_since_update is not None and seconds_since_update >= 900:
                if state_text == "Running":
                    health_kind = "stuck"
                    health_label = "Possibly stuck"
                    stuck = True
                    health_detail = f"No progress for {age_label(updated_at)}"
                else:
                    health_kind = "stale"
                    health_label = "Stale"
                    stale = True
                    health_detail = f"No fresh update for {age_label(updated_at)}"
            elif state_text == "Running":
                if seconds_since_update is not None and seconds_since_update >= 300:
                    health_kind = "running_slow"
                    health_label = "Still working"
                    health_detail = f"Quiet for {age_label(updated_at)}"
                else:
                    health_detail = "Working normally"
            elif state_text == "Completed":
                health_detail = "Ready to jump back"
            display_title = derive_session_task_label(
                source=raw_source,
                title=str(session.get("title") or ""),
                summary=str(session.get("summary") or ""),
                question=str(interaction.get("question") or ""),
                approval_type=approval_type,
                cwd=str(session.get("cwd") or ""),
                display_title=str(session.get("collapsed_headline") or session.get("display_title") or ""),
                task_label=str(session.get("task_label") or ""),
                review_title=first_text(review_payload.get("headline"), review_payload.get("title")),
                recovered_hint=recovered_hint,
            )
            display_summary = normalize_text(session.get("summary") or "")
            if (
                is_generic_title(display_summary, raw_source, str(session.get("cwd") or session.get("workspace") or ""))
                or display_summary == "Approval remembered. Agent resuming."
            ):
                preview_lines = recovered_hint.get("preview_lines") if isinstance(recovered_hint, dict) else []
                if preview_lines:
                    display_summary = normalize_text(preview_lines[-1])
            context_label = first_text(
                session.get("context_label"),
                derive_context_label(
                    raw_source,
                    str(session.get("cwd") or session.get("workspace") or ""),
                    str(jump_target.get("terminal") or ""),
                    str(jump_target.get("tty") or ""),
                ),
            )
            review_fields = derive_review_fields(
                source=raw_source,
                approval_type=approval_type,
                question=str(interaction.get("question") or ""),
                summary=str(session.get("summary") or ""),
                title=str(session.get("title") or ""),
                cwd=str(session.get("cwd") or ""),
                workspace=str(session.get("workspace") or ""),
                state_text=state_text,
                review_payload=review_payload,
            )
            response_age_seconds = seconds_since_update if (bool(choices) or bool(interaction.get("question")) or bool(approval_type)) else -1
            if response_age_seconds is None:
                response_age_seconds = -1
            response_urgency = "none"
            if response_age_seconds >= 75:
                response_urgency = "critical"
            elif response_age_seconds >= 30:
                response_urgency = "warning"
            pretty = {
                "id": session["id"],
                "title": display_title,
                "rawTitle": str(session.get("title") or ""),
                "displayTitle": display_title,
                "taskLabel": display_title,
                "contextLabel": context_label,
                "workspaceLabel": workspace_name(str(session.get("cwd") or session.get("workspace") or "")),
                "terminalLabel": first_text(jump_target.get("terminal"), jump_target.get("tty")),
                "source": raw_source.replace("_", " ").title(),
                "state": state_text,
                "summary": display_summary or str(session.get("summary") or ""),
                "attention": int(session.get("attention_score", 0)),
                "updated": age_label(updated_at),
                "updatedAt": updated_at,
                "ageSeconds": seconds_since_update if seconds_since_update is not None else -1,
                "jumpable": bool(
                    jump_target.get("tmux_pane")
                    or jump_target.get("tmux_window")
                    or jump_target.get("pid")
                    or session.get("cwd")
                    or session.get("workspace")
                ),
                "peekable": bool(recovered_hint.get("preview_lines") or recovered_hint.get("transcript_path") or jump_target.get("tty")),
                "peekSendable": peek_send_supported(jump_target),
                "question": str(interaction.get("question") or "").strip(),
                "choices": choices,
                "approvalType": approval_type,
                "responseAgeSeconds": response_age_seconds,
                "responseUrgency": response_urgency,
                "stuck": stuck,
                "stale": stale,
                "healthKind": health_kind,
                "healthLabel": health_label,
                "healthDetail": health_detail,
                "reviewHeadline": review_fields["reviewHeadline"],
                "reviewCommand": review_fields["reviewCommand"],
                "reviewReason": review_fields["reviewReason"],
                "reviewScope": review_fields["reviewScope"],
                "reviewRisk": review_fields["reviewRisk"],
                "peekLines": build_peek_lines(
                    source=raw_source,
                    cwd=str(session.get("cwd") or ""),
                    summary=display_summary or str(session.get("summary") or ""),
                    question=str(interaction.get("question") or ""),
                    review_command=review_fields["reviewCommand"],
                    review_reason=review_fields["reviewReason"],
                    recovered_hint=recovered_hint,
                ),
                "artifactSessionId": first_text(
                    recovered_hint.get("session_id"),
                    artifacts_payload.get("session_id"),
                    artifacts_payload.get("source_session_id"),
                ),
                "jumpPid": str(jump_pid or jump_target.get("pid") or ""),
                "jumpTty": str(jump_target.get("tty") or ""),
                "jumpTerminal": str(jump_target.get("terminal") or ""),
            }
            if not pretty["choices"] and pretty["approvalType"] and state_text in {"Blocked", "Waiting User"}:
                pretty["choices"] = fallback_response_choices(raw_source, approval_type, pretty["summary"])
            pretty["needsResponse"] = bool(
                state_text in {"Blocked", "Waiting User"}
                and (pretty["question"] or pretty["choices"] or pretty["approvalType"])
            )
            pretty_sessions.append(pretty)
            if not prompt_session and pretty["needsResponse"]:
                prompt_session = pretty

            previous = previous_sessions.get(pretty["id"])
            if previous is None:
                timeline_entries.append(
                    self._timeline_entry(
                        pretty,
                        "started",
                        "Session started",
                        pretty["summary"],
                    )
                )
                continue

            previous_state = str(previous.get("state") or "").replace("_", " ").title()
            previous_summary = str(previous.get("summary") or "")
            previous_needs_response = bool(previous.get("needsResponse"))
            current_needs_response = bool(pretty["needsResponse"])

            if previous_state != pretty["state"]:
                if pretty["state"] in {"Blocked", "Waiting User"}:
                    timeline_entries.append(
                        self._timeline_entry(
                            pretty,
                            "approval",
                            "Approval needed",
                            pretty["question"] or pretty["summary"],
                        )
                    )
                elif pretty["state"] == "Running" and previous_state in {"Blocked", "Waiting User"}:
                    timeline_entries.append(
                        self._timeline_entry(
                            pretty,
                            "resumed",
                            "Resumed",
                            "Continued after approval",
                        )
                    )
                elif pretty["state"] == "Completed":
                    timeline_entries.append(
                        self._timeline_entry(
                            pretty,
                            "completed",
                            "Completed",
                            pretty["summary"],
                        )
                    )
                elif pretty["state"] == "Failed":
                    timeline_entries.append(
                        self._timeline_entry(
                            pretty,
                            "failed",
                            "Failed",
                            pretty["summary"],
                        )
                    )
                elif pretty["state"] == "Stale":
                    timeline_entries.append(
                        self._timeline_entry(
                            pretty,
                            "stale",
                            "Stale",
                            "No heartbeat",
                        )
                    )
                else:
                    timeline_entries.append(
                        self._timeline_entry(
                            pretty,
                            "updated",
                            "State changed",
                            pretty["summary"],
                        )
                    )
            elif previous_summary != pretty["summary"] or previous_needs_response != current_needs_response:
                timeline_entries.append(
                    self._timeline_entry(
                        pretty,
                        "updated",
                        "Updated",
                        pretty["summary"],
                    )
                )

        pretty_sessions = dedupe_display_sessions(pretty_sessions)
        prompt_session = next((item for item in pretty_sessions if item.get("needsResponse")), {})
        previous_prompt_present = bool(self._prompt_session)
        previous_prompt_id = normalize_text(self._prompt_session.get("id") if isinstance(self._prompt_session, dict) else "")
        previous_blocked_count = int(self._blocked_count)
        previous_prompt_key = self._prompt_key_for_session(self._prompt_session)

        self._sessions = pretty_sessions
        self._prompt_session = prompt_session
        self._active_count = len(pretty_sessions)
        self._blocked_count = sum(
            1
            for item in pretty_sessions
            if normalize_text(item.get("state")).lower() in {"blocked", "waiting user"} or bool(item.get("needsResponse"))
        )
        snapshot_timeline = snapshot.get("timeline") if isinstance(snapshot.get("timeline"), list) else []
        normalized_snapshot_timeline = [
            self._normalize_timeline_item(item)
            for item in snapshot_timeline
            if isinstance(item, dict)
        ]
        self._timeline = self._merge_timeline_entries(
            normalized_snapshot_timeline,
            timeline_entries,
            self._timeline,
        )

        self._play_event_cue(pretty_sessions)

        current_prompt_key = self._prompt_key_for_session(self._prompt_session)
        prompt_is_new = bool(current_prompt_key) and current_prompt_key != previous_prompt_key
        prompt_is_suppressed = bool(current_prompt_key) and current_prompt_key == self._suppressed_prompt_key

        if self._prompt_session:
            self._headline = "Approve or reply"
            if self._prompt_attention_enabled and prompt_is_new and not prompt_is_suppressed and not self._expanded:
                self._expanded = True
                self.expandedChanged.emit()
            if self._prompt_attention_enabled and prompt_is_new and not prompt_is_suppressed:
                self.attentionRequested.emit()
        elif self._blocked_count:
            self._headline = "Attention needed"
        elif self._active_count:
            self._headline = "Agents cruising"
        else:
            self._headline = "Waiting for agents"
        if not self._prompt_session and previous_prompt_present:
            self._suppressed_prompt_key = ""

        self.sessionsChanged.emit()
        self.timelineChanged.emit()
        self.countsChanged.emit()
        self.headlineChanged.emit()
        self.snapshotChanged.emit()

    def _play_event_cue(self, sessions):
        if self._quiet_mode:
            self._previous_states = {session["id"]: session["state"] for session in sessions}
            return
        now = time.monotonic()
        if now - self._last_sound_at < 0.35:
            self._previous_states = {session["id"]: session["state"] for session in sessions}
            return

        urgent_triggered = False
        completed_triggered = False
        for session in sessions:
            previous = self._previous_states.get(session["id"])
            current = session["state"]
            if current in {"Blocked", "Waiting User"} and previous != current:
                urgent_triggered = True
                break
            if current == "Completed" and previous != current:
                completed_triggered = True

        self._previous_states = {session["id"]: session["state"] for session in sessions}

        if urgent_triggered:
            self._play_sound("approval")
        elif completed_triggered:
            self._play_sound("completed")

    def _play_sound(self, sound_id: str):
        self._last_sound_at = time.monotonic()
        if not self._sound_effects_initialized:
            self._init_sound_effects()
        sound_path = self._sound_effects.get(sound_id)
        if sound_path and self._sound_player:
            try:
                subprocess.Popen(
                    [*self._sound_player, sound_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            except Exception:
                pass
        if shutil.which("canberra-gtk-play"):
            try:
                subprocess.Popen(
                    ["canberra-gtk-play", "-i", sound_id],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            except Exception:
                pass

        try:
            QGuiApplication.beep()
        except Exception:
            pass

    def fetch_snapshot_once(self):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(0.8)
                client.connect(self._socket_path)
                client.sendall(b'{"type":"snapshot"}\n')

                buffer = b""
                while not buffer.endswith(b"\n"):
                    chunk = client.recv(65536)
                    if not chunk:
                        break
                    buffer += chunk

            data = json.loads(buffer.decode("utf-8").strip())
            self._set_connected(True)
            return data["snapshot"]
        except Exception:
            self._set_connected(False)
            with self._state_path.open("r", encoding="utf-8") as handle:
                return json.load(handle)

    def _send_quiet_mode(self):
        payload = {
            "type": "set_quiet_mode",
            "enabled": self._quiet_mode,
            "reason": "shell-toggle",
        }
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(0.4)
                client.connect(self._socket_path)
                client.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
                buffer = b""
                while not buffer.endswith(b"\n"):
                    chunk = client.recv(65536)
                    if not chunk:
                        break
                    buffer += chunk
        except Exception:
            pass

    def _telegram_api_call(self, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        token = self._telegram_bot_token.strip()
        if not token:
            return {}
        url = f"https://api.telegram.org/bot{token}/{method}"
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(request, timeout=8.0) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read().decode("utf-8")
            except Exception:
                raw = ""
            if raw:
                try:
                    data = json.loads(raw)
                    return data if isinstance(data, dict) else {}
                except Exception:
                    return {}
            return {}
        except Exception:
            return {}
        try:
            data = json.loads(raw)
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def _telegram_send_message(self, chat_id: str, text: str, *, reply_markup: dict[str, Any] | None = None) -> bool:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        response = self._telegram_api_call("sendMessage", payload)
        return bool(response.get("ok"))

    def _telegram_callback_token(self, session: dict[str, Any]) -> str:
        request = self._approval_request_for_session(session)
        if request:
            return self._approval_request_token(request)
        source = normalize_text(session.get("source")).lower() or "agent"
        session_id = normalize_text(session.get("id"))
        digest = hashlib.sha1(f"{source}:{session_id}".encode("utf-8")).hexdigest()
        return digest[:10]

    def _telegram_resolve_session(self, token: str) -> dict[str, Any] | None:
        normalized = normalize_text(token)
        if not normalized:
            return None
        for request_path in self._approval_request_files():
            request = self._read_json_file_maybe(request_path)
            if not request or normalize_text(request.get("source")) == "":
                continue
            if self._approval_request_token(request) == normalized:
                return self._session_from_approval_request(request, normalized)
        prompt_session_id = normalize_text(self._prompt_session.get("id")) if isinstance(self._prompt_session, dict) else ""
        if prompt_session_id and self._telegram_callback_token(self._prompt_session) == normalized:
            raw_prompt = self._find_raw_session(prompt_session_id)
            if raw_prompt:
                return raw_prompt
        for session in self._sessions:
            if self._telegram_callback_token(session) == normalized:
                raw = self._find_raw_session(str(session.get("id") or ""))
                if raw:
                    return raw
        for request_path in self._approval_request_files():
            request = self._read_json_file_maybe(request_path)
            if not request or normalize_text(request.get("source")) == "":
                continue
            candidate_ids = [
                normalize_text(request.get("ui_session_id")),
                normalize_text(request.get("session_id")),
            ]
            for candidate_id in candidate_ids:
                if not candidate_id:
                    continue
                if self._telegram_callback_token({"source": request.get("source"), "id": candidate_id}) == normalized:
                    return self._session_from_approval_request(request, normalized)
        return None

    def _telegram_poll_updates(self) -> None:
        if not self._telegram_bot_token:
            return
        payload = {
            "timeout": 0,
            "allowed_updates": ["message", "callback_query"],
        }
        if self._telegram_last_update_id > 0:
            payload["offset"] = self._telegram_last_update_id + 1
        response = self._telegram_api_call("getUpdates", payload)
        updates = response.get("result") if isinstance(response.get("result"), list) else []
        for item in updates:
            if not isinstance(item, dict):
                continue
            update_id = int(item.get("update_id") or 0)
            if update_id > self._telegram_last_update_id:
                self._telegram_last_update_id = update_id
            callback = item.get("callback_query") if isinstance(item.get("callback_query"), dict) else {}
            if callback:
                self._handle_telegram_callback(callback)
                continue
            message = item.get("message") if isinstance(item.get("message"), dict) else {}
            if message:
                self._handle_telegram_message(message)
        if updates:
            self._write_view_prefs()

    def _handle_telegram_message(self, message: dict[str, Any]) -> None:
        chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
        chat_id = str(chat.get("id") or "").strip()
        text = str(message.get("text") or "").strip()
        if not chat_id:
            return
        if text.startswith("/start"):
            self._telegram_chat_id = chat_id
            self._telegram_status = f"Telegram paired and saved with {chat_id}"
            self.telegramChanged.emit()
            self._write_view_prefs()
            self._telegram_send_message(chat_id, "Vibe Island paired. Approval requests will appear here when Telegram notifications are enabled.")
            return
        target_token = self._telegram_reply_targets.get(chat_id)
        if target_token and text:
            session = self._telegram_resolve_session(target_token)
            if session:
                self._queue_telegram_response_feedback(
                    str(session.get("id") or ""),
                    chat_id,
                    "Reply delivered. The agent should continue with your instruction.",
                    "The reply could not be delivered to the agent.",
                )
                self._dispatch_response(session, choice_index=3, followup_text=text)
            else:
                self._telegram_send_message(chat_id, "That approval request is no longer active.")
            self._telegram_reply_targets.pop(chat_id, None)
            return

    def _handle_telegram_callback(self, callback: dict[str, Any]) -> None:
        data = str(callback.get("data") or "").strip()
        message = callback.get("message") if isinstance(callback.get("message"), dict) else {}
        chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
        chat_id = str(chat.get("id") or "").strip()
        callback_id = str(callback.get("id") or "").strip()
        if not data:
            return
        parts = data.split("|")
        if len(parts) != 3 or parts[0] != "vi":
            return
        token = parts[1]
        action = parts[2]
        session = self._telegram_resolve_session(token)
        answer_text = "Done"
        if not session:
            answer_text = "Request already cleared"
        elif action == "reply":
            self._telegram_reply_targets[chat_id] = token
            answer_text = "Send your reply text in this chat"
            self._telegram_send_message(chat_id, "Reply with what the agent should do differently. Your next Telegram message will be sent as option 3.")
        else:
            choice_index = 1
            success_text = "Approval sent. The agent should resume shortly."
            failure_text = "The approval could not be delivered to the agent."
            if action == "allow-session":
                choice_index = 2
                success_text = "Session permission sent. The agent should resume shortly."
            elif action == "deny":
                choice_index = 3
                success_text = "Deny decision sent to the agent."
                failure_text = "The deny decision could not be delivered to the agent."
            self._queue_telegram_response_feedback(
                str(session.get("id") or ""),
                chat_id,
                success_text,
                failure_text,
            )
            self._dispatch_response(session, choice_index=choice_index)
            answer_text = "Decision sent"
        if callback_id:
            self._telegram_api_call("answerCallbackQuery", {"callback_query_id": callback_id, "text": answer_text, "show_alert": False})

    def _telegram_notification_markup(self, session: dict[str, Any]) -> dict[str, Any]:
        token = self._telegram_callback_token(session)
        return {
            "inline_keyboard": [
                [
                    {"text": "Allow once", "callback_data": f"vi|{token}|allow-once"},
                    {"text": "Allow session", "callback_data": f"vi|{token}|allow-session"},
                ],
                [
                    {"text": "Reply / deny", "callback_data": f"vi|{token}|reply"},
                ],
            ]
        }

    def _telegram_should_notify_session(self, session: dict[str, Any]) -> bool:
        if not isinstance(session, dict):
            return False
        if bool(session.get("isCollabSession")):
            return False
        if not bool(session.get("needsResponse")):
            return False
        state_text = normalize_text(session.get("state"))
        if state_text not in {"Blocked", "Waiting User"}:
            return False
        source_text = normalize_text(session.get("source")).lower()
        if source_text not in {"claude", "codex"}:
            return False
        choices = session.get("choices") if isinstance(session.get("choices"), list) else []
        if len(choices) == 0:
            return False
        approval_type = normalize_text(session.get("approvalType"))
        question = normalize_text(session.get("question"))
        if not choices and not approval_type and not question:
            return False
        summary = normalize_text(session.get("summary")).lower()
        title = normalize_text(session.get("title")).lower()
        detail = normalize_text(session.get("reviewCommand")).lower()
        combined = "\n".join([title, question.lower(), summary, detail])
        if title in {"system", "bridge"}:
            return False
        noise_markers = (
            "bridge mode is active",
            "headless unavailable",
            "invalid_request_error",
            "collaboration ui",
            "review the collaboration",
            "system\n",
        )
        if any(marker in combined for marker in noise_markers):
            return False
        return True

    def _telegram_message_digest(self, session: dict[str, Any]) -> str:
        parts = [
            normalize_text(session.get("id")),
            normalize_text(session.get("source")),
            normalize_text(session.get("question")),
            normalize_text(session.get("summary")),
            normalize_text(session.get("reviewCommand")),
            "|".join(str(item).strip() for item in (session.get("choices") or []) if str(item).strip()),
        ]
        return hashlib.sha1("||".join(parts).encode("utf-8")).hexdigest()

    def _telegram_notification_text(self, session: dict[str, Any]) -> str:
        title = normalize_text(session.get("title")) or "Approval needed"
        source = normalize_text(session.get("source")) or "Agent"
        question = normalize_text(session.get("question")) or "The agent is waiting for your decision."
        detail = normalize_text(session.get("reviewCommand")) or normalize_text(session.get("summary"))
        choices = [str(item).strip() for item in (session.get("choices") or []) if str(item).strip()]
        lines = [f"{source}: {title}", question]
        if detail and detail != question:
            lines.append(detail)
        for index, choice in enumerate(choices[:3], start=1):
            lines.append(f"{index}. {choice}")
        lines.append("Reply / deny lets you type a custom instruction from Telegram.")
        return "\n".join(lines)

    def _maybe_notify_telegram(self) -> None:
        if not (self._telegram_enabled and self._telegram_bot_token and self._telegram_chat_id):
            return
        now = time.time()
        active_tokens = set()
        for session in self._sessions:
            if not self._telegram_should_notify_session(session):
                continue
            token = self._telegram_callback_token(session)
            active_tokens.add(token)
            digest = self._telegram_message_digest(session)
            notification_state = self._telegram_notified_sessions.get(token, {})
            last_sent = float(notification_state.get("sent_at", 0.0) or 0.0)
            last_digest = str(notification_state.get("digest") or "")
            if last_digest == digest:
                continue
            if now - last_sent < TELEGRAM_NOTIFICATION_COOLDOWN_SECONDS:
                continue
            sent = self._telegram_send_message(
                self._telegram_chat_id,
                self._telegram_notification_text(session),
                reply_markup=self._telegram_notification_markup(session),
            )
            if sent:
                self._telegram_notified_sessions[token] = {
                    "sent_at": now,
                    "digest": digest,
                    "title": normalize_text(session.get("title")),
                }
                self._telegram_status = f"Telegram sent {normalize_text(session.get('title')) or 'approval'}"
                self.telegramChanged.emit()
        stale_tokens = [token for token in self._telegram_notified_sessions if token not in active_tokens]
        for token in stale_tokens:
            self._telegram_notified_sessions.pop(token, None)

    def _telegram_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                if self._telegram_bot_token:
                    self._telegram_poll_updates()
                    self._maybe_notify_telegram()
            except Exception:
                pass
            self._stop_event.wait(TELEGRAM_POLL_INTERVAL_SECONDS)

    def _poll_loop(self):
        while not self._stop_event.is_set():
            try:
                self._subscribe_loop()
            except Exception:
                try:
                    snapshot = self.fetch_snapshot_once()
                    self.snapshotReady.emit(snapshot)
                    self._refresh_usage_snapshot(force=True, sessions=(snapshot.get("sessions") if isinstance(snapshot, dict) else None))
                except Exception:
                    self._refresh_usage_snapshot()
                time.sleep(1.0)

    def _subscribe_loop(self):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(1.0)
            client.connect(self._socket_path)
            client.sendall(b'{"type":"subscribe"}\n')
            self._set_connected(True)

            buffer = b""
            while not self._stop_event.is_set():
                try:
                    chunk = client.recv(65536)
                except (TimeoutError, socket.timeout):
                    self._refresh_usage_snapshot()
                    continue

                if not chunk:
                    raise ConnectionError("subscription closed")

                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line.strip():
                        continue
                    payload = json.loads(line.decode("utf-8"))
                    if payload.get("type") == "snapshot" and "snapshot" in payload:
                        self.snapshotReady.emit(payload["snapshot"])
                        self._refresh_usage_snapshot()

    def _resolve_prefs_path(self):
        override = os.environ.get("VIBEISLAND_SHELL_STATE")
        if override:
            return Path(override)
        return DEFAULT_PREFS

    def _load_prefs(self):
        try:
            if not self._prefs_path.exists():
                return None
            with self._prefs_path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return None

    def _apply_loaded_prefs(self):
        prefs = self._loaded_prefs or {}
        window = prefs.get("window", {})
        self._window_x = int(window.get("x", -1))
        self._window_y = int(window.get("y", 18))
        self._window_width, self._window_height = self._clamp_expanded_size(
            int(window.get("width", EXPANDED_DEFAULT_WIDTH)),
            int(window.get("height", EXPANDED_DEFAULT_HEIGHT)),
        )
        self._collapsed_width = self._clamp_collapsed_width(
            int(window.get("collapsed_width", COLLAPSED_DEFAULT_WIDTH))
        )
        self._window_x, self._window_y = self._clamp_window_position(
            self._window_x,
            self._window_y,
            self._window_width if bool(prefs.get("expanded", True)) else self._collapsed_width,
            self._window_height if bool(prefs.get("expanded", True)) else 58,
        )
        self._expanded = bool(prefs.get("expanded", True))
        self._replay_expanded = bool(prefs.get("replay_expanded", True))
        self._auto_expand_allowed = self._expanded
        self._quiet_mode = bool(prefs.get("quiet_mode", False))
        self._focus_mode = bool(prefs.get("focus_mode", False))
        self._pinned = bool(prefs.get("pinned", False))
        self._prompt_attention_enabled = bool(prefs.get("prompt_attention_enabled", True))
        telegram = prefs.get("telegram", {}) if isinstance(prefs.get("telegram"), dict) else {}
        self._telegram_bot_token = str(telegram.get("bot_token") or "").strip()
        self._telegram_chat_id = str(telegram.get("chat_id") or "").strip()
        self._telegram_enabled = bool(telegram.get("enabled", False) and self._telegram_bot_token)
        self._telegram_last_update_id = int(telegram.get("last_update_id", 0) or 0)
        if self._telegram_bot_token and self._telegram_chat_id:
            self._telegram_status = f"Telegram paired and saved with {self._telegram_chat_id}"
        elif self._telegram_bot_token:
            self._telegram_status = "Token saved. Send /start to the bot from Telegram to pair this machine."
        else:
            self._telegram_status = "Telegram notifications are off"
        self.geometryChanged.emit()
        self.expandedChanged.emit()
        self.replayExpandedChanged.emit()
        self.quietModeChanged.emit()
        self.focusModeChanged.emit()
        self.pinnedChanged.emit()
        self.promptAttentionChanged.emit()
        self.telegramChanged.emit()

    def _available_screen_geometry(self) -> tuple[int, int, int, int]:
        screen = None
        app = QGuiApplication.instance()
        if app is not None:
            screen = app.primaryScreen()
        if screen is None:
            return (0, 0, 1440, 900)
        geometry = screen.availableGeometry()
        width = max(int(geometry.width()), 720)
        height = max(int(geometry.height()), 560)
        return (int(geometry.x()), int(geometry.y()), width, height)

    def _clamp_expanded_size(self, width: int, height: int) -> tuple[int, int]:
        _, _, screen_width, screen_height = self._available_screen_geometry()
        max_width = max(EXPANDED_MIN_WIDTH, min(EXPANDED_MAX_WIDTH, int(screen_width * 0.82)))
        max_height = max(EXPANDED_MIN_HEIGHT, min(EXPANDED_MAX_HEIGHT, int(screen_height * 0.84)))
        clamped_width = max(EXPANDED_MIN_WIDTH, min(int(width or EXPANDED_DEFAULT_WIDTH), max_width))
        clamped_height = max(EXPANDED_MIN_HEIGHT, min(int(height or EXPANDED_DEFAULT_HEIGHT), max_height))
        return clamped_width, clamped_height

    def _clamp_collapsed_width(self, width: int) -> int:
        return max(COLLAPSED_MIN_WIDTH, min(int(width or COLLAPSED_DEFAULT_WIDTH), COLLAPSED_MAX_WIDTH))

    def _clamp_window_position(self, x: int, y: int, width: int, height: int) -> tuple[int, int]:
        screen_x, screen_y, screen_width, screen_height = self._available_screen_geometry()
        top_margin = max(screen_y + 12, 18)
        normalized_y = max(top_margin, min(int(y), screen_y + screen_height - max(int(height), 80)))
        normalized_x = int(x)
        max_x = screen_x + screen_width - max(int(width), 120)
        if normalized_x < screen_x - 12 or normalized_x > max_x:
            normalized_x = -1
        return normalized_x, normalized_y

    def _write_view_prefs(self):
        self._write_prefs(
            {
                "window": {
                    "x": self._window_x,
                    "y": self._window_y,
                    "width": self._window_width,
                    "height": self._window_height,
                    "collapsed_width": self._collapsed_width,
                },
                "expanded": self._expanded,
                "replay_expanded": self._replay_expanded,
                "quiet_mode": self._quiet_mode,
                "focus_mode": self._focus_mode,
                "pinned": self._pinned,
                "prompt_attention_enabled": self._prompt_attention_enabled,
                "telegram": {
                    "enabled": self._telegram_enabled,
                    "bot_token": self._telegram_bot_token,
                    "chat_id": self._telegram_chat_id,
                    "last_update_id": self._telegram_last_update_id,
                },
            }
        )

    def _timeline_entry(self, session, kind, label, detail):
        updated_at = str(session.get("updatedAt") or session.get("updated_at") or "")
        session_id = str(session.get("id") or "")
        title = str(session.get("title") or "").strip() or "Untitled"
        source = str(session.get("source") or "").strip()
        return {
            "id": f"{session_id}:{kind}:{updated_at or label}",
            "sessionId": session_id,
            "title": title,
            "source": source,
            "kind": kind,
            "label": label,
            "detail": str(detail or "").strip(),
            "updated": age_label(updated_at) if updated_at else "now",
            "accent": "#ff8e9d" if kind in {"approval", "failed", "stale"} else ("#8ef8cb" if kind == "completed" else "#7dd8ff"),
        }

    def _normalize_timeline_item(self, item):
        session_id = str(item.get("sessionId") or item.get("session_id") or item.get("id") or "")
        kind = str(item.get("kind") or "").strip()
        label = str(item.get("label") or "").strip()
        if label == "":
            label = timeline_label_for_kind(kind)
        detail = str(item.get("detail") or item.get("summary") or "").strip()
        title = str(item.get("title") or "").strip() or "Untitled"
        source = str(item.get("source") or "").strip()
        updated = str(item.get("updated") or "").strip()
        if updated == "":
            updated = age_label(str(item.get("ts") or ""))
        return {
            "id": str(item.get("event_id") or item.get("id") or f"{session_id}:{kind}:{label}:{detail}"),
            "sessionId": session_id,
            "title": title,
            "source": source,
            "kind": kind or "updated",
            "label": label,
            "detail": detail,
            "updated": updated or "now",
            "accent": str(item.get("accent") or timeline_accent_for_kind(kind)),
        }

    def _merge_timeline_entries(self, *groups):
        merged = []
        seen = set()
        for group in groups:
            if not group:
                continue
            for item in group:
                if not isinstance(item, dict):
                    continue
                key = str(item.get("id") or "")
                if key == "" or key in seen:
                    continue
                seen.add(key)
                merged.append(item)
        return merged[:8]

    def _write_prefs(self, payload):
        try:
            self._prefs_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._prefs_path.with_suffix(".tmp")
            with tmp_path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
            os.replace(tmp_path, self._prefs_path)
            self._loaded_prefs = payload
        except Exception:
            pass

    def _clear_prefs(self):
        try:
            if self._prefs_path.exists():
                self._prefs_path.unlink()
        except Exception:
            pass


def build_tray_icon() -> QIcon:
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor("#00000000"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    painter.fillRect(4, 4, 24, 24, QColor("#0a0e12"))
    painter.setPen(QColor("#27313a"))
    painter.drawRect(4, 4, 24, 24)
    cells = [
        (9, 9), (13, 9), (17, 9),
        (9, 13), (13, 13), (17, 13),
        (9, 17), (13, 17),
    ]
    for x, y in cells:
        painter.fillRect(x, y, 3, 3, QColor("#dfe8ef"))
    painter.fillRect(21, 17, 3, 3, QColor("#82b3c8"))
    painter.end()
    return QIcon(pixmap)


class TrayController(QObject):
    def __init__(self, app: QApplication, backend: Backend, window):
        super().__init__()
        self._app = app
        self._backend = backend
        self._window = window
        self._tray: QSystemTrayIcon | None = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        self._tray = QSystemTrayIcon(build_tray_icon(), self._app)
        self._tray.setToolTip("Vibe Island")
        menu = QMenu()

        summon_action = QAction("Summon Island", menu)
        summon_action.triggered.connect(self.summon)
        menu.addAction(summon_action)

        expand_action = QAction("Toggle Expand", menu)
        expand_action.triggered.connect(self._backend.toggleExpanded)
        menu.addAction(expand_action)

        pin_action = QAction("Toggle Pin", menu)
        pin_action.triggered.connect(self._backend.togglePinned)
        menu.addAction(pin_action)

        menu.addSeparator()

        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self._app.quit)
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)
        self._backend.summonRequested.connect(self.summon)
        self._tray.show()

    def _on_activated(self, reason):
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
            QSystemTrayIcon.ActivationReason.MiddleClick,
        }:
            self.summon()

    def summon(self):
        if self._window is None:
            return
        self._window.show()
        if hasattr(self._window, "raise_"):
            self._window.raise_()
        self._window.requestActivate()


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Vibe Island Linux shell prototype")
    parser.add_argument("--socket", default=DEFAULT_SOCKET, help="Unix socket path for vibeislandd")
    parser.add_argument(
        "--state",
        default=str(DEFAULT_STATE),
        help="Fallback JSON state file when the daemon is unavailable",
    )
    return parser.parse_args(argv)

def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    app = QApplication(sys.argv)
    app.setApplicationName("Vibe Island Shell")

    engine = QQmlApplicationEngine()
    backend = Backend(args.socket, Path(args.state))
    app.aboutToQuit.connect(backend.shutdown)
    engine.rootContext().setContextProperty("backend", backend)
    engine.load(QUrl.fromLocalFile(str(ROOT / "ui" / "Main.qml")))

    if not engine.rootObjects():
        return 1

    tray = TrayController(app, backend, engine.rootObjects()[0])
    app.setProperty("_vibeisland_tray", tray)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
