use std::{
    collections::HashMap,
    fs,
    fs::File,
    io::{BufRead, BufReader as StdBufReader},
    path::{Path, PathBuf},
    sync::{
        Mutex,
        atomic::{AtomicUsize, Ordering},
    },
};

use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use rusqlite::{Connection, params};
use serde::{Deserialize, Serialize};
use tokio::{
    io::{AsyncBufReadExt, AsyncWriteExt, BufReader},
    net::{UnixListener, UnixStream},
    sync::{RwLock, broadcast},
    time::{Duration, MissedTickBehavior, interval},
};
use tracing::{error, info, warn};
use vibeisland_common::{
    AgentEvent, AgentSource, ClientRequest, EventKind, JumpTarget, ProgressInfo, QuietModeState,
    ReplayTimelineEntry, ReviewInfo, ServerResponse, SessionState, SessionSummary, Snapshot,
    StuckInfo, UsageBillingMode, UsageSummary, PeekMetadata, ArtifactIdentity,
    OverdueSeverity, attention_score,
};

const REPLAY_TIMELINE_LIMIT: usize = 48;
const RECENT_EVENT_LIMIT: usize = 128;

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(default)]
struct StoredTaskLabel {
    source: AgentSource,
    tty: String,
    cwd: Option<String>,
    workspace: Option<String>,
    session_id: Option<String>,
    title: String,
    collapsed_headline: Option<String>,
    task_label: Option<String>,
    summary: String,
    review: ReviewInfo,
    usage: Option<UsageSummary>,
    identity: ArtifactIdentity,
    peek: PeekMetadata,
    updated_at: DateTime<Utc>,
}

#[derive(Debug)]
struct AppState {
    sessions: RwLock<HashMap<String, SessionSummary>>,
    quiet_mode: RwLock<QuietModeState>,
    usage_baseline: RwLock<HashMap<String, u64>>,
    db: Mutex<Connection>,
    snapshots: broadcast::Sender<Snapshot>,
    subscribers: AtomicUsize,
}

impl AppState {
    fn new(db: Connection) -> Self {
        let (snapshots, _) = broadcast::channel(64);
        Self {
            sessions: RwLock::new(HashMap::new()),
            quiet_mode: RwLock::new(QuietModeState::default()),
            usage_baseline: RwLock::new(HashMap::new()),
            db: Mutex::new(db),
            snapshots,
            subscribers: AtomicUsize::new(0),
        }
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            std::env::var("RUST_LOG").unwrap_or_else(|_| "vibeisland_daemon=info".to_string()),
        )
        .init();

    let socket_path = socket_path();
    let db_path = db_path();

    if let Some(parent) = socket_path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("creating socket dir {}", parent.display()))?;
    }
    if let Some(parent) = db_path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("creating db dir {}", parent.display()))?;
    }

    let db = Connection::open(&db_path)
        .with_context(|| format!("opening sqlite db {}", db_path.display()))?;
    init_db(&db)?;

    if socket_path.exists() {
        fs::remove_file(&socket_path)
            .with_context(|| format!("removing stale socket {}", socket_path.display()))?;
    }

    let state = std::sync::Arc::new(AppState::new(db));
    clear_state(&state).await?;
    refresh_live_processes(&state).await?;

    {
        let state = state.clone();
        tokio::spawn(async move {
            let mut tick = interval(Duration::from_secs(2));
            tick.set_missed_tick_behavior(MissedTickBehavior::Delay);
            loop {
                tick.tick().await;
                if let Err(err) = refresh_live_processes(&state).await {
                    warn!("process scan failed: {err:#}");
                }
            }
        });
    }

    let listener = UnixListener::bind(&socket_path)
        .with_context(|| format!("binding socket {}", socket_path.display()))?;

    info!("vibeislandd listening on {}", socket_path.display());
    info!("sqlite state at {}", db_path.display());

    loop {
        match listener.accept().await {
            Ok((stream, _)) => {
                let state = state.clone();
                tokio::spawn(async move {
                    if let Err(err) = handle_client(stream, state).await {
                        error!("client error: {err:#}");
                    }
                });
            }
            Err(err) => warn!("accept error: {err:#}"),
        }
    }
}

fn socket_path() -> PathBuf {
    std::env::var("VIBEISLAND_SOCKET")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("/tmp/vibeisland.sock"))
}

fn db_path() -> PathBuf {
    if let Ok(path) = std::env::var("VIBEISLAND_DB") {
        return PathBuf::from(path);
    }

    if let Some(base) = dirs::state_dir() {
        return base.join("vibeisland").join("vibeisland.db");
    }

    Path::new("/tmp").join("vibeisland.db")
}

fn init_db(db: &Connection) -> Result<()> {
    db.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS task_labels (
            task_key TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        ",
    )?;
    Ok(())
}

#[derive(Debug, Clone, Default)]
struct ArtifactContext {
    title: Option<String>,
    collapsed_headline: Option<String>,
    preview_lines: Vec<String>,
    usage: Option<UsageSummary>,
    identity: ArtifactIdentity,
    peek: PeekMetadata,
}

fn home_dir() -> PathBuf {
    dirs::home_dir().unwrap_or_else(|| PathBuf::from("/tmp"))
}

fn codex_root() -> PathBuf {
    home_dir().join(".codex")
}

fn claude_root() -> PathBuf {
    home_dir().join(".claude")
}

fn codex_state_db_path() -> PathBuf {
    codex_root().join("state_5.sqlite")
}

fn codex_auth_path() -> PathBuf {
    codex_root().join("auth.json")
}

fn claude_sessions_dir() -> PathBuf {
    claude_root().join("sessions")
}

fn claude_projects_dir() -> PathBuf {
    claude_root().join("projects")
}

fn normalize_whitespace(value: &str) -> String {
    value.split_whitespace().collect::<Vec<_>>().join(" ")
}

fn first_text(values: &[Option<String>]) -> Option<String> {
    values
        .iter()
        .filter_map(|value| value.as_ref())
        .map(|value| normalize_whitespace(value))
        .find(|value| !value.is_empty())
}

fn read_json_file(path: &Path) -> Option<serde_json::Value> {
    let data = fs::read_to_string(path).ok()?;
    serde_json::from_str(&data).ok()
}

fn read_jsonl_lines(path: &Path) -> Vec<serde_json::Value> {
    let mut rows = Vec::new();
    let file = match File::open(path) {
        Ok(file) => file,
        Err(_) => return rows,
    };
    let reader = StdBufReader::new(file);
    for line in reader.lines().map_while(Result::ok) {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        if let Ok(value) = serde_json::from_str::<serde_json::Value>(trimmed) {
            rows.push(value);
        }
    }
    rows
}

fn collect_jsonl_files(dir: &Path, out: &mut Vec<PathBuf>) {
    let entries = match fs::read_dir(dir) {
        Ok(entries) => entries,
        Err(_) => return,
    };

    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            collect_jsonl_files(&path, out);
            continue;
        }
        if path
            .extension()
            .and_then(|value| value.to_str())
            .map(|value| value.eq_ignore_ascii_case("jsonl"))
            .unwrap_or(false)
        {
            out.push(path);
        }
    }
}

fn truncate_text(value: &str, limit: usize) -> String {
    let normalized = normalize_whitespace(value);
    if normalized.chars().count() <= limit {
        return normalized;
    }
    normalized.chars().take(limit.saturating_sub(1)).collect::<String>() + "…"
}

fn trim_task_phrase(value: &str) -> String {
    let mut text = normalize_whitespace(value);
    let prefixes = [
        "一个",
        "一款",
        "一套",
        "一个简易的",
        "一个简易",
        "简易的",
        "简易",
        "简单的",
        "简单",
        "基础的",
        "基础",
        "轻量的",
        "可运行的",
        "可用的",
        "新的",
        "这个",
        "该",
        "用于",
        "来",
        "去",
        "并且",
        "以及",
    ];

    loop {
        let mut changed = false;
        for prefix in prefixes {
            if text.starts_with(prefix) {
                text = text[prefix.len()..].trim_start().to_string();
                changed = true;
            }
        }
        if !changed {
            break;
        }
    }

    text.trim_matches(|ch: char| matches!(ch, '"' | '“' | '”' | '\'' | '，' | ',' | '。' | '.' | '!' | '?' | ';' | ':' | '：'))
        .to_string()
}

fn path_basename(path: Option<&str>) -> String {
    path.and_then(|value| Path::new(value).file_name())
        .map(|name| name.to_string_lossy().trim().to_string())
        .unwrap_or_default()
}

fn extract_url_host(text: &str) -> Option<String> {
    let normalized = normalize_whitespace(text);
    for scheme in ["https://", "http://"] {
        if let Some(index) = normalized.find(scheme) {
            let tail = &normalized[index + scheme.len()..];
            let host = tail
                .split(|ch: char| ch.is_whitespace() || ch == '/' || ch == '`' || ch == '"' || ch == '\'' || ch == ')' || ch == '(')
                .next()
                .unwrap_or("")
                .trim();
            if !host.is_empty() {
                return Some(host.to_string());
            }
        }
    }
    None
}

