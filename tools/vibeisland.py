#!/usr/bin/env python
from __future__ import annotations

import argparse
from collections import deque
import json
import os
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent.parent
BRIDGE_SCRIPT = Path(__file__).resolve()
DEFAULT_SOCKET = os.environ.get("VIBEISLAND_SOCKET", "/tmp/vibeisland.sock")
CLAUDE_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
CODEX_CONFIG_PATH = Path.home() / ".codex" / "config.toml"
CODEX_HOOKS_PATH = Path.home() / ".codex" / "hooks.json"
CODEX_HISTORY_PATH = Path.home() / ".codex" / "history.jsonl"
BACKUP_ROOT = Path.home() / ".config" / "vibeisland" / "backups"
STATE_ROOT = Path(os.environ.get("VIBEISLAND_STATE_DIR") or (Path.home() / ".local" / "state" / "vibeisland"))
CLAUDE_STATUSLINE_PATH = STATE_ROOT / "claude_statusline.json"
APPROVAL_REQUESTS_DIR = STATE_ROOT / "approval_requests"
APPROVAL_RULES_DIR = STATE_ROOT / "approval_rules"
LAUNCHER_STATE_PATH = STATE_ROOT / "launcher_state.json"
LAUNCHER_LOG_DIR = STATE_ROOT / "logs"
DEFAULT_BIN_DIR = Path.home() / ".local" / "bin"
DEFAULT_APPLICATIONS_DIR = Path.home() / ".local" / "share" / "applications"
MANAGED_APPROVAL_TIMEOUT = float(os.environ.get("VIBEISLAND_APPROVAL_TIMEOUT", "600"))
MANAGED_APPROVAL_POLL_INTERVAL = 0.05
KNOWN_TERMINALS = {
    "alacritty",
    "code",
    "code-insiders",
    "cursor",
    "ghostty",
    "gnome-terminal-server",
    "kitty",
    "konsole",
    "terminator",
    "tilix",
    "wezterm",
    "xterm",
}
LIVE_SCAN_NONINTERACTIVE = {
    "claude": {
        "auth",
        "completion",
        "debug",
        "doctor",
        "help",
        "install",
        "logout",
        "login",
        "mcp",
        "plugin",
        "plugins",
        "setup-token",
        "update",
        "upgrade",
        "--help",
        "-h",
    },
    "codex": {
        "apply",
        "app-server",
        "cloud",
        "completion",
        "debug",
        "exec",
        "features",
        "fork",
        "help",
        "login",
        "logout",
        "mcp",
        "mcp-server",
        "review",
        "resume",
        "--help",
        "-h",
    },
}

