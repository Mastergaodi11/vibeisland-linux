use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum AgentSource {
    Claude,
    Codex,
    Gemini,
    Unknown,
}

impl Default for AgentSource {
    fn default() -> Self {
        Self::Unknown
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum SessionState {
    Running,
    Blocked,
    WaitingUser,
    Completed,
    Failed,
    Stale,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum OverdueSeverity {
    None,
    Warning,
    Critical,
}

impl Default for OverdueSeverity {
    fn default() -> Self {
        Self::None
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum EventKind {
    SessionStarted,
    SessionHeartbeat,
    SessionUpdated,
    PlanUpdated,
    NeedsApproval,
    AskUser,
    Completed,
    Failed,
    Cancelled,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum UsageBillingMode {
    Unknown,
    Subscription,
    ApiKey,
}

impl Default for UsageBillingMode {
    fn default() -> Self {
        Self::Unknown
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct SessionRef {
    pub id: String,
    pub run_id: Option<String>,
    pub title: Option<String>,
    pub task_label: Option<String>,
    pub workspace: Option<String>,
    pub cwd: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ArtifactIdentity {
    pub source_session_id: Option<String>,
    pub backend_session_id: Option<String>,
    pub artifact_kind: Option<String>,
    pub artifact_path: Option<String>,
    pub title_source: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct PeekMetadata {
    pub supported: bool,
    pub source_session_id: Option<String>,
    pub backend_session_id: Option<String>,
    pub transcript_path: Option<String>,
    #[serde(default)]
    pub preview_lines: Vec<String>,
    pub input_hint: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct UsageWindow {
    pub window: Option<String>,
    pub remaining_percent: Option<u8>,
    pub used_percent: Option<u8>,
    pub remaining_tokens: Option<u64>,
    pub used_tokens: Option<u64>,
    pub limit_tokens: Option<u64>,
    pub reset_at: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct UsageSummary {
    pub source: AgentSource,
    pub mode: UsageBillingMode,
    #[serde(default)]
    pub five_hour: Option<UsageWindow>,
    #[serde(default)]
    pub seven_day: Option<UsageWindow>,
    pub session_tokens: Option<u64>,
    pub source_session_id: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ProgressInfo {
    pub phase: Option<String>,
    pub pct: Option<f32>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct StuckInfo {
    pub is_stuck: bool,
    pub score: u8,
    pub reason: Option<String>,
    pub stalled_for_seconds: Option<i64>,
    pub last_progress_at: Option<DateTime<Utc>>,
    pub signal: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct Interaction {
    pub approval_type: Option<String>,
    pub question: Option<String>,
    #[serde(default)]
    pub choices: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ReviewInfo {
    pub headline: Option<String>,
    pub command: Option<String>,
    pub detail: Option<String>,
    pub reason: Option<String>,
    pub risk: Option<String>,
    pub scope: Option<String>,
    pub workspace_hint: Option<String>,
    pub tool_name: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct JumpTarget {
    pub terminal: Option<String>,
    pub tty: Option<String>,
    pub pid: Option<u32>,
    pub tmux_session: Option<String>,
    pub tmux_window: Option<String>,
    pub tmux_pane: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentEvent {
    pub schema: String,
    pub event_id: String,
    pub ts: DateTime<Utc>,
    pub source: AgentSource,
    pub adapter: String,
    pub session: SessionRef,
    pub kind: EventKind,
    pub state: SessionState,
    pub summary: String,
    #[serde(default)]
    pub progress: ProgressInfo,
    #[serde(default)]
    pub interaction: Interaction,
    #[serde(default)]
    pub review: ReviewInfo,
    #[serde(default)]
    pub jump_target: JumpTarget,
    #[serde(default)]
    pub raw: serde_json::Value,
}

impl AgentEvent {
    pub fn demo(
        session_id: &str,
        source: AgentSource,
        kind: EventKind,
        state: SessionState,
        title: &str,
        summary: &str,
    ) -> Self {
        Self {
            schema: "v1".to_string(),
            event_id: uuid::Uuid::new_v4().to_string(),
            ts: Utc::now(),
            source,
            adapter: "demo".to_string(),
            session: SessionRef {
                id: session_id.to_string(),
                run_id: None,
                title: Some(title.to_string()),
                task_label: Some(title.to_string()),
                workspace: None,
                cwd: None,
            },
            kind,
            state,
            summary: summary.to_string(),
            progress: ProgressInfo::default(),
            interaction: Interaction::default(),
            review: ReviewInfo::default(),
            jump_target: JumpTarget::default(),
            raw: serde_json::json!({}),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionSummary {
    pub id: String,
    pub title: String,
    #[serde(default)]
    pub collapsed_headline: Option<String>,
    #[serde(default)]
    pub task_label: Option<String>,
    pub source: AgentSource,
    #[serde(default)]
    pub workspace: Option<String>,
    #[serde(default)]
    pub cwd: Option<String>,
    pub state: SessionState,
    pub summary: String,
    pub attention_score: u8,
    pub updated_at: DateTime<Utc>,
    pub created_at: DateTime<Utc>,
    pub last_event_kind: EventKind,
    pub progress: ProgressInfo,
    pub interaction: Interaction,
    #[serde(default)]
    pub review: ReviewInfo,
    #[serde(default)]
    pub usage: Option<UsageSummary>,
    #[serde(default)]
    pub identity: ArtifactIdentity,
    #[serde(default)]
    pub peek: PeekMetadata,
    #[serde(default)]
    pub overdue_severity: OverdueSeverity,
    pub jump_target: JumpTarget,
    #[serde(default)]
    pub stuck: StuckInfo,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReplayTimelineEntry {
    pub event_id: String,
    pub session_id: String,
    pub ts: DateTime<Utc>,
    pub source: AgentSource,
    pub title: String,
    #[serde(default)]
    pub task_label: Option<String>,
    pub kind: EventKind,
    pub state: SessionState,
    pub summary: String,
    #[serde(default)]
    pub workspace: Option<String>,
    #[serde(default)]
    pub cwd: Option<String>,
    pub attention_score: u8,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QuietModeState {
    pub enabled: bool,
    pub enabled_at: Option<DateTime<Utc>>,
    pub suppress_below_attention: u8,
    pub reason: Option<String>,
}

impl Default for QuietModeState {
    fn default() -> Self {
        Self {
            enabled: false,
            enabled_at: None,
            suppress_below_attention: 80,
            reason: None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Snapshot {
    pub generated_at: DateTime<Utc>,
    pub active_count: usize,
    pub blocked_count: usize,
    #[serde(default)]
    pub usage: Vec<UsageSummary>,
    #[serde(default)]
    pub timeline: Vec<ReplayTimelineEntry>,
    #[serde(default)]
    pub quiet_mode: QuietModeState,
    pub sessions: Vec<SessionSummary>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ClientRequest {
    Publish {
        event: AgentEvent,
    },
    Snapshot,
    Subscribe,
    Clear,
    Ping,
    SetQuietMode {
        enabled: bool,
        #[serde(default)]
        suppress_below_attention: Option<u8>,
        #[serde(default)]
        reason: Option<String>,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ServerResponse {
    Ack { ok: bool },
    Pong,
    Snapshot { snapshot: Snapshot },
    Error { message: String },
}

pub fn attention_score(state: &SessionState, kind: &EventKind) -> u8 {
    match (state, kind) {
        (SessionState::Blocked, _) => 100,
        (SessionState::WaitingUser, _) => 90,
        (SessionState::Failed, _) => 80,
        (SessionState::Completed, _) => 55,
        (_, EventKind::PlanUpdated) => 35,
        _ => 20,
    }
}