fn extract_named_file_target(text: &str) -> Option<String> {
    let normalized = normalize_whitespace(text);
    let lowered = normalized.to_lowercase();
    let ext = [
        "txt", "md", "json", "yaml", "yml", "toml", "py", "js", "ts", "tsx", "jsx", "html",
        "css", "csv", "ini", "conf", "sh", "rs", "cpp", "c", "h", "hpp", "java", "kt", "go",
        "php", "rb", "swift",
    ];

    for extension in ext {
        let marker = format!("{extension} 文件");
        if lowered.contains(&marker) {
            let prefix = normalized.split(&marker).next().unwrap_or("");
            let name = prefix
                .rsplit(|ch: char| ch.is_whitespace() || ch == '"' || ch == '“' || ch == '”' || ch == '\'' || ch == '：' || ch == ':')
                .next()
                .unwrap_or("")
                .trim_matches(|ch: char| matches!(ch, '"' | '“' | '”' | '\'' | '，' | ',' | '。' | '.' | '!' | '?' | ';' | ':'));
            let cleaned = trim_task_phrase(name);
            if !cleaned.is_empty() {
                return Some(format!("{cleaned}.{extension}"));
            }
        }
    }
    None
}

fn summarize_task_title(text: &str) -> Option<String> {
    let normalized = normalize_whitespace(text);
    if normalized.is_empty() {
        return None;
    }
    let lowered = normalized.to_lowercase();

    if (lowered.contains("vibe island")
        || lowered.contains("vibeisland")
        || lowered.contains("灵动岛"))
        && (lowered.contains("复刻")
            || lowered.contains("复现")
            || lowered.contains("clone")
            || lowered.contains("fork")
            || lowered.contains("rebuild")
            || lowered.contains("rewrite")
            || lowered.contains("implement")
            || lowered.contains("build"))
    {
        return Some("Rebuild Vibe Island for Linux".to_string());
    }
    if lowered.contains("tetris") || normalized.contains("俄罗斯方块") {
        return Some("Build Tetris game".to_string());
    }
    if lowered.contains("snake") || normalized.contains("贪吃蛇") {
        return Some("Build Snake game".to_string());
    }
    if lowered.contains("gomoku") || normalized.contains("五子棋") {
        return Some("Build Gomoku game".to_string());
    }
    if let Some(host) = extract_url_host(&normalized) {
        if lowered.contains("curl") || lowered.contains("wget") || lowered.contains("http") {
            if lowered.contains("-i") || lowered.contains("--head") {
                return Some(format!("Fetch {host} headers"));
            }
            return Some(format!("Fetch {host}"));
        }
    }
    if let Some(target) = extract_named_file_target(&normalized) {
        if lowered.contains("create")
            || lowered.contains("write")
            || lowered.contains("add ")
            || lowered.contains("added")
            || lowered.contains("创建")
            || lowered.contains("新建")
            || lowered.contains("生成")
            || lowered.contains("写入")
            || lowered.contains("已创建")
            || lowered.contains("添加")
        {
            return Some(format!("Create {target}"));
        }
    }

    let build_markers = [
        ("build", "Build"),
        ("make", "Build"),
        ("create", "Build"),
        ("implement", "Build"),
        ("develop", "Build"),
        ("做", "Build"),
        ("制作", "Build"),
        ("实现", "Build"),
        ("开发", "Build"),
        ("搭建", "Build"),
        ("fix", "Fix"),
        ("修复", "Fix"),
        ("optimize", "Optimize"),
        ("优化", "Optimize"),
        ("refactor", "Refactor"),
        ("重构", "Refactor"),
    ];

    for (needle, action) in build_markers {
        if let Some(pos) = lowered.find(needle) {
            let tail = normalized[pos + needle.len()..].trim();
            if !tail.is_empty() {
                let cleaned = trim_task_phrase(
                    tail.trim_start_matches(|ch: char| matches!(ch, ':' | '：' | ' '))
                        .trim_start_matches('的'),
                );
                if !cleaned.is_empty() {
                    return Some(truncate_text(&format!("{action} {cleaned}"), 52));
                }
            }
        }
    }

    if normalized.len() <= 52 {
        return Some(normalized);
    }
    Some(truncate_text(&normalized, 52))
}

fn dedupe_lines(lines: Vec<String>, limit: usize) -> Vec<String> {
    let mut out = Vec::new();
    for line in lines {
        let normalized = normalize_whitespace(&line);
        if normalized.is_empty() {
            continue;
        }
        if out.iter().any(|existing: &String| normalize_whitespace(existing) == normalized) {
            continue;
        }
        out.push(normalized);
        if out.len() >= limit {
            break;
        }
    }
    out
}

fn artifact_identity_is_meaningful(identity: &ArtifactIdentity) -> bool {
    identity.source_session_id.is_some()
        || identity.backend_session_id.is_some()
        || identity.artifact_kind.is_some()
        || identity.artifact_path.is_some()
        || identity.title_source.is_some()
}

fn usage_summary_is_meaningful(usage: &UsageSummary) -> bool {
    usage.session_tokens.is_some()
        || usage.five_hour.is_some()
        || usage.seven_day.is_some()
        || !matches!(usage.mode, UsageBillingMode::Unknown)
}

fn peek_metadata_is_meaningful(peek: &PeekMetadata) -> bool {
    peek.source_session_id.is_some()
        || peek.backend_session_id.is_some()
        || peek.transcript_path.is_some()
        || !peek.preview_lines.is_empty()
        || peek.input_hint.is_some()
}

fn artifact_context_is_meaningful(context: &ArtifactContext) -> bool {
    context
        .title
        .as_deref()
        .map(|value| !value.trim().is_empty())
        .unwrap_or(false)
        || context
            .collapsed_headline
            .as_deref()
            .map(|value| !value.trim().is_empty())
            .unwrap_or(false)
        || !context.preview_lines.is_empty()
        || context
            .usage
            .as_ref()
            .map(usage_summary_is_meaningful)
            .unwrap_or(false)
        || artifact_identity_is_meaningful(&context.identity)
        || peek_metadata_is_meaningful(&context.peek)
}

fn match_workspace_path(candidate: Option<&str>, cwd: Option<&str>) -> bool {
    let left = candidate.map(str::trim).unwrap_or_default();
    let right = cwd.map(str::trim).unwrap_or_default();
    if left.is_empty() || right.is_empty() {
        return false;
    }
    if left == right {
        return true;
    }
    let canonical_left = fs::canonicalize(left).ok();
    let canonical_right = fs::canonicalize(right).ok();
    match (canonical_left, canonical_right) {
        (Some(left_path), Some(right_path)) => left_path == right_path,
        _ => false,
    }
}

fn load_codex_auth_mode() -> UsageBillingMode {
    let value = match read_json_file(&codex_auth_path()) {
        Some(value) => value,
        None => return UsageBillingMode::Unknown,
    };
    let auth_mode = value
        .get("auth_mode")
        .and_then(|item| item.as_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    if auth_mode.contains("api") {
        return UsageBillingMode::ApiKey;
    }
    if value
        .get("OPENAI_API_KEY")
        .and_then(|item| item.as_str())
        .map(|item| !item.trim().is_empty())
        .unwrap_or(false)
    {
        return UsageBillingMode::ApiKey;
    }
    if auth_mode.contains("chatgpt") || auth_mode.contains("subscription") || auth_mode.contains("plus") {
        return UsageBillingMode::Subscription;
    }
    UsageBillingMode::Unknown
}

fn load_codex_thread_context(cwd: &Path) -> Option<ArtifactContext> {
    let db_path = codex_state_db_path();
    if !db_path.exists() {
        return None;
    }

    let conn = Connection::open(&db_path).ok()?;
    let mut stmt = conn
        .prepare(
            "SELECT id, cwd, title, first_user_message, rollout_path, updated_at, tokens_used
             FROM threads
             ORDER BY updated_at DESC
             LIMIT 400",
        )
        .ok()?;
    let rows = stmt
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
                row.get::<_, Option<String>>(4)?,
                row.get::<_, i64>(5)?,
                row.get::<_, i64>(6)?,
            ))
        })
        .ok()?;

    let cwd_text = cwd.to_string_lossy().to_string();
    let mut best: Option<ArtifactContext> = None;
    for row in rows.flatten() {
        let (id, row_cwd, title, first_user_message, rollout_path, _updated_at, tokens_used) = row;
        if !match_workspace_path(Some(&row_cwd), Some(&cwd_text)) {
            continue;
        }
        let task_title = first_text(&[
            summarize_task_title(&first_user_message),
            summarize_task_title(&title),
            Some(title.clone()),
            Some(first_user_message.clone()),
        ]);
        let preview_lines = dedupe_lines(
            vec![
                task_title.clone().unwrap_or_else(|| truncate_text(&first_user_message, 88)),
                truncate_text(&first_user_message, 132),
                truncate_text(&title, 132),
            ],
            4,
        );
        let artifact_path = rollout_path.unwrap_or_else(|| db_path.display().to_string());
        let context = ArtifactContext {
            title: task_title.clone(),
            collapsed_headline: task_title.clone(),
            preview_lines: preview_lines.clone(),
            usage: Some(UsageSummary {
                source: AgentSource::Codex,
                mode: load_codex_auth_mode(),
                five_hour: None,
                seven_day: None,
                session_tokens: Some(tokens_used.max(0) as u64),
                source_session_id: Some(id.clone()),
            }),
            identity: ArtifactIdentity {
                source_session_id: Some(id.clone()),
                backend_session_id: Some(id.clone()),
                artifact_kind: Some("codex_thread_db".to_string()),
                artifact_path: Some(artifact_path),
                title_source: Some(if task_title.is_some() {
                    "first_user_message".to_string()
                } else {
                    "thread_title".to_string()
                }),
            },
            peek: PeekMetadata {
                supported: true,
                source_session_id: Some(id.clone()),
                backend_session_id: Some(id.clone()),
                transcript_path: None,
                preview_lines,
                input_hint: Some("Type a follow-up and press send".to_string()),
            },
        };
        best = Some(context);
        break;
    }

    if let Some(best) = best {
        if artifact_context_is_meaningful(&best) {
            return Some(best);
        }
    }

    load_codex_rollout_context(cwd)
}