CHOICE_LINE_RE = re.compile(r"^\s*(\d+)[\.\)\]:：、-]\s*(.+?)\s*$")
APPROVAL_HINTS = (
    "权限审批",
    "需要权限",
    "需要审批",
    "allow once",
    "allow for session",
    "approval",
    "approve",
    "permission",
    "你要如何处理",
    "请选择",
    "choose one",
    "how should i proceed",
)
SAFE_READONLY_COMMANDS = {
    "basename",
    "cat",
    "dirname",
    "echo",
    "env",
    "fd",
    "file",
    "find",
    "git",
    "grep",
    "head",
    "less",
    "ls",
    "nl",
    "printf",
    "ps",
    "pwd",
    "readlink",
    "realpath",
    "rg",
    "sed",
    "sort",
    "stat",
    "tail",
    "tree",
    "uname",
    "wc",
    "which",
}
NETWORK_COMMANDS = {"curl", "http", "https", "nc", "ncat", "ping", "rsync", "scp", "ssh", "telnet", "wget"}
WRITE_COMMANDS = {
    "chmod",
    "chown",
    "cp",
    "dd",
    "docker",
    "install",
    "kubectl",
    "make",
    "mkdir",
    "mount",
    "mv",
    "npm",
    "pacman",
    "pip",
    "pip3",
    "pnpm",
    "podman",
    "python",
    "python3",
    "rm",
    "rmdir",
    "sudo",
    "systemctl",
    "tee",
    "touch",
    "umount",
    "uv",
    "yarn",
    "yay",
}
RISKY_COMMAND_MARKERS = (
    "&&",
    "||",
    ">",
    ">>",
    "2>",
    "1>",
    "http://",
    "https://",
    "| sudo ",
)
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
    "bash wants approval",
    "claude needs your permission",
    "codex wants approval",
    "approval request",
    "permission request",
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
    "codex session",
    "claude session",
    "agent session",
    "codex @",
    "claude @",
    "agent @",
    "codex ·",
    "claude ·",
    "agent ·",
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
OPERATIONAL_COMMAND_PREFIXES = (
    "pwd",
    "pwd &&",
    "ls",
    "ls -",
    "find ",
    "rg --files",
    "fd ",
    "command -v ",
    "which ",
    "test -f ",
    "test -e ",
    "sed -n ",
    "cat progress.md",
    "cat skill.md",
    "read skill.md",
    "read progress.md",
    "node -v",
    "npm -v",
    "pnpm -v",
    "python -v",
    "python3 -v",
)
OPERATIONAL_STEP_PREFIXES = (
    "explored",
    "list ",
    "read skill.md",
    "read progress.md",
    "ran pwd",
    "ran ls",
    "ran find ",
    "ran command -v ",
    "ran test -f ",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def truncate(value: str | None, limit: int = 88) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def strip_label_noise(text: str) -> str:
    return re.sub(r"^[\s•●◦◉○·*>⎿>]+", "", text).strip()


def normalize_text(text: str | None) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    lines = [strip_label_noise(line) for line in value.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return ""
    return "\n".join(lines)


def is_boilerplate_reply(text: str | None) -> bool:
    lowered = normalize_text(text).lower()
    if not lowered:
        return False
    return any(hint in lowered for hint in BOILERPLATE_REPLY_HINTS)


def is_low_signal_task_label(text: str | None) -> bool:
    lowered = normalize_text(text).lower()
    if not lowered:
        return True
    if is_boilerplate_reply(lowered):
        return True
    if lowered.startswith(
        (
            "codex @ ",
            "claude @ ",
            "gemini @ ",
            "openclaw @ ",
            "agent @ ",
            "codex session",
            "claude session",
            "gemini session",
            "openclaw session",
            "agent session",
        )
    ):
        return True
    if any(lowered.startswith(prefix) for prefix in OPERATIONAL_COMMAND_PREFIXES):
        return True
    if any(lowered.startswith(prefix) for prefix in OPERATIONAL_STEP_PREFIXES):
        return True
    if "&& node -v" in lowered or "&& npm -v" in lowered or "&& pnpm -v" in lowered:
        return True
    if lowered in {
        "completed",
        "updated",
        "running",
        "done",
        "finish",
        "finished",
        "startup",
        "booting",
        "booting island",
        "initializing",
        "initialising",
        "starting up",
    }:
        return True
    return any(lowered.startswith(prefix) for prefix in LOW_SIGNAL_LABEL_PREFIXES)


def extract_command_candidate(text: str | None) -> str:
    content = normalize_text(text)
    if not content:
        return ""

    for raw_line in content.splitlines():
        stripped = strip_label_noise(raw_line)
        if not stripped:
            continue
        if stripped.lower().startswith(("bash:", "command:", "cmd:")):
            candidate = stripped.split(":", 1)[1].strip()
            if candidate:
                return truncate(candidate, 120)
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

    code_match = re.search(r"`([^`]+)`", content)
    if code_match:
        candidate = normalize_text(code_match.group(1))
        if candidate:
            return truncate(candidate, 120)

    sentence_match = COMMAND_INTENT_RE.search(content)
    if sentence_match:
        candidate = normalize_text(sentence_match.group(1)).rstrip(" .!?，。；;")
        if candidate:
            return truncate(candidate, 120)

    if re.search(r"\b(curl|wget|git|bash|python|python3|pnpm|npm|uv|make|sed|tee|rm|mv|cp)\b", content, re.I):
        return truncate(content, 120)

    return ""


def summarize_command_label(command: str | None) -> str:
    content = normalize_text(command)
    if not content:
        return ""
    if is_low_signal_task_label(content):
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
                return truncate(f"Fetch {host} headers", 44)
            if any(flag in tokens for flag in ("-L", "--location")):
                return truncate(f"Follow redirects from {host}", 44)
            return truncate(f"Fetch {host}", 44)
        return "Fetch URL"

    if program == "wget":
        if host:
            return truncate(f"Fetch {host}", 44)
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
            return truncate(git_labels[subcommand], 44)

    if program in {"npm", "pnpm", "yarn"}:
        if len(tokens) > 1 and not tokens[1].startswith("-"):
            subcommand = tokens[1].lower()
            if subcommand in {"install", "add", "test", "run", "build", "start", "dev", "publish"}:
                return truncate(f"Run {program} {subcommand}", 44)
        return truncate(f"Run {program}", 44)

    if program in {"python", "python3", "uv"}:
        if len(tokens) > 1 and not tokens[1].startswith("-"):
            return truncate(f"Run {program} {Path(tokens[1]).name}", 44)
        return truncate(f"Run {program}", 44)

    if program in {"bash", "sh", "zsh"}:
        if len(tokens) >= 3 and tokens[1] in {"-lc", "-c"}:
            nested = summarize_command_label(" ".join(tokens[2:]))
            if nested:
                return nested
        return "Run shell command"

    if program in COMMAND_PROGRAM_ALIASES:
        label = COMMAND_PROGRAM_ALIASES[program]
        if host and label == "Fetch":
            return truncate(f"{label} {host}", 44)
        return truncate(label, 44)

    if host:
        return truncate(f"Check {host}", 44)

    if len(content) <= 44 and "\n" not in content:
        return truncate(content, 44)

    return ""


def first_sentence_fragment(text: str | None) -> str:
    content = normalize_text(text)
    if not content:
        return ""
    fragment = re.split(r"[\n。！？!?；;]", content, maxsplit=1)[0]
    return normalize_text(fragment)


def summarize_file_task_label(text: str | None, limit: int = 44) -> str:
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
    candidate = candidate.strip(" \"'`，。,:;")
    return candidate


def summarize_goal_task_label(text: str | None, limit: int = 44) -> str:
    content = first_sentence_fragment(text)
    if not content:
        return ""

    lowered = content.lower()
    if "俄罗斯方块" in content or "tetris" in lowered:
        return truncate("Build Tetris game", limit)

    action_patterns = (
        ("Fix", r"(?:fix|修复)\s+(.+)"),
        ("Optimize", r"(?:optimize|优化)\s+(.+)"),
        ("Refactor", r"(?:refactor|重构)\s+(.+)"),
    )
    for action, pattern in action_patterns:
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
        if target:
            target = re.sub(r"(?:来测试.*|用于测试.*|方便测试.*)$", "", target, flags=re.I).strip()
            target = re.sub(r"\s+", " ", target).strip("，。,:;")
            if target:
                return truncate(f"Build {target}", limit)

    return ""


def review_scope_from(
    command: str | None,
    detail: str | None,
    cwd: str | None,
    tool_name: str | None,
) -> str | None:
    for candidate in (command, detail):
        content = normalize_text(candidate)
        if not content:
            continue
        host_match = URL_RE.search(content)
        if host_match:
            return host_match.group(1).rstrip(").,]`")
        path_match = re.search(r"([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+)", content)
        if path_match:
            return path_match.group(1)

    workspace = workspace_hint_from_cwd(cwd)
    if workspace:
        return workspace
    if tool_name:
        return truncate(tool_name, 32)
    return None


def derive_task_label_from_text(text: str | None, cwd: str | None = None, limit: int = 44) -> str:
    content = normalize_text(text)
    if not content:
        return ""

    if is_low_signal_task_label(content):
        return ""
    cwd_name = Path(cwd or os.getcwd()).name.strip().lower()
    if cwd_name and content.lower() == cwd_name:
        return ""
    if content.startswith("{") or content.startswith("["):
        return ""

    command_candidate = extract_command_candidate(content)
    if command_candidate:
        command_label = summarize_command_label(command_candidate)
        if command_label:
            return truncate(command_label, limit)

    file_label = summarize_file_task_label(content, limit=limit)
    if file_label:
        return file_label

    goal_label = summarize_goal_task_label(content, limit=limit)
    if goal_label:
        return goal_label

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    for line in lines:
        candidate = strip_label_noise(line).strip("●•-:—> ")
        if not candidate:
            continue
        if is_low_signal_task_label(candidate):
            continue
        if cwd_name and candidate.lower() == cwd_name:
            continue
        if candidate.startswith("{") or candidate.startswith("["):
            continue
        command_label = summarize_command_label(candidate)
        if command_label:
            return truncate(command_label, limit)
        file_label = summarize_file_task_label(candidate, limit=limit)
        if file_label:
            return file_label
        goal_label = summarize_goal_task_label(candidate, limit=limit)
        if goal_label:
            return goal_label
        if len(candidate.split()) == 1 and len(candidate) > limit:
            continue
        return truncate(candidate, limit)

    return ""


def derive_title(text: str | None, cwd: str | None = None) -> str:
    candidate = derive_task_label_from_text(text, cwd, limit=44)
    if candidate:
        return candidate
    cwd_path = Path(cwd or os.getcwd())
    return cwd_path.name or "Untitled session"


def derive_task_label(text: str | None, cwd: str | None = None) -> str:
    candidate = derive_task_label_from_text(text, cwd, limit=52)
    return truncate(candidate, 52)


def workspace_hint_from_cwd(cwd: str | None) -> str | None:
    if not cwd:
        return None
    path = Path(cwd)
    if path.name:
        return path.name
    return str(path)


def review_risk_label(command: str | None, tool_name: str | None, approval_type: str | None, detail: str | None) -> str:
    text = " ".join(
        part for part in [str(command or ""), str(detail or ""), str(tool_name or ""), str(approval_type or "")] if part
    ).lower()
    if any(marker in text for marker in ("http://", "https://", "curl ", "wget ", "ssh ", "scp ", "rsync ")):
        return "network access"
    if any(marker in text for marker in ("rm ", "mv ", "cp ", "chmod ", "chown ", "mkdir ", "touch ", "tee ", "edit", "write")):
        return "workspace writes"
    if any(marker in text for marker in ("read", "grep", "cat", "ls", "pwd", "status", "diff")):
        return "read only"
    return "command execution"


def build_review_info(
    *,
    cwd: str | None,
    command: str | None,
    detail: str | None,
    tool_name: str | None,
    approval_type: str | None,
) -> dict[str, Any]:
    command_text = truncate(command, 140) if command else None
    detail_text = truncate(detail, 140) if detail else None
    risk = review_risk_label(command_text or detail_text, tool_name, approval_type, detail_text)
    reason_text = detail_text or command_text or (truncate(tool_name, 64) if tool_name else None)
    return {
        "headline": {
            "network access": "Network access review",
            "workspace writes": "Workspace write review",
            "read only": "Read-only review",
        }.get(risk, "Command execution review"),
        "command": command_text,
        "detail": detail_text,
        "reason": reason_text,
        "risk": risk,
        "scope": truncate(review_scope_from(command_text, detail_text, cwd, tool_name) or "", 80) or workspace_hint_from_cwd(cwd),
        "workspace_hint": workspace_hint_from_cwd(cwd),
        "tool_name": truncate(tool_name, 32) if tool_name else None,
    }


def first_present(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def load_json_maybe(value: str | None) -> Any:
    if value is None:
        return None
    return json.loads(value)


def read_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def read_recent_jsonl(path: str | os.PathLike[str] | None, limit: int = 200) -> list[dict[str, Any]]:
    if not path:
        return []

    file_path = Path(path)
    if not file_path.exists():
        return []

    with file_path.open("r", encoding="utf-8") as handle:
        lines = deque(handle, maxlen=limit)

    items: list[dict[str, Any]] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            items.append(payload)
    return items


def extract_prompt_from_collection(values: Any) -> str:
    if isinstance(values, list):
        for item in reversed(values):
            candidate = extract_prompt_from_collection(item)
            if candidate:
                return candidate
        return ""

    if isinstance(values, dict):
        role = str(values.get("role") or values.get("speaker") or values.get("type") or "").lower()
        if role and role not in {"user", "user_message", "input_text", "message"}:
            content = values.get("content")
            if content is not None:
                return extract_prompt_from_collection(content)

        for key in ("text", "prompt", "message", "content", "input"):
            candidate = values.get(key)
            if isinstance(candidate, str):
                normalized = normalize_text(candidate)
                if normalized:
                    return normalized
            elif candidate is not None:
                nested = extract_prompt_from_collection(candidate)
                if nested:
                    return nested
        return ""

    if isinstance(values, str):
        return normalize_text(values)

    return ""


def extract_prompt_from_payload(payload: dict[str, Any]) -> str:
    for key in ("prompt", "user_prompt", "user_message", "last_user_message", "request", "instruction"):
        text = normalize_text(payload.get(key))
        if text:
            return text

    turn_context = payload.get("turn_context")
    if isinstance(turn_context, dict):
        for key in ("prompt", "user_prompt", "last_user_message", "request", "instruction"):
            text = normalize_text(turn_context.get(key))
            if text:
                return text
        for key in ("input_messages", "messages", "conversation", "items"):
            candidate = extract_prompt_from_collection(turn_context.get(key))
            if candidate:
                return candidate

    for key in ("input_messages", "messages", "conversation", "items"):
        candidate = extract_prompt_from_collection(payload.get(key))
        if candidate:
            return candidate

    return ""


def load_codex_history_prompt(session_id: str | None) -> str:
    target = normalize_text(session_id)
    if not target or not CODEX_HISTORY_PATH.exists():
        return ""

    for item in reversed(read_recent_jsonl(CODEX_HISTORY_PATH, limit=800)):
        if normalize_text(item.get("session_id")) != target:
            continue
        text = normalize_text(item.get("text"))
        if text:
            return text
    return ""


def stable_task_label_for_event(
    source: str,
    session_id: str | None,
    payload: dict[str, Any],
    cwd: str | None,
    *extra_candidates: Any,
) -> str | None:
    candidates: list[str] = []

    prompt = extract_prompt_from_payload(payload)
    if prompt:
        candidates.append(prompt)

    if source == "codex":
        history_prompt = load_codex_history_prompt(session_id)
        if history_prompt:
            candidates.append(history_prompt)

    for candidate in extra_candidates:
        normalized = normalize_text(candidate)
        if normalized:
            candidates.append(normalized)

    for candidate in candidates:
        label = derive_task_label(candidate, cwd)
        if label and not is_low_signal_task_label(label):
            return truncate(label, 52)

    return None


def load_codex_turn_context(transcript_path: str | None, turn_id: str | None) -> dict[str, Any]:
    if not transcript_path:
        return {}

    for item in reversed(read_recent_jsonl(transcript_path, limit=400)):
        if item.get("type") != "turn_context":
            continue
        payload = item.get("payload")
        if not isinstance(payload, dict):
            continue
        if turn_id and payload.get("turn_id") != turn_id:
            continue
        return payload
    return {}


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, path)


def safe_slug(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return "unknown"
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text)


def approval_request_key(source: str, session_id: str) -> str:
    return f"{safe_slug(source)}--{safe_slug(session_id)}"


def approval_request_path(source: str, session_id: str) -> Path:
    return APPROVAL_REQUESTS_DIR / f"{approval_request_key(source, session_id)}.json"


def approval_rule_path(source: str, session_id: str) -> Path:
    return APPROVAL_RULES_DIR / f"{approval_request_key(source, session_id)}.json"


def read_json_file_maybe(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def write_json_file(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def clear_approval_request(source: str, session_id: str) -> None:
    path = approval_request_path(source, session_id)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except Exception:
        pass


def load_session_rules(source: str, session_id: str) -> list[dict[str, Any]]:
    payload = read_json_file_maybe(approval_rule_path(source, session_id))
    rules = payload.get("rules")
    if not isinstance(rules, list):
        return []
    return [rule for rule in rules if isinstance(rule, dict)]


def save_session_rules(source: str, session_id: str, rules: list[dict[str, Any]]) -> None:
    write_json_file(
        approval_rule_path(source, session_id),
        {
            "source": source,
            "session_id": session_id,
            "updated_at": now_iso(),
            "rules": rules,
        },
    )


def backup_file(path: Path) -> Path | None:
    if not path.exists():
        return None
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination_dir = BACKUP_ROOT / timestamp
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / path.name
    shutil.copy2(path, destination)
    return destination


def load_launcher_state() -> dict[str, Any]:
    return read_json_file_maybe(LAUNCHER_STATE_PATH)


def save_launcher_state(payload: dict[str, Any]) -> None:
    write_json_file(LAUNCHER_STATE_PATH, payload)


def process_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def terminate_process_group(pid: int | None, sig: int = signal.SIGTERM) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.killpg(pid, sig)
        return True
    except ProcessLookupError:
        return False
    except Exception:
        try:
            os.kill(pid, sig)
            return True
        except Exception:
            return False


def socket_healthy(socket_path: str = DEFAULT_SOCKET, timeout: float = 0.8) -> bool:
    payload = json.dumps({"type": "snapshot"}).encode("utf-8") + b"\n"
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect(socket_path)
            client.sendall(payload)
            buffer = b""
            while not buffer.endswith(b"\n"):
                chunk = client.recv(65536)
                if not chunk:
                    break
                buffer += chunk
        if not buffer:
            return False
        response = json.loads(buffer.decode("utf-8").strip())
        return isinstance(response, dict) and response.get("type") == "snapshot"
    except Exception:
        return False


def wait_for_socket(socket_path: str, timeout_seconds: float = 16.0) -> bool:
    deadline = time.monotonic() + max(timeout_seconds, 0.5)
    while time.monotonic() < deadline:
        if socket_healthy(socket_path, timeout=0.6):
            return True
        time.sleep(0.35)
    return False


def build_daemon_command() -> list[str]:
    built = ROOT / "target" / "debug" / "vibeisland-daemon"
    if built.exists() and os.access(built, os.X_OK):
        return [str(built)]
    return ["cargo", "run", "-p", "vibeisland-daemon"]


def build_shell_command(socket_path: str) -> list[str]:
    return [sys.executable, "-m", "apps.shell", "--socket", socket_path]


def log_path(name: str) -> Path:
    safe_name = safe_slug(name)
    return LAUNCHER_LOG_DIR / f"{safe_name}.log"


def spawn_background_process(command: list[str], *, cwd: Path, log_file: Path, extra_env: dict[str, str] | None = None) -> int:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    if extra_env:
        env.update({key: str(value) for key, value in extra_env.items()})
    handle = log_file.open("ab")
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        stdout=handle,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        preexec_fn=os.setsid,
        env=env,
        close_fds=True,
    )
    handle.close()
    return int(process.pid)


def send_request(request: dict[str, Any], socket_path: str = DEFAULT_SOCKET) -> dict[str, Any]:
    payload = json.dumps(request).encode("utf-8") + b"\n"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(socket_path)
        client.sendall(payload)
        buffer = b""
        while not buffer.endswith(b"\n"):
            chunk = client.recv(65536)
            if not chunk:
                break
            buffer += chunk
    if not buffer:
        return {}
    return json.loads(buffer.decode("utf-8").strip())


def make_event(
    *,
    source: str,
    session_id: str,
    kind: str,
    state: str,
    title: str,
    summary: str,
    adapter: str = "vibe-bridge",
    workspace: str | None = None,
    cwd: str | None = None,
    run_id: str | None = None,
    approval_type: str | None = None,
    question: str | None = None,
    choices: Iterable[str] | None = None,
    task_label: str | None = None,
    review: dict[str, Any] | None = None,
    phase: str | None = None,
    pct: float | None = None,
    terminal: str | None = None,
    tty: str | None = None,
    pid: int | None = None,
    tmux_session: str | None = None,
    tmux_window: str | None = None,
    tmux_pane: str | None = None,
    raw: Any | None = None,
) -> dict[str, Any]:
    return {
        "schema": "v1",
        "event_id": str(uuid.uuid4()),
        "ts": now_iso(),
        "source": source,
        "adapter": adapter,
        "session": {
            "id": session_id,
            "run_id": run_id,
            "title": title,
            "task_label": (task_label or "").strip() or None,
            "workspace": workspace or os.getcwd(),
            "cwd": cwd or os.getcwd(),
        },
        "kind": kind,
        "state": state,
        "summary": summary,
        "progress": {"phase": phase, "pct": pct},
        "interaction": {
            "approval_type": approval_type,
            "question": question,
            "choices": list(choices or []),
        },
        "review": review or {},
        "jump_target": {
            "terminal": terminal,
            "tty": tty,
            "pid": pid,
            "tmux_session": tmux_session,
            "tmux_window": tmux_window,
            "tmux_pane": tmux_pane,
        },
        "raw": raw if raw is not None else {},
    }


def publish_event(
    event: dict[str, Any],
    socket_path: str = DEFAULT_SOCKET,
    *,
    ignore_errors: bool = False,
) -> dict[str, Any]:
    try:
        return send_request({"type": "publish", "event": event}, socket_path)
    except Exception:
        if ignore_errors:
            return {"type": "ack", "ok": False}
        raise


def request_snapshot(socket_path: str = DEFAULT_SOCKET) -> dict[str, Any]:
    response = send_request({"type": "snapshot"}, socket_path)
    return response.get("snapshot", {})


def subscribe(socket_path: str = DEFAULT_SOCKET):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(socket_path)
        client.sendall(b'{"type":"subscribe"}\n')
        buffer = b""
        while True:
            chunk = client.recv(65536)
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                if line.strip():
                    yield json.loads(line.decode("utf-8"))


def read_payload_from_input(raw_arg: str | None = None) -> Any:
    if raw_arg:
        try:
            return json.loads(raw_arg)
        except json.JSONDecodeError:
            return {"message": raw_arg}

    if not sys.stdin.isatty():
        content = sys.stdin.read().strip()
        if content:
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return {"message": content}

    return {}


def detect_terminal() -> str | None:
    env = os.environ
    if env.get("TMUX") or env.get("TMUX_PANE"):
        return "tmux"
    if env.get("KITTY_WINDOW_ID") or env.get("KITTY_PID"):
        return "kitty"
    if env.get("WEZTERM_PANE"):
        return "wezterm"
    term_program = (env.get("TERM_PROGRAM") or "").lower()
    if term_program:
        aliases = {
            "vscode": "vscode",
            "code": "vscode",
            "cursor": "cursor",
            "ghostty": "ghostty",
            "wezterm": "wezterm",
            "kitty": "kitty",
        }
        return aliases.get(term_program, term_program)
    return None


def basename_token(value: str | None) -> str:
    token = (value or "").strip().strip('"').split(" ", 1)[0]
    if not token:
        return ""
    return Path(token).name.lower()


def command_matches_name(name: str, exe: str | None = None, cmdline: str | None = None) -> bool:
    expected = name.lower()
    return basename_token(exe) == expected or basename_token(cmdline) == expected


def detect_tty() -> str | None:
    for fd in (0, 1, 2):
        try:
            return os.ttyname(fd)
        except OSError:
            continue
    return None


def detect_tmux_target() -> dict[str, Any]:
    if not (os.environ.get("TMUX") or os.environ.get("TMUX_PANE")):
        return {
            "tmux_session": None,
            "tmux_window": None,
            "tmux_pane": os.environ.get("TMUX_PANE"),
            "tty": detect_tty(),
        }

    script = "#{session_name}\n#{window_index}\n#{pane_id}\n#{pane_tty}"
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-p", script],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            session_name, window_index, pane_id, pane_tty = (
                result.stdout.strip().splitlines() + ["", "", "", ""]
            )[:4]
            return {
                "tmux_session": session_name or None,
                "tmux_window": window_index or None,
                "tmux_pane": pane_id or os.environ.get("TMUX_PANE"),
                "tty": pane_tty or detect_tty(),
            }
    except Exception:
        pass

    return {
        "tmux_session": None,
        "tmux_window": None,
        "tmux_pane": os.environ.get("TMUX_PANE"),
        "tty": detect_tty(),
    }


def detect_tty_from_pid_chain(pid: int | None, max_depth: int = 8) -> str | None:
    current = int(pid or 0)
    seen: set[int] = set()
    for _ in range(max_depth):
        if current <= 1 or current in seen:
            break
        seen.add(current)
        try:
            candidate = os.readlink(f"/proc/{current}/fd/0")
        except OSError:
            candidate = None
        if candidate and candidate.startswith("/dev/") and "(deleted)" not in candidate:
            return candidate
        try:
            stat_parts = (Path("/proc") / str(current) / "stat").read_text(encoding="utf-8").split()
            current = int(stat_parts[3]) if len(stat_parts) > 3 else 0
        except Exception:
            break
    return None


def detect_jump_target() -> dict[str, Any]:
    tmux = detect_tmux_target()
    pid = os.getppid()
    ancestors = process_ancestors(pid)
    host = next((item for item in ancestors if detect_host_process_name(item) is not None), None)
    terminal = detect_terminal() or detect_host_process_name(host or {})
    target_pid = int(host["pid"]) if host and host.get("pid") else pid
    tty = (
        tmux.get("tty")
        or detect_tty()
        or detect_tty_from_pid_chain(os.getpid())
        or detect_tty_from_pid_chain(pid)
        or detect_tty_from_pid_chain(target_pid)
    )
    return {
        "terminal": terminal,
        "tty": tty,
        "pid": target_pid,
        "tmux_session": tmux.get("tmux_session") or f"best:{terminal or 'unknown'}:{target_pid}",
        "tmux_window": tmux.get("tmux_window") or f"pid:{target_pid}",
        "tmux_pane": tmux.get("tmux_pane") or "%0",
    }


def extract_choices_from_schema(schema: Any) -> list[str]:
    if not isinstance(schema, dict):
        return []
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return []

    choices: list[str] = []
    for name, value in properties.items():
        if not isinstance(value, dict):
            continue
        enum_values = value.get("enum")
        if isinstance(enum_values, list) and enum_values:
            return [str(item) for item in enum_values]
        title = value.get("title") or name
        choices.append(str(title))
    return choices[:6]


def extract_choices_from_text(message: str | None) -> list[str]:
    if not message:
        return []

    choices: list[str] = []
    for raw_line in str(message).splitlines():
        match = CHOICE_LINE_RE.match(raw_line.strip())
        if not match:
            continue
        choice = truncate(match.group(2).strip(), 64)
        if choice and choice not in choices:
            choices.append(choice)
    return choices[:6]


def detect_interaction_from_message(message: str | None) -> dict[str, Any] | None:
    if not message:
        return None

    text = str(message).strip()
    if not text:
        return None

    lowered = text.lower()
    choices = extract_choices_from_text(text)
    if len(choices) < 2:
        return None

    question = None
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        if CHOICE_LINE_RE.match(line):
            break
        if line.endswith(("?", "？")):
            question = truncate(line, 120)
    if question is None and any(hint in lowered for hint in APPROVAL_HINTS):
        question = "你要如何处理？"

    if question is None:
        return None

    is_approval = any(hint in lowered for hint in APPROVAL_HINTS)
    return {
        "kind": "needs_approval" if is_approval else "ask_user",
        "state": "blocked" if is_approval else "waiting_user",
        "approval_type": "approval_prompt" if is_approval else "choice_prompt",
        "question": question,
        "choices": choices,
        "summary": truncate(question, 140),
        "title": derive_title(question),
    }


def default_approval_choices() -> list[str]:
    return ["Allow once", "Allow for session", "Deny"]


def claude_approval_details(tool_name: str, tool_input: dict[str, Any], payload: dict[str, Any]) -> tuple[str, str, list[str]]:
    detail = first_present(
        tool_input.get("command"),
        tool_input.get("file_path"),
        tool_input.get("description"),
        payload.get("message"),
        payload.get("reason"),
    )
    question = truncate(
        first_present(
            payload.get("message"),
            f"Claude needs your permission to use {tool_name}",
        ),
        140,
    ) or f"Claude needs your permission to use {tool_name}"
    summary = truncate(f"{tool_name} wants approval: {detail}" if detail else question, 140)
    tool_label = str(tool_name or "tool").strip() or "tool"
    command_name = shell_command_name(str(detail or ""))
    if tool_label.lower() == "bash":
        default_choices = [
            "Yes",
            f"Yes, and don't ask again for: {command_name}:*" if command_name else "Yes, and don't ask again for Bash",
            "No, tell Claude what to do differently",
        ]
    else:
        normalized_label = truncate(tool_label, 18) or "this tool"
        default_choices = [
            "Allow once",
            f"Allow {normalized_label} for this session",
            "No, tell Claude what to do differently",
        ]
    choices = (
        extract_choices_from_schema(payload.get("requested_schema"))
        or extract_choices_from_text(first_present(payload.get("message"), payload.get("reason")))
        or default_choices
    )
    return question, summary, choices


def shell_command_name(command: str) -> str:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = command.strip().split()
    return tokens[0].lower() if tokens else ""


def is_safe_readonly_command(command: str) -> bool:
    text = command.strip()
    if not text:
        return False

    lowered = text.lower()
    if any(marker in lowered for marker in RISKY_COMMAND_MARKERS):
        return False

    program = shell_command_name(text)
    if program not in SAFE_READONLY_COMMANDS:
        return False

    if program == "git":
        return bool(
            re.match(
                r"^git\s+(status|diff|show|log|branch|rev-parse|grep|ls-files)(\s|$)",
                lowered,
            )
        )
    return True


def is_risky_command(command: str) -> bool:
    text = command.strip()
    if not text:
        return False

    lowered = text.lower()
    if any(marker in lowered for marker in RISKY_COMMAND_MARKERS):
        return True

    program = shell_command_name(text)
    if program in NETWORK_COMMANDS or program in WRITE_COMMANDS:
        return True

    return bool(
        re.search(
            r"\b(git\s+(push|pull|fetch|clone)|npm\s+(install|publish)|pnpm\s+(add|install|publish)|yarn\s+(add|install)|pip3?\s+install|uv\s+(run|pip|add)|make\s+install)\b",
            lowered,
        )
    )


def claude_pretool_requires_approval(payload: dict[str, Any]) -> bool:
    tool_name = str(payload.get("tool_name") or "").strip()
    tool_input = payload.get("tool_input") or {}
    lowered = tool_name.lower()

    if lowered == "bash":
        return is_risky_command(str(tool_input.get("command") or ""))
    if lowered in {"edit", "write", "multiedit", "notebookedit"}:
        return True
    if lowered.startswith("mcp__"):
        return True
    return False


def codex_pretool_requires_approval(
    payload: dict[str, Any],
    command: str,
) -> tuple[bool, dict[str, Any]]:
    turn_context = payload.get("turn_context") if isinstance(payload.get("turn_context"), dict) else None
    if not isinstance(turn_context, dict):
        turn_context = load_codex_turn_context(
            str(payload.get("transcript_path") or ""),
            str(payload.get("turn_id") or ""),
        )
    approval_policy = str(turn_context.get("approval_policy") or "").strip().lower()
    if approval_policy == "":
        return False, turn_context

    if approval_policy == "never":
        return is_risky_command(command), turn_context

    if approval_policy == "untrusted":
        return not is_safe_readonly_command(command), turn_context

    if approval_policy == "on-request":
        return is_risky_command(command), turn_context

    return False, turn_context


def codex_approval_details(command: str) -> tuple[str, str, str, list[str]]:
    text = command.strip()
    host_match = URL_RE.search(text)
    if host_match:
        approval_type = "network"
        question = f"Allow network access to {host_match.group(1)}?"
    elif re.search(r"\b(rm|mv|cp|mkdir|touch|tee|chmod|chown)\b", text):
        approval_type = "shell_write"
        question = "Allow this shell command to modify files?"
    else:
        approval_type = "bash"
        question = "Allow this shell command?"

    prefix = truncate(text, 36) or "this command"
    summary = truncate(f"Bash wants approval: {text}" if text else "Bash wants approval", 140)
    choices = [
        "Yes, proceed",
        f"Always allow `{prefix}`",
        "No, tell Codex what to do differently",
    ]
    return approval_type, question, summary, choices


def approval_rule_for_payload(source: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    lowered_source = str(source or "").strip().lower()
    if lowered_source == "codex":
        command = str(((payload.get("tool_input") or {}).get("command") or "")).strip()
        if not command:
            return None
        return {"kind": "command_exact", "tool_name": "Bash", "command": command}

    if lowered_source == "claude":
        tool_name = str(payload.get("tool_name") or "").strip()
        tool_input = payload.get("tool_input") or {}
        if tool_name.lower() == "bash":
            command = str(tool_input.get("command") or "").strip()
            if not command:
                return None
            return {"kind": "command_exact", "tool_name": tool_name, "command": command}
        if tool_name:
            return {"kind": "tool_name", "tool_name": tool_name}
    return None


def session_rule_matches(rule: dict[str, Any], source: str, payload: dict[str, Any]) -> bool:
    candidate = approval_rule_for_payload(source, payload)
    if not candidate:
        return False
    if str(rule.get("kind") or "") != str(candidate.get("kind") or ""):
        return False
    if str(rule.get("tool_name") or "") != str(candidate.get("tool_name") or ""):
        return False
    if candidate.get("kind") == "command_exact":
        return str(rule.get("command") or "") == str(candidate.get("command") or "")
    return True


def build_managed_approval_request(
    *,
    source: str,
    payload: dict[str, Any],
    approval_type: str,
    question: str,
    summary: str,
    choices: list[str],
) -> dict[str, Any]:
    tool_input = payload.get("tool_input") or {}
    cwd = str(payload.get("cwd") or os.getcwd())
    session_id = str(payload.get("session_id") or "")
    title_seed = first_present(tool_input.get("command"), tool_input.get("file_path"), question, summary)
    stable_label = stable_task_label_for_event(
        source,
        session_id,
        payload,
        cwd,
        title_seed,
        question,
        summary,
    )
    task_label = stable_label or derive_task_label(title_seed, cwd) or None
    title = truncate(stable_label, 44) if stable_label else derive_title(title_seed, cwd)
    review = build_review_info(
        cwd=cwd,
        command=str(tool_input.get("command") or "") or None,
        detail=first_present(tool_input.get("description"), tool_input.get("file_path"), question, summary),
        tool_name=str(payload.get("tool_name") or ""),
        approval_type=approval_type,
    )
    return {
        "request_key": approval_request_key(str(source), session_id),
        "source": source,
        "session_id": session_id,
        "ui_session_id": session_id,
        "run_id": str(payload.get("turn_id") or ""),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "cwd": cwd,
        "title": title,
        "task_label": task_label,
        "tool_name": str(payload.get("tool_name") or ""),
        "command": str(tool_input.get("command") or ""),
        "approval_type": approval_type,
        "question": question,
        "summary": summary,
        "choices": list(choices),
        "review": review,
        "rule": approval_rule_for_payload(source, payload),
        "jump_target": {},
    }


def managed_clear_event(
    *,
    source: str,
    payload: dict[str, Any],
    title_hint: str,
    summary: str,
    state: str = "running",
    kind: str = "session_updated",
) -> dict[str, Any]:
    cwd = payload.get("cwd") or os.getcwd()
    jump = detect_jump_target()
    session_id = str(payload.get("session_id") or f"{source}-{uuid.uuid4().hex[:8]}")
    stable_label = stable_task_label_for_event(
        source,
        session_id,
        payload,
        cwd,
        title_hint,
        payload.get("question"),
        payload.get("summary"),
        payload.get("last_assistant_message"),
    )
    title = truncate(stable_label, 44) if stable_label else derive_title(title_hint, cwd)
    task_label = stable_label or derive_task_label(title_hint, cwd)
    return make_event(
        source=source,
        adapter=f"{source}-hook",
        session_id=session_id,
        run_id=str(payload.get("turn_id") or "") or None,
        kind=kind,
        state=state,
        title=title,
        task_label=task_label,
        summary=summary,
        workspace=cwd,
        cwd=cwd,
        terminal=jump["terminal"],
        tty=jump["tty"],
        pid=jump["pid"],
        tmux_session=jump["tmux_session"],
        tmux_window=jump["tmux_window"],
        tmux_pane=jump["tmux_pane"],
        raw={"managed_approval": True},
    )


def apply_session_rule(source: str, session_id: str, rule: dict[str, Any] | None) -> None:
    if not rule:
        return
    existing = load_session_rules(source, session_id)
    for item in existing:
        if item == rule:
            return
    existing.append(rule)
    save_session_rules(source, session_id, existing)


def has_matching_session_rule(source: str, session_id: str, payload: dict[str, Any]) -> bool:
    for rule in load_session_rules(source, session_id):
        if session_rule_matches(rule, source, payload):
            return True
    return False


def write_managed_approval_request(request: dict[str, Any]) -> None:
    write_json_file(
        approval_request_path(str(request.get("source") or ""), str(request.get("session_id") or "")),
        request,
    )


def wait_for_managed_approval(
    request: dict[str, Any],
    blocked_event: dict[str, Any],
    socket_path: str,
) -> dict[str, Any]:
    source = str(request.get("source") or "")
    session_id = str(request.get("session_id") or "")
    path = approval_request_path(source, session_id)
    deadline = time.monotonic() + max(MANAGED_APPROVAL_TIMEOUT, 1.0)
    last_publish = 0.0

    while time.monotonic() < deadline:
        now = time.monotonic()
        if now - last_publish >= 2.0:
            publish_event(blocked_event, socket_path, ignore_errors=True)
            last_publish = now
        payload = read_json_file_maybe(path)
        decision = payload.get("decision")
        if isinstance(decision, dict) and decision.get("action"):
            return decision
        time.sleep(MANAGED_APPROVAL_POLL_INTERVAL)

    return {"action": "timeout", "reason": "Vibe Island approval timed out."}


def managed_deny_output(reason: str) -> int:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": truncate(reason, 240) or "Blocked by Vibe Island.",
                }
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


def maybe_complete_managed_approval(
    *,
    source: str,
    payload: dict[str, Any],
    request: dict[str, Any],
    decision: dict[str, Any],
    socket_path: str,
    title_hint: str,
) -> int:
    session_id = str(request.get("session_id") or "")
    action = str(decision.get("action") or "")
    followup = truncate(str(decision.get("followup_text") or "").strip(), 240)

    try:
        if action == "allow_session":
            apply_session_rule(source, session_id, request.get("rule") if isinstance(request.get("rule"), dict) else None)
            publish_event(
                managed_clear_event(
                    source=source,
                    payload=payload,
                    title_hint=title_hint,
                    summary="Approval granted and remembered for this session.",
                ),
                socket_path,
                ignore_errors=True,
            )
            return 0
        if action == "allow_once":
            publish_event(
                managed_clear_event(
                    source=source,
                    payload=payload,
                    title_hint=title_hint,
                    summary="Approval granted via Vibe Island.",
                ),
                socket_path,
                ignore_errors=True,
            )
            return 0

        if action == "deny":
            reason = followup or str(decision.get("reason") or "").strip() or "Blocked by Vibe Island."
            publish_event(
                managed_clear_event(
                    source=source,
                    payload=payload,
                    title_hint=title_hint,
                    summary=truncate(f"Denied: {reason}", 140),
                    state="failed",
                    kind="failed",
                ),
                socket_path,
                ignore_errors=True,
            )
            return managed_deny_output(reason)

        timeout_reason = str(decision.get("reason") or "Vibe Island approval timed out.")
        publish_event(
            managed_clear_event(
                source=source,
                payload=payload,
                title_hint=title_hint,
                summary=truncate(timeout_reason, 140),
                state="failed",
                kind="failed",
            ),
            socket_path,
            ignore_errors=True,
        )
        return managed_deny_output(timeout_reason)
    finally:
        clear_approval_request(source, session_id)


def maybe_log_hook_payload(channel: str, payload: Any) -> None:
    path_value = os.environ.get("VIBEISLAND_HOOK_LOG")
    if not path_value:
        return
    try:
        path = Path(path_value)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"channel": channel, "payload": payload}, ensure_ascii=False))
            handle.write("\n")
    except Exception:
        pass