fn load_codex_rollout_context(cwd: &Path) -> Option<ArtifactContext> {
    let root = codex_root().join("sessions");
    if !root.exists() {
        return None;
    }

    let mut files = Vec::new();
    collect_jsonl_files(&root, &mut files);
    files.sort_by_key(|path| fs::metadata(path).and_then(|meta| meta.modified()).ok());
    files.reverse();

    let cwd_text = cwd.to_string_lossy().to_string();
    for path in files {
        let rows = read_jsonl_lines(&path);
        if rows.is_empty() {
            continue;
        }

        let mut session_id = None;
        let mut rollout_cwd = None;
        let mut prompt_lines = Vec::new();
        let mut assistant_lines = Vec::new();
        let mut preview_lines = Vec::new();

        for value in rows {
            let kind = value.get("type").and_then(|item| item.as_str()).unwrap_or("");
            let payload = value.get("payload").unwrap_or(&serde_json::Value::Null);

            match kind {
                "session_meta" => {
                    session_id = payload
                        .get("id")
                        .and_then(|item| item.as_str())
                        .map(str::to_string);
                    rollout_cwd = payload
                        .get("cwd")
                        .and_then(|item| item.as_str())
                        .map(str::to_string);
                }
                "response_item" => {
                    let role = payload
                        .get("role")
                        .and_then(|item| item.as_str())
                        .unwrap_or("");
                    let mut chunks = Vec::new();
                    if let Some(content) = payload.get("content").and_then(|item| item.as_array()) {
                        for entry in content {
                            if let Some(text) = entry.get("text").and_then(|item| item.as_str()) {
                                chunks.push(text.to_string());
                            }
                        }
                    }
                    let joined = normalize_whitespace(&chunks.join(" "));
                    if joined.is_empty() {
                        continue;
                    }
                    if role == "user" {
                        prompt_lines.push(joined.clone());
                    } else if role == "assistant" {
                        assistant_lines.push(joined.clone());
                    }
                    preview_lines.push(joined);
                }
                "event_msg" => {
                    if let Some(message) = payload.get("message").and_then(|item| item.as_str()) {
                        let normalized = normalize_whitespace(message);
                        if normalized.is_empty() {
                            continue;
                        }
                        if preview_lines.len() < 6 {
                            preview_lines.push(normalized.clone());
                        }
                        if message.contains("user_message") {
                            prompt_lines.push(normalized.clone());
                        } else if message.contains("assistant_message") {
                            assistant_lines.push(normalized.clone());
                        }
                    }
                }
                _ => {}
            }
        }

        if !match_workspace_path(rollout_cwd.as_deref(), Some(&cwd_text)) {
            continue;
        }

        let prompt_text = prompt_lines.first().cloned().unwrap_or_default();
        let assistant_text = assistant_lines.first().cloned().unwrap_or_default();
        let title = first_text(&[
            summarize_task_title(&prompt_text),
            summarize_task_title(&assistant_text),
            Some(prompt_text.clone()),
            Some(assistant_text.clone()),
        ]);

        let preview = dedupe_lines(
            {
                let mut lines = Vec::new();
                if let Some(value) = title.clone() {
                    lines.push(value);
                }
                lines.extend(preview_lines.into_iter().take(5));
                lines
            },
            6,
        );
        let artifact_path = path.display().to_string();
        let context = ArtifactContext {
            title: title.clone(),
            collapsed_headline: title,
            preview_lines: preview.clone(),
            usage: Some(UsageSummary {
                source: AgentSource::Codex,
                mode: load_codex_auth_mode(),
                five_hour: None,
                seven_day: None,
                session_tokens: None,
                source_session_id: session_id.clone(),
            }),
            identity: ArtifactIdentity {
                source_session_id: session_id,
                backend_session_id: None,
                artifact_kind: Some("codex_rollout".to_string()),
                artifact_path: Some(artifact_path),
                title_source: Some("rollout_jsonl".to_string()),
            },
            peek: PeekMetadata {
                supported: true,
                source_session_id: None,
                backend_session_id: None,
                transcript_path: Some(path.display().to_string()),
                preview_lines: preview,
                input_hint: Some("Type a follow-up and press send".to_string()),
            },
        };

        if artifact_context_is_meaningful(&context) {
            return Some(context);
        }
    }

    None
}

fn find_claude_session_record(pid: u32) -> Option<(String, String)> {
    let path = claude_sessions_dir().join(format!("{pid}.json"));
    let value = read_json_file(&path)?;
    let session_id = value.get("sessionId").and_then(|item| item.as_str())?.to_string();
    let cwd = value
        .get("cwd")
        .and_then(|item| item.as_str())
        .unwrap_or("")
        .to_string();
    Some((session_id, cwd))
}

fn find_project_transcript(session_id: &str) -> Option<PathBuf> {
    let projects = claude_projects_dir();
    if !projects.exists() {
        return None;
    }
    let mut stack = vec![projects];
    while let Some(dir) = stack.pop() {
        let entries = match fs::read_dir(&dir) {
            Ok(entries) => entries,
            Err(_) => continue,
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() {
                stack.push(path);
                continue;
            }
            if path.extension().and_then(|value| value.to_str()) != Some("jsonl") {
                continue;
            }
            if path.file_name().and_then(|value| value.to_str()) == Some(&format!("{session_id}.jsonl")) {
                return Some(path);
            }
        }
    }
    None
}

fn claude_line_content(value: &serde_json::Value) -> Option<String> {
    if let Some(content) = value.get("content").and_then(|item| item.as_str()) {
        let text = normalize_whitespace(content);
        if !text.is_empty() {
            return Some(text);
        }
    }

    if let Some(message) = value.get("message").and_then(|item| item.as_object()) {
        if let Some(text) = message.get("content").and_then(|item| item.as_str()) {
            let text = normalize_whitespace(text);
            if !text.is_empty() {
                return Some(text);
            }
        }
        if let Some(array) = message.get("content").and_then(|item| item.as_array()) {
            let mut parts = Vec::new();
            for block in array {
                if let Some(text) = block.get("text").and_then(|item| item.as_str()) {
                    let text = normalize_whitespace(text);
                    if !text.is_empty() {
                        parts.push(text);
                    }
                } else if let Some(input) = block.get("input").and_then(|item| item.as_object()) {
                    if let Some(command) = input.get("command").and_then(|item| item.as_str()) {
                        let command = normalize_whitespace(command);
                        if !command.is_empty() {
                            parts.push(format!("$ {command}"));
                        }
                    }
                }
            }
            if !parts.is_empty() {
                return Some(parts.join(" "));
            }
        }
    }
    None
}

fn load_claude_artifact_context(pid: u32) -> Option<ArtifactContext> {
    let (session_id, _cwd) = find_claude_session_record(pid)?;
    let transcript = find_project_transcript(&session_id);
    let mut prompt = String::new();
    let mut preview_lines = Vec::new();
    let mut session_tokens = 0u64;
    let mut last_assistant = String::new();

    if let Some(path) = transcript.as_ref() {
        for line in read_jsonl_lines(path) {
            let kind = line
                .get("type")
                .and_then(|item| item.as_str())
                .unwrap_or("")
                .to_ascii_lowercase();
            if kind == "last-prompt" {
                if let Some(value) = line.get("lastPrompt").and_then(|item| item.as_str()) {
                    let value = normalize_whitespace(value);
                    if !value.is_empty() {
                        prompt = value;
                    }
                }
                continue;
            }
            if kind == "user" {
                if let Some(value) = claude_line_content(&line) {
                    if prompt.is_empty() {
                        prompt = value.clone();
                    }
                    preview_lines.push(format!("You: {}", truncate_text(&value, 96)));
                }
                continue;
            }
            if kind == "assistant" {
                if let Some(value) = claude_line_content(&line) {
                    if last_assistant.is_empty() {
                        last_assistant = value.clone();
                    }
                    preview_lines.push(truncate_text(&value, 96));
                }
                if let Some(message) = line.get("message").and_then(|item| item.as_object()) {
                    if let Some(usage) = message.get("usage").and_then(|item| item.as_object()) {
                        let input = usage
                            .get("input_tokens")
                            .and_then(|item| item.as_u64())
                            .unwrap_or(0);
                        let output = usage
                            .get("output_tokens")
                            .and_then(|item| item.as_u64())
                            .unwrap_or(0);
                        let cache = usage
                            .get("cache_creation_input_tokens")
                            .and_then(|item| item.as_u64())
                            .unwrap_or(0)
                            + usage
                                .get("cache_read_input_tokens")
                                .and_then(|item| item.as_u64())
                                .unwrap_or(0);
                        session_tokens = session_tokens.saturating_add(input + output + cache);
                    }
                }
                continue;
            }
            if kind == "system" {
                if let Some(summary) = line.get("subtype").and_then(|item| item.as_str()) {
                    preview_lines.push(truncate_text(summary, 96));
                }
            }
        }
    }

    let title = first_text(&[
        summarize_task_title(&prompt),
        summarize_task_title(&last_assistant),
        Some(prompt.clone()),
        Some(last_assistant.clone()),
    ]);
    let mut summary_preview = Vec::new();
    if let Some(value) = title.clone() {
        summary_preview.push(value);
    }
    summary_preview.extend(preview_lines.into_iter().take(5));
    let preview = dedupe_lines(summary_preview, 6);
    let artifact_path = transcript
        .as_ref()
        .map(|path| path.display().to_string())
        .unwrap_or_else(|| claude_sessions_dir().join(format!("{pid}.json")).display().to_string());
    Some(ArtifactContext {
        title: title.clone(),
        collapsed_headline: title,
        preview_lines: preview.clone(),
        usage: Some(UsageSummary {
            source: AgentSource::Claude,
            mode: if std::env::var("ANTHROPIC_API_KEY").ok().map(|value| !value.trim().is_empty()).unwrap_or(false) {
                UsageBillingMode::ApiKey
            } else {
                UsageBillingMode::Subscription
            },
            five_hour: None,
            seven_day: None,
            session_tokens: Some(session_tokens),
            source_session_id: Some(session_id.clone()),
        }),
        identity: ArtifactIdentity {
            source_session_id: Some(session_id.clone()),
            backend_session_id: Some(session_id.clone()),
            artifact_kind: Some("claude_transcript".to_string()),
            artifact_path: Some(artifact_path.clone()),
            title_source: Some(if prompt.is_empty() { "assistant_reply".to_string() } else { "last_prompt".to_string() }),
        },
        peek: PeekMetadata {
            supported: true,
            source_session_id: Some(session_id.clone()),
            backend_session_id: Some(session_id.clone()),
            transcript_path: transcript.map(|path| path.display().to_string()),
            preview_lines: preview,
            input_hint: Some("Type a follow-up and press send".to_string()),
        },
    })
}

async fn handle_client(stream: UnixStream, state: std::sync::Arc<AppState>) -> Result<()> {
    let (reader, mut writer) = stream.into_split();
    let mut lines = BufReader::new(reader).lines();

    while let Some(line) = lines.next_line().await? {
        if line.trim().is_empty() {
            continue;
        }

        let request: ClientRequest = match serde_json::from_str(&line) {
            Ok(request) => request,
            Err(err) => {
                write_response(
                    &mut writer,
                    &ServerResponse::Error {
                        message: format!("invalid request: {err}"),
                    },
                )
                .await?;
                continue;
            }
        };

        match request {
            ClientRequest::Ping => write_response(&mut writer, &ServerResponse::Pong).await?,
            ClientRequest::Snapshot => {
                let snapshot = build_snapshot(&state).await;
                write_response(&mut writer, &ServerResponse::Snapshot { snapshot }).await?;
            }
            ClientRequest::Subscribe => {
                state.subscribers.fetch_add(1, Ordering::SeqCst);
                let snapshot = build_snapshot(&state).await;
                write_response(&mut writer, &ServerResponse::Snapshot { snapshot }).await?;
                let stream_result = stream_snapshots(&mut writer, state.clone()).await;
                let last = state.subscribers.fetch_sub(1, Ordering::SeqCst) == 1;
                if last {
                    clear_state(&state).await?;
                    refresh_live_processes(&state).await?;
                }
                stream_result?;
                break;
            }
            ClientRequest::Clear => {
                clear_state(&state).await?;
                write_response(&mut writer, &ServerResponse::Ack { ok: true }).await?;
            }
            ClientRequest::Publish { event } => {
                let snapshot = process_event(&state, event).await?;
                let _ = state.snapshots.send(snapshot);
                write_response(&mut writer, &ServerResponse::Ack { ok: true }).await?;
            }
            ClientRequest::SetQuietMode {
                enabled,
                suppress_below_attention,
                reason,
            } => {
                let snapshot =
                    set_quiet_mode(&state, enabled, suppress_below_attention, reason).await?;
                let _ = state.snapshots.send(snapshot);
                write_response(&mut writer, &ServerResponse::Ack { ok: true }).await?;
            }
        }
    }

    Ok(())
}

async fn stream_snapshots<W>(writer: &mut W, state: std::sync::Arc<AppState>) -> Result<()>
where
    W: AsyncWriteExt + Unpin,
{
    let mut receiver = state.snapshots.subscribe();

    loop {
        let snapshot = match receiver.recv().await {
            Ok(snapshot) => snapshot,
            Err(broadcast::error::RecvError::Lagged(_)) => build_snapshot(&state).await,
            Err(broadcast::error::RecvError::Closed) => break,
        };

        write_response(writer, &ServerResponse::Snapshot { snapshot }).await?;
    }

    Ok(())
}

async fn write_response<W>(writer: &mut W, response: &ServerResponse) -> Result<()>
where
    W: AsyncWriteExt + Unpin,
{
    let payload = serde_json::to_string(response)?;
    writer.write_all(payload.as_bytes()).await?;
    writer.write_all(b"\n").await?;
    writer.flush().await?;
    Ok(())
}

async fn build_snapshot(state: &std::sync::Arc<AppState>) -> Snapshot {
    let now = Utc::now();
    let quiet_mode = state.quiet_mode.read().await.clone();
    let recent_events = load_recent_events(state, RECENT_EVENT_LIMIT)
        .await
        .unwrap_or_default();
    let timeline = build_replay_timeline(&recent_events);

    let mut events_by_session: HashMap<String, Vec<&AgentEvent>> = HashMap::new();
    for event in &recent_events {
        events_by_session
            .entry(event.session.id.clone())
            .or_default()
            .push(event);
    }

    let sessions = state.sessions.read().await;
    let mut items: Vec<SessionSummary> = sessions.values().cloned().collect();
    drop(sessions);

    for item in &mut items {
        let recent = events_by_session
            .get(&item.id)
            .map(Vec::as_slice)
            .unwrap_or(&[]);
        item.stuck = derive_stuck_info(item, recent, now);
        item.overdue_severity = derive_overdue_severity(item, recent, now);
        if item.stuck.is_stuck {
            item.attention_score = item.attention_score.max(item.stuck.score.max(95));
        }
        if matches!(item.overdue_severity, OverdueSeverity::Critical) {
            item.attention_score = item.attention_score.max(95);
        } else if matches!(item.overdue_severity, OverdueSeverity::Warning) {
            item.attention_score = item.attention_score.max(80);
        }
    }

    items.sort_by(|left, right| {
        right
            .attention_score
            .cmp(&left.attention_score)
            .then_with(|| right.updated_at.cmp(&left.updated_at))
    });

    let blocked_count = items
        .iter()
        .filter(|session| {
            matches!(
                session.state,
                SessionState::Blocked | SessionState::WaitingUser | SessionState::Failed
            )
        })
        .count();

    let usage = build_usage_snapshot(state, &items).await;

    Snapshot {
        generated_at: now,
        active_count: items.len(),
        blocked_count,
        usage,
        timeline,
        quiet_mode,
        sessions: items,
    }
}

fn interaction_present(interaction: &vibeisland_common::Interaction) -> bool {
    interaction
        .approval_type
        .as_deref()
        .map(|value| !value.trim().is_empty())
        .unwrap_or(false)
        || interaction
            .question
            .as_deref()
            .map(|value| !value.trim().is_empty())
            .unwrap_or(false)
        || !interaction.choices.is_empty()
}

fn raw_flag(raw: &serde_json::Value, key: &str) -> bool {
    raw.get(key)
        .and_then(|value| value.as_bool())
        .unwrap_or(false)
}

async fn refresh_live_processes(state: &std::sync::Arc<AppState>) -> Result<()> {
    let discovered = discover_live_sessions(state)?;

    let live_ids: std::collections::HashSet<String> = discovered
        .iter()
        .map(|session| session.id.clone())
        .collect();

    {
        let mut sessions = state.sessions.write().await;
        for summary in discovered {
            sessions
                .entry(summary.id.clone())
                .and_modify(|existing| {
                    let existing_label = preferred_summary_label(existing);
                    let discovered_label = preferred_summary_label(&summary);
                    let merged_title = choose_task_label(
                        existing_label.clone(),
                        discovered_label.clone(),
                        existing.title.clone(),
                    );
                    existing.title = merged_title.clone();
                    existing.task_label = Some(choose_task_label(
                        existing
                            .task_label
                            .as_deref()
                            .map(str::to_string)
                            .or(existing_label),
                        summary.task_label.clone().or(discovered_label),
                        merged_title,
                    ));
                    existing.source = summary.source.clone();
                    existing.workspace = summary.workspace.clone();
                    existing.cwd = summary.cwd.clone();
                    existing.updated_at = summary.updated_at;
                    existing.jump_target = summary.jump_target.clone();
                    if summary
                        .collapsed_headline
                        .as_deref()
                        .map(|value| !value.trim().is_empty())
                        .unwrap_or(false)
                    {
                        existing.collapsed_headline = summary.collapsed_headline.clone();
                    }
                    if artifact_identity_is_meaningful(&summary.identity) {
                        existing.identity = summary.identity.clone();
                    }
                    if peek_metadata_is_meaningful(&summary.peek) {
                        existing.peek = summary.peek.clone();
                    }
                    if summary
                        .usage
                        .as_ref()
                        .map(usage_summary_is_meaningful)
                        .unwrap_or(false)
                    {
                        existing.usage = summary.usage.clone();
                    }
                    if !matches!(summary.overdue_severity, OverdueSeverity::None) {
                        existing.overdue_severity = summary.overdue_severity.clone();
                    }
                    if review_present(&summary.review) {
                        existing.review = summary.review.clone();
                    }

                    let keep_existing_state = !matches!(
                        existing.last_event_kind,
                        EventKind::SessionHeartbeat | EventKind::SessionStarted
                    ) || !matches!(existing.state, SessionState::Running);

                    if !keep_existing_state {
                        existing.state = summary.state.clone();
                        existing.summary = summary.summary.clone();
                        existing.attention_score = summary.attention_score;
                        existing.last_event_kind = summary.last_event_kind.clone();
                        existing.progress = summary.progress.clone();
                        existing.interaction = summary.interaction.clone();
                    }
                })
                .or_insert(summary);
        }

        sessions.retain(|session_id, _summary| {
            if session_id.starts_with("live::") {
                live_ids.contains(session_id)
            } else {
                true
            }
        });
    }

    persist_sessions_snapshot(state).await?;
    let snapshot = build_snapshot(state).await;
    let _ = state.snapshots.send(snapshot);
    Ok(())
}