def event_from_claude_hook(payload: dict[str, Any]) -> dict[str, Any]:
    hook_name = payload.get("hook_event_name", "Unknown")
    cwd = payload.get("cwd") or os.getcwd()
    session_id = payload.get("session_id") or f"claude-{uuid.uuid4().hex[:8]}"
    run_id = payload.get("turn_id")
    jump = detect_jump_target()

    kind = "session_updated"
    state = "running"
    summary = truncate(first_present(payload.get("message"), payload.get("reason"), hook_name)) or hook_name
    title_seed = first_present(payload.get("prompt"), payload.get("message"))
    title = derive_title(title_seed, cwd)
    task_label = derive_task_label(title_seed, cwd) or None
    approval_type = None
    question = None
    choices: list[str] = []
    review: dict[str, Any] = {}

    if hook_name == "SessionStart":
        kind = "session_started"
        summary = f"Claude session started ({payload.get('source', 'startup')})"
        title = derive_title(payload.get("source"), cwd)
        task_label = derive_task_label(payload.get("source"), cwd) or None
    elif hook_name == "UserPromptSubmit":
        prompt = payload.get("prompt") or "Claude prompt submitted"
        kind = "session_updated"
        summary = truncate(prompt, 120)
        title = derive_title(prompt, cwd)
        task_label = derive_task_label(prompt, cwd) or None
    elif hook_name == "PreToolUse":
        tool_name = payload.get("tool_name") or "tool"
        tool_input = payload.get("tool_input") or {}
        detail = first_present(
            tool_input.get("command"),
            tool_input.get("file_path"),
            tool_input.get("description"),
            tool_name,
        )
        summary = truncate(f"{tool_name}: {detail}" if detail else f"Claude is preparing {tool_name}", 140)
        title = derive_title(detail or str(tool_name), cwd)
        task_label = derive_task_label(detail or str(tool_name), cwd) or None
        if claude_pretool_requires_approval(payload):
            kind = "needs_approval"
            state = "blocked"
            approval_type = str(tool_name).lower()
            question, summary, choices = claude_approval_details(tool_name, tool_input, payload)
            review = build_review_info(
                cwd=cwd,
                command=str(tool_input.get("command") or "") or None,
                detail=first_present(tool_input.get("description"), tool_input.get("file_path"), question, detail),
                tool_name=str(tool_name),
                approval_type=approval_type,
            )
    elif hook_name == "PermissionRequest":
        tool_name = payload.get("tool_name") or "tool"
        tool_input = payload.get("tool_input") or {}
        kind = "needs_approval"
        state = "blocked"
        approval_type = str(tool_name).lower()
        question, summary, choices = claude_approval_details(tool_name, tool_input, payload)
        title = derive_title(
            first_present(tool_input.get("command"), tool_input.get("file_path"), question),
            cwd,
        )
        task_label = derive_task_label(
            first_present(tool_input.get("command"), tool_input.get("file_path"), question),
            cwd,
        ) or None
        review = build_review_info(
            cwd=cwd,
            command=str(tool_input.get("command") or "") or None,
            detail=first_present(tool_input.get("description"), tool_input.get("file_path"), question, summary),
            tool_name=str(tool_name),
            approval_type=approval_type,
        )
    elif hook_name == "Notification":
        notification_type = payload.get("notification_type") or payload.get("message_type") or "notification"
        message = first_present(payload.get("message"), payload.get("content"), notification_type)
        summary = truncate(str(message))
        title = derive_title(payload.get("title") or message, cwd)
        task_label = derive_task_label(payload.get("title") or message, cwd) or None
        lowered = str(notification_type).lower()
        if "permission" in lowered:
            kind = "needs_approval"
            state = "blocked"
            approval_type = "notification"
            question = truncate(str(message), 120)
            choices = extract_choices_from_text(str(message)) or ["Yes", "Yes, don't ask again", "No"]
            review = build_review_info(
                cwd=cwd,
                command=None,
                detail=question,
                tool_name=str(notification_type),
                approval_type=approval_type,
            )
        elif "idle" in lowered:
            kind = "completed"
            state = "completed"
        else:
            kind = "session_updated"
    elif hook_name == "Elicitation":
        kind = "ask_user"
        state = "waiting_user"
        question = str(payload.get("message") or "Claude needs input")
        choices = extract_choices_from_schema(payload.get("requested_schema"))
        summary = truncate(question)
        title = derive_title(question, cwd)
        task_label = derive_task_label(question, cwd) or None
    elif hook_name == "Stop":
        last_message = payload.get("last_assistant_message") or "Claude finished responding"
        inferred = detect_interaction_from_message(last_message)
        if inferred:
            kind = inferred["kind"]
            state = inferred["state"]
            approval_type = inferred["approval_type"]
            question = inferred["question"]
            choices = inferred["choices"]
            summary = inferred["summary"]
            title = derive_title(question, cwd)
            task_label = derive_task_label(question, cwd) or None
        else:
            kind = "completed"
            state = "completed"
            summary = truncate(last_message, 140)
            title = derive_title(last_message, cwd)
            task_label = derive_task_label(last_message, cwd) or None
    elif hook_name == "PostToolUse":
        tool_name = payload.get("tool_name") or "tool"
        tool_input = payload.get("tool_input") or {}
        detail = first_present(tool_input.get("command"), tool_input.get("file_path"), payload.get("cwd"))
        summary = truncate(f"{tool_name}: {detail}" if detail else f"{tool_name} completed")
        title = derive_title(detail or tool_name, cwd)
        task_label = derive_task_label(detail or tool_name, cwd) or None
    elif hook_name == "PostToolUseFailure":
        kind = "failed"
        state = "failed"
        tool_name = payload.get("tool_name") or "tool"
        tool_input = payload.get("tool_input") or {}
        detail = first_present(tool_input.get("command"), tool_input.get("file_path"), payload.get("reason"))
        summary = truncate(f"{tool_name} failed: {detail}" if detail else f"{tool_name} failed")
        title = derive_title(detail or tool_name, cwd)
        task_label = derive_task_label(detail or tool_name, cwd) or None

    stable_label = stable_task_label_for_event(
        "claude",
        session_id,
        payload,
        cwd,
        payload.get("prompt"),
        payload.get("user_prompt"),
    )
    if stable_label:
        task_label = stable_label
        title = truncate(stable_label, 44)

    return make_event(
        source="claude",
        adapter="claude-hook",
        session_id=session_id,
        run_id=run_id,
        kind=kind,
        state=state,
        title=title,
        task_label=task_label,
        summary=summary,
        approval_type=approval_type,
        question=question,
        choices=choices,
        review=review,
        workspace=cwd,
        cwd=cwd,
        terminal=jump["terminal"],
        tty=jump["tty"],
        pid=jump["pid"],
        tmux_session=jump["tmux_session"],
        tmux_window=jump["tmux_window"],
        tmux_pane=jump["tmux_pane"],
        raw=payload,
    )