async fn clear_state(state: &std::sync::Arc<AppState>) -> Result<()> {
    {
        let mut sessions = state.sessions.write().await;
        sessions.clear();
    }
    {
        let mut quiet_mode = state.quiet_mode.write().await;
        *quiet_mode = QuietModeState::default();
    }

    {
        let db = state.db.lock().expect("db mutex poisoned");
        db.execute("DELETE FROM events", [])?;
        db.execute("DELETE FROM sessions", [])?;
    }

    let snapshot = build_snapshot(state).await;
    let _ = state.snapshots.send(snapshot);
    Ok(())
}

async fn persist_sessions_snapshot(state: &std::sync::Arc<AppState>) -> Result<()> {
    let sessions = state.sessions.read().await;
    let rows: Vec<SessionSummary> = sessions.values().cloned().collect();
    drop(sessions);

    let db = state.db.lock().expect("db mutex poisoned");
    for summary in rows {
        let payload = serde_json::to_string(&summary)?;
        db.execute(
            "INSERT OR REPLACE INTO sessions (session_id, payload, updated_at)
             VALUES (?1, ?2, ?3)",
            params![summary.id, payload, summary.updated_at.to_rfc3339()],
        )?;
    }
    Ok(())
}

async fn persist_task_label(
    state: &std::sync::Arc<AppState>,
    summary: &SessionSummary,
) -> Result<()> {
    let tty = match summary
        .jump_target
        .tty
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        Some(value) => value.to_string(),
        None => return Ok(()),
    };

    let task_label = preferred_summary_label(summary);
    if task_label.is_none() {
        return Ok(());
    }
    let task_label = task_label.unwrap();

    let payload = StoredTaskLabel {
        source: summary.source.clone(),
        tty: tty.clone(),
        cwd: summary.cwd.clone(),
        workspace: summary.workspace.clone(),
        session_id: Some(summary.id.clone()),
        collapsed_headline: summary.collapsed_headline.clone(),
        title: task_label.clone(),
        task_label: Some(task_label.clone()),
        summary: summary.summary.clone(),
        review: summary.review.clone(),
        usage: summary.usage.clone(),
        identity: summary.identity.clone(),
        peek: summary.peek.clone(),
        updated_at: summary.updated_at,
    };
    let payload_json = serde_json::to_string(&payload)?;
    let task_key = task_label_key(&payload.source, &payload.tty);

    let db = state.db.lock().expect("db mutex poisoned");
    db.execute(
        "INSERT OR REPLACE INTO task_labels (task_key, payload, updated_at)
         VALUES (?1, ?2, ?3)",
        params![task_key, payload_json, payload.updated_at.to_rfc3339()],
    )?;
    Ok(())
}

fn review_present(review: &ReviewInfo) -> bool {
    review
        .headline
        .as_deref()
        .map(|value| !value.trim().is_empty())
        .unwrap_or(false)
        || review
            .command
            .as_deref()
            .map(|value| !value.trim().is_empty())
            .unwrap_or(false)
        || review
            .detail
            .as_deref()
            .map(|value| !value.trim().is_empty())
            .unwrap_or(false)
        || review
            .reason
            .as_deref()
            .map(|value| !value.trim().is_empty())
            .unwrap_or(false)
        || review
            .risk
            .as_deref()
            .map(|value| !value.trim().is_empty())
            .unwrap_or(false)
        || review
            .scope
            .as_deref()
            .map(|value| !value.trim().is_empty())
            .unwrap_or(false)
        || review
            .workspace_hint
            .as_deref()
            .map(|value| !value.trim().is_empty())
            .unwrap_or(false)
        || review
            .tool_name
            .as_deref()
            .map(|value| !value.trim().is_empty())
            .unwrap_or(false)
}

fn normalize_label_value(value: &str) -> String {
    value.split_whitespace().collect::<Vec<_>>().join(" ")
}

fn is_low_signal_task_label(value: &str) -> bool {
    let lowered = normalize_label_value(value).to_lowercase();
    if lowered.is_empty() {
        return true;
    }

    if lowered.starts_with("codex @ ")
        || lowered.starts_with("claude @ ")
        || lowered.starts_with("gemini @ ")
        || lowered.starts_with("openclaw @ ")
        || lowered.starts_with("agent @ ")
        || lowered.starts_with("codex session")
        || lowered.starts_with("claude session")
        || lowered.starts_with("gemini session")
        || lowered.starts_with("openclaw session")
        || lowered.starts_with("agent session")
    {
        return true;
    }

    const PREFIXES: &[&str] = &[
        "agent-turn-complete",
        "command execution review",
        "network access review",
        "workspace write review",
        "read-only review",
        "review before approve",
        "task review",
        "question to answer",
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
        "running sessionstart hook",
        "running userpromptsubmit hook",
        "running pretooluse hook",
        "running posttooluse hook",
        "sessionstart hook",
        "userpromptsubmit hook",
        "pretooluse hook",
        "posttooluse hook",
        "detected live",
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
        "codex session",
        "claude session",
        "agent session",
        "codex @",
        "claude @",
        "agent @",
        "codex ·",
        "claude ·",
        "agent ·",
    ];

    if PREFIXES.iter().any(|prefix| lowered.starts_with(prefix)) {
        return true;
    }

    const CONTAINS: &[&str] = &[
        "i'm ready to help. i see you've provided",
        "i'm ready to help. i see you've sent",
        "what would you like me to help with",
        "what would you like me to do",
        "ready to help",
    ];

    if CONTAINS.iter().any(|snippet| lowered.contains(snippet)) {
        return true;
    }

    if lowered.contains("&& node -v")
        || lowered.contains("&& npm -v")
        || lowered.contains("&& pnpm -v")
    {
        return true;
    }

    matches!(
        lowered.as_str(),
        "completed" | "updated" | "running" | "done" | "finished"
    )
}

fn preferred_summary_label(summary: &SessionSummary) -> Option<String> {
    preferred_label(summary.title.as_str(), summary.task_label.as_deref())
        .or_else(|| {
            summary
                .collapsed_headline
                .as_deref()
                .map(normalize_label_value)
                .filter(|value| !value.is_empty() && !is_low_signal_task_label(value))
        })
}

fn preferred_label(title: &str, task_label: Option<&str>) -> Option<String> {
    if let Some(task_label) = task_label {
        let normalized = normalize_label_value(task_label);
        if !normalized.is_empty() && !is_low_signal_task_label(&normalized) {
            return Some(normalized);
        }
    }

    let normalized_title = normalize_label_value(title);
    if !normalized_title.is_empty() && !is_low_signal_task_label(&normalized_title) {
        return Some(normalized_title);
    }
    None
}

fn is_workspace_like_label(value: &str, cwd: Option<&str>, workspace: Option<&str>) -> bool {
    let normalized = normalize_label_value(value);
    if normalized.is_empty() {
        return true;
    }
    let lowered = normalized.to_lowercase();
    if lowered.starts_with('{') || lowered.starts_with('[') {
        return true;
    }

    let cwd_name = path_basename(cwd);
    if !cwd_name.is_empty() && lowered == cwd_name.to_lowercase() {
        return true;
    }

    let workspace_name = path_basename(workspace);
    !workspace_name.is_empty() && lowered == workspace_name.to_lowercase()
}

fn explicit_event_task_label(event: &AgentEvent) -> Option<String> {
    if let Some(task_label) = event.session.task_label.as_deref() {
        let normalized = normalize_label_value(task_label);
        if !normalized.is_empty()
            && !is_low_signal_task_label(&normalized)
            && !is_workspace_like_label(
                &normalized,
                event.session.cwd.as_deref(),
                event.session.workspace.as_deref(),
            )
        {
            return Some(normalized);
        }
    }

    let normalized = normalize_label_value(event.session.title.as_deref().unwrap_or(""));
    if !normalized.is_empty()
        && !is_low_signal_task_label(&normalized)
        && !is_workspace_like_label(
            &normalized,
            event.session.cwd.as_deref(),
            event.session.workspace.as_deref(),
        )
    {
        return Some(normalized);
    }
    None
}