def event_from_codex_hook(payload: dict[str, Any]) -> dict[str, Any]:
    hook_name = payload.get("hook_event_name", "Unknown")
    cwd = payload.get("cwd") or os.getcwd()
    session_id = payload.get("session_id") or f"codex-{uuid.uuid4().hex[:8]}"
    run_id = payload.get("turn_id")
    jump = detect_jump_target()
    raw_payload = dict(payload)

    kind = "session_updated"
    state = "running"
    summary = truncate(first_present(payload.get("message"), hook_name)) or hook_name
    title_seed = first_present(payload.get("prompt"), payload.get("message"))
    title = derive_title(title_seed, cwd)
    task_label = derive_task_label(title_seed, cwd) or None
    approval_type = None
    question = None
    choices: list[str] = []
    review: dict[str, Any] = {}

    if hook_name == "SessionStart":
        kind = "session_started"
        summary = f"Codex session started ({payload.get('source', 'startup')})"
        title = derive_title(payload.get("source"), cwd)
        task_label = derive_task_label(payload.get("source"), cwd) or None
    elif hook_name == "UserPromptSubmit":
        prompt = payload.get("prompt") or "Codex prompt submitted"
        summary = truncate(prompt, 120)
        title = derive_title(prompt, cwd)
        task_label = derive_task_label(prompt, cwd) or None
    elif hook_name == "PreToolUse":
        command = ((payload.get("tool_input") or {}).get("command") or "").strip()
        summary = truncate(f"Bash: {command}" if command else "Codex is about to run Bash")
        title = derive_title(command or "Bash", cwd)
        task_label = derive_task_label(command or "Bash", cwd) or None
        requires_approval, turn_context = codex_pretool_requires_approval(payload, command)
        if turn_context:
            raw_payload["turn_context"] = turn_context
        if requires_approval:
            kind = "needs_approval"
            state = "blocked"
            approval_type, question, summary, choices = codex_approval_details(command)
            review = build_review_info(
                cwd=cwd,
                command=command or None,
                detail=first_present(payload.get("message"), payload.get("reason"), question),
                tool_name="Bash",
                approval_type=approval_type,
            )
    elif hook_name == "PermissionRequest":
        tool_name = payload.get("tool_name") or payload.get("tool") or "tool"
        tool_input = payload.get("tool_input") or {}
        detail = first_present(
            tool_input.get("command"),
            tool_input.get("description"),
            payload.get("message"),
            payload.get("reason"),
        )
        kind = "needs_approval"
        state = "blocked"
        approval_type = str(tool_name).lower()
        question = f"Approve {tool_name}?"
        choices = extract_choices_from_schema(payload.get("requested_schema")) or default_approval_choices()
        summary = truncate(
            f"{tool_name} wants approval: {detail}" if detail else f"{tool_name} wants approval",
            140,
        )
        title = derive_title(detail or tool_name, cwd)
        task_label = derive_task_label(detail or tool_name, cwd) or None
        review = build_review_info(
            cwd=cwd,
            command=str(tool_input.get("command") or "") or None,
            detail=first_present(tool_input.get("description"), payload.get("message"), payload.get("reason"), detail),
            tool_name=str(tool_name),
            approval_type=approval_type,
        )
    elif hook_name == "PermissionDenied":
        kind = "failed"
        state = "failed"
        tool_name = payload.get("tool_name") or payload.get("tool") or "tool"
        detail = first_present(payload.get("reason"), payload.get("message"), tool_name)
        summary = truncate(f"Permission denied: {detail}", 140)
        title = derive_title(detail, cwd)
        task_label = derive_task_label(detail, cwd) or None
    elif hook_name == "PostToolUse":
        command = ((payload.get("tool_input") or {}).get("command") or "").strip()
        summary = truncate(f"Completed: {command}" if command else "Codex completed a Bash step")
        title = derive_title(command or "Bash", cwd)
        task_label = derive_task_label(command or "Bash", cwd) or None
    elif hook_name == "PostToolUseFailure":
        kind = "failed"
        state = "failed"
        command = ((payload.get("tool_input") or {}).get("command") or "").strip()
        detail = first_present(payload.get("reason"), command, payload.get("message"))
        summary = truncate(f"Bash failed: {detail}" if detail else "Codex Bash step failed", 140)
        title = derive_title(detail or "Bash failed", cwd)
        task_label = derive_task_label(detail or "Bash failed", cwd) or None
    elif hook_name == "Stop":
        last_message = payload.get("last_assistant_message") or "Codex finished responding"
        inferred = detect_interaction_from_message(last_message)
        if inferred:
            kind = inferred["kind"]
            state = inferred["state"]
            approval_type = inferred["approval_type"]
            question = inferred["question"]
            choices = inferred["choices"]
            summary = inferred["summary"]
            title = derive_title(question, cwd)
            task_label = derive_task_label(question, cwd) or None
        else:
            kind = "completed"
            state = "completed"
            summary = truncate(last_message, 140)
            title = derive_title(last_message, cwd)
            task_label = derive_task_label(last_message, cwd) or None
    elif hook_name == "StopFailure":
        kind = "failed"
        state = "failed"
        detail = first_present(payload.get("reason"), payload.get("last_assistant_message"), "Codex failed")
        summary = truncate(str(detail), 140)
        title = derive_title(str(detail), cwd)
        task_label = derive_task_label(str(detail), cwd) or None

    stable_label = stable_task_label_for_event(
        "codex",
        session_id,
        raw_payload,
        cwd,
        payload.get("prompt"),
        payload.get("user_prompt"),
    )
    if stable_label:
        task_label = stable_label
        title = truncate(stable_label, 44)

    return make_event(
        source="codex",
        adapter="codex-hook",
        session_id=session_id,
        run_id=run_id,
        kind=kind,
        state=state,
        title=title,
        task_label=task_label,
        summary=summary,
        approval_type=approval_type,
        question=question,
        choices=choices,
        review=review,
        workspace=cwd,
        cwd=cwd,
        terminal=jump["terminal"],
        tty=jump["tty"],
        pid=jump["pid"],
        tmux_session=jump["tmux_session"],
        tmux_window=jump["tmux_window"],
        tmux_pane=jump["tmux_pane"],
        raw=raw_payload,
    )


def extract_message_text(value: Any) -> str:
    if isinstance(value, str):
        return normalize_text(value)
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                item_type = str(item.get("type") or "").lower()
                if item_type in {"text", "input_text", "output_text"}:
                    parts.append(str(item.get("text") or item.get("content") or ""))
        return normalize_text(" ".join(parts))
    if isinstance(value, dict):
        return normalize_text(
            first_present(
                value.get("text"),
                value.get("content"),
                value.get("message"),
            )
        )
    return ""


def extract_notify_task_seed(payload: dict[str, Any]) -> str:
    direct = first_present(
        payload.get("prompt"),
        payload.get("last_user_message"),
        payload.get("user_message"),
        payload.get("thread_title"),
        payload.get("title"),
    )
    if direct:
        return normalize_text(direct)

    for key in ("input_messages", "input-messages", "messages"):
        value = payload.get(key)
        if not isinstance(value, list):
            continue
        for item in reversed(value):
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or item.get("author") or item.get("type") or "").lower()
            if "user" not in role:
                continue
            content = extract_message_text(item.get("content"))
            if content:
                return content

    return normalize_text(
        first_present(
            payload.get("summary"),
            payload.get("last_assistant_message"),
            payload.get("message"),
        )
    )