fn choose_task_label(
    existing: Option<String>,
    candidate: Option<String>,
    fallback: String,
) -> String {
    if let Some(existing) = existing {
        if !is_low_signal_task_label(&existing) {
            return existing;
        }
    }

    if let Some(candidate) = candidate {
        if !is_low_signal_task_label(&candidate) {
            return candidate;
        }
    }

    fallback
}

fn task_label_key(source: &AgentSource, tty: &str) -> String {
    format!("{}::{}", stringify_source(source).to_lowercase(), tty)
}

fn load_task_label(
    state: &std::sync::Arc<AppState>,
    source: &AgentSource,
    tty: &str,
) -> Option<StoredTaskLabel> {
    let task_key = task_label_key(source, tty);
    let db = state.db.lock().expect("db mutex poisoned");
    let payload: Option<String> = db
        .query_row(
            "SELECT payload FROM task_labels WHERE task_key = ?1",
            params![task_key],
            |row| row.get(0),
        )
        .ok();
    payload.and_then(|value| serde_json::from_str(&value).ok())
}

fn load_recent_event_task_label(
    state: &std::sync::Arc<AppState>,
    source: &AgentSource,
    session_id: Option<&str>,
    tty: &str,
) -> Option<String> {
    let normalized_session_id = session_id
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .unwrap_or_default();
    let normalized_tty = tty.trim();
    if normalized_session_id.is_empty() && normalized_tty.is_empty() {
        return None;
    }

    let db = state.db.lock().expect("db mutex poisoned");
    let mut stmt = db
        .prepare(
            "SELECT payload
             FROM events
             ORDER BY created_at DESC
             LIMIT 400",
        )
        .ok()?;
    let rows = stmt
        .query_map([], |row| row.get::<_, String>(0))
        .ok()?;

    for payload_json in rows.flatten() {
        let event: AgentEvent = match serde_json::from_str(&payload_json) {
            Ok(event) => event,
            Err(_) => continue,
        };
        if &event.source != source {
            continue;
        }
        let event_session_id = event
            .session
            .id
            .trim();
        let event_tty = event
            .jump_target
            .tty
            .as_deref()
            .map(str::trim)
            .unwrap_or_default();
        let session_matches =
            !normalized_session_id.is_empty() && event_session_id == normalized_session_id;
        let tty_matches = !normalized_tty.is_empty() && event_tty == normalized_tty;
        if !session_matches && !tty_matches {
            continue;
        }
        if let Some(label) = explicit_event_task_label(&event) {
            return Some(label);
        }
    }

    None
}

async fn process_event(state: &std::sync::Arc<AppState>, event: AgentEvent) -> Result<Snapshot> {
    let resolved_id = {
        let sessions = state.sessions.read().await;
        resolve_session_id(&sessions, &event)
    };

    {
        let mut sessions = state.sessions.write().await;
        let now = event.ts;
        let existing_summary = sessions.get(&resolved_id).cloned();
        let incoming_label = explicit_event_task_label(&event);
        let codex_cwd = event
            .session
            .cwd
            .as_deref()
            .or(event.session.workspace.as_deref());
        let artifact = match event.source {
            AgentSource::Codex => codex_cwd.map(Path::new).and_then(load_codex_thread_context),
            AgentSource::Claude => event.jump_target.pid.and_then(load_claude_artifact_context),
            _ => None,
        };
        let artifact_label = artifact
            .as_ref()
            .and_then(|context| context.title.clone())
            .filter(|value| !value.trim().is_empty());
        let fallback_title = format!("{} session", stringify_source(&event.source));
        let existing_label = existing_summary.as_ref().and_then(preferred_summary_label);
        let final_title = choose_task_label(
            existing_label.clone(),
            artifact_label.clone().or(incoming_label.clone()),
            fallback_title.clone(),
        );
        let task_label = Some(final_title.clone());

        let summary = sessions
            .entry(resolved_id.clone())
            .or_insert_with(|| SessionSummary {
                id: resolved_id.clone(),
                title: final_title.clone(),
                collapsed_headline: Some(final_title.clone()),
                task_label: task_label.clone(),
                source: event.source.clone(),
                workspace: event.session.workspace.clone(),
                cwd: event.session.cwd.clone(),
                state: event.state.clone(),
                summary: event.summary.clone(),
                attention_score: attention_score(&event.state, &event.kind),
                updated_at: now,
                created_at: now,
                last_event_kind: event.kind.clone(),
                progress: event.progress.clone(),
                interaction: event.interaction.clone(),
                review: event.review.clone(),
                usage: artifact.as_ref().and_then(|context| context.usage.clone()),
                identity: artifact
                    .as_ref()
                    .map(|context| context.identity.clone())
                    .unwrap_or_default(),
                peek: artifact
                    .as_ref()
                    .map(|context| context.peek.clone())
                    .unwrap_or_default(),
                overdue_severity: OverdueSeverity::None,
                jump_target: event.jump_target.clone(),
                stuck: StuckInfo::default(),
            });

        let optimistic_response = raw_flag(&event.raw, "optimistic_response");
        let preserve_existing_prompt = !optimistic_response
            && matches!(event.state, SessionState::Running)
            && !interaction_present(&event.interaction)
            && (matches!(
                summary.state,
                SessionState::Blocked | SessionState::WaitingUser
            ) || interaction_present(&summary.interaction));

        summary.title = final_title.clone();
        summary.collapsed_headline = Some(final_title.clone());
        summary.task_label = task_label;
        summary.source = event.source.clone();
        summary.workspace = event.session.workspace.clone();
        summary.cwd = event.session.cwd.clone();
        summary.updated_at = now;
        summary.jump_target = event.jump_target.clone();
        if review_present(&event.review) {
            summary.review = event.review.clone();
        }
        if let Some(context) = artifact.as_ref() {
            if context
                .usage
                .as_ref()
                .map(usage_summary_is_meaningful)
                .unwrap_or(false)
            {
                summary.usage = context.usage.clone();
            }
            if artifact_identity_is_meaningful(&context.identity) {
                summary.identity = context.identity.clone();
            }
            if peek_metadata_is_meaningful(&context.peek) {
                summary.peek = context.peek.clone();
            }
            if context
                .collapsed_headline
                .as_deref()
                .map(|value| !value.trim().is_empty())
                .unwrap_or(false)
            {
                summary.collapsed_headline = context.collapsed_headline.clone();
            } else if summary.collapsed_headline.is_none() {
                summary.collapsed_headline = Some(final_title.clone());
            }
        } else if summary.collapsed_headline.is_none() {
            summary.collapsed_headline = Some(final_title.clone());
        }

        if !preserve_existing_prompt {
            summary.state = event.state.clone();
            summary.summary = event.summary.clone();
            summary.attention_score = attention_score(&event.state, &event.kind);
            summary.last_event_kind = event.kind.clone();
            summary.progress = event.progress.clone();
            summary.interaction = event.interaction.clone();
        }
    }

    persist_event(state, &event, &resolved_id).await?;
    if let Some(summary) = state.sessions.read().await.get(&resolved_id).cloned() {
        if let Err(err) = persist_task_label(state, &summary).await {
            warn!("task label persistence failed: {err:#}");
        }
    }
    Ok(build_snapshot(state).await)
}

async fn set_quiet_mode(
    state: &std::sync::Arc<AppState>,
    enabled: bool,
    suppress_below_attention: Option<u8>,
    reason: Option<String>,
) -> Result<Snapshot> {
    {
        let mut quiet_mode = state.quiet_mode.write().await;
        quiet_mode.enabled = enabled;
        quiet_mode.enabled_at = if enabled { Some(Utc::now()) } else { None };
        if let Some(threshold) = suppress_below_attention {
            quiet_mode.suppress_below_attention = threshold;
        }
        quiet_mode.reason = reason.and_then(|value| {
            let trimmed = value.trim().to_string();
            if trimmed.is_empty() {
                None
            } else {
                Some(trimmed)
            }
        });
    }

    Ok(build_snapshot(state).await)
}

async fn load_recent_events(
    state: &std::sync::Arc<AppState>,
    limit: usize,
) -> Result<Vec<AgentEvent>> {
    let rows = {
        let db = state.db.lock().expect("db mutex poisoned");
        let mut stmt = db.prepare(
            "SELECT payload FROM events
             ORDER BY created_at DESC, event_id DESC
             LIMIT ?1",
        )?;
        let mut rows = Vec::new();
        let event_rows = stmt.query_map(params![limit as i64], |row| row.get::<_, String>(0))?;
        for row in event_rows {
            let payload = match row {
                Ok(payload) => payload,
                Err(err) => {
                    warn!("skipping unreadable event row: {err}");
                    continue;
                }
            };

            match serde_json::from_str::<AgentEvent>(&payload) {
                Ok(event) => rows.push(event),
                Err(err) => warn!("skipping malformed event payload: {err}"),
            }
        }
        rows
    };

    Ok(rows)
}