def event_from_codex_notify(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {"message": str(payload)}

    cwd = payload.get("cwd") or os.getcwd()
    session_id = first_present(payload.get("thread_id"), payload.get("session_id"), payload.get("id"))
    if session_id is None:
        session_id = f"codex-{uuid.uuid4().hex[:8]}"

    status = str(payload.get("status") or payload.get("event") or "agent-turn-complete").lower()
    state = "completed"
    kind = "completed"
    if "fail" in status or "error" in status:
        state = "failed"
        kind = "failed"

    summary = truncate(
        first_present(
            payload.get("last_assistant_message"),
            payload.get("message"),
            payload.get("summary"),
            status,
        ),
        140,
    ) or "Codex turn completed"
    task_seed = extract_notify_task_seed(payload)
    title = derive_title(first_present(payload.get("title"), payload.get("thread_title"), task_seed, summary), cwd)
    task_label = derive_task_label(task_seed or summary, cwd) or None
    stable_label = stable_task_label_for_event(
        "codex",
        str(session_id),
        payload,
        cwd,
        task_seed,
        payload.get("title"),
        payload.get("thread_title"),
    )
    if stable_label:
        task_label = stable_label
        title = truncate(stable_label, 44)
    jump = detect_jump_target()

    return make_event(
        source="codex",
        adapter="codex-notify",
        session_id=str(session_id),
        run_id=payload.get("turn_id"),
        kind=kind,
        state=state,
        title=title,
        task_label=task_label,
        summary=summary,
        workspace=cwd,
        cwd=cwd,
        terminal=jump["terminal"],
        tty=jump["tty"],
        pid=jump["pid"],
        tmux_session=jump["tmux_session"],
        tmux_window=jump["tmux_window"],
        tmux_pane=jump["tmux_pane"],
        raw=payload,
    )


def choose_jump_target(payload: dict[str, Any]) -> dict[str, Any] | None:
    if "jump_target" in payload and isinstance(payload["jump_target"], dict):
        return payload["jump_target"]

    sessions = payload.get("sessions")
    if isinstance(sessions, list) and sessions:

        def priority(session: dict[str, Any]) -> tuple[int, int]:
            attention = int(session.get("attention_score", 0))
            blocked = 1 if str(session.get("state", "")).lower() in {"blocked", "waiting_user"} else 0
            return (blocked, attention)

        best = max(sessions, key=priority)
        target = best.get("jump_target")
        if isinstance(target, dict):
            return target

    return None


def tmux_target_from_jump_target(target: dict[str, Any]) -> str | None:
    tmux_pane = target.get("tmux_pane")
    if tmux_pane:
        tmux_session = target.get("tmux_session")
        tmux_window = target.get("tmux_window")
        if str(tmux_session or "").startswith("best:") or str(tmux_window or "").startswith("pid:"):
            return None
        if tmux_session and tmux_window:
            return f"{tmux_session}:{tmux_window}.{str(tmux_pane).lstrip('%')}"
        return str(tmux_pane)

    tmux_window = target.get("tmux_window")
    tmux_session = target.get("tmux_session")
    if str(tmux_session or "").startswith("best:") or str(tmux_window or "").startswith("pid:"):
        return None
    if tmux_session and tmux_window:
        return f"{tmux_session}:{tmux_window}"

    if tmux_session:
        return str(tmux_session)

    return None


def execute_tmux_jump(target: dict[str, Any], dry_run: bool = False) -> int:
    tmux_target = tmux_target_from_jump_target(target)
    if tmux_target and shutil.which("tmux") is not None:
        command = ["tmux", "select-pane", "-t", tmux_target]
        if dry_run:
            print(" ".join(shlex.quote(part) for part in command))
            return 0

        try:
            result = subprocess.run(command, check=False)
            if result.returncode == 0:
                return 0
        except FileNotFoundError:
            pass

    return execute_jump({"jump_target": target}, dry_run=dry_run)


def process_ancestors(pid: int | None, max_depth: int = 8) -> list[dict[str, Any]]:
    if not pid:
        return []

    items: list[dict[str, Any]] = []
    current = int(pid)
    seen: set[int] = set()
    for _ in range(max_depth):
        if current <= 1 or current in seen:
            break
        seen.add(current)
        proc_dir = Path("/proc") / str(current)
        if not proc_dir.exists():
            break

        cmdline = (proc_dir / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "ignore").strip()
        stat_parts = (proc_dir / "stat").read_text(encoding="utf-8").split()
        ppid = int(stat_parts[3]) if len(stat_parts) > 3 else 0
        exe_name = Path(cmdline.split(" ", 1)[0]).name if cmdline else ""
        items.append({"pid": current, "ppid": ppid, "cmdline": cmdline, "exe": exe_name})
        current = ppid
    return items


def activate_window_by_pid(pid: int | None, dry_run: bool = False) -> bool:
    if not pid or shutil.which("xdotool") is None:
        return False

    if dry_run:
        command = ["xdotool", "search", "--onlyvisible", "--pid", str(pid)]
        print(" ".join(shlex.quote(part) for part in command))
        return True

    search = subprocess.run(
        ["xdotool", "search", "--onlyvisible", "--pid", str(pid)],
        check=False,
        capture_output=True,
        text=True,
    )
    if search.returncode != 0:
        return False

    for window_id in [line.strip() for line in search.stdout.splitlines() if line.strip()]:
        result = subprocess.run(
            ["xdotool", "windowactivate", "--sync", window_id],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            return True
    return False


def open_in_konsole(cwd: str | None, dry_run: bool = False) -> bool:
    if not cwd or shutil.which("konsole") is None:
        return False
    command = ["konsole", "--workdir", cwd]
    if dry_run:
        print(" ".join(shlex.quote(part) for part in command))
        return True
    subprocess.Popen(command, cwd=cwd)
    return True


def open_with_xdg(path_value: str | None, dry_run: bool = False) -> bool:
    if not path_value or shutil.which("xdg-open") is None:
        return False
    command = ["xdg-open", path_value]
    if dry_run:
        print(" ".join(shlex.quote(part) for part in command))
        return True
    subprocess.Popen(command)
    return True


def snapshot_known_pids(snapshot: dict[str, Any]) -> set[int]:
    known: set[int] = set()
    for session in snapshot.get("sessions", []):
        jump_target = session.get("jump_target") or {}
        pid = jump_target.get("pid")
        if isinstance(pid, int) and pid > 0:
            known.add(pid)
    return known


def snapshot_known_signatures(snapshot: dict[str, Any]) -> set[tuple[str, str, str]]:
    signatures: set[tuple[str, str, str]] = set()
    for session in snapshot.get("sessions", []):
        source = str(session.get("source") or "").strip().lower()
        cwd = str(session.get("cwd") or session.get("workspace") or "").strip()
        jump_target = session.get("jump_target") or {}
        tty = str(jump_target.get("tty") or "").strip()
        if source and cwd and tty:
            signatures.add((source, cwd, tty))
    return signatures


def read_proc_cmdline(pid: int) -> list[str]:
    raw = (Path("/proc") / str(pid) / "cmdline").read_bytes()
    return [part.decode("utf-8", "ignore") for part in raw.split(b"\x00") if part]


def read_proc_cwd(pid: int) -> str | None:
    try:
        return os.readlink(f"/proc/{pid}/cwd")
    except OSError:
        return None


def read_proc_tty(pid: int) -> str | None:
    try:
        return os.readlink(f"/proc/{pid}/fd/0")
    except OSError:
        return None


def detect_terminal_from_ancestors(ancestors: list[dict[str, Any]]) -> str | None:
    for item in ancestors:
        exe = str(item.get("exe") or "").lower()
        if exe in KNOWN_TERMINALS:
            return exe
        cmdline = str(item.get("cmdline") or "").lower()
        for name in KNOWN_TERMINALS:
            if command_matches_name(name, exe=exe, cmdline=cmdline):
                return name
    return None


def detect_host_process_name(item: dict[str, Any]) -> str | None:
    exe = str(item.get("exe") or "").lower()
    if exe in KNOWN_TERMINALS:
        return exe

    cmdline = str(item.get("cmdline") or "").lower()
    for name in KNOWN_TERMINALS:
        if command_matches_name(name, exe=exe, cmdline=cmdline):
            return name
    return None


def classify_live_agent(argv: list[str]) -> str | None:
    if not argv:
        return None

    lowered = [arg.lower() for arg in argv]
    if any(
        "vibeisland.py" in arg or "claude-hook" in arg or "codex-hook" in arg or "codex-notify" in arg
        for arg in lowered
    ):
        return None

    for source in ("claude", "codex"):
        for index, token in enumerate(lowered):
            if Path(token).name != source:
                continue
            next_token = lowered[index + 1] if index + 1 < len(lowered) else ""
            if next_token in LIVE_SCAN_NONINTERACTIVE[source]:
                return None
            return source
    return None


def discover_live_agent_sessions(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    known_pids = snapshot_known_pids(snapshot)
    known_signatures = snapshot_known_signatures(snapshot)
    discovered: list[dict[str, Any]] = []

    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue

        pid = int(entry.name)
        if pid in known_pids:
            continue

        try:
            argv = read_proc_cmdline(pid)
        except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
            continue

        source = classify_live_agent(argv)
        if source is None:
            continue

        cwd = read_proc_cwd(pid)
        ancestors = process_ancestors(pid)
        terminal = detect_terminal_from_ancestors(ancestors)
        tty = read_proc_tty(pid)
        if not tty or not tty.startswith("/dev/"):
            continue
        if cwd and (source, cwd, tty) in known_signatures:
            continue
        title = derive_title(cwd or " ".join(argv[:2]), cwd)
        summary = truncate(
            f"{source.title()} running" + (f" in {cwd}" if cwd else ""),
            120,
        )

        discovered.append(
            make_event(
                source=source,
                adapter="process-scan",
                session_id=f"live::{source}::{pid}",
                kind="session_started",
                state="running",
                title=title,
                summary=summary,
                workspace=cwd,
                cwd=cwd,
                terminal=terminal,
                tty=tty,
                pid=pid,
                tmux_session=None,
                tmux_window=None,
                tmux_pane=None,
                raw={
                    "cmdline": argv,
                    "ancestors": ancestors,
                    "source": source,
                },
            )
        )

    return discovered


def extract_pid_from_target(target: dict[str, Any]) -> int | None:
    pid = target.get("pid")
    if isinstance(pid, int) and pid > 0:
        return pid

    for key in ("tmux_window", "tmux_session", "tmux_pane"):
        value = str(target.get(key) or "")
        match = re.search(r"pid:(\d+)", value)
        if match:
            return int(match.group(1))

    return None


def extract_cwd_from_target(target: dict[str, Any]) -> str | None:
    for key in ("cwd", "workspace"):
        value = target.get(key)
        if isinstance(value, str) and value.strip():
            return value

    pid = extract_pid_from_target(target)
    if pid:
        try:
            return os.readlink(f"/proc/{pid}/cwd")
        except OSError:
            return None

    return None


def list_session_bus_services() -> list[str]:
    if shutil.which("busctl") is not None:
        try:
            result = subprocess.run(
                ["busctl", "--user", "list"],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                services: list[str] = []
                for line in result.stdout.splitlines():
                    if not line.strip():
                        continue
                    services.append(line.split()[0])
                return services
        except Exception:
            pass

    if shutil.which("qdbus6") is not None:
        try:
            result = subprocess.run(
                ["qdbus6"],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return [line.strip() for line in result.stdout.splitlines() if line.strip()]
        except Exception:
            pass

    return []


def list_session_bus_entries() -> list[dict[str, Any]]:
    if shutil.which("busctl") is None:
        return []

    try:
        result = subprocess.run(
            ["busctl", "--user", "list"],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        return []

    if result.returncode != 0:
        return []

    entries: list[dict[str, Any]] = []
    lines = result.stdout.splitlines()
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 3:
            continue
        name, pid_text, process = parts[0], parts[1], parts[2]
        pid = None
        if pid_text.isdigit():
            pid = int(pid_text)
        entries.append({"name": name, "pid": pid, "process": process})
    return entries


def session_bus_names_for_pid(pid: int | None) -> list[str]:
    if not pid:
        return []

    names: list[str] = []
    for entry in list_session_bus_entries():
        if entry.get("pid") != pid:
            continue
        name = str(entry.get("name") or "")
        if name:
            names.append(name)
    return names


def session_bus_tree_paths(service: str, prefix: str) -> list[str]:
    if shutil.which("busctl") is None:
        return []

    try:
        result = subprocess.run(
            ["busctl", "--user", "tree", service],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        return []

    if result.returncode != 0:
        return []

    paths: list[str] = []
    seen: set[str] = set()
    for line in result.stdout.splitlines():
        match = re.search(r"(/\S+)", line)
        if match is None:
            continue
        path = match.group(1).strip()
        if not path.startswith(prefix) or path in seen:
            continue
        seen.add(path)
        paths.append(path)
    return paths


def run_session_bus_method_with_string(
    service: str,
    object_path: str,
    interface: str,
    method: str,
    argument: str,
    *,
    dry_run: bool = False,
) -> bool:
    busctl_command = ["busctl", "--user", "call", service, object_path, interface, method, "s", argument]
    if dry_run:
        print(" ".join(shlex.quote(part) for part in busctl_command))
        return True

    if shutil.which("busctl") is not None:
        try:
            result = subprocess.run(
                busctl_command,
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass

    if shutil.which("gdbus") is not None:
        try:
            result = subprocess.run(
                [
                    "gdbus",
                    "call",
                    "--session",
                    "--dest",
                    service,
                    "--object-path",
                    object_path,
                    "--method",
                    f"{interface}.{method}",
                    argument,
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass

    return False


def busctl_call_int(service: str, object_path: str, interface: str, method: str) -> int | None:
    if shutil.which("busctl") is None:
        return None
    try:
        result = subprocess.run(
            ["busctl", "--user", "call", service, object_path, interface, method],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None

    if result.returncode != 0:
        return None

    match = re.search(r"(-?\d+)", result.stdout)
    if match is None:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def konsole_session_paths(service: str) -> list[str]:
    return session_bus_tree_paths(service, "/Sessions/")


def konsole_session_path_for_pid(service: str, pid: int | None) -> str | None:
    paths = konsole_session_paths(service)
    if not paths:
        return None

    if pid is not None:
        for path in paths:
            foreground_pid = busctl_call_int(
                service,
                path,
                "org.kde.konsole.Session",
                "foregroundProcessId",
            )
            process_pid = busctl_call_int(service, path, "org.kde.konsole.Session", "processId")
            if pid in {foreground_pid, process_pid}:
                return path

    return paths[0]


def send_text_to_konsole_session(
    service_or_pid: str | int | None,
    response_text: str,
    *,
    append_enter: bool = True,
    dry_run: bool = False,
) -> bool:
    if service_or_pid is None:
        return False

    service = (
        service_or_pid
        if isinstance(service_or_pid, str) and service_or_pid.startswith("org.kde.konsole-")
        else f"org.kde.konsole-{service_or_pid}"
    )
    if service not in set(list_session_bus_services()):
        return False

    session_path = konsole_session_path_for_pid(service, int(service_or_pid) if isinstance(service_or_pid, int) else None)
    if session_path is None:
        return False

    payload = response_text
    if append_enter:
        payload = payload if payload.endswith("\n") else payload + "\n"

    if dry_run:
        print(
            " ".join(
                shlex.quote(part)
                for part in [
                    "busctl",
                    "--user",
                    "call",
                    service,
                    session_path,
                    "org.kde.konsole.Session",
                    "sendText",
                    "s",
                    payload,
                ]
            )
        )
        return True

    if run_session_bus_method_with_string(
        service,
        session_path,
        "org.kde.konsole.Session",
        "sendText",
        payload,
    ):
        return True

    return False


def is_kde_wayland_session() -> bool:
    session_type = str(os.environ.get("XDG_SESSION_TYPE") or "").lower()
    if session_type != "wayland":
        return False

    desktop = " ".join(
        [
            str(os.environ.get("DESKTOP_SESSION") or ""),
            str(os.environ.get("XDG_CURRENT_DESKTOP") or ""),
            str(os.environ.get("KDE_FULL_SESSION") or ""),
        ]
    ).lower()
    return "plasma" in desktop or "kde" in desktop or "true" in desktop


def _journal_lines_since(since: str) -> list[str]:
    if shutil.which("journalctl") is None:
        return []

    try:
        result = subprocess.run(
            ["journalctl", "--user", "--since", since, "-o", "cat", "--no-pager"],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        return []

    if result.returncode != 0:
        return []
    return result.stdout.splitlines()


def _wait_for_kwin_focus_result(token: str, since: str, timeout_seconds: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    matched_prefix = f"vibeisland-kwin-focus {token} matched"
    nomatch_prefix = f"vibeisland-kwin-focus {token} nomatch"

    while time.monotonic() < deadline:
        for line in _journal_lines_since(since):
            if matched_prefix in line:
                return True
            if nomatch_prefix in line:
                return False
        time.sleep(0.1)

    return False


def activate_with_kwin_script(pid: int | None, dry_run: bool = False) -> bool:
    if not pid or shutil.which("busctl") is None or not is_kde_wayland_session():
        return False

    token = uuid.uuid4().hex[:12]
    plugin_name = f"vibeislandfocus{token}"
    script_path = Path(tempfile.gettempdir()) / f"{plugin_name}.js"
    script_content = "\n".join(
        [
            f'var targetPid = {int(pid)};',
            f'var token = "{token}";',
            "var matched = false;",
            "for (const w of workspace.stackingOrder) {",
            "  if (w.pid === targetPid) {",
            "    matched = true;",
            "    if (w.minimized) {",
            "      w.minimized = false;",
            "    }",
            "    if (!w.onAllDesktops && w.desktops.length > 0) {",
            "      workspace.currentDesktop = w.desktops[0];",
            "    }",
            "    workspace.activeWindow = w;",
            '    print("vibeisland-kwin-focus", token, "matched", w.pid, w.caption);',
            "    break;",
            "  }",
            "}",
            "if (!matched) {",
            '  print("vibeisland-kwin-focus", token, "nomatch", targetPid);',
            "}",
            "",
        ]
    )
    script_path.write_text(script_content, encoding="utf-8")

    commands = [
        [
            "busctl",
            "--user",
            "call",
            "org.kde.KWin",
            "/Scripting",
            "org.kde.kwin.Scripting",
            "loadScript",
            "ss",
            str(script_path),
            plugin_name,
        ],
        [
            "busctl",
            "--user",
            "call",
            "org.kde.KWin",
            "/Scripting",
            "org.kde.kwin.Scripting",
            "start",
        ],
    ]

    unload_command = [
        "busctl",
        "--user",
        "call",
        "org.kde.KWin",
        "/Scripting",
        "org.kde.kwin.Scripting",
        "unloadScript",
        "s",
        plugin_name,
    ]

    if dry_run:
        for command in commands + [unload_command]:
            print(" ".join(shlex.quote(part) for part in command))
        try:
            script_path.unlink(missing_ok=True)
        except Exception:
            pass
        return True

    since = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        for command in commands:
            result = subprocess.run(command, check=False, capture_output=True, text=True)
            if result.returncode != 0:
                return False
        return _wait_for_kwin_focus_result(token, since)
    finally:
        try:
            subprocess.run(unload_command, check=False, capture_output=True, text=True)
        except Exception:
            pass
        try:
            script_path.unlink(missing_ok=True)
        except Exception:
            pass


def run_session_bus_method(
    service: str,
    object_path: str,
    interface: str,
    method: str,
    *,
    dry_run: bool = False,
) -> bool:
    busctl_command = ["busctl", "--user", "call", service, object_path, interface, method]
    if dry_run:
        print(" ".join(shlex.quote(part) for part in busctl_command))
        return True

    if shutil.which("busctl") is not None:
        try:
            result = subprocess.run(
                busctl_command,
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass

    if shutil.which("gdbus") is not None:
        try:
            result = subprocess.run(
                [
                    "gdbus",
                    "call",
                    "--session",
                    "--dest",
                    service,
                    "--object-path",
                    object_path,
                    "--method",
                    f"{interface}.{method}",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass

    return False


def call_session_bus_method(
    service: str,
    object_path: str,
    interface: str,
    method: str,
    *,
    signature: str = "",
    args: list[str] | None = None,
    dry_run: bool = False,
) -> tuple[bool, str]:
    command = ["busctl", "--user", "call", service, object_path, interface, method]
    if signature:
        command.append(signature)
        command.extend(args or [])

    if dry_run:
        print(" ".join(shlex.quote(part) for part in command))
        return True, ""

    if shutil.which("busctl") is None:
        return False, ""

    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        return False, ""

    return result.returncode == 0, result.stdout.strip()


def activate_application_service(
    service: str,
    object_path: str,
    *,
    dry_run: bool = False,
) -> bool:
    activated = run_session_bus_method(
        service,
        object_path,
        "org.freedesktop.Application",
        "Activate",
        dry_run=dry_run,
    )
    action = run_session_bus_method(
        service,
        object_path,
        "org.freedesktop.Application",
        "ActivateAction",
        dry_run=dry_run,
    ) if dry_run else False

    if dry_run:
        print(
            "gdbus call --session --dest "
            + shlex.quote(service)
            + " --object-path "
            + shlex.quote(object_path)
            + " --method org.freedesktop.Application.ActivateAction focus-window [] {}"
        )
        return activated or action

    if activated:
        return True

    if shutil.which("gdbus") is None:
        return False

    try:
        result = subprocess.run(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                service,
                "--object-path",
                object_path,
                "--method",
                "org.freedesktop.Application.ActivateAction",
                "focus-window",
                "[]",
                "{}",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except Exception:
        return False


def list_konsole_session_paths(service: str) -> list[str]:
    if shutil.which("busctl") is None:
        return []

    try:
        result = subprocess.run(
            ["busctl", "--user", "tree", service],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        return []

    if result.returncode != 0:
        return []

    paths: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"(/Sessions/\d+)", result.stdout):
        path = match.group(1)
        if path in seen:
            continue
        seen.add(path)
        paths.append(path)
    return paths


def konsole_session_int(service: str, session_path: str, method: str) -> int | None:
    ok, output = call_session_bus_method(
        service,
        session_path,
        "org.kde.konsole.Session",
        method,
    )
    if not ok:
        return None
    match = re.search(r"\bi\s+(-?\d+)\b", output)
    if not match:
        return None
    return int(match.group(1))


def konsole_session_ttys(service: str, session_path: str) -> tuple[str | None, str | None]:
    process_pid = konsole_session_int(service, session_path, "processId")
    foreground_pid = konsole_session_int(service, session_path, "foregroundProcessId")
    process_tty = normalize_tty_path(read_proc_tty(process_pid)) if process_pid else None
    foreground_tty = normalize_tty_path(read_proc_tty(foreground_pid)) if foreground_pid else None
    return process_tty, foreground_tty


def find_konsole_session_target(target: dict[str, Any]) -> tuple[str, str] | None:
    session_bus_services = set(list_session_bus_services())
    konsole_services = sorted(service for service in session_bus_services if service.startswith("org.kde.konsole-"))
    if not konsole_services:
        return None

    original_pid = extract_pid_from_target(target)
    candidate_pids: list[int] = []
    candidate_ttys: set[str] = set()
    target_tty = normalize_tty_path(target.get("tty"))
    if target_tty:
        candidate_ttys.add(target_tty)
    for item in jump_process_candidates(original_pid):
        pid = int(item.get("pid") or 0)
        if pid > 0 and pid not in candidate_pids:
            candidate_pids.append(pid)
            candidate_tty = normalize_tty_path(read_proc_tty(pid))
            if candidate_tty:
                candidate_ttys.add(candidate_tty)
    if original_pid and original_pid not in candidate_pids:
        candidate_pids.insert(0, original_pid)

    best_match: tuple[str, str] | None = None
    best_score = -1
    for service in konsole_services:
        for session_path in list_konsole_session_paths(service):
            foreground_pid = konsole_session_int(service, session_path, "foregroundProcessId")
            process_pid = konsole_session_int(service, session_path, "processId")
            process_tty, foreground_tty = konsole_session_ttys(service, session_path)
            score = 0
            if original_pid and foreground_pid == original_pid:
                score += 14
            elif original_pid and process_pid == original_pid:
                score += 11
            elif foreground_pid in candidate_pids:
                score += 8
            elif process_pid in candidate_pids:
                score += 6

            if target_tty and foreground_tty == target_tty:
                score += 7
            elif target_tty and process_tty == target_tty:
                score += 5
            elif foreground_tty and foreground_tty in candidate_ttys:
                score += 4
            elif process_tty and process_tty in candidate_ttys:
                score += 3

            if score > best_score:
                best_match = (service, session_path)
                best_score = score

    return best_match if best_score > 0 else None


def send_response_via_konsole_session(
    target: dict[str, Any],
    response_text: str,
    *,
    append_enter: bool = True,
    dry_run: bool = False,
) -> bool:
    if shutil.which("busctl") is None:
        return False

    match = find_konsole_session_target(target)
    if match is None:
        return False

    service, session_path = match
    payload = sanitize_terminal_message(response_text)
    if append_enter:
        payload = payload + terminal_submit_suffix()

    ok, _ = call_session_bus_method(
        service,
        session_path,
        "org.kde.konsole.Session",
        "sendText",
        signature="s",
        args=[payload],
        dry_run=dry_run,
    )
    return ok


def focus_existing_konsole(dry_run: bool = False) -> bool:
    konsole_services = [service for service in list_session_bus_services() if service.startswith("org.kde.konsole-")]
    if not konsole_services:
        return False

    for service in konsole_services:
        if activate_konsole_service(service, dry_run=dry_run):
            return True
    return False


def activate_konsole_service(service_or_pid: str | int | None, dry_run: bool = False) -> bool:
    if service_or_pid is None:
        return False

    service = (
        service_or_pid
        if isinstance(service_or_pid, str) and service_or_pid.startswith("org.kde.konsole-")
        else f"org.kde.konsole-{service_or_pid}"
    )
    if service not in set(list_session_bus_services()):
        return False

    if activate_application_service(service, "/org/kde/konsole", dry_run=dry_run):
        return True

    return all(
        run_session_bus_method(
            service,
            "/konsole/MainWindow_1",
            "org.qtproject.Qt.QWidget",
            method,
            dry_run=dry_run,
        )
        for method in ("showNormal", "raise", "setFocus")
    )


def activate_known_app_by_pid(pid: int | None, host_name: str | None, dry_run: bool = False) -> bool:
    if not pid or not host_name:
        return False

    object_paths = {
        "konsole": ["/org/kde/konsole"],
        "code": ["/org/freedesktop/Application"],
        "code-insiders": ["/org/freedesktop/Application"],
        "cursor": ["/org/freedesktop/Application"],
    }.get(host_name, ["/org/freedesktop/Application"])

    for service in session_bus_names_for_pid(pid):
        if service.startswith(":") or service.startswith("org.freedesktop.DBus"):
            for object_path in object_paths:
                if activate_application_service(service, object_path, dry_run=dry_run):
                    return True

    return False


def activate_window_via_kwin(pid: int | None, dry_run: bool = False) -> bool:
    return activate_with_kwin_script(pid, dry_run=dry_run)


def restore_window_focus(pid: int | None, dry_run: bool = False) -> bool:
    if not pid:
        return False
    if activate_window_via_kwin(pid, dry_run=dry_run):
        return True
    if activate_window_by_pid(pid, dry_run=dry_run):
        return True
    return False


def jump_process_candidates(pid: int | None) -> list[dict[str, Any]]:
    if not pid:
        return []

    ancestors = process_ancestors(pid)
    ordered: list[dict[str, Any]] = []
    seen: set[int] = set()

    for item in ancestors:
        if detect_host_process_name(item) is None:
            continue
        current = int(item["pid"])
        if current in seen:
            continue
        ordered.append(item)
        seen.add(current)

    for item in ancestors:
        current = int(item["pid"])
        if current in seen:
            continue
        ordered.append(item)
        seen.add(current)

    return ordered


def has_existing_jump_target(target: dict[str, Any]) -> bool:
    if extract_pid_from_target(target) is not None:
        return True
    if str(target.get("tty") or "").strip():
        return True
    return tmux_target_from_jump_target(target) is not None


def execute_jump(payload: dict[str, Any], dry_run: bool = False) -> int:
    target = choose_jump_target(payload) or {}
    cwd = payload.get("cwd") or payload.get("workspace") or extract_cwd_from_target(target)
    existing_target = has_existing_jump_target(target)

    if isinstance(payload.get("session"), dict):
        cwd = cwd or payload["session"].get("cwd") or payload["session"].get("workspace")

    if tmux_target_from_jump_target(target) and shutil.which("tmux") is not None:
        tmux_result = execute_tmux_jump(target, dry_run=dry_run)
        if tmux_result == 0:
            return 0

    pid = extract_pid_from_target(target)
    for candidate in jump_process_candidates(pid):
        candidate_pid = int(candidate["pid"])
        host_name = detect_host_process_name(candidate)

        if activate_window_via_kwin(candidate_pid, dry_run=dry_run):
            return 0

        activated = False

        if host_name == "konsole":
            activated = activate_konsole_service(candidate_pid, dry_run=dry_run) or activated

        activated = activate_known_app_by_pid(candidate_pid, host_name, dry_run=dry_run) or activated

        if activated:
            return 0

        if activate_window_by_pid(candidate_pid, dry_run=dry_run):
            return 0

    if pid is None and focus_existing_konsole(dry_run=dry_run):
        return 0

    if existing_target:
        print("Unable to focus the existing session window", file=sys.stderr)
        return 1

    if open_with_xdg(cwd, dry_run=dry_run):
        return 0

    print("No usable jump strategy found", file=sys.stderr)
    return 1


def cmd_reconcile(args: argparse.Namespace) -> int:
    snapshot = request_snapshot(args.socket)
    live_events = discover_live_agent_sessions(snapshot)

    published = 0
    for event in live_events:
        if args.print_events:
            print(json.dumps(event, ensure_ascii=False))
            continue
        publish_event(event, args.socket, ignore_errors=True)
        published += 1

    if args.json:
        print(
            json.dumps(
                {
                    "known": len(snapshot.get("sessions", [])),
                    "discovered": len(live_events),
                    "published": published,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    elif not args.print_events:
        print(f"reconciled={published} discovered={len(live_events)}", flush=True)

    return 0


def bridge_command_string(subcommand: str) -> str:
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(BRIDGE_SCRIPT))} {subcommand}"


def build_claude_hooks() -> dict[str, list[dict[str, Any]]]:
    command = bridge_command_string("claude-hook")
    handler = {"type": "command", "command": command, "timeout": 8}
    pretool_handler = {"type": "command", "command": command}
    return {
        "SessionStart": [{"matcher": "startup|resume", "hooks": [handler]}],
        "UserPromptSubmit": [{"hooks": [handler]}],
        "PreToolUse": [{"hooks": [pretool_handler]}],
        "PermissionRequest": [
            {"matcher": "Bash|Edit|Write|MultiEdit|NotebookEdit|mcp__.*", "hooks": [handler]}
        ],
        "Notification": [{"matcher": "permission_prompt|idle_prompt", "hooks": [handler]}],
        "Elicitation": [{"hooks": [handler]}],
        "Stop": [{"hooks": [handler]}],
        "PostToolUse": [{"matcher": "Bash|Edit|Write|MultiEdit", "hooks": [handler]}],
        "PostToolUseFailure": [{"matcher": "Bash|Edit|Write|MultiEdit", "hooks": [handler]}],
    }


def build_claude_statusline() -> dict[str, Any]:
    return {
        "type": "command",
        "command": bridge_command_string("claude-statusline"),
    }


def build_codex_hooks() -> dict[str, list[dict[str, Any]]]:
    command = bridge_command_string("codex-hook")
    handler = {"type": "command", "command": command}
    return {
        "SessionStart": [{"matcher": "startup|resume", "hooks": [handler]}],
        "UserPromptSubmit": [{"hooks": [handler]}],
        "PreToolUse": [{"matcher": "Bash", "hooks": [handler]}],
        "PermissionRequest": [{"hooks": [handler]}],
        "PermissionDenied": [{"hooks": [handler]}],
        "PostToolUse": [{"matcher": "Bash", "hooks": [handler]}],
        "PostToolUseFailure": [{"hooks": [handler]}],
        "Stop": [{"hooks": [handler]}],
        "StopFailure": [{"hooks": [handler]}],
    }


def group_contains_marker(group: dict[str, Any], marker: str) -> bool:
    hooks = group.get("hooks")
    if not isinstance(hooks, list):
        return False
    for hook in hooks:
        if not isinstance(hook, dict):
            continue
        command = str(hook.get("command") or "")
        if marker in command and BRIDGE_SCRIPT.name in command:
            return True
    return False


def merge_hook_groups(
    existing_groups: Any,
    generated_groups: list[dict[str, Any]],
    marker: str,
) -> list[dict[str, Any]]:
    existing = existing_groups if isinstance(existing_groups, list) else []
    filtered = [group for group in existing if not group_contains_marker(group, marker)]
    filtered.extend(generated_groups)
    return filtered


def render_toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ", ".join(json.dumps(item, ensure_ascii=False) for item in value) + "]"
    if value is None:
        return '""'
    return json.dumps(value, ensure_ascii=False)


def set_toml_key(text: str, key: str, value: Any, section: str | None = None) -> str:
    lines = text.splitlines()
    rendered = f"{key} = {render_toml_value(value)}"
    trailing_newline = "\n" if text.endswith("\n") or not text else ""

    if section is None:
        for index, line in enumerate(lines):
            stripped = line.strip()
            if line.startswith((" ", "\t")):
                continue
            if re.match(rf"^{re.escape(key)}\s*=", stripped):
                lines[index] = rendered
                return "\n".join(lines) + trailing_newline
        insert_at = 0
        while insert_at < len(lines) and not lines[insert_at].strip():
            insert_at += 1
        lines.insert(insert_at, rendered)
        return "\n".join(lines) + trailing_newline

    header = f"[{section}]"
    header_index = next((idx for idx, line in enumerate(lines) if line.strip() == header), None)
    if header_index is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(header)
        lines.append(rendered)
        return "\n".join(lines) + trailing_newline

    end_index = len(lines)
    for index in range(header_index + 1, len(lines)):
        if lines[index].strip().startswith("[") and lines[index].strip().endswith("]"):
            end_index = index
            break

    for index in range(header_index + 1, end_index):
        stripped = lines[index].strip()
        if re.match(rf"^{re.escape(key)}\s*=", stripped):
            lines[index] = rendered
            return "\n".join(lines) + trailing_newline

    lines.insert(end_index, rendered)
    return "\n".join(lines) + trailing_newline


def install_claude_hooks(settings_path: Path, dry_run: bool = False) -> dict[str, Any]:
    data = read_json_file(settings_path, {})
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}

    for event_name, groups in build_claude_hooks().items():
        hooks[event_name] = merge_hook_groups(hooks.get(event_name), groups, "claude-hook")

    data["hooks"] = hooks
    data["statusLine"] = build_claude_statusline()
    rendered = json.dumps(data, indent=2, ensure_ascii=False) + "\n"

    backup = None
    if not dry_run:
        backup = backup_file(settings_path)
        atomic_write_text(settings_path, rendered)

    return {
        "path": str(settings_path),
        "backup": str(backup) if backup else None,
        "events": sorted(build_claude_hooks().keys()),
        "status_line": build_claude_statusline(),
        "dry_run": dry_run,
    }


def install_codex_hooks(
    config_path: Path,
    hooks_path: Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    config_text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    config_text = set_toml_key(config_text, "notify", [sys.executable, str(BRIDGE_SCRIPT), "codex-notify"])
    config_text = set_toml_key(config_text, "approval_policy", "never")
    config_text = set_toml_key(config_text, "codex_hooks", True, section="features")

    hooks_data = read_json_file(hooks_path, {})
    hooks = hooks_data.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}

    for event_name, groups in build_codex_hooks().items():
        hooks[event_name] = merge_hook_groups(hooks.get(event_name), groups, "codex-hook")

    hooks_data["hooks"] = hooks
    hooks_rendered = json.dumps(hooks_data, indent=2, ensure_ascii=False) + "\n"

    config_backup = None
    hooks_backup = None
    if not dry_run:
        config_backup = backup_file(config_path)
        hooks_backup = backup_file(hooks_path)
        atomic_write_text(config_path, config_text if config_text.endswith("\n") else config_text + "\n")
        atomic_write_text(hooks_path, hooks_rendered)

    return {
        "config_path": str(config_path),
        "hooks_path": str(hooks_path),
        "config_backup": str(config_backup) if config_backup else None,
        "hooks_backup": str(hooks_backup) if hooks_backup else None,
        "events": sorted(build_codex_hooks().keys()),
        "dry_run": dry_run,
    }


def build_common_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--socket", default=DEFAULT_SOCKET)
    parser.add_argument("--session-id", required=False)
    parser.add_argument("--title", default="Untitled session")
    parser.add_argument("--summary", default="")
    parser.add_argument("--kind", default="session_updated")
    parser.add_argument("--state", default="running")
    parser.add_argument("--workspace")
    parser.add_argument("--cwd")
    parser.add_argument("--run-id")
    parser.add_argument("--approval-type")
    parser.add_argument("--question")
    parser.add_argument("--choice", action="append", default=[])
    parser.add_argument("--phase")
    parser.add_argument("--pct", type=float)
    parser.add_argument("--terminal")
    parser.add_argument("--tty")
    parser.add_argument("--pid", type=int)
    parser.add_argument("--tmux-session")
    parser.add_argument("--tmux-window")
    parser.add_argument("--tmux-pane")
    parser.add_argument("--raw-json")
    return parser


def emit_event(source: str, args: argparse.Namespace) -> int:
    session_id = args.session_id or f"{source}-{uuid.uuid4().hex[:8]}"
    raw = load_json_maybe(args.raw_json) if args.raw_json else {}
    event = make_event(
        source=source,
        session_id=session_id,
        kind=args.kind,
        state=args.state,
        title=args.title,
        summary=args.summary,
        workspace=args.workspace,
        cwd=args.cwd,
        run_id=args.run_id,
        approval_type=args.approval_type,
        question=args.question,
        choices=args.choice,
        phase=args.phase,
        pct=args.pct,
        terminal=args.terminal,
        tty=args.tty,
        pid=args.pid,
        tmux_session=args.tmux_session,
        tmux_window=args.tmux_window,
        tmux_pane=args.tmux_pane,
        raw=raw,
    )
    response = publish_event(event, args.socket)
    print(json.dumps(response, ensure_ascii=False), flush=True)
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    for message in subscribe(args.socket):
        snapshot = message.get("snapshot", message)
        if args.json:
            print(json.dumps(snapshot, ensure_ascii=False), flush=True)
            continue

        sessions = snapshot.get("sessions", [])
        blocked = snapshot.get("blocked_count", 0)
        active = snapshot.get("active_count", len(sessions))
        print(f"[watch] active={active} blocked={blocked}", flush=True)
        for session in sessions[:5]:
            print(
                f"  - {session.get('title', 'Untitled')} | {session.get('state')} | "
                f"{session.get('summary', '')}",
                flush=True,
            )
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    snapshot = request_snapshot(args.socket)
    print(json.dumps(snapshot, ensure_ascii=False, indent=2), flush=True)
    return 0


def cmd_tmux_jump(args: argparse.Namespace) -> int:
    payload: dict[str, Any] | None = None
    if not sys.stdin.isatty():
        raw = sys.stdin.read().strip()
        if raw:
            payload = json.loads(raw)

    target = None
    if payload:
        target = choose_jump_target(payload)

    if target is None:
        target = {
            "tmux_session": args.tmux_session,
            "tmux_window": args.tmux_window,
            "tmux_pane": args.tmux_pane,
        }

    return execute_tmux_jump(target, dry_run=args.dry_run)


def cmd_jump(args: argparse.Namespace) -> int:
    payload: dict[str, Any]
    if args.session_json:
        payload = json.loads(args.session_json)
    else:
        payload = read_payload_from_input(None)
        if not isinstance(payload, dict):
            payload = {}
    return execute_jump(payload, dry_run=args.dry_run)


def response_for_choice(payload: dict[str, Any], choice_index: int) -> tuple[str, bool]:
    source = str(payload.get("source") or "").lower()
    interaction = payload.get("interaction")
    approval_type = ""
    if isinstance(interaction, dict):
        approval_type = str(interaction.get("approval_type") or "").lower()

    if source == "codex" and approval_type:
        if choice_index == 1:
            return "", True
        if choice_index == 2:
            return "p", False
        if choice_index == 3:
            return "\x1b", False

    return str(choice_index), True


def resolve_managed_approval_request(
    payload: dict[str, Any],
    *,
    choice_index: int = 0,
    choice_text: str = "",
    followup_text: str = "",
    dry_run: bool = False,
) -> bool:
    source = str(payload.get("source") or "").strip().lower()
    session_id = str(payload.get("id") or (payload.get("session") or {}).get("id") or "").strip()
    if not source or not session_id:
        return False

    def normalize_jump_target(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def pending_request_files() -> list[Path]:
        if not APPROVAL_REQUESTS_DIR.exists():
            return []
        return sorted(
            APPROVAL_REQUESTS_DIR.glob("*.json"),
            key=lambda candidate: candidate.stat().st_mtime,
            reverse=True,
        )

    def request_has_decision(candidate: dict[str, Any]) -> bool:
        return isinstance(candidate.get("decision"), dict) and bool((candidate.get("decision") or {}).get("action"))

    def request_match_score(candidate: dict[str, Any]) -> int:
        if str(candidate.get("source") or "").strip().lower() != source:
            return -1
        if request_has_decision(candidate):
            return -1

        candidate_session_id = str(candidate.get("session_id") or "").strip()
        candidate_ui_session_id = str(candidate.get("ui_session_id") or "").strip()
        if session_id and session_id in {candidate_session_id, candidate_ui_session_id}:
            return 100

        payload_jump = normalize_jump_target(payload.get("jump_target"))
        candidate_jump = normalize_jump_target(candidate.get("jump_target"))
        payload_tty = normalize_tty_path(payload_jump.get("tty"))
        candidate_tty = normalize_tty_path(candidate_jump.get("tty"))
        if payload_tty and candidate_tty and payload_tty == candidate_tty:
            return 90

        payload_pid = payload_jump.get("pid")
        candidate_pid = candidate_jump.get("pid")
        try:
            payload_pid = int(payload_pid) if payload_pid is not None else None
        except Exception:
            payload_pid = None
        try:
            candidate_pid = int(candidate_pid) if candidate_pid is not None else None
        except Exception:
            candidate_pid = None
        if payload_pid and candidate_pid and payload_pid == candidate_pid:
            return 80

        payload_cwd = str(payload.get("cwd") or payload.get("workspace") or "").strip()
        candidate_cwd = str(candidate.get("cwd") or "").strip()
        if payload_cwd and candidate_cwd and payload_cwd == candidate_cwd:
            return 40

        return -1

    path = approval_request_path(source, session_id)
    request = read_json_file_maybe(path)
    if not request:
        scored_matches: list[tuple[int, Path, dict[str, Any]]] = []
        for candidate_path in pending_request_files():
            candidate = read_json_file_maybe(candidate_path)
            score = request_match_score(candidate)
            if score > 0:
                scored_matches.append((score, candidate_path, candidate))
        if scored_matches:
            scored_matches.sort(key=lambda item: item[0], reverse=True)
            _, path, request = scored_matches[0]
    if not request:
        return False

    action = ""
    if choice_index == 2:
        action = "allow_session"
    elif choice_index == 3 or str(followup_text or "").strip():
        action = "deny"
    else:
        action = "allow_once"

    resolution = {
        "action": action,
        "choice_index": int(choice_index or 0),
        "choice_text": str(choice_text or "").strip(),
        "followup_text": str(followup_text or "").strip(),
        "reason": str(choice_text or "").strip(),
        "resolved_at": now_iso(),
    }

    if dry_run:
        print(
            json.dumps(
                {
                    "managed_approval": True,
                    "source": source,
                    "session_id": session_id,
                    "decision": resolution,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return True

    def emit_optimistic_response_event() -> None:
        payload_source = str(request.get("source") or payload.get("source") or source or "agent").strip().lower() or "agent"
        cwd = str(payload.get("cwd") or payload.get("workspace") or request.get("cwd") or os.getcwd())
        jump_target = normalize_jump_target(payload.get("jump_target") or request.get("jump_target"))
        event_session_id = str(payload.get("id") or session_id)
        label_session_id = str(request.get("session_id") or event_session_id)
        label_payload = dict(request)
        label_payload.update(payload)
        if action == "allow_session":
            summary = "Approval remembered. Agent resuming."
        elif action == "allow_once":
            summary = "Approval sent. Agent resuming."
        elif resolution["followup_text"]:
            summary = truncate(f"Reply sent: {resolution['followup_text']}", 140)
        else:
            summary = "Reply sent. Agent resuming."
        stable_label = stable_task_label_for_event(
            payload_source,
            label_session_id,
            label_payload,
            cwd,
            request.get("task_label"),
            request.get("title"),
            request.get("question"),
            request.get("summary"),
            request.get("command"),
            payload.get("title"),
            payload.get("summary"),
            payload.get("last_assistant_message"),
        )
        title_hint = str(
            first_present(
                request.get("question"),
                payload.get("title"),
                payload.get("summary"),
                payload.get("last_assistant_message"),
                "Agent",
            )
        )
        title = truncate(stable_label, 44) if stable_label else derive_title(title_hint, cwd)
        task_label = stable_label or derive_task_label(title_hint, cwd) or None
        event = make_event(
            source=payload_source,
            adapter="vibe-bridge",
            session_id=event_session_id,
            kind="session_updated",
            state="running",
            title=title,
            task_label=task_label,
            summary=summary,
            workspace=str(payload.get("workspace") or cwd),
            cwd=cwd,
            review=request.get("review") if isinstance(request.get("review"), dict) else None,
            terminal=jump_target.get("terminal"),
            tty=jump_target.get("tty"),
            pid=jump_target.get("pid"),
            tmux_session=jump_target.get("tmux_session"),
            tmux_window=jump_target.get("tmux_window"),
            tmux_pane=jump_target.get("tmux_pane"),
            raw={"managed_approval": True, "optimistic_response": True, "decision": resolution},
        )
        publish_event(event, ignore_errors=True)

    request["decision"] = resolution
    request["updated_at"] = now_iso()
    write_managed_approval_request(request)
    emit_optimistic_response_event()
    print(f"Resolved managed approval for {source}:{session_id} -> {action}", flush=True)
    return True


def send_response_via_tmux(
    target: dict[str, Any],
    response_text: str,
    *,
    append_enter: bool = True,
    dry_run: bool = False,
) -> bool:
    tmux_target = tmux_target_from_jump_target(target)
    if not tmux_target or shutil.which("tmux") is None:
        return False

    sanitized_response = sanitize_terminal_message(response_text)
    commands: list[list[str]] = []
    if response_text == "\x1b":
        commands.append(["tmux", "send-keys", "-t", tmux_target, "Escape"])
    elif sanitized_response:
        commands.append(["tmux", "send-keys", "-t", tmux_target, "-l", sanitized_response])
    if append_enter:
        commands.append(["tmux", "send-keys", "-t", tmux_target, "Enter"])
    if dry_run:
        for command in commands:
            print(" ".join(shlex.quote(part) for part in command))
        return True

    try:
        for command in commands:
            result = subprocess.run(command, check=False, capture_output=True, text=True)
            if result.returncode != 0:
                return False
        return True
    except Exception:
        return False


def normalize_tty_path(value: str | None) -> str | None:
    if not value:
        return None
    tty = str(value).strip()
    if " " in tty:
        tty = tty.split(" ", 1)[0]
    if tty.startswith("/dev/"):
        return tty
    return None


def sanitize_terminal_message(value: str | None) -> str:
    text = str(value or "")
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)
    text = re.sub(r"\r?\n+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def terminal_submit_suffix() -> str:
    return "\r"


def send_response_via_tty(
    target: dict[str, Any],
    response_text: str,
    *,
    append_enter: bool = True,
    dry_run: bool = False,
) -> bool:
    tty = normalize_tty_path(target.get("tty"))
    if not tty:
        return False

    payload = sanitize_terminal_message(response_text)
    if append_enter:
        payload = payload + terminal_submit_suffix()
    if dry_run:
        printable = payload.encode("unicode_escape").decode("ascii")
        print(f"write {tty} << {printable}")
        return True

    try:
        fd = os.open(tty, os.O_WRONLY | os.O_NONBLOCK)
        try:
            os.write(fd, payload.encode("utf-8"))
        finally:
            os.close(fd)
        return True
    except Exception:
        return False


def send_response_via_active_window(
    payload: dict[str, Any],
    response_text: str,
    *,
    append_enter: bool = True,
    return_focus_pid: int | None = None,
    dry_run: bool = False,
) -> bool:
    if shutil.which("xdotool") is None or not os.environ.get("DISPLAY"):
        return False

    if execute_jump(payload, dry_run=dry_run) != 0:
        return False

    commands: list[list[str]] = []
    sanitized_response = sanitize_terminal_message(response_text)

    if response_text == "\x1b":
        commands.append(["xdotool", "key", "Escape"])
    elif sanitized_response:
        commands.append(["xdotool", "type", "--clearmodifiers", "--delay", "1", sanitized_response])
    if append_enter:
        commands.append(["xdotool", "key", "Return"])

    if dry_run:
        for command in commands:
            print(" ".join(shlex.quote(part) for part in command))
        if return_focus_pid:
            restore_window_focus(return_focus_pid, dry_run=True)
        return True

    time.sleep(0.25)
    try:
        for index, command in enumerate(commands):
            result = subprocess.run(command, check=False, capture_output=True, text=True)
            if result.returncode != 0:
                return False
            if index == 0 and sanitized_response:
                time.sleep(0.16)
            else:
                time.sleep(0.07)
        if return_focus_pid:
            time.sleep(0.18)
            restore_window_focus(return_focus_pid, dry_run=dry_run)
        return True
    except Exception:
        return False


def execute_response(
    payload: dict[str, Any],
    *,
    response_text: str,
    append_enter: bool = True,
    dry_run: bool = False,
) -> int:
    target = choose_jump_target(payload) or payload.get("jump_target") or {}
    if not response_text and not append_enter:
        print("No response text provided", file=sys.stderr)
        return 1

    if send_response_via_tmux(target, response_text, append_enter=append_enter, dry_run=dry_run):
        return 0
    if send_response_via_konsole_session(
        target,
        response_text,
        append_enter=append_enter,
        dry_run=dry_run,
    ):
        return 0
    if send_response_via_active_window(
        payload,
        response_text,
        append_enter=append_enter,
        dry_run=dry_run,
    ):
        return 0

    print(
        "Unable to send response back to the session terminal with a native input path. Use JUMP for this terminal.",
        file=sys.stderr,
    )
    return 1


def execute_session_message(
    payload: dict[str, Any],
    *,
    message_text: str,
    return_focus_pid: int | None = None,
    dry_run: bool = False,
) -> int:
    target = choose_jump_target(payload) or payload.get("jump_target") or {}
    message = sanitize_terminal_message(message_text)
    if not message.strip():
        print("No session message provided", file=sys.stderr)
        return 1

    if send_response_via_tmux(target, message, append_enter=True, dry_run=dry_run):
        return 0
    if send_response_via_konsole_session(target, message, append_enter=True, dry_run=dry_run):
        return 0
    if send_response_via_active_window(
        payload,
        message,
        append_enter=True,
        return_focus_pid=return_focus_pid,
        dry_run=dry_run,
    ):
        return 0

    print(
        "No native in-session send path is available for this terminal host. Use JUMP to continue in the original terminal.",
        file=sys.stderr,
    )
    return 1


def execute_response_with_followup(
    payload: dict[str, Any],
    *,
    response_text: str,
    append_enter: bool = True,
    followup_text: str = "",
    dry_run: bool = False,
) -> int:
    result = execute_response(
        payload,
        response_text=response_text,
        append_enter=append_enter,
        dry_run=dry_run,
    )
    if result != 0:
        return result

    followup = str(followup_text or "").strip()
    if not followup:
        return result

    if dry_run:
        print("sleep 0.25")
    else:
        time.sleep(0.25)

    return execute_response(
        payload,
        response_text=followup,
        append_enter=True,
        dry_run=dry_run,
    )


def cmd_respond(args: argparse.Namespace) -> int:
    if args.session_json:
        payload = json.loads(args.session_json)
    else:
        payload = read_payload_from_input(None)
        if not isinstance(payload, dict):
            payload = {}

    if resolve_managed_approval_request(
        payload,
        choice_index=int(args.choice_index or 0),
        choice_text=str(args.text or ""),
        followup_text=str(args.followup_text or ""),
        dry_run=args.dry_run,
    ):
        return 0

    if args.choice_index or args.followup_text:
        print(
            f"No managed approval request matched {payload.get('source', 'unknown')}:{payload.get('id', '')}; falling back to terminal injection.",
            file=sys.stderr,
        )

    response_text = args.text or ""
    append_enter = True
    if args.choice_index:
        response_text, append_enter = response_for_choice(payload, args.choice_index)

    return execute_response_with_followup(
        payload,
        response_text=response_text,
        append_enter=append_enter,
        followup_text=args.followup_text or "",
        dry_run=args.dry_run,
    )


def cmd_send_peek(args: argparse.Namespace) -> int:
    if args.session_json:
        payload = json.loads(args.session_json)
    else:
        payload = read_payload_from_input(None)
        if not isinstance(payload, dict):
            payload = {}
    return execute_session_message(
        payload,
        message_text=str(args.text or ""),
        return_focus_pid=args.return_focus_pid,
        dry_run=args.dry_run,
    )


def maybe_handle_managed_claude_pretool(payload: dict[str, Any], socket_path: str) -> int | None:
    if payload.get("hook_event_name") != "PreToolUse":
        return None
    if not claude_pretool_requires_approval(payload):
        return None

    source = "claude"
    session_id = str(payload.get("session_id") or "")
    if not session_id:
        return None

    tool_name = str(payload.get("tool_name") or "tool")
    tool_input = payload.get("tool_input") or {}
    question, summary, choices = claude_approval_details(tool_name, tool_input, payload)
    title_hint = str(first_present(tool_input.get("command"), tool_input.get("file_path"), question) or question)

    if has_matching_session_rule(source, session_id, payload):
        publish_event(
            managed_clear_event(
                source=source,
                payload=payload,
                title_hint=title_hint,
                summary="Auto-approved via Vibe Island session rule.",
            ),
            socket_path,
            ignore_errors=True,
        )
        return 0

    blocked_event = event_from_claude_hook(payload)
    if isinstance(blocked_event.get("raw"), dict):
        blocked_event["raw"]["managed_approval"] = True
    request = build_managed_approval_request(
        source=source,
        payload=payload,
        approval_type=str(tool_name).lower(),
        question=question,
        summary=summary,
        choices=choices,
    )
    blocked_session = blocked_event.get("session") or {}
    blocked_title = normalize_text(blocked_session.get("title"))
    blocked_task_label = normalize_text(blocked_session.get("task_label"))
    if blocked_title:
        request["title"] = blocked_title
    if blocked_task_label and not is_low_signal_task_label(blocked_task_label):
        request["task_label"] = blocked_task_label
    request["jump_target"] = blocked_event.get("jump_target") or {}
    request["ui_session_id"] = str(blocked_event.get("session", {}).get("id") or request.get("session_id") or "")
    write_managed_approval_request(request)
    decision = wait_for_managed_approval(request, blocked_event, socket_path)
    return maybe_complete_managed_approval(
        source=source,
        payload=payload,
        request=request,
        decision=decision,
        socket_path=socket_path,
        title_hint=title_hint,
    )


def maybe_handle_managed_codex_pretool(payload: dict[str, Any], socket_path: str) -> int | None:
    if payload.get("hook_event_name") != "PreToolUse":
        return None

    command = str(((payload.get("tool_input") or {}).get("command") or "")).strip()
    requires_approval, turn_context = codex_pretool_requires_approval(payload, command)
    if not requires_approval:
        return None

    source = "codex"
    session_id = str(payload.get("session_id") or "")
    if not session_id:
        return None

    if has_matching_session_rule(source, session_id, payload):
        publish_event(
            managed_clear_event(
                source=source,
                payload=payload,
                title_hint=command or "Bash",
                summary="Auto-approved via Vibe Island session rule.",
            ),
            socket_path,
            ignore_errors=True,
        )
        return 0

    if turn_context:
        payload = dict(payload)
        payload["turn_context"] = turn_context

    approval_type, question, summary, choices = codex_approval_details(command)
    blocked_event = event_from_codex_hook(payload)
    if isinstance(blocked_event.get("raw"), dict):
        blocked_event["raw"]["managed_approval"] = True
    request = build_managed_approval_request(
        source=source,
        payload=payload,
        approval_type=approval_type,
        question=question,
        summary=summary,
        choices=choices,
    )
    blocked_session = blocked_event.get("session") or {}
    blocked_title = normalize_text(blocked_session.get("title"))
    blocked_task_label = normalize_text(blocked_session.get("task_label"))
    if blocked_title:
        request["title"] = blocked_title
    if blocked_task_label and not is_low_signal_task_label(blocked_task_label):
        request["task_label"] = blocked_task_label
    request["jump_target"] = blocked_event.get("jump_target") or {}
    request["ui_session_id"] = str(blocked_event.get("session", {}).get("id") or request.get("session_id") or "")
    write_managed_approval_request(request)
    decision = wait_for_managed_approval(request, blocked_event, socket_path)
    return maybe_complete_managed_approval(
        source=source,
        payload=payload,
        request=request,
        decision=decision,
        socket_path=socket_path,
        title_hint=command or question,
    )


def _percent_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return max(0, min(100, int(round(float(value)))))
    except Exception:
        return None


def _candidate_window_names(kind: str) -> tuple[str, ...]:
    if kind == "5h":
        return (
            "primary",
            "five_hour",
            "fivehour",
            "5h",
            "short_term",
            "shortterm",
            "hourly",
        )
    return (
        "secondary",
        "seven_day",
        "sevenday",
        "7d",
        "long_term",
        "longterm",
        "weekly",
    )


def _rate_limit_window(rate_limits: dict[str, Any], kind: str) -> dict[str, Any]:
    if not isinstance(rate_limits, dict):
        return {}

    normalized_map: dict[str, dict[str, Any]] = {}
    for key, value in rate_limits.items():
        if not isinstance(value, dict):
            continue
        normalized_key = str(key).strip().lower().replace("-", "").replace("_", "")
        normalized_map[normalized_key] = value

    for candidate in _candidate_window_names(kind):
        value = normalized_map.get(candidate.replace("-", "").replace("_", ""))
        if value:
            return value

    for normalized_key, value in normalized_map.items():
        if kind == "5h" and ("5" in normalized_key or "five" in normalized_key or "hour" in normalized_key):
            return value
        if kind == "7d" and ("7" in normalized_key or "seven" in normalized_key or "week" in normalized_key or "day" in normalized_key):
            return value

    return {}


def _remaining_percent(window: dict[str, Any]) -> int | None:
    if not isinstance(window, dict):
        return None
    for key in ("remaining_percentage", "remaining_percent", "remainingPercent"):
        value = _percent_int(window.get(key))
        if value is not None:
            return value
    for key in ("used_percentage", "used_percent", "usedPercent", "utilization", "percentage"):
        value = _percent_int(window.get(key))
        if value is not None:
            return max(0, 100 - value)
    return None


def render_claude_statusline(snapshot: dict[str, Any]) -> str:
    model = snapshot.get("model") if isinstance(snapshot.get("model"), dict) else {}
    model_label = truncate(first_present(model.get("display_name"), model.get("name"), "Claude"), 20) or "Claude"
    context_window = snapshot.get("context_window") if isinstance(snapshot.get("context_window"), dict) else {}
    context_remaining = _percent_int(
        first_present(
            context_window.get("remaining_percentage"),
            context_window.get("remaining_percent"),
            context_window.get("remainingPercent"),
        )
    )
    rate_limits = snapshot.get("rate_limits") if isinstance(snapshot.get("rate_limits"), dict) else {}
    five_hour = _remaining_percent(_rate_limit_window(rate_limits, "5h"))
    seven_day = _remaining_percent(_rate_limit_window(rate_limits, "7d"))

    parts = [model_label]
    if context_remaining is not None:
        parts.append(f"ctx {context_remaining}%")
    if five_hour is not None:
        parts.append(f"5h {five_hour}%")
    if seven_day is not None:
        parts.append(f"7d {seven_day}%")
    return " | ".join(parts)


def cmd_claude_statusline(args: argparse.Namespace) -> int:
    try:
        payload = read_payload_from_input(args.payload)
        if not isinstance(payload, dict):
            payload = {}
        snapshot = {
            "updated_at": now_iso(),
            "session_id": first_present(payload.get("session_id"), payload.get("sessionId")),
            "workspace": payload.get("workspace") if isinstance(payload.get("workspace"), dict) else {},
            "transcript_path": normalize_text(payload.get("transcript_path")),
            "model": payload.get("model") if isinstance(payload.get("model"), dict) else {},
            "context_window": payload.get("context_window") if isinstance(payload.get("context_window"), dict) else {},
            "current_usage": payload.get("current_usage") if isinstance(payload.get("current_usage"), dict) else {},
            "rate_limits": payload.get("rate_limits") if isinstance(payload.get("rate_limits"), dict) else {},
        }
        write_json_file(CLAUDE_STATUSLINE_PATH, snapshot)
        print(render_claude_statusline(snapshot), flush=True)
    except Exception as exc:
        print(f"[vibeisland] claude-statusline error: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_claude_hook(args: argparse.Namespace) -> int:
    try:
        payload = read_payload_from_input(args.payload)
        if not isinstance(payload, dict):
            payload = {"message": str(payload)}
        maybe_log_hook_payload("claude-hook", payload)
        if args.print_event:
            event = event_from_claude_hook(payload)
            print(json.dumps(event, ensure_ascii=False, indent=2))
            return 0
        managed = maybe_handle_managed_claude_pretool(payload, args.socket)
        if managed is not None:
            return managed
        event = event_from_claude_hook(payload)
        publish_event(event, args.socket, ignore_errors=True)
    except Exception as exc:
        print(f"[vibeisland] claude-hook error: {exc}", file=sys.stderr)
    return 0


def cmd_codex_hook(args: argparse.Namespace) -> int:
    try:
        payload = read_payload_from_input(args.payload)
        if not isinstance(payload, dict):
            payload = {"message": str(payload)}
        maybe_log_hook_payload("codex-hook", payload)
        if args.print_event:
            event = event_from_codex_hook(payload)
            print(json.dumps(event, ensure_ascii=False, indent=2))
            return 0
        managed = maybe_handle_managed_codex_pretool(payload, args.socket)
        if managed is not None:
            return managed
        event = event_from_codex_hook(payload)
        publish_event(event, args.socket, ignore_errors=True)
    except Exception as exc:
        print(f"[vibeisland] codex-hook error: {exc}", file=sys.stderr)
    return 0


def cmd_codex_notify(args: argparse.Namespace) -> int:
    try:
        payload = read_payload_from_input(args.payload)
        maybe_log_hook_payload("codex-notify", payload)
        event = event_from_codex_notify(payload)
        if args.print_event:
            print(json.dumps(event, ensure_ascii=False, indent=2))
            return 0
        publish_event(event, args.socket, ignore_errors=True)
    except Exception as exc:
        print(f"[vibeisland] codex-notify error: {exc}", file=sys.stderr)
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    results: dict[str, Any] = {"target": args.target, "dry_run": args.dry_run}

    if args.target in {"claude", "all"}:
        results["claude"] = install_claude_hooks(Path(args.claude_settings), args.dry_run)

    if args.target in {"codex", "all"}:
        results["codex"] = install_codex_hooks(
            Path(args.codex_config),
            Path(args.codex_hooks),
            args.dry_run,
        )

    print(json.dumps(results, ensure_ascii=False, indent=2), flush=True)
    return 0


def launcher_status(socket_path: str = DEFAULT_SOCKET) -> dict[str, Any]:
    state = load_launcher_state()
    daemon = state.get("daemon") if isinstance(state.get("daemon"), dict) else {}
    shell = state.get("shell") if isinstance(state.get("shell"), dict) else {}
    prefs = read_json_file_maybe(Path.home() / ".config" / "vibeisland-shell" / "state.json")
    socket_live = socket_healthy(socket_path)
    daemon_pid = int(daemon.get("pid") or 0) or None
    shell_pid = int(shell.get("pid") or 0) or None
    daemon_running = process_alive(daemon_pid)
    shell_running = process_alive(shell_pid)
    daemon_status = "running" if socket_live else ("stale" if daemon_running else "stopped")
    if socket_live and not daemon_running:
        daemon_status = "external"
    shell_status = "running" if shell_running else "stopped"
    telegram = prefs.get("telegram") if isinstance(prefs.get("telegram"), dict) else {}
    return {
        "socket_path": socket_path,
        "socket_live": socket_live,
        "daemon": {
            "status": daemon_status,
            "pid": daemon_pid,
            "log": daemon.get("log"),
            "command": daemon.get("command"),
        },
        "shell": {
            "status": shell_status,
            "pid": shell_pid,
            "log": shell.get("log"),
            "command": shell.get("command"),
        },
        "prefs_path": str(Path.home() / ".config" / "vibeisland-shell" / "state.json"),
        "telegram": {
            "enabled": bool(telegram.get("enabled")),
            "paired": bool(normalize_text(telegram.get("chat_id"))),
            "chat_id": normalize_text(telegram.get("chat_id")),
        },
    }


def render_status_text(payload: dict[str, Any]) -> str:
    socket_label = "live" if payload.get("socket_live") else "down"
    daemon = payload.get("daemon") if isinstance(payload.get("daemon"), dict) else {}
    shell = payload.get("shell") if isinstance(payload.get("shell"), dict) else {}
    telegram = payload.get("telegram") if isinstance(payload.get("telegram"), dict) else {}
    lines = [
        f"socket: {socket_label} ({payload.get('socket_path')})",
        f"daemon: {daemon.get('status')} pid={first_present(daemon.get('pid'), '-')}",
        f"shell: {shell.get('status')} pid={first_present(shell.get('pid'), '-')}",
        f"telegram: {'enabled' if telegram.get('enabled') else 'off'} / {'paired' if telegram.get('paired') else 'unpaired'}",
    ]
    return "\n".join(lines)


def cmd_status(args: argparse.Namespace) -> int:
    payload = launcher_status(args.socket)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
    else:
        print(render_status_text(payload), flush=True)
    return 0


def cmd_launch(args: argparse.Namespace) -> int:
    state = load_launcher_state()
    daemon = state.get("daemon") if isinstance(state.get("daemon"), dict) else {}
    shell = state.get("shell") if isinstance(state.get("shell"), dict) else {}

    daemon_started = False
    if not socket_healthy(args.socket):
        stale_pid = int(daemon.get("pid") or 0) or None
        if stale_pid and process_alive(stale_pid):
            terminate_process_group(stale_pid, signal.SIGTERM)
            time.sleep(0.4)
        daemon_command = build_daemon_command()
        daemon_log = str(log_path("daemon"))
        daemon_pid = spawn_background_process(daemon_command, cwd=ROOT, log_file=Path(daemon_log))
        daemon = {
            "pid": daemon_pid,
            "command": daemon_command,
            "log": daemon_log,
            "started_at": now_iso(),
        }
        daemon_started = True
        if not wait_for_socket(args.socket):
            terminate_process_group(daemon_pid, signal.SIGKILL)
            print(
                json.dumps(
                    {
                        "started": False,
                        "reason": "daemon_failed",
                        "log": daemon_log,
                        "socket": args.socket,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                flush=True,
            )
            return 1
    elif not process_alive(int(daemon.get("pid") or 0) or None):
        daemon = {
            "pid": None,
            "command": [],
            "log": None,
            "started_at": now_iso(),
        }

    shell_started = False
    shell_pid = int(shell.get("pid") or 0) or None
    if not process_alive(shell_pid):
        shell_command = build_shell_command(args.socket)
        shell_log = str(log_path("shell"))
        shell_pid = spawn_background_process(
            shell_command,
            cwd=ROOT,
            log_file=Path(shell_log),
            extra_env={"VIBEISLAND_SOCKET": args.socket},
        )
        shell = {
            "pid": shell_pid,
            "command": shell_command,
            "log": shell_log,
            "started_at": now_iso(),
        }
        shell_started = True

    state = {
        "updated_at": now_iso(),
        "socket": args.socket,
        "daemon": daemon,
        "shell": shell,
    }
    save_launcher_state(state)
    payload = launcher_status(args.socket)
    payload["started"] = daemon_started or shell_started
    payload["daemon_started"] = daemon_started
    payload["shell_started"] = shell_started
    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
    return 0


def _stop_entry(entry: dict[str, Any] | None) -> bool:
    if not isinstance(entry, dict):
        return False
    pid = int(entry.get("pid") or 0) or None
    if not pid or not process_alive(pid):
        return False
    terminate_process_group(pid, signal.SIGTERM)
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if not process_alive(pid):
            return True
        time.sleep(0.1)
    terminate_process_group(pid, signal.SIGKILL)
    return True


def cmd_stop(args: argparse.Namespace) -> int:
    state = load_launcher_state()
    daemon = state.get("daemon") if isinstance(state.get("daemon"), dict) else {}
    shell = state.get("shell") if isinstance(state.get("shell"), dict) else {}
    shell_stopped = _stop_entry(shell)
    daemon_stopped = _stop_entry(daemon)
    if LAUNCHER_STATE_PATH.exists():
        try:
            LAUNCHER_STATE_PATH.unlink()
        except Exception:
            pass
    payload = launcher_status(args.socket)
    payload["stopped"] = {
        "shell": shell_stopped,
        "daemon": daemon_stopped,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
    return 0


def build_desktop_launcher_script(repo_root: Path) -> str:
    return textwrap.dedent(
        f"""\
        #!/usr/bin/env bash
        exec {shlex.quote(sys.executable)} {shlex.quote(str(repo_root / 'tools' / 'vibeisland.py'))} "$@"
        """
    )


def build_desktop_entry(bin_path: Path, repo_root: Path) -> str:
    icon_path = repo_root / "apps" / "shell" / "assets" / "default-agent.svg"
    return textwrap.dedent(
        f"""\
        [Desktop Entry]
        Type=Application
        Name=Vibe Island
        Comment=Floating AI agent island for Linux
        Exec={shlex.quote(str(bin_path))}
        Icon={icon_path}
        Terminal=false
        Categories=Development;Utility;
        StartupNotify=false
        """
    )


def cmd_install_desktop(args: argparse.Namespace) -> int:
    repo_root = ROOT
    bin_dir = Path(args.bin_dir).expanduser()
    applications_dir = Path(args.applications_dir).expanduser()
    launcher_path = bin_dir / "vibeisland"
    desktop_path = applications_dir / "vibeisland.desktop"

    if not args.dry_run:
        bin_dir.mkdir(parents=True, exist_ok=True)
        applications_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(launcher_path, build_desktop_launcher_script(repo_root))
        os.chmod(launcher_path, 0o755)
        atomic_write_text(desktop_path, build_desktop_entry(launcher_path, repo_root))

    payload = {
        "launcher": str(launcher_path),
        "desktop_entry": str(desktop_path),
        "dry_run": args.dry_run,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
    return 0


def public_docs_index(language: str = "en") -> str:
    if language == "zh":
        return textwrap.dedent(
            """\
            # Vibe Island 文档索引

            英文版：`docs/README.md`

            维护说明：公开版仓库至少维护以下中英文文档并保持同步。

            ## 推荐阅读顺序

            1. [../README.zh-CN.md](../README.zh-CN.md)
            2. [PRD.zh-CN.md](./PRD.zh-CN.md)
            3. [TECHNICAL_DESIGN.zh-CN.md](./TECHNICAL_DESIGN.zh-CN.md)
            4. [INTEGRATION_SETUP.zh-CN.md](./INTEGRATION_SETUP.zh-CN.md)

            ## 文档地图

            - [PRD.md](./PRD.md)
              产品目标、范围、支持环境与后续路线。
            - [PRD.zh-CN.md](./PRD.zh-CN.md)
              PRD 中文版。
            - [TECHNICAL_DESIGN.md](./TECHNICAL_DESIGN.md)
              架构、事件流、壳层行为与启动策略。
            - [TECHNICAL_DESIGN.zh-CN.md](./TECHNICAL_DESIGN.zh-CN.md)
              技术设计中文版。
            - [INTEGRATION_SETUP.md](./INTEGRATION_SETUP.md)
              Claude Code / Codex / Telegram 的配置说明。
            - [INTEGRATION_SETUP.zh-CN.md](./INTEGRATION_SETUP.zh-CN.md)
              集成配置说明中文版。
            """
        )
    return textwrap.dedent(
        """\
        # Vibe Island Docs Index

        Chinese version: `docs/README.zh-CN.md`

        Maintenance note: keep the English and Chinese public docs in sync.

        ## Reading order

        1. [../README.md](../README.md)
        2. [PRD.md](./PRD.md)
        3. [TECHNICAL_DESIGN.md](./TECHNICAL_DESIGN.md)
        4. [INTEGRATION_SETUP.md](./INTEGRATION_SETUP.md)

        ## Document map

        - [PRD.md](./PRD.md)
          Product goals, scope, supported environments, and roadmap.
        - [PRD.zh-CN.md](./PRD.zh-CN.md)
          Chinese PRD.
        - [TECHNICAL_DESIGN.md](./TECHNICAL_DESIGN.md)
          Architecture, event flow, shell behavior, and launcher strategy.
        - [TECHNICAL_DESIGN.zh-CN.md](./TECHNICAL_DESIGN.zh-CN.md)
          Chinese technical design.
        - [INTEGRATION_SETUP.md](./INTEGRATION_SETUP.md)
          Claude Code / Codex / Telegram configuration guide.
        - [INTEGRATION_SETUP.zh-CN.md](./INTEGRATION_SETUP.zh-CN.md)
          Chinese integration guide.
        """
    )


def strip_markdown_section(text: str, heading: str) -> str:
    pattern = re.compile(rf"\n## {re.escape(heading)}\n.*?(?=\n## |\Z)", re.S)
    return pattern.sub("\n", text)


def sanitize_public_markdown(path: Path, export_root: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace(str(ROOT), "/path/to/vibeisland-linux")
    link_pattern = re.compile(r"\[([^\]]+)\]\((/[^)]+)\)")

    def replace_link(match: re.Match[str]) -> str:
        label = match.group(1)
        target = Path(match.group(2))
        try:
            relative_target = target.relative_to(ROOT)
        except Exception:
            return match.group(0)
        output_target = export_root / relative_target
        if not output_target.exists():
            return f"`{relative_target.as_posix()}`"
        rel_link = os.path.relpath(output_target, path.parent).replace(os.sep, "/")
        return f"[{label}]({rel_link})"

    text = link_pattern.sub(replace_link, text)
    if path.name == "INTEGRATION_SETUP.md":
        text = strip_markdown_section(text, "Optional collaboration runtime")
    elif path.name == "INTEGRATION_SETUP.zh-CN.md":
        text = strip_markdown_section(text, "可选：协作运行时")
    elif path.name == "TECHNICAL_DESIGN.md":
        start_marker = "For optional collaboration sessions, the shell consumes a narrow public contract through:"
        end_marker = "\n## Why This Stack"
        if start_marker in text and end_marker in text:
            start = text.index(start_marker)
            end = text.index(end_marker, start)
            text = text[:start] + text[end:]
        text = strip_markdown_section(text, "Collaboration Registry")
    elif path.name == "TECHNICAL_DESIGN.zh-CN.md":
        start_marker = "对于可选的协作会话，shell 会通过一层很窄的公开契约来消费协作状态："
        end_marker = "\n## 为什么选这套技术栈"
        if start_marker in text and end_marker in text:
            start = text.index(start_marker)
            end = text.index(end_marker, start)
            text = text[:start] + text[end:]
        text = strip_markdown_section(text, "协作 Registry")
    path.write_text(text, encoding="utf-8")


def should_export_path(relative_path: Path) -> bool:
    text = relative_path.as_posix()
    if text in {
        ".codex",
        "target",
        ".vibeisland",
        ".tmp-collab-smoke",
        "plugins",
        "claude-marketplace",
        ".tmp-pretool.json",
        "Untitled-1.txt",
        "tools/agent_collab.py",
        "apps/shell/collab_adapter.py",
        "apps/shell/ui/Main.qml.backup",
        "docs/AGENT_COLLAB_SYSTEM.md",
        "docs/AGENT_COLLAB_SYSTEM.zh-CN.md",
        "docs/COLLAB_WORKFLOW.md",
        "docs/COLLAB_WORKFLOW.zh-CN.md",
        "docs/PROJECT_BOUNDARIES.md",
        "docs/PROJECT_BOUNDARIES.zh-CN.md",
        "docs/SOURCE_FINDINGS.md",
        "docs/SOURCE_FINDINGS.zh-CN.md",
        "docs/schemas/collab_registry.schema.json",
    }:
        return False
    blocked_prefixes = (
        "target/",
        ".vibeisland/",
        ".tmp-collab-smoke/",
        "plugins/",
        "claude-marketplace/",
    )
    if any(text.startswith(prefix) for prefix in blocked_prefixes):
        return False
    parts = relative_path.parts
    if "__pycache__" in parts:
        return False
    if relative_path.suffix in {".pyc", ".pyo"}:
        return False
    return True


def cmd_export_public(args: argparse.Namespace) -> int:
    output_dir = Path(args.output).expanduser().resolve()
    if output_dir.exists():
        if any(output_dir.iterdir()) and not args.force:
            print(f"Output directory is not empty: {output_dir}", file=sys.stderr)
            return 1
        if args.force:
            shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    copied_files: list[str] = []
    output_relative: Path | None = None
    if output_dir.is_relative_to(ROOT):
        output_relative = output_dir.relative_to(ROOT)
    for path in ROOT.rglob("*"):
        relative_path = path.relative_to(ROOT)
        if output_relative and (relative_path == output_relative or output_relative in relative_path.parents):
            continue
        if not should_export_path(relative_path):
            continue
        if not path.exists():
            continue
        destination = output_dir / relative_path
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        copied_files.append(relative_path.as_posix())

    docs_dir = output_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "README.md").write_text(public_docs_index("en"), encoding="utf-8")
    (docs_dir / "README.zh-CN.md").write_text(public_docs_index("zh"), encoding="utf-8")

    for markdown_path in output_dir.rglob("*.md"):
        sanitize_public_markdown(markdown_path, output_dir)

    payload = {
        "output": str(output_dir),
        "copied_files": len(copied_files),
        "excluded": [
            "tools/agent_collab.py",
            "apps/shell/collab_adapter.py",
            "plugins/vibeisland-collab",
            "claude-marketplace",
            "docs/AGENT_COLLAB_SYSTEM*",
            "docs/COLLAB_WORKFLOW*",
            "docs/PROJECT_BOUNDARIES*",
            "docs/SOURCE_FINDINGS*",
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vibeisland")
    sub = parser.add_subparsers(dest="command", required=True)

    launch = sub.add_parser("launch", help="Start the daemon and shell together")
    launch.add_argument("--socket", default=DEFAULT_SOCKET)
    launch.set_defaults(handler=cmd_launch)

    stop = sub.add_parser("stop", help="Stop launcher-managed daemon and shell")
    stop.add_argument("--socket", default=DEFAULT_SOCKET)
    stop.set_defaults(handler=cmd_stop)

    status = sub.add_parser("status", help="Show launcher, socket, and Telegram status")
    status.add_argument("--socket", default=DEFAULT_SOCKET)
    status.add_argument("--json", action="store_true")
    status.set_defaults(handler=cmd_status)

    install_desktop = sub.add_parser("install-desktop", help="Install launcher and desktop entry")
    install_desktop.add_argument("--bin-dir", default=str(DEFAULT_BIN_DIR))
    install_desktop.add_argument("--applications-dir", default=str(DEFAULT_APPLICATIONS_DIR))
    install_desktop.add_argument("--dry-run", action="store_true")
    install_desktop.set_defaults(handler=cmd_install_desktop)

    export_public = sub.add_parser("export-public", help="Export a collaboration-free public repository tree")
    export_public.add_argument("--output", required=True)
    export_public.add_argument("--force", action="store_true")
    export_public.set_defaults(handler=cmd_export_public)

    common = build_common_parser()

    emit = sub.add_parser("emit", parents=[common], help="Emit a generic event")
    emit.set_defaults(handler=lambda args: emit_event(args.source, args))
    emit.add_argument("--source", default="unknown")

    for source_name in ("claude", "codex"):
        command = sub.add_parser(source_name, parents=[common], help=f"Emit a {source_name} event")
        command.set_defaults(handler=lambda args, source_name=source_name: emit_event(source_name, args))

    watch = sub.add_parser("watch", help="Stream snapshots from the daemon")
    watch.add_argument("--socket", default=DEFAULT_SOCKET)
    watch.add_argument("--json", action="store_true")
    watch.set_defaults(handler=cmd_watch)

    snapshot = sub.add_parser("snapshot", help="Fetch one snapshot")
    snapshot.add_argument("--socket", default=DEFAULT_SOCKET)
    snapshot.set_defaults(handler=cmd_snapshot)

    tmux_jump = sub.add_parser("tmux-jump", help="Jump to the tmux target in a snapshot or event")
    tmux_jump.add_argument("--tmux-session")
    tmux_jump.add_argument("--tmux-window")
    tmux_jump.add_argument("--tmux-pane")
    tmux_jump.add_argument("--dry-run", action="store_true")
    tmux_jump.set_defaults(handler=cmd_tmux_jump)

    jump = sub.add_parser("jump", help="Best-effort jump to a session or snapshot target")
    jump.add_argument("--session-json")
    jump.add_argument("--dry-run", action="store_true")
    jump.set_defaults(handler=cmd_jump)

    respond = sub.add_parser("respond", help="Send a selected response back to a session terminal")
    respond.add_argument("--session-json")
    respond.add_argument("--text", default="")
    respond.add_argument("--choice-index", type=int)
    respond.add_argument("--followup-text", default="")
    respond.add_argument("--dry-run", action="store_true")
    respond.set_defaults(handler=cmd_respond)

    send_peek = sub.add_parser("send-peek", help="Send a follow-up message into a live session without switching windows")
    send_peek.add_argument("--session-json")
    send_peek.add_argument("--text", default="")
    send_peek.add_argument("--return-focus-pid", type=int)
    send_peek.add_argument("--dry-run", action="store_true")
    send_peek.set_defaults(handler=cmd_send_peek)

    reconcile = sub.add_parser("reconcile", help="Scan live Claude/Codex processes and seed the daemon")
    reconcile.add_argument("--socket", default=DEFAULT_SOCKET)
    reconcile.add_argument("--json", action="store_true")
    reconcile.add_argument("--print-events", action="store_true")
    reconcile.set_defaults(handler=cmd_reconcile)

    install = sub.add_parser("install", help="Install Claude/Codex integration hooks")
    install.add_argument("target", choices=["claude", "codex", "all"])
    install.add_argument("--dry-run", action="store_true")
    install.add_argument("--claude-settings", default=str(CLAUDE_SETTINGS_PATH))
    install.add_argument("--codex-config", default=str(CODEX_CONFIG_PATH))
    install.add_argument("--codex-hooks", default=str(CODEX_HOOKS_PATH))
    install.set_defaults(handler=cmd_install)

    claude_statusline = sub.add_parser("claude-statusline", help="Capture Claude status line input for quota HUD")
    claude_statusline.add_argument("--payload")
    claude_statusline.set_defaults(handler=cmd_claude_statusline)

    claude_hook = sub.add_parser("claude-hook", help="Bridge Claude hook input into vibeisland")
    claude_hook.add_argument("--socket", default=DEFAULT_SOCKET)
    claude_hook.add_argument("--payload")
    claude_hook.add_argument("--print-event", action="store_true")
    claude_hook.set_defaults(handler=cmd_claude_hook)

    codex_hook = sub.add_parser("codex-hook", help="Bridge Codex hook input into vibeisland")
    codex_hook.add_argument("--socket", default=DEFAULT_SOCKET)
    codex_hook.add_argument("--payload")
    codex_hook.add_argument("--print-event", action="store_true")
    codex_hook.set_defaults(handler=cmd_codex_hook)

    codex_notify = sub.add_parser("codex-notify", help="Bridge Codex notify payload into vibeisland")
    codex_notify.add_argument("--socket", default=DEFAULT_SOCKET)
    codex_notify.add_argument("payload", nargs="?")
    codex_notify.add_argument("--print-event", action="store_true")
    codex_notify.set_defaults(handler=cmd_codex_notify)

    return parser


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        argv = ["launch"]
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