fn build_replay_timeline(events: &[AgentEvent]) -> Vec<ReplayTimelineEntry> {
    events
        .iter()
        .filter(|event| is_timeline_event(&event.kind))
        .take(REPLAY_TIMELINE_LIMIT)
        .map(|event| {
            let title = event
                .session
                .task_label
                .clone()
                .filter(|value| !value.trim().is_empty())
                .or_else(|| {
                    event
                        .session
                        .title
                        .clone()
                        .filter(|value| !value.trim().is_empty())
                })
                .unwrap_or_else(|| format!("{} session", stringify_source(&event.source)));

            ReplayTimelineEntry {
                event_id: event.event_id.clone(),
                session_id: event.session.id.clone(),
                ts: event.ts.clone(),
                source: event.source.clone(),
                title,
                task_label: event
                    .session
                    .task_label
                    .clone()
                    .filter(|value| !value.trim().is_empty()),
                kind: event.kind.clone(),
                state: event.state.clone(),
                summary: event.summary.clone(),
                workspace: event.session.workspace.clone(),
                cwd: event.session.cwd.clone(),
                attention_score: attention_score(&event.state, &event.kind),
            }
        })
        .collect()
}

fn is_timeline_event(kind: &EventKind) -> bool {
    !matches!(kind, EventKind::SessionHeartbeat)
}

fn derive_stuck_info(
    summary: &SessionSummary,
    recent_events: &[&AgentEvent],
    now: DateTime<Utc>,
) -> StuckInfo {
    let last_progress_at = recent_events
        .iter()
        .copied()
        .find(|event| !matches!(event.kind, EventKind::SessionHeartbeat))
        .map(|event| event.ts.clone())
        .or(Some(summary.updated_at.clone()));

    let stalled_for_seconds = last_progress_at
        .map(|ts| (now - ts).num_seconds().max(0))
        .unwrap_or(0);

    let failure_count = recent_events
        .iter()
        .copied()
        .filter(|event| matches!(event.kind, EventKind::Failed))
        .count();

    let state_threshold = match summary.state {
        SessionState::Blocked => Some((20 * 60, "approval_wait")),
        SessionState::WaitingUser => Some((10 * 60, "user_wait")),
        SessionState::Running => Some((15 * 60, "no_progress")),
        SessionState::Stale => Some((5 * 60, "stale_session")),
        SessionState::Completed | SessionState::Failed => None,
    };

    if summary.state == SessionState::Running && failure_count >= 2 && stalled_for_seconds >= 5 * 60
    {
        return StuckInfo {
            is_stuck: true,
            score: 90,
            reason: Some(format!(
                "repeated failures ({} failures) without new progress",
                failure_count
            )),
            stalled_for_seconds: Some(stalled_for_seconds),
            last_progress_at,
            signal: Some("repeated_failures".to_string()),
        };
    }

    if let Some((threshold, signal)) = state_threshold {
        if stalled_for_seconds >= threshold {
            let score = match summary.state {
                SessionState::Blocked => 95,
                SessionState::WaitingUser => 92,
                SessionState::Running => 82,
                SessionState::Stale => 75,
                SessionState::Completed | SessionState::Failed => 0,
            };
            let reason = match summary.state {
                SessionState::Blocked => "waiting too long for approval".to_string(),
                SessionState::WaitingUser => "waiting too long for user input".to_string(),
                SessionState::Running => "no meaningful progress for too long".to_string(),
                SessionState::Stale => "session appears stale".to_string(),
                SessionState::Completed | SessionState::Failed => String::new(),
            };
            return StuckInfo {
                is_stuck: true,
                score,
                reason: Some(reason),
                stalled_for_seconds: Some(stalled_for_seconds),
                last_progress_at,
                signal: Some(signal.to_string()),
            };
        }
    }

    StuckInfo {
        is_stuck: false,
        score: 0,
        reason: None,
        stalled_for_seconds: Some(stalled_for_seconds),
        last_progress_at,
        signal: None,
    }
}

fn derive_overdue_severity(
    summary: &SessionSummary,
    recent_events: &[&AgentEvent],
    now: DateTime<Utc>,
) -> OverdueSeverity {
    let requires_attention = matches!(
        summary.state,
        SessionState::Blocked | SessionState::WaitingUser
    ) || interaction_present(&summary.interaction)
        || review_present(&summary.review);

    if !requires_attention {
        return OverdueSeverity::None;
    }

    let last_progress_at = recent_events
        .iter()
        .copied()
        .find(|event| !matches!(event.kind, EventKind::SessionHeartbeat))
        .map(|event| event.ts.clone())
        .unwrap_or_else(|| summary.updated_at.clone());

    let stalled_for_seconds = (now - last_progress_at).num_seconds().max(0);
    if stalled_for_seconds >= 75 {
        OverdueSeverity::Critical
    } else if stalled_for_seconds >= 30 {
        OverdueSeverity::Warning
    } else {
        OverdueSeverity::None
    }
}

async fn build_usage_snapshot(
    state: &std::sync::Arc<AppState>,
    sessions: &[SessionSummary],
) -> Vec<UsageSummary> {
    let mut output: HashMap<String, UsageSummary> = HashMap::new();
    let mut baseline = state.usage_baseline.write().await;

    for session in sessions {
        let usage = match session.usage.clone() {
            Some(usage) => usage,
            None => continue,
        };
        let source_key = stringify_source(&usage.source).to_string();
        let current_tokens = usage.session_tokens.unwrap_or(0);
        let baseline_key = usage
            .source_session_id
            .clone()
            .unwrap_or_else(|| format!("{source_key}::{}", session.id));
        let starting_tokens = baseline.entry(baseline_key).or_insert(current_tokens);
        let delta_tokens = current_tokens.saturating_sub(*starting_tokens);
        let entry = output.entry(source_key).or_insert_with(|| usage.clone());
        entry.mode = usage.mode.clone();
        entry.five_hour = usage.five_hour.clone().or_else(|| entry.five_hour.clone());
        entry.seven_day = usage.seven_day.clone().or_else(|| entry.seven_day.clone());
        entry.session_tokens = Some(entry.session_tokens.unwrap_or(0).saturating_add(delta_tokens));
        entry.source_session_id = usage.source_session_id.clone().or(entry.source_session_id.clone());
    }

    let mut usage = output.into_values().collect::<Vec<_>>();
    usage.sort_by(|left, right| stringify_source(&left.source).cmp(stringify_source(&right.source)));
    usage
}

fn resolve_session_id(sessions: &HashMap<String, SessionSummary>, event: &AgentEvent) -> String {
    if sessions.contains_key(&event.session.id) {
        return event.session.id.clone();
    }

    if let Some(event_tty) = event.jump_target.tty.as_deref() {
        let mut matching: Vec<&SessionSummary> = sessions
            .values()
            .filter(|summary| {
                summary.source == event.source
                    && summary.jump_target.tty.as_deref() == Some(event_tty)
            })
            .collect();
        matching.sort_by(|left, right| right.updated_at.cmp(&left.updated_at));
        if let Some(summary) = matching.first() {
            return summary.id.clone();
        }
    }

    if let Some(event_pid) = event.jump_target.pid {
        let mut matching: Vec<&SessionSummary> = sessions
            .values()
            .filter(|summary| {
                summary.source == event.source && summary.jump_target.pid == Some(event_pid)
            })
            .collect();
        matching.sort_by(|left, right| right.updated_at.cmp(&left.updated_at));
        if let Some(summary) = matching.first() {
            return summary.id.clone();
        }
    }

    let has_jump_identity = event.jump_target.tty.is_some() || event.jump_target.pid.is_some();
    let event_cwd = event
        .session
        .cwd
        .as_deref()
        .or(event.session.workspace.as_deref());
    if !has_jump_identity {
        if let Some(cwd) = event_cwd {
            let mut matching: Vec<&SessionSummary> = sessions
                .values()
                .filter(|summary| {
                    summary.source == event.source
                        && summary.cwd.as_deref().or(summary.workspace.as_deref()) == Some(cwd)
                })
                .collect();
            matching.sort_by(|left, right| right.updated_at.cmp(&left.updated_at));
            if matching.len() == 1 {
                if let Some(summary) = matching.first() {
                    return summary.id.clone();
                }
            }
        }
    }

    event.session.id.clone()
}

fn detect_agent_source(cmdline: &str) -> Option<AgentSource> {
    let lower = cmdline.to_ascii_lowercase();
    if lower.contains("vibeisland.py jump") || lower.contains("tools.vibeisland jump") {
        return None;
    }
    let token = cmdline.split_whitespace().next().unwrap_or("");
    let token_lower = token.to_ascii_lowercase();

    if token_lower.contains("claude") || lower.contains(" claude") || lower.starts_with("claude ") {
        return Some(AgentSource::Claude);
    }
    if token_lower.contains("codex") || lower.contains(" codex") || lower.starts_with("codex ") {
        return Some(AgentSource::Codex);
    }
    None
}

fn detect_terminal_name(cmdline: &str) -> Option<String> {
    let candidates = [
        "konsole",
        "kitty",
        "wezterm",
        "ghostty",
        "alacritty",
        "code-insiders",
        "code",
        "cursor",
        "vscode",
        "gnome-terminal",
        "xfce4-terminal",
        "tilix",
        "xterm",
    ];

    for token in cmdline.split_whitespace() {
        let normalized = token.trim_matches('"').to_ascii_lowercase();
        let basename = Path::new(&normalized)
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or(&normalized);

        if let Some(name) = candidates.iter().find(|name| **name == basename) {
            return Some((*name).to_string());
        }
    }

    None
}

fn agent_slug(source: &AgentSource) -> &'static str {
    match source {
        AgentSource::Claude => "claude",
        AgentSource::Codex => "codex",
        AgentSource::Gemini => "gemini",
        AgentSource::Unknown => "agent",
    }
}

fn discover_live_sessions(state: &std::sync::Arc<AppState>) -> Result<Vec<SessionSummary>> {
    let mut live = Vec::new();
    for entry in fs::read_dir("/proc")? {
        let entry = match entry {
            Ok(entry) => entry,
            Err(_) => continue,
        };
        let file_name = entry.file_name();
        let pid: u32 = match file_name.to_string_lossy().parse() {
            Ok(pid) => pid,
            Err(_) => continue,
        };

        if let Some(summary) = discover_process_session(state, pid)? {
            live.push(summary);
        }
    }
    Ok(live)
}

fn discover_process_session(
    state: &std::sync::Arc<AppState>,
    pid: u32,
) -> Result<Option<SessionSummary>> {
    let proc_path = PathBuf::from("/proc").join(pid.to_string());
    let cmdline = match fs::read(proc_path.join("cmdline")) {
        Ok(bytes) => bytes,
        Err(_) => return Ok(None),
    };
    if cmdline.is_empty() {
        return Ok(None);
    }

    let cmdline = String::from_utf8_lossy(&cmdline)
        .replace('\0', " ")
        .trim()
        .to_string();

    let source = match detect_agent_source(&cmdline) {
        Some(source) => source,
        None => return Ok(None),
    };

    let cwd = fs::read_link(proc_path.join("cwd"))
        .ok()
        .map(|path| path.to_string_lossy().to_string());
    let tty = fs::read_link(proc_path.join("fd/0"))
        .ok()
        .map(|path| path.to_string_lossy().to_string());
    if tty
        .as_deref()
        .map(|value| !value.starts_with("/dev/") || value.contains("(deleted)"))
        .unwrap_or(true)
    {
        return Ok(None);
    }
    let (terminal, terminal_host_pid) = discover_terminal_host(pid, 8);
    let cwd_display = cwd
        .as_deref()
        .and_then(|path| Path::new(path).file_name())
        .map(|name| name.to_string_lossy().to_string())
        .unwrap_or_else(|| "workspace".to_string());
    let tty_value = tty.clone().unwrap_or_default();
    let live_session_id = format!("live::{}::{}", agent_slug(&source), pid);
    let cached = load_task_label(state, &source, &tty_value);
    let artifact = match source {
        AgentSource::Codex => cwd
            .as_deref()
            .map(Path::new)
            .and_then(load_codex_thread_context),
        AgentSource::Claude => load_claude_artifact_context(pid),
        _ => None,
    };
    let cached_label = cached
        .as_ref()
        .and_then(|record| {
            preferred_label(&record.title, record.task_label.as_deref())
                .or_else(|| record.collapsed_headline.clone())
        })
        .or_else(|| load_recent_event_task_label(state, &source, Some(&live_session_id), &tty_value));
    let artifact_label = artifact
        .as_ref()
        .and_then(|context| context.title.clone())
        .filter(|value| !value.trim().is_empty());
    let title = artifact_label
        .clone()
        .or_else(|| cached_label.clone())
        .unwrap_or_else(|| format!("{} @ {}", stringify_source(&source), cwd_display));
    let now = Utc::now();
    let host_label = terminal
        .as_deref()
        .map(|term| format!(" via {}", term))
        .unwrap_or_default();
    let jump_target = JumpTarget {
        terminal,
        tty,
        pid: terminal_host_pid.or(Some(pid)),
        tmux_session: None,
        tmux_window: None,
        tmux_pane: None,
    };
    let summary_text = cached
        .as_ref()
        .map(|record| {
            if record.summary.trim().is_empty() {
                format!(
                    "Detected live {} process{}",
                    summary_source(&source),
                    host_label
                )
            } else {
                record.summary.clone()
            }
        })
        .unwrap_or_else(|| {
            format!(
                "Detected live {} process{}",
                summary_source(&source),
                host_label
            )
        });
    let task_label = artifact_label
        .clone()
        .or_else(|| cached_label.clone())
        .or_else(|| Some(title.clone()))
        .filter(|value| !is_low_signal_task_label(value))
        .or_else(|| Some(title.clone()));
    let collapsed_headline = artifact
        .as_ref()
        .and_then(|context| context.collapsed_headline.clone())
        .or_else(|| task_label.clone());
    let preview_lines = artifact
        .as_ref()
        .map(|context| context.preview_lines.clone())
        .unwrap_or_else(|| {
            dedupe_lines(
                vec![
                    title.clone(),
                    summary_text.clone(),
                    cached
                        .as_ref()
                        .map(|record| record.summary.clone())
                        .unwrap_or_default(),
                ],
                4,
            )
        });
    let usage = artifact.as_ref().and_then(|context| context.usage.clone()).or_else(|| {
        Some(UsageSummary {
            source: source.clone(),
            mode: if matches!(source, AgentSource::Codex) {
                load_codex_auth_mode()
            } else if std::env::var("ANTHROPIC_API_KEY").ok().map(|value| !value.trim().is_empty()).unwrap_or(false) {
                UsageBillingMode::ApiKey
            } else {
                UsageBillingMode::Unknown
            },
            five_hour: None,
            seven_day: None,
            session_tokens: None,
            source_session_id: None,
        })
    });
    let identity = artifact
        .as_ref()
        .map(|context| context.identity.clone())
        .unwrap_or_default();
    let peek = artifact
        .as_ref()
        .map(|context| context.peek.clone())
        .unwrap_or_else(|| PeekMetadata {
            supported: true,
            source_session_id: None,
            backend_session_id: None,
            transcript_path: None,
            preview_lines: preview_lines.clone(),
            input_hint: Some("Type a follow-up and press send".to_string()),
        });
    let task_label = task_label
        .as_ref()
        .map(|value| value.to_string());
    let review = cached.map(|record| record.review).unwrap_or_default();

    let summary = SessionSummary {
        id: live_session_id,
        title,
        collapsed_headline,
        task_label,
        source,
        workspace: cwd.clone(),
        cwd,
        state: SessionState::Running,
        summary: summary_text,
        attention_score: attention_score(&SessionState::Running, &EventKind::SessionHeartbeat),
        updated_at: now,
        created_at: now,
        last_event_kind: EventKind::SessionHeartbeat,
        progress: ProgressInfo::default(),
        interaction: vibeisland_common::Interaction::default(),
        review,
        usage,
        identity,
        peek,
        overdue_severity: OverdueSeverity::None,
        jump_target,
        stuck: StuckInfo::default(),
    };
    Ok(Some(summary))
}

fn discover_terminal_host(pid: u32, max_depth: usize) -> (Option<String>, Option<u32>) {
    let mut current = pid;
    for _ in 0..max_depth {
        let proc_path = PathBuf::from("/proc").join(current.to_string());
        let cmdline = match fs::read(proc_path.join("cmdline")) {
            Ok(bytes) => bytes,
            Err(_) => break,
        };
        if cmdline.is_empty() {
            break;
        }
        let cmdline = String::from_utf8_lossy(&cmdline)
            .replace('\0', " ")
            .trim()
            .to_string();
        if let Some(terminal) = detect_terminal_name(&cmdline) {
            return (Some(terminal), Some(current));
        }

        let stat = match fs::read_to_string(proc_path.join("stat")) {
            Ok(text) => text,
            Err(_) => break,
        };
        let ppid = stat
            .split_whitespace()
            .nth(3)
            .and_then(|value| value.parse::<u32>().ok());
        match ppid {
            Some(next) if next > 0 && next != current => current = next,
            _ => break,
        }
    }

    (None, None)
}

fn summary_source(source: &AgentSource) -> &'static str {
    match source {
        AgentSource::Claude => "Claude",
        AgentSource::Codex => "Codex",
        AgentSource::Gemini => "Gemini",
        AgentSource::Unknown => "Agent",
    }
}

async fn persist_event(
    state: &std::sync::Arc<AppState>,
    event: &AgentEvent,
    resolved_id: &str,
) -> Result<()> {
    let summary = {
        let sessions = state.sessions.read().await;
        sessions
            .get(resolved_id)
            .cloned()
            .context("missing session after event update")?
    };

    let mut stored_event = event.clone();
    stored_event.session.id = resolved_id.to_string();
    let event_payload = serde_json::to_string(&stored_event)?;
    let summary_payload = serde_json::to_string(&summary)?;

    let db = state.db.lock().expect("db mutex poisoned");
    db.execute(
        "INSERT OR REPLACE INTO events (event_id, session_id, payload, created_at)
         VALUES (?1, ?2, ?3, ?4)",
        params![
            event.event_id,
            resolved_id,
            event_payload,
            event.ts.to_rfc3339(),
        ],
    )?;
    db.execute(
        "INSERT OR REPLACE INTO sessions (session_id, payload, updated_at)
         VALUES (?1, ?2, ?3)",
        params![summary.id, summary_payload, summary.updated_at.to_rfc3339()],
    )?;

    Ok(())
}

fn stringify_source(source: &vibeisland_common::AgentSource) -> &'static str {
    match source {
        vibeisland_common::AgentSource::Claude => "Claude",
        vibeisland_common::AgentSource::Codex => "Codex",
        vibeisland_common::AgentSource::Gemini => "Gemini",
        vibeisland_common::AgentSource::Unknown => "Agent",
    }
}
