import QtQuick 2.15
import QtQml 2.15
import QtQuick.Window 2.15

Window {
    id: root
    visible: true
    width: 316
    height: 58
    minimumWidth: backend.expanded ? root.expandedMinWidth : 284
    minimumHeight: backend.expanded ? root.expandedMinHeight : root.collapsedHeight
    maximumWidth: Math.max(minimumWidth, Screen.width - 16)
    maximumHeight: Math.max(minimumHeight, Screen.height - 16)
    color: "transparent"
    title: "Vibe Island"
    flags: Qt.FramelessWindowHint
           | Qt.Tool
           | (backend.pinned ? Qt.WindowStaysOnTopHint : 0)

    property int collapsedHeight: 58
    property int expandedMinWidth: 600
    property int expandedMinHeight: 420
    property bool geometryReady: false
    property bool dragging: false
    property bool systemMoveTriggered: false
    property bool resizingWindow: false
    property string primaryFont: "Noto Sans"
    property string monoFont: "Monospace"
    property bool promptNeedsTextReply: false
    property string promptReplyDraft: ""
    property int selectedPromptChoice: 0
    property string promptReplyTargetId: ""
    property var responseStates: ({})
    property string peekSessionId: ""
    property var peekDrafts: ({})
    property var peekLineOverrides: ({})
    property string activePeekInputSessionId: ""
    property string typingPeekSessionId: ""
    property bool sessionSyncPending: false
    property bool settingsOpen: false
    property string telegramDraftToken: ""
    property string telegramDraftChatId: ""
    property bool telegramDraftEnabled: false
    signal requestPeekInputFocus(string sessionId)
    property real sessionScrollY: 0
    property bool restoringSessionScroll: false
    property bool modelUpdating: false
    property var sessionModelCache: []
    property color surfaceBase: "#020304"
    property color surfacePanel: "#06080b"
    property color surfaceCard: "#090c10"
    property color surfaceCardAlt: "#0c1014"
    property color borderSoft: "#ffffff08"
    property color borderStrong: "#ffffff10"
    property color inkStrong: "#eef2f6"
    property color inkMuted: "#8f98a2"
    property color inkDim: "#66707a"
    property color graphiteRaised: "#13171b"
    property color graphitePanel: "#101419"
    property color graphitePanelAlt: "#0d1115"
    property color graphiteInset: "#080b0e"
    property color graphiteBorder: "#232a31"
    property color graphiteBorderStrong: "#313a44"
    property color graphiteMuted: "#97a2ad"
    property color graphiteSubtle: "#76818d"
    property color accentCyan: "#7ea6b5"
    property color accentRose: "#bb7480"
    property color accentGreen: "#63a678"
    property color accentAmber: "#977654"
    property color accentOrange: "#aa724f"
    property color accentSlate: "#8d97a2"
    property bool headerCompact: backend.expanded && width < 760
    property bool headerTight: backend.expanded && width < 700
    property bool headerUltraCompact: backend.expanded && width < 640

    function centerIfNeeded() {
        if (backend.windowX >= 0) {
            x = backend.windowX
            y = backend.windowY
        } else {
            x = Math.round((Screen.width - width) / 2)
            y = 18
        }
    }

    function syncWindowGeometry(recenter) {
        var targetWidth = backend.expanded ? backend.windowWidth : backend.collapsedWidth
        var targetHeight = backend.expanded ? backend.windowHeight : root.collapsedHeight
        if (Math.round(root.width) !== Math.round(targetWidth)) {
            root.width = targetWidth
        }
        if (Math.round(root.height) !== Math.round(targetHeight)) {
            root.height = targetHeight
        }
        if (recenter === true) {
            root.centerIfNeeded()
        }
    }

    function headerMetric(baseValue, compactValue, tightValue) {
        if (root.headerUltraCompact) {
            return tightValue
        }
        if (root.headerCompact) {
            return compactValue
        }
        return baseValue
    }

    function activePillText() {
        return root.headerUltraCompact
                ? backend.activeCount + " ACT"
                : backend.activeCount + " ACTIVE"
    }

    function urgentPillText() {
        return root.headerUltraCompact
                ? backend.blockedCount + " URG"
                : backend.blockedCount + " URGENT"
    }

    function livePillText() {
        if (!backend.connected) {
            return root.headerCompact ? "DEMO" : "DEMO"
        }
        return root.headerUltraCompact ? "LIVE" : "LIVE"
    }

    function quietPillText() {
        return root.headerUltraCompact ? "QT" : "QUIET"
    }

    function schedulePersist() {
        if (geometryReady) {
            persistTimer.restart()
        }
    }

    function rememberSessionScroll(value) {
        if (restoringSessionScroll || modelUpdating) {
            return
        }
        sessionScrollY = Math.max(0, value)
    }

    function sessionItems() {
        if (root.sessionModelCache === undefined || root.sessionModelCache === null) {
            return []
        }
        return root.sessionModelCache
    }

    function syncSessionModel(preserveCurrentScroll) {
        if (preserveCurrentScroll === undefined) {
            preserveCurrentScroll = true
        }
        if (preserveCurrentScroll && sessionList !== null && sessionList !== undefined && !restoringSessionScroll) {
            sessionScrollY = Math.max(0, sessionList.contentY)
        }
        modelUpdating = true
        sessionModelCache = backend.sessions
        restoreSessionScroll()
    }

    function applyLatestSessionModel(preserveCurrentScroll) {
        root.syncSessionModel(preserveCurrentScroll)
        root.clearSettledResponseStates()
        if (root.promptReplyTargetId !== "" && !root.hasResponsiveSession(root.promptReplyTargetId)) {
            root.resetPromptReplyState()
        }
    }

    function flushDeferredSessionSync() {
        if (!sessionSyncPending || typingPeekSessionId !== "" || peekSessionId !== "") {
            return
        }
        sessionSyncPending = false
        applyLatestSessionModel(true)
    }

    function sanitizePeekText(text) {
        var normalized = text === undefined || text === null ? "" : String(text)
        normalized = normalized.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, "")
        normalized = normalized.replace(/\r?\n+/g, " ")
        normalized = normalized.replace(/\s+/g, " ").trim()
        return normalized
    }

    function restoreSessionScroll() {
        if (sessionList === null || sessionList === undefined) {
            modelUpdating = false
            return
        }
        restoringSessionScroll = true
        Qt.callLater(function() {
            var maxY = Math.max(0, sessionList.contentHeight - sessionList.height)
            sessionList.contentY = Math.min(root.sessionScrollY, maxY)
            Qt.callLater(function() {
                restoringSessionScroll = false
                modelUpdating = false
            })
        })
    }

    function isUrgent(stateText, attention) {
        return stateText === "Blocked" || stateText === "Waiting User" || attention >= 90
    }

    function accentFor(stateText, attention) {
        if (stateText === "Blocked" || stateText === "Waiting User" || attention >= 90) {
            return root.accentRose
        }
        if (stateText === "Completed") {
            return root.accentGreen
        }
        if (stateText === "Failed") {
            return root.accentAmber
        }
        return root.accentCyan
    }

    function statePlate(stateText, attention) {
        if (stateText === "Blocked" || stateText === "Waiting User" || attention >= 90) {
            return "#181017"
        }
        if (stateText === "Completed") {
            return "#0f1614"
        }
        if (stateText === "Failed") {
            return "#141210"
        }
        return "#0f141a"
    }

    function subtitleText() {
        if (backend.quietMode) {
            return "QUIET MODE. NOISE FILTERED."
        }
        if (backend.blockedCount > 0) {
            return "APPROVALS READY. JUMP BACK NOW."
        }
        if (backend.hasPromptSession) {
            return "REPLY FROM THE ISLAND."
        }
        if (backend.activeCount > 0) {
            return "EVERY AGENT. ONE GLANCE."
        }
        return "WAITING AT THE NOTCH."
    }

    function allSessionsSleeping() {
        var items = sessionItems()
        if (items.length === 0) {
            return false
        }
        if (backend.blockedCount > 0 || backend.hasPromptSession) {
            return false
        }
        for (var i = 0; i < items.length; ++i) {
            var session = items[i]
            if (session === undefined || session === null) {
                continue
            }
            var stateText = safeText(session.state)
            var ageSeconds = Number(session.ageSeconds)
            var quietLongEnough = ageSeconds >= 720 || ageSeconds < 0
            if (session.responseUrgency === "critical" || session.responseUrgency === "warning") {
                return false
            }
            if (stateText === "Blocked" || stateText === "Waiting User") {
                return false
            }
            if (stateText === "Completed" || stateText === "Failed" || session.stale) {
                continue
            }
            if ((stateText === "Running" || session.stuck) && quietLongEnough) {
                continue
            }
            return false
        }
        return true
    }

    function expandedCapsuleTitle() {
        if (backend.hasPromptSession) {
            var questionText = promptValue("question")
            if (questionText !== "") {
                return questionText
            }
            var summaryText = promptValue("summary")
            if (summaryText !== "") {
                return summaryText
            }
            return "Approval needed"
        }
        if (allSessionsSleeping()) {
            return "Sleeping"
        }
        var session = collapsedSession()
        if (session !== null) {
            return sessionDisplayTitle(session)
        }
        return safeText(backend.headline)
    }

    function collapsedAccent() {
        if (allSessionsSleeping()) {
            return root.accentGreen
        }
        var session = collapsedSession()
        if (session === null) {
            return root.accentCyan
        }
        return root.sessionHealthAccent(session)
    }

    function safeText(value) {
        if (value === undefined || value === null) {
            return ""
        }
        return String(value)
    }

    function promptValue(key) {
        if (!backend.hasPromptSession || backend.promptSession === undefined || backend.promptSession === null) {
            return ""
        }
        return safeText(backend.promptSession[key])
    }

    function promptChoices() {
        if (!backend.hasPromptSession || backend.promptSession === undefined || backend.promptSession === null) {
            return []
        }
        var choices = backend.promptSession.choices
        if (choices === undefined || choices === null || choices.length === undefined) {
            return []
        }
        return choices
    }

    function sessionChoices(session) {
        if (session === undefined || session === null) {
            return []
        }
        var choices = session.choices
        if (choices === undefined || choices === null || choices.length === undefined) {
            return []
        }
        return choices
    }

    function sessionVisibleInFocus(session) {
        return session !== undefined && session !== null
    }

    function sessionHealthTag(session) {
        if (session === undefined || session === null) {
            return ""
        }
        if (session.responseUrgency === "critical") {
            return "OVERDUE"
        }
        if (session.responseUrgency === "warning") {
            return "WAITING"
        }
        if (session.healthLabel !== undefined && session.healthLabel !== null && safeText(session.healthLabel) !== "") {
            return safeText(session.healthLabel).toUpperCase()
        }
        if (session.stale) {
            return "STALE"
        }
        if (session.stuck) {
            return "STUCK"
        }
        return safeText(session.state).toUpperCase()
    }

    function sessionHealthDetail(session) {
        if (session === undefined || session === null) {
            return ""
        }
        if (session.healthDetail !== undefined && session.healthDetail !== null) {
            return safeText(session.healthDetail)
        }
        return safeText(session.summary)
    }

    function sessionHealthAccent(session) {
        if (session === undefined || session === null) {
            return root.accentCyan
        }
        if (session.responseUrgency === "critical") {
            return root.accentRose
        }
        if (session.responseUrgency === "warning") {
            return root.accentOrange
        }
        if (session.state === "Blocked" || session.state === "Waiting User" || session.attention >= 90) {
            return root.accentRose
        }
        if (session.stale) {
            return root.accentAmber
        }
        if (session.stuck) {
            return root.accentAmber
        }
        if (session.state === "Completed") {
            return root.accentGreen
        }
        if (session.state === "Failed") {
            return root.accentAmber
        }
        return root.accentCyan
    }

    function sessionPlate(session) {
        if (session === undefined || session === null) {
            return root.surfaceCard
        }
        if (session.responseUrgency === "critical") {
            return "#171116"
        }
        if (session.responseUrgency === "warning") {
            return "#18120d"
        }
        if (session.state === "Blocked" || session.state === "Waiting User" || session.attention >= 90) {
            return "#181017"
        }
        if (session.stale) {
            return "#131210"
        }
        if (session.stuck) {
            return "#191410"
        }
        if (session.state === "Completed") {
            return "#0f1614"
        }
        if (session.state === "Failed") {
            return "#141210"
        }
        return root.surfaceCard
    }

    function sessionSummaryTone(session) {
        if (session === undefined || session === null) {
            return root.inkMuted
        }
        if (session.responseUrgency === "critical") {
            return "#f2c9d0"
        }
        if (session.responseUrgency === "warning") {
            return "#e4c7a7"
        }
        if (session.stale || session.stuck) {
            return "#d3b28a"
        }
        if (session.state === "Blocked" || session.state === "Waiting User") {
            return "#e0d3d9"
        }
        if (session.state === "Completed") {
            return "#c8ead7"
        }
        if (session.state === "Failed") {
            return "#d7b28b"
        }
        return root.inkMuted
    }

    function timelineEntries() {
        if (backend.timeline === undefined || backend.timeline === null) {
            return []
        }
        var items = backend.timeline
        if (!backend.replayExpanded) {
            return items.slice(0, 1)
        }
        if (items.length <= 4) {
            return items
        }
        return items.slice(0, 4)
    }

    function collapsedSession() {
        if (allSessionsSleeping()) {
            return null
        }
        var items = sessionItems()
        if (items.length === 0) {
            return null
        }
        return items[0]
    }

    function collapsedStatusText() {
        if (allSessionsSleeping()) {
            return "SLEEPING"
        }
        var session = collapsedSession()
        if (session === null) {
            return backend.connected ? "LIVE" : "IDLE"
        }
        if (session.responseUrgency === "critical") {
            return "RED ALERT"
        }
        if (session.responseUrgency === "warning") {
            return "WAITING"
        }
        if (session.state === "Blocked" || session.state === "Waiting User") {
            return "APPROVAL"
        }
        if (session.state === "Completed") {
            return "DONE"
        }
        return "RUNNING"
    }

    function collapsedProjectTitle() {
        if (allSessionsSleeping()) {
            return "All agents tucked in"
        }
        var session = collapsedSession()
        if (session === null) {
            return "Waiting for agents"
        }
        return sessionDisplayTitle(session)
    }

    function sessionSpriteKind(session) {
        if (session === undefined || session === null) {
            return "island"
        }
        if (session.responseUrgency === "critical") {
            return "alert"
        }
        var provider = sessionProviderKey(session)
        if (provider === "openai") {
            return "codex"
        }
        if (provider === "anthropic") {
            return "claude"
        }
        if (provider === "collab") {
            return "island"
        }
        return "terminal"
    }

    function sessionSpriteAccent(session) {
        if (session === undefined || session === null) {
            return root.accentCyan
        }
        if (session.responseUrgency === "critical") {
            return "#d47b84"
        }
        if (session.responseUrgency === "warning") {
            return "#b18a61"
        }
        var provider = sessionProviderKey(session)
        if (provider === "openai") {
            return "#7fa7be"
        }
        if (provider === "anthropic") {
            return "#b97a6e"
        }
        if (provider === "collab") {
            return "#6fb390"
        }
        return "#8d97a2"
    }

    function sessionProviderKey(session) {
        if (session === undefined || session === null) {
            return "default"
        }
        if (!!session.isCollabSession) {
            return "collab"
        }
        var source = safeText(session.source).toLowerCase()
        if (source.indexOf("codex") !== -1 || source.indexOf("openai") !== -1) {
            return "openai"
        }
        if (source.indexOf("claude") !== -1 || source.indexOf("anthropic") !== -1) {
            return "anthropic"
        }
        return "default"
    }

    function collapsedSpriteKind() {
        if (allSessionsSleeping()) {
            return "sleep"
        }
        var session = collapsedSession()
        if (session === null) {
            return "island"
        }
        return sessionSpriteKind(session)
    }

    function collapsedSpriteAccent() {
        if (allSessionsSleeping()) {
            return "#77c193"
        }
        var session = collapsedSession()
        if (session === null) {
            return "#8fb1c4"
        }
        return sessionSpriteAccent(session)
    }

    function collapsedContextText() {
        if (allSessionsSleeping()) {
            return "No live work right now"
        }
        var session = collapsedSession()
        if (session === null) {
            return "Waiting for agents"
        }
        return root.sessionContextLabel(session)
    }

    function usageValue(sourceKey, field) {
        if (backend.usage === undefined || backend.usage === null) {
            return ""
        }
        var sourceUsage = backend.usage[sourceKey]
        if (sourceUsage === undefined || sourceUsage === null) {
            return ""
        }
        return safeText(sourceUsage[field])
    }

    function usageSessionTokens(sourceKey) {
        if (backend.usage === undefined || backend.usage === null) {
            return 0
        }
        var sourceUsage = backend.usage[sourceKey]
        if (sourceUsage === undefined || sourceUsage === null) {
            return 0
        }
        return Number(sourceUsage.sessionTokens || 0)
    }

    function usageDetail(sourceKey) {
        if (backend.usage === undefined || backend.usage === null) {
            return ""
        }
        var sourceUsage = backend.usage[sourceKey]
        if (sourceUsage === undefined || sourceUsage === null) {
            return ""
        }
        return safeText(sourceUsage.detail)
    }

    function isPeekOpen(sessionId) {
        return safeText(sessionId) !== "" && peekSessionId === safeText(sessionId)
    }

    function peekDraftFor(sessionId) {
        var normalized = safeText(sessionId)
        if (normalized === "" || peekDrafts === undefined || peekDrafts === null) {
            return ""
        }
        var value = peekDrafts[normalized]
        return value === undefined || value === null ? "" : String(value)
    }

    function setPeekDraft(sessionId, text) {
        var normalized = safeText(sessionId)
        if (normalized === "") {
            return
        }
        var current = peekDraftFor(normalized)
        var nextText = text === undefined || text === null ? "" : String(text)
        if (current === nextText) {
            return
        }
        var next = Object.assign({}, peekDrafts || {})
        next[normalized] = nextText
        peekDrafts = next
    }

    function clearPeekDraft(sessionId) {
        var normalized = safeText(sessionId)
        if (normalized === "" || peekDrafts === undefined || peekDrafts === null) {
            return
        }
        var next = Object.assign({}, peekDrafts || {})
        delete next[normalized]
        peekDrafts = next
    }

    function togglePeek(sessionId) {
        var normalized = safeText(sessionId)
        if (normalized === "") {
            return
        }
        if (peekSessionId === normalized) {
            activePeekInputSessionId = ""
            typingPeekSessionId = ""
            peekSessionId = ""
            flushDeferredSessionSync()
            return
        }
        peekSessionId = normalized
        setPeekDraft(normalized, peekDraftFor(normalized))
        backend.refreshPeekPreview(normalized)
    }

    function sessionPeekLines(session) {
        if (session === undefined || session === null) {
            return []
        }
        var sessionId = safeText(session.id)
        if (sessionId !== "" && peekLineOverrides !== undefined && peekLineOverrides !== null) {
            var overrideLines = peekLineOverrides[sessionId]
            if (overrideLines !== undefined && overrideLines !== null && overrideLines.length !== undefined) {
                return overrideLines
            }
        }
        if (session.peekLines === undefined || session.peekLines === null) {
            return []
        }
        return session.peekLines
    }

    function submitPeek(sessionId, typedText) {
        var targetId = safeText(sessionId)
        var draftText = typedText === undefined || typedText === null
                ? peekDraftFor(targetId)
                : String(typedText)
        var targetSession = null
        var items = sessionItems()
        for (var i = 0; i < items.length; i += 1) {
            if (safeText(items[i].id) === targetId) {
                targetSession = items[i]
                break
            }
        }
        if (targetSession !== null && targetSession.peekSendable === false) {
            return
        }
        var text = sanitizePeekText(draftText)
        if (targetId === "" || text === "" || isResponding(targetId)) {
            return
        }
        setPeekDraft(targetId, text)
        beginResponse(targetId, "SENDING")
        activePeekInputSessionId = ""
        typingPeekSessionId = ""
        backend.sendPeekMessage(targetId, text)
    }

    function sessionQuestion(session) {
        if (session === undefined || session === null) {
            return ""
        }
        var question = safeText(session.question)
        if (question !== "") {
            return question
        }
        return safeText(session.summary)
    }

    function sessionDisplayTitle(session) {
        if (session === undefined || session === null) {
            return ""
        }
        var displayTitle = safeText(session.displayTitle)
        if (displayTitle !== "") {
            return displayTitle
        }
        var taskLabel = safeText(session.taskLabel)
        if (taskLabel !== "") {
            return taskLabel
        }
        var title = safeText(session.title)
        if (title !== "") {
            return title
        }
        return sessionQuestion(session)
    }

    function sessionIsCollab(session) {
        if (session === undefined || session === null) {
            return false
        }
        return !!session.isCollabSession
    }

    function sessionCollabActor(session, fallbackActor) {
        if (!sessionIsCollab(session)) {
            return ""
        }
        var actor = safeText(session.collabCurrentActor).toLowerCase()
        if (actor === "") {
            actor = safeText(session.collabNextActor).toLowerCase()
        }
        if (actor === "") {
            actor = safeText(fallbackActor).toLowerCase()
        }
        return actor
    }

    function sessionCollabDisplayName(rawValue) {
        var value = safeText(rawValue).replace(/_/g, " ").trim()
        if (value === "") {
            return ""
        }
        var lower = value.toLowerCase()
        if (lower === "claude") {
            return "Claude"
        }
        if (lower === "codex") {
            return "Codex"
        }
        if (lower === "system") {
            return "System"
        }
        if (lower === "bridge") {
            return "Bridge"
        }
        if (lower === "headless auto") {
            return "Headless Auto"
        }
        if (lower === "headless_auto") {
            return "Headless Auto"
        }
        return value.charAt(0).toUpperCase() + value.slice(1)
    }

    function sessionCollabCurrentActorLabel(session) {
        if (!sessionIsCollab(session)) {
            return ""
        }
        var actor = sessionCollabDisplayName(session.collabCurrentActor)
        if (actor !== "") {
            return actor
        }
        return "Idle"
    }

    function sessionCollabNextActorLabel(session) {
        if (!sessionIsCollab(session)) {
            return ""
        }
        var actor = sessionCollabDisplayName(session.collabNextActor)
        if (actor !== "") {
            return actor
        }
        return "Unspecified"
    }

    function sessionCollabPhaseLabel(session) {
        if (!sessionIsCollab(session)) {
            return ""
        }
        var phase = safeText(session.collabPhase).replace(/_/g, " ").trim()
        if (phase === "") {
            return ""
        }
        return phase.toUpperCase()
    }

    function sessionCollabStrategyLabel(session) {
        if (!sessionIsCollab(session)) {
            return ""
        }
        var strategy = safeText(session.collabStrategy).replace(/_/g, " ").trim()
        if (strategy === "") {
            return "BRIDGE"
        }
        return strategy.toUpperCase()
    }

    function sessionCollabRecentLines(session) {
        if (!sessionIsCollab(session)) {
            return []
        }
        var lines = []
        var summary = safeText(session.summary)
        var ledgerLines = []
        if (summary !== "") {
            lines.push(summary)
        }
        var source = sessionPeekLines(session)
        for (var i = 0; i < source.length; i += 1) {
            var line = safeText(source[i])
            if (line !== "" && line !== summary && ledgerLines.indexOf(line) === -1) {
                ledgerLines.push(line)
            }
        }
        var ledgerLimit = summary !== "" ? 2 : 3
        if (ledgerLines.length > ledgerLimit) {
            ledgerLines = ledgerLines.slice(ledgerLines.length - ledgerLimit)
        }
        for (var j = 0; j < ledgerLines.length; j += 1) {
            lines.push(ledgerLines[j])
        }
        if (lines.length === 0) {
            lines.push("No handoff context yet")
        }
        return lines
    }

    function sessionContextLabel(session) {
        if (session === undefined || session === null) {
            return ""
        }
        if (sessionIsCollab(session)) {
            var collabBits = []
            var phase = sessionCollabPhaseLabel(session)
            var currentActor = sessionCollabDisplayName(session.collabCurrentActor)
            var nextActor = sessionCollabDisplayName(session.collabNextActor)
            var strategy = sessionCollabStrategyLabel(session)
            if (phase !== "") {
                collabBits.push(phase)
            }
            if (currentActor !== "" || nextActor !== "") {
                collabBits.push((currentActor !== "" ? currentActor : "System") + " → " + (nextActor !== "" ? nextActor : "Idle"))
            }
            if (strategy !== "") {
                collabBits.push(strategy)
            }
            var workspace = safeText(session.workspaceLabel)
            if (workspace !== "") {
                collabBits.push(workspace)
            }
            return collabBits.join(" · ")
        }
        var context = safeText(session.contextLabel)
        if (context !== "") {
            return context
        }
        var source = safeText(session.source)
        var workspace = safeText(session.workspaceLabel)
        if (workspace === "") {
            workspace = safeText(session.cwd)
            if (workspace !== "") {
                var parts = workspace.split("/")
                workspace = parts.length > 0 ? parts[parts.length - 1] : workspace
            }
        }
        var terminal = safeText(session.terminalLabel)
        var parts = []
        if (source !== "") {
            parts.push(source)
        }
        if (workspace !== "") {
            parts.push(workspace)
        }
        if (terminal !== "") {
            parts.push(terminal)
        }
        return parts.join(" · ")
    }

    function sessionReviewHeadline(session) {
        if (session === undefined || session === null) {
            return "REVIEW BEFORE APPROVE"
        }
        var headline = safeText(session.reviewHeadline)
        if (headline !== "") {
            return headline
        }
        if (session.state === "Blocked" || session.state === "Waiting User") {
            return "REVIEW BEFORE APPROVE"
        }
        if (session.needsResponse) {
            return "REVIEW REQUEST"
        }
        return "TASK REVIEW"
    }

    function sessionReviewCommand(session) {
        if (session === undefined || session === null) {
            return ""
        }
        var value = safeText(session.reviewCommand)
        if (value !== "") {
            return value
        }
        return safeText(session.question) !== "" ? safeText(session.question) : safeText(session.summary)
    }

    function sessionReviewReason(session) {
        if (session === undefined || session === null) {
            return ""
        }
        var value = safeText(session.reviewReason)
        if (value !== "") {
            return value
        }
        return safeText(session.summary)
    }

    function sessionReviewScope(session) {
        if (session === undefined || session === null) {
            return ""
        }
        var value = safeText(session.reviewScope)
        if (value !== "") {
            return value
        }
        return sessionContextLabel(session)
    }

    function sessionReviewRisk(session) {
        if (session === undefined || session === null) {
            return ""
        }
        var value = safeText(session.reviewRisk)
        if (value !== "") {
            return value
        }
        if (session.stuck) {
            return "Needs attention"
        }
        if (session.state === "Blocked" || session.state === "Waiting User") {
            return "Pending approval"
        }
        return ""
    }

    function hasResponsiveSession(sessionId) {
        if (safeText(sessionId) === "") {
            return false
        }
        var items = sessionItems()
        for (var i = 0; i < items.length; i += 1) {
            var session = items[i]
            if (safeText(session.id) === safeText(sessionId) && !!session.needsResponse) {
                return true
            }
        }
        return false
    }

    function sessionChoicePanelHeight(session) {
        var choices = sessionChoices(session)
        if (choices.length === 0) {
            return 0
        }
        var longChoice = false
        for (var i = 0; i < choices.length; i += 1) {
            if (safeText(choices[i]).length > 20) {
                longChoice = true
                break
            }
        }
        return longChoice || choices.length > 2 ? 94 : 62
    }

    function sessionReviewPanelHeight(session, inlineReply) {
        var height = 26
        if (sessionReviewHeadline(session) !== "") {
            height += 18
        }
        if (sessionReviewCommand(session) !== "") {
            height += 30
        }
        if (sessionReviewReason(session) !== "") {
            height += 16
        }
        if (sessionReviewScope(session) !== "" || sessionReviewRisk(session) !== "") {
            height += 22
        }
        if (inlineReply) {
            height += 92
        } else {
            height += sessionChoicePanelHeight(session)
        }
        return height
    }

    function resetPromptReplyState() {
        promptNeedsTextReply = false
        promptReplyDraft = ""
        selectedPromptChoice = 0
        promptReplyTargetId = ""
    }

    function responseState(sessionId) {
        var key = safeText(sessionId)
        if (key === "" || responseStates[key] === undefined) {
            return null
        }
        return responseStates[key]
    }

    function isResponding(sessionId) {
        return responseState(sessionId) !== null
    }

    function cloneResponseStates() {
        var copy = {}
        for (var key in responseStates) {
            copy[key] = responseStates[key]
        }
        return copy
    }

    function clearResponseState(sessionId) {
        var key = safeText(sessionId)
        if (key === "" || responseStates[key] === undefined) {
            return
        }
        var next = cloneResponseStates()
        delete next[key]
        responseStates = next
    }

    function clearSettledResponseStates() {
        var next = cloneResponseStates()
        var changed = false
        var items = sessionItems()
        for (var key in responseStates) {
            var foundPending = false
            for (var i = 0; i < items.length; i += 1) {
                var session = items[i]
                if (safeText(session.id) !== key) {
                    continue
                }
                if (!!session.needsResponse) {
                    foundPending = true
                }
                break
            }
            if (!foundPending) {
                delete next[key]
                changed = true
            }
        }
        if (changed) {
            responseStates = next
        }
    }

    function responseBadgeLabel(sessionId) {
        var state = responseState(sessionId)
        if (state === null) {
            return ""
        }
        return safeText(state.label)
    }

    function beginResponse(sessionId, label) {
        var key = safeText(sessionId)
        if (key === "") {
            return
        }
        var next = cloneResponseStates()
        next[key] = {
            "label": safeText(label) !== "" ? safeText(label) : "SENDING",
            "startedAt": Date.now()
        }
        responseStates = next
    }

    function choiceSubmitLabel(choiceNumber, choiceText) {
        if (choiceNumber === 2) {
            return "SAVING RULE"
        }
        if (choiceNeedsFollowup(choiceNumber, choiceText)) {
            return "PREPARING REPLY"
        }
        return "SENDING"
    }

    function choiceNeedsFollowup(choiceNumber, choiceText) {
        if (choiceNumber !== 3) {
            return false
        }
        var lowered = safeText(choiceText).toLowerCase()
        return lowered.indexOf("tell") !== -1
                || lowered.indexOf("different") !== -1
                || lowered.indexOf("explain") !== -1
    }

    function promptSupportsFollowup() {
        var choices = promptChoices()
        if (choices.length < 3) {
            return false
        }
        return choiceNeedsFollowup(3, choices[2])
    }

    function sessionSupportsFollowup(session, choiceNumber, choiceText) {
        return choiceNeedsFollowup(choiceNumber, choiceText)
    }

    function openPromptReply(choiceNumber, sessionId) {
        selectedPromptChoice = choiceNumber
        promptReplyTargetId = safeText(sessionId) !== "" ? safeText(sessionId) : promptValue("id")
        promptNeedsTextReply = true
    }

    function submitPromptReply(sessionId) {
        var targetId = safeText(sessionId) !== "" ? safeText(sessionId) : promptValue("id")
        var followup = promptReplyDraft.trim()
        if (targetId === "" || followup === "") {
            return
        }
        beginResponse(targetId, "SENDING REPLY")
        backend.respondToSessionWithFollowup(
                    targetId,
                    selectedPromptChoice > 0 ? selectedPromptChoice : 3,
                    followup)
        resetPromptReplyState()
    }

    Behavior on x {
        enabled: !root.dragging
        NumberAnimation {
            duration: 220
            easing.type: Easing.InOutQuart
        }
    }

    Behavior on width {
        enabled: !root.dragging
        NumberAnimation {
            duration: 260
            easing.type: Easing.InOutQuart
        }
    }

    Behavior on y {
        enabled: !root.dragging
        NumberAnimation {
            duration: 220
            easing.type: Easing.InOutQuart
        }
    }

    Behavior on height {
        NumberAnimation {
            duration: 340
            easing.type: Easing.InOutQuart
        }
    }

    Timer {
        id: persistTimer
        interval: 160
        repeat: false
        onTriggered: backend.saveWindowState(root.x, root.y, root.width, root.height, backend.expanded)
    }

    Timer {
        id: peekRefreshTimer
        interval: 1200
        repeat: true
        running: root.peekSessionId !== ""
        onTriggered: backend.refreshPeekPreview(root.peekSessionId)
    }

    Timer {
        id: peekTypingReleaseTimer
        interval: 650
        repeat: false
        onTriggered: {
            if (root.typingPeekSessionId !== "") {
                root.typingPeekSessionId = ""
                root.flushDeferredSessionSync()
            }
        }
    }

    Timer {
        id: pinnedKeepAliveTimer
        interval: 1200
        repeat: true
        running: backend.pinned && root.visible
        onTriggered: root.raise()
    }

    Component.onCompleted: {
        syncWindowGeometry(false)
        centerIfNeeded()
        root.sessionModelCache = backend.sessions
        root.telegramDraftToken = backend.telegramBotToken
        root.telegramDraftChatId = backend.telegramChatId
        root.telegramDraftEnabled = backend.telegramEnabled
        geometryReady = true
    }

    onClosing: backend.shutdown()
    onXChanged: schedulePersist()
    onYChanged: schedulePersist()
    onWidthChanged: schedulePersist()
    onHeightChanged: schedulePersist()
    onActiveChanged: {
        if (backend.pinned && !root.active) {
            root.raise()
        }
    }

    Connections {
        target: backend

        function onSessionsChanged() {
            if (root.peekSessionId !== "" || root.activePeekInputSessionId !== "" || root.typingPeekSessionId !== "") {
                root.sessionSyncPending = true
                if (root.peekSessionId !== "") {
                    backend.refreshPeekPreview(root.peekSessionId)
                }
                return
            }
            root.applyLatestSessionModel(true)
            if (root.peekSessionId !== "") {
                backend.refreshPeekPreview(root.peekSessionId)
            }
        }

        function onResponseFinished(sessionId, ok, message) {
            if (ok) {
                root.clearPeekDraft(sessionId)
                if (root.activePeekInputSessionId === root.safeText(sessionId)) {
                    root.activePeekInputSessionId = ""
                }
                if (root.typingPeekSessionId === root.safeText(sessionId)) {
                    root.typingPeekSessionId = ""
                }
                root.flushDeferredSessionSync()
                backend.refreshPeekPreview(sessionId)
                if (!root.hasResponsiveSession(sessionId)) {
                    root.clearResponseState(sessionId)
                }
            } else {
                root.clearResponseState(sessionId)
                if (root.safeText(sessionId) !== "") {
                    root.peekSessionId = root.safeText(sessionId)
                    Qt.callLater(function() {
                        root.requestPeekInputFocus(root.safeText(sessionId))
                    })
                }
            }
        }

        function onExpandedChanged() {
            root.syncWindowGeometry(false)
            if (backend.expanded) {
                root.restoreSessionScroll()
            }
        }

        function onPinnedChanged() {
            if (backend.pinned) {
                Qt.callLater(function() {
                    root.raise()
                })
            }
        }

        function onAttentionRequested() {
            root.show()
            root.raise()
            root.requestActivate()
        }

        function onSummonRequested() {
            root.show()
            root.raise()
            root.requestActivate()
        }

        function onGeometryChanged() {
            root.syncWindowGeometry(false)
        }

        function onPeekPreviewReady(sessionId, lines) {
            var normalized = root.safeText(sessionId)
            if (normalized === "") {
                return
            }
            var next = Object.assign({}, root.peekLineOverrides || {})
            next[normalized] = lines
            root.peekLineOverrides = next
        }

        function onTelegramChanged() {
            root.telegramDraftToken = backend.telegramBotToken
            root.telegramDraftChatId = backend.telegramChatId
            root.telegramDraftEnabled = backend.telegramEnabled
        }
    }

    Item {
        anchors.fill: parent

        Rectangle {
            anchors.fill: parent
            radius: 36
            color: root.surfaceBase
            opacity: 0.78
        }

        Rectangle {
            anchors.fill: parent
            radius: 36
            color: "#000000"
            opacity: 0.14
        }

        Rectangle {
            id: islandShell
            anchors.fill: parent
            radius: 36
            gradient: Gradient {
                GradientStop { position: 0.0; color: "#0f1418" }
                GradientStop { position: 0.36; color: "#090c10" }
                GradientStop { position: 1.0; color: "#06080b" }
            }
            border.width: 1
            border.color: backend.blockedCount > 0 ? "#6b485312" : "#20262d16"
            opacity: 0.985
        }

        Rectangle {
            anchors.left: islandShell.left
            anchors.right: islandShell.right
            anchors.top: islandShell.top
            anchors.margins: 1
            height: 44
            radius: 35
            color: "#ffffff"
            opacity: 0.005
        }

        Rectangle {
            anchors.horizontalCenter: islandShell.horizontalCenter
            anchors.top: islandShell.top
            anchors.topMargin: 7
            width: islandShell.width * 0.48
            height: 9
            radius: 4.5
            gradient: Gradient {
                GradientStop { position: 0.0; color: "#00ffffff" }
                GradientStop { position: 0.5; color: backend.blockedCount > 0 ? "#2e39410d" : "#1820270a" }
                GradientStop { position: 1.0; color: "#00ffffff" }
            }
        }

        Rectangle {
            id: capsule
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: 24
            anchors.rightMargin: 24
            anchors.top: parent.top
            anchors.topMargin: 12
            height: 48
            radius: 24
            gradient: Gradient {
                GradientStop { position: 0.0; color: backend.expanded ? "#0e1317" : "#10151a" }
                GradientStop { position: 0.24; color: backend.expanded ? "#0a0f13" : "#0c1115" }
                GradientStop { position: 0.76; color: backend.expanded ? "#070b0f" : "#090d11" }
                GradientStop { position: 1.0; color: backend.expanded ? "#06080b" : "#070a0d" }
            }
            border.width: 1
            border.color: backend.expanded ? "#141a20" : "#0b1014"

                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 1
                    height: parent.height * 0.44
                    radius: parent.radius
                    color: "#ffffff"
                    opacity: backend.expanded ? 0.008 : 0.004
                }

                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: 1
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    height: 1
                    color: "#000000"
                    opacity: backend.expanded ? 0.14 : 0.24
                }

                Row {
                    id: expandedHeaderLead
                    visible: backend.expanded
                    anchors.left: parent.left
                    anchors.leftMargin: 14
                    anchors.right: expandedHeaderActions.left
                    anchors.rightMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 9

                    Rectangle {
                        width: 30
                        height: 30
                        radius: 10
                        gradient: Gradient {
                            GradientStop { position: 0.0; color: "#11161c" }
                            GradientStop { position: 1.0; color: "#090d12" }
                        }
                        border.width: 1
                        border.color: "#1f2730"

                        PixelSprite {
                            anchors.centerIn: parent
                            width: 20
                            height: 20
                            kind: backend.hasPromptSession ? "alert" : (allSessionsSleeping() ? "sleep" : "island")
                            accent: backend.hasPromptSession ? root.accentRose : (allSessionsSleeping() ? "#77c193" : "#8fb5c4")
                            glow: "#f2f5f8"
                            secondary: "#31404b"
                        }
                    }

                    Text {
                        width: Math.max(96, expandedHeaderLead.width - 42)
                        anchors.verticalCenter: parent.verticalCenter
                        text: root.expandedCapsuleTitle()
                        color: root.inkStrong
                        font.family: root.primaryFont
                        font.pixelSize: root.headerCompact ? 13 : 14
                        font.bold: true
                        font.letterSpacing: 0.3
                        elide: Text.ElideRight
                    }
                }

            Row {
                id: expandedHeaderActions
                visible: backend.expanded
                anchors.right: parent.right
                anchors.rightMargin: 34
                anchors.verticalCenter: parent.verticalCenter
                spacing: 4

                Rectangle {
                    width: root.headerMetric(78, 72, 64)
                    height: 24
                    radius: 11
                    color: backend.activeCount > 0 ? "#0a0d11" : "#080b0f"
                    border.width: 1
                    border.color: backend.activeCount > 0 ? "#1c232a0f" : "#ffffff04"

                    Text {
                        anchors.centerIn: parent
                        text: root.activePillText()
                        color: backend.activeCount > 0 ? "#adb6bf" : root.inkMuted
                        font.family: root.primaryFont
                        font.pixelSize: root.headerUltraCompact ? 7 : 8
                        font.bold: true
                        font.letterSpacing: 0.7
                    }
                }

                Rectangle {
                    width: root.headerMetric(84, 78, 70)
                    height: 24
                    radius: 11
                    color: backend.blockedCount > 0 ? "#0d090b" : "#080b0f"
                    border.width: 1
                    border.color: backend.blockedCount > 0 ? "#492f3810" : "#ffffff04"

                    Text {
                        anchors.centerIn: parent
                        text: root.urgentPillText()
                        color: backend.blockedCount > 0 ? "#b88d96" : root.inkMuted
                        font.family: root.primaryFont
                        font.pixelSize: root.headerUltraCompact ? 7 : 8
                        font.bold: true
                        font.letterSpacing: 0.7
                    }
                }

                Rectangle {
                    width: root.headerMetric(70, 62, 54)
                    height: 24
                    radius: 11
                    color: backend.connected ? "#091014" : "#080b0f"
                    border.width: 1
                    border.color: backend.connected ? "#20353e0f" : "#ffffff04"

                    Item {
                        anchors.fill: parent

                        Rectangle {
                            id: livePulse
                            anchors.left: parent.left
                            anchors.leftMargin: 8
                            anchors.verticalCenter: parent.verticalCenter
                            width: 10
                            height: 10
                            radius: 5
                            color: backend.connected ? "#6e9f82" : "#7c8792"
                            opacity: 0.08

                            SequentialAnimation on scale {
                                loops: Animation.Infinite
                                NumberAnimation { from: 0.86; to: 1.22; duration: 900; easing.type: Easing.OutCubic }
                                NumberAnimation { from: 1.22; to: 0.86; duration: 900; easing.type: Easing.OutCubic }
                            }

                            SequentialAnimation on opacity {
                                loops: Animation.Infinite
                                NumberAnimation { from: 0.12; to: 0.28; duration: 900 }
                                NumberAnimation { from: 0.28; to: 0.12; duration: 900 }
                            }
                        }

                        Rectangle {
                            anchors.left: parent.left
                            anchors.leftMargin: 10
                            anchors.verticalCenter: parent.verticalCenter
                            width: 5
                            height: 5
                            radius: 2.5
                            color: backend.connected ? "#6e9f82" : "#7c8792"
                        }

                        Text {
                            anchors.right: parent.right
                            anchors.rightMargin: 8
                            anchors.verticalCenter: parent.verticalCenter
                            text: root.livePillText()
                            color: backend.connected ? "#9ba5ae" : root.inkMuted
                            font.family: root.primaryFont
                            font.pixelSize: root.headerUltraCompact ? 7 : 8
                            font.bold: true
                            font.letterSpacing: 0.7
                        }
                    }
                }

                Rectangle {
                    width: root.headerMetric(68, 60, 50)
                    height: 24
                    radius: 11
                    color: backend.quietMode ? "#0c1117" : "#090d11"
                    border.width: 1
                    border.color: backend.quietMode ? "#202a34" : "#161d25"

                    Text {
                        anchors.centerIn: parent
                        text: root.quietPillText()
                        color: backend.quietMode ? "#b7c2cb" : root.inkMuted
                        font.family: root.primaryFont
                        font.pixelSize: root.headerUltraCompact ? 8 : 9
                        font.bold: true
                        font.letterSpacing: 0.7
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: backend.toggleQuietMode()
                    }
                }

                Rectangle {
                    width: 24
                    height: 24
                    radius: 11
                    color: "#090d11"
                    border.width: 1
                    border.color: backend.pinned ? "#30404c" : "#171e25"

                    PixelSprite {
                        anchors.centerIn: parent
                        width: 13
                        height: 13
                        kind: backend.pinned ? "pin-on" : "pin-off"
                        accent: backend.pinned ? "#8fb5c4" : "#76818b"
                        glow: "#eef3f7"
                        secondary: "#2d3742"
                    }

                    MouseArea {
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: backend.togglePinned()
                    }
                }

                Rectangle {
                    width: 22
                    height: 22
                    radius: 11
                    color: settingsOpen ? "#0c1218" : "#090d11"
                    border.width: 1
                    border.color: settingsOpen ? "#2b3945" : "#171e25"

                    PixelSprite {
                        anchors.centerIn: parent
                        width: 12
                        height: 12
                        kind: "settings"
                        accent: settingsOpen ? "#8fb5c4" : "#77828d"
                        glow: "#eef3f7"
                        secondary: "#2d3742"
                    }

                    MouseArea {
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: settingsOpen = !settingsOpen
                    }
                }

            }

            Row {
                visible: !backend.expanded
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.leftMargin: 10
                anchors.rightMargin: 76
                anchors.verticalCenter: parent.verticalCenter
                spacing: 7

                Rectangle {
                    width: 24
                    height: 24
                    radius: 8
                    color: "#0b1014"
                    border.width: 1
                    border.color: "#1a2128"

                    PixelSprite {
                        anchors.centerIn: parent
                        width: 14
                        height: 14
                        kind: root.collapsedSpriteKind()
                        accent: root.collapsedSpriteAccent()
                        glow: "#eef3f7"
                        secondary: "#2f3943"
                    }
                }

                Rectangle {
                    id: collapsedStatusPill
                    width: Math.max(62, collapsedStatusLabel.implicitWidth + 18)
                    height: 18
                    radius: 9
                    color: Qt.rgba(root.collapsedAccent().r,
                                   root.collapsedAccent().g,
                                   root.collapsedAccent().b,
                                   0.10)
                    border.width: 1
                    border.color: Qt.rgba(root.collapsedAccent().r,
                                          root.collapsedAccent().g,
                                          root.collapsedAccent().b,
                                          0.34)

                    Row {
                        anchors.centerIn: parent
                        spacing: 4

                        Rectangle {
                            width: 5
                            height: 5
                            radius: 2.5
                            anchors.verticalCenter: parent.verticalCenter
                            color: root.collapsedAccent()
                        }

                        Text {
                            id: collapsedStatusLabel
                            text: root.collapsedStatusText()
                            color: "#f2f5f8"
                            font.family: root.primaryFont
                            font.pixelSize: 9
                            font.bold: true
                            font.letterSpacing: 0.7
                        }
                    }
                }

                Column {
                    width: parent.width - 24 - collapsedStatusPill.width - parent.spacing * 2
                    spacing: 0
                    clip: true

                    Text {
                        width: parent.width
                        text: root.collapsedProjectTitle()
                        color: "#f2f5f8"
                        font.family: root.primaryFont
                        font.pixelSize: 12
                        font.bold: true
                        font.letterSpacing: 0.1
                        elide: Text.ElideRight
                    }

                    Text {
                        width: parent.width
                        text: root.collapsedContextText()
                        color: root.graphiteMuted
                        font.family: root.primaryFont
                        font.pixelSize: 8
                        font.letterSpacing: 0.2
                        elide: Text.ElideRight
                    }
                }
            }

                Row {
                    id: capsuleControlStrip
                    anchors.right: parent.right
                    anchors.rightMargin: backend.expanded ? 12 : 10
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: backend.expanded ? 6 : 4

                    Rectangle {
                        visible: !backend.expanded
                        width: 20
                        height: 20
                        radius: 11
                        color: settingsOpen ? "#0c1218" : "#090d11"
                        border.width: 1
                        border.color: settingsOpen ? "#2b3945" : "#171e25"

                        PixelSprite {
                            anchors.centerIn: parent
                            width: 12
                            height: 12
                            kind: "settings"
                            accent: settingsOpen ? "#8fb5c4" : "#77828d"
                            glow: "#eef3f7"
                            secondary: "#2d3742"
                        }

                        MouseArea {
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                settingsOpen = true
                                backend.toggleExpanded()
                                backend.saveWindowState(root.x, root.y, root.width, root.height, backend.expanded)
                            }
                        }
                    }

                    Rectangle {
                        visible: !backend.expanded
                        width: 20
                        height: 20
                        radius: 11
                        color: "#090d11"
                        border.width: 1
                        border.color: backend.pinned ? "#30404c" : "#171e25"

                        PixelSprite {
                            anchors.centerIn: parent
                            width: 12
                            height: 12
                            kind: backend.pinned ? "pin-on" : "pin-off"
                            accent: backend.pinned ? "#8fb5c4" : "#76818b"
                            glow: "#eef3f7"
                            secondary: "#2d3742"
                        }

                        MouseArea {
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: backend.togglePinned()
                        }
                    }

                    Rectangle {
                        id: toggleCapsuleButton
                        width: backend.expanded ? 22 : 20
                        height: backend.expanded ? 22 : 20
                        radius: 11
                        color: toggleMouse.containsMouse ? "#0b1014" : "#090d11"
                        border.width: 1
                        border.color: toggleMouse.containsMouse ? "#1d2730" : "#171e25"

                        PixelSprite {
                            anchors.centerIn: parent
                            width: 11
                            height: 11
                            kind: backend.expanded ? "chevron-up" : "chevron-down"
                            animate: false
                            accent: "#73808a"
                            glow: "#eef3f7"
                            secondary: "#2d3742"
                        }

                        property bool containsMouse: toggleMouse.containsMouse

                        MouseArea {
                            id: toggleMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                backend.toggleExpanded()
                                backend.saveWindowState(root.x, root.y, root.width, root.height, backend.expanded)
                            }
                        }
                    }
                }

                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: 4
                    width: 156
                    height: 2
                    radius: 1
                    color: backend.blockedCount > 0 ? root.accentRose : root.accentCyan
                    opacity: 0.12
                }

            MouseArea {
                visible: backend.expanded
                anchors.left: parent.left
                anchors.leftMargin: 10
                anchors.right: expandedHeaderActions.left
                anchors.rightMargin: 8
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                acceptedButtons: Qt.LeftButton
                hoverEnabled: true
                cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                onPressed: {
                    root.dragging = true
                    root.systemMoveTriggered = root.startSystemMove()
                }
                onReleased: {
                    root.dragging = false
                    root.systemMoveTriggered = false
                    root.schedulePersist()
                }
            }

            MouseArea {
                visible: !backend.expanded
                anchors.left: parent.left
                anchors.leftMargin: 8
                anchors.right: capsuleControlStrip.left
                anchors.rightMargin: 6
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                acceptedButtons: Qt.LeftButton
                hoverEnabled: true
                cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                onPressed: {
                    root.dragging = true
                    root.systemMoveTriggered = root.startSystemMove()
                }
                onReleased: {
                    root.dragging = false
                    root.systemMoveTriggered = false
                    root.schedulePersist()
                }
            }
        }

            Rectangle {
                id: bodyPanel
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.leftMargin: 20
                anchors.rightMargin: 20
                anchors.top: capsule.bottom
                anchors.topMargin: 10
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 14
                radius: 20
                color: "#070a0d"
                border.width: 1
                border.color: "#12181e"
                opacity: backend.expanded ? 1 : 0
                visible: backend.expanded

            Behavior on opacity {
                NumberAnimation {
                    duration: 280
                    easing.type: Easing.InOutQuart
                }
            }

                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 1
                    height: 40
                    radius: 25
                    color: "#ffffff"
                    opacity: 0.006
                }

            Row {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.leftMargin: 14
                anchors.rightMargin: 14
                anchors.topMargin: 11
                height: 22
                spacing: 6

                Text {
                    text: "MONITOR"
                    color: root.inkStrong
                    font.family: root.primaryFont
                    font.pixelSize: 10
                    font.bold: true
                    font.letterSpacing: 1.2
                }

                Text {
                    text: "APPROVE"
                    color: root.inkMuted
                    font.family: root.primaryFont
                    font.pixelSize: 10
                    font.letterSpacing: 1.2
                }

                Text {
                    text: "ASK"
                    color: root.inkMuted
                    font.family: root.primaryFont
                    font.pixelSize: 10
                    font.letterSpacing: 1.2
                }

                Text {
                    text: "JUMP"
                    color: root.inkMuted
                    font.family: root.primaryFont
                    font.pixelSize: 10
                    font.letterSpacing: 1.2
                }

                Text {
                    visible: backend.hasPromptSession
                    text: "RESPOND"
                    color: root.inkStrong
                    font.family: root.primaryFont
                    font.pixelSize: 10
                    font.bold: true
                    font.letterSpacing: 1.2
                }

                Item {
                    width: Math.max(8, parent.width - (backend.hasPromptSession ? 360 : 300))
                    height: 1
                }

                Text {
                    text: backend.connected
                          ? (backend.activeCount > 0 ? "LIVE SOCKET" : "LIVE SCAN")
                          : "FALLBACK JSON"
                    color: root.inkDim
                    font.family: root.primaryFont
                    font.pixelSize: 10
                    font.letterSpacing: 1.2
                }
            }

            Rectangle {
                id: promptCard
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.topMargin: 44
                anchors.leftMargin: 10
                anchors.rightMargin: 10
                visible: false && backend.hasPromptSession
                height: visible ? ((backend.promptChoiceCount > 2 ? 138 : 104) + (root.promptNeedsTextReply ? 86 : 0)) : 0
                radius: 22
                gradient: Gradient {
                    GradientStop { position: 0.0; color: "#13171c" }
                    GradientStop { position: 0.5; color: "#0f1318" }
                    GradientStop { position: 1.0; color: "#0b0f13" }
                }
                border.width: 1
                border.color: "#ffffff12"

                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 1
                    height: 40
                    radius: 21
                    color: "#ffffff"
                    opacity: 0.04
                }

                Column {
                    anchors.fill: parent
                    anchors.leftMargin: 14
                    anchors.rightMargin: 14
                    anchors.topMargin: 12
                    anchors.bottomMargin: 12
                    spacing: 10

                    Row {
                        width: parent.width
                        spacing: 8

                        Rectangle {
                            width: 10
                            height: 10
                            radius: 5
                            color: "#ff97a5"
                        }

                        Text {
                            text: root.promptValue("approvalType") !== "" ? "APPROVAL REQUEST" : "QUESTION FOR YOU"
                            color: root.accentRose
                            font.family: root.primaryFont
                            font.pixelSize: 11
                            font.bold: true
                            font.letterSpacing: 1.3
                        }

                        Item {
                            width: Math.max(6, parent.width - 230)
                            height: 1
                        }

                        Text {
                            text: root.promptValue("source").toUpperCase()
                            color: root.inkDim
                            font.family: root.primaryFont
                            font.pixelSize: 10
                            font.letterSpacing: 1.1
                        }
                    }

                    Text {
                        width: parent.width
                        text: root.promptValue("question") !== "" ? root.promptValue("question") : root.promptValue("summary")
                        color: root.inkStrong
                        font.family: root.primaryFont
                        font.pixelSize: 14
                        font.bold: true
                        wrapMode: Text.WordWrap
                    }

                    Text {
                        width: parent.width
                        visible: root.promptValue("summary") !== ""
                                 && root.promptValue("summary") !== (root.promptValue("question") !== "" ? root.promptValue("question") : "")
                        text: root.promptValue("summary")
                        color: root.inkMuted
                        font.family: root.primaryFont
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }

                    Flow {
                        width: parent.width
                        spacing: 8

                        Repeater {
                            model: root.promptChoices()

                            delegate: Rectangle {
                                id: choiceChip
                                required property int index
                                required property var modelData
                                property int choiceNumber: index + 1
                                property string choiceText: root.safeText(modelData)
                                property bool destructive: choiceNumber === 3
                                property bool secondary: choiceNumber === 2

                                        width: Math.min(promptCard.width - 28, Math.max(118, choiceLabel.implicitWidth + 34))
                                        height: 34
                                        radius: 17
                                        color: choiceChip.destructive ? "#110f12" : "#0c1115"
                                        border.width: 1
                                        border.color: choiceChip.destructive ? "#cb72841c" : (choiceChip.secondary ? "#73bfdc1a" : "#ffffff0b")
                                        opacity: 0.96

                                        Text {
                                            id: choiceLabel
                                            anchors.centerIn: parent
                                            text: choiceChip.choiceNumber + ". " + choiceChip.choiceText
                                            color: choiceChip.destructive ? root.accentRose : (choiceChip.secondary ? root.accentCyan : root.inkStrong)
                                            font.family: root.primaryFont
                                            font.pixelSize: 10
                                            font.bold: true
                                            font.letterSpacing: 0.8
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        if (choiceChip.choiceNumber === 3 && root.promptSupportsFollowup()) {
                                            root.openPromptReply(choiceChip.choiceNumber)
                                            return
                                        }
                                        root.resetPromptReplyState()
                                        backend.respondToSession(root.promptValue("id"), choiceChip.choiceNumber, choiceChip.choiceText)
                                    }
                                }
                            }
                        }
                    }

                    Rectangle {
                        id: promptReplyPanel
                        visible: root.promptNeedsTextReply
                        width: parent.width
                        height: visible ? 78 : 0
                        radius: 16
                        color: "#090d11"
                        border.width: 1
                        border.color: "#27313a"

                        Component.onCompleted: {
                            if (visible) {
                                if (replyInput.text !== root.promptReplyDraft) {
                                    replyInput.text = root.promptReplyDraft
                                }
                                Qt.callLater(function() {
                                    replyInput.forceActiveFocus()
                                })
                            }
                        }

                        onVisibleChanged: {
                            if (visible) {
                                if (replyInput.text !== root.promptReplyDraft) {
                                    replyInput.text = root.promptReplyDraft
                                }
                                Qt.callLater(function() {
                                    replyInput.forceActiveFocus()
                                })
                            }
                        }

                        Column {
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            anchors.topMargin: 10
                            anchors.bottomMargin: 10
                            spacing: 8

                            Text {
                                text: root.promptValue("source").toLowerCase() === "claude"
                                      ? "Tell Claude what to do differently"
                                      : "Tell Codex what to do differently"
                                color: "#e6ebef"
                                font.family: root.primaryFont
                                font.pixelSize: 11
                                font.bold: true
                                font.letterSpacing: 0.8
                            }

                            Rectangle {
                                width: parent.width
                                height: 28
                                radius: 14
                                color: "#080b0f"
                                border.width: 1
                                border.color: "#1f2730"

                                TextInput {
                                    id: replyInput
                                    anchors.fill: parent
                                    anchors.leftMargin: 12
                                    anchors.rightMargin: 12
                                    anchors.topMargin: 6
                                    anchors.bottomMargin: 6
                                    color: "#f7fbff"
                                    font.family: root.primaryFont
                                    font.pixelSize: 10
                                    clip: true
                                    selectByMouse: true
                                    selectedTextColor: "#0d0e11"
                                    selectionColor: "#8bd3e4"
                                    focus: root.promptNeedsTextReply
                                    onTextChanged: root.promptReplyDraft = text
                                    Component.onCompleted: {
                                        if (root.promptNeedsTextReply && text !== root.promptReplyDraft) {
                                            text = root.promptReplyDraft
                                        }
                                    }
                                    Keys.onReturnPressed: function(event) {
                                        if (!event.isAutoRepeat) {
                                            root.submitPromptReply()
                                            event.accepted = true
                                        }
                                    }
                                    Keys.onEnterPressed: function(event) {
                                        if (!event.isAutoRepeat) {
                                            root.submitPromptReply()
                                            event.accepted = true
                                        }
                                    }
                                }

                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    anchors.left: parent.left
                                    anchors.leftMargin: 12
                                    visible: replyInput.text.length === 0
                                    text: "Describe what the agent should do instead..."
                                    color: "#77818c"
                                    font.family: root.primaryFont
                                    font.pixelSize: 9
                                }
                            }

                            Row {
                                spacing: 8

                            Rectangle {
                                    width: 108
                                    height: 26
                                    radius: 13
                                    color: "#0f1418"
                                    border.width: 1
                                    border.color: "#6faabe18"
                                    opacity: root.promptReplyDraft.trim() === "" ? 0.45 : 1.0

                                Text {
                                    anchors.centerIn: parent
                                        text: "SEND REPLY"
                                        color: "#b9c4cf"
                                        font.family: root.primaryFont
                                        font.pixelSize: 11
                                        font.bold: true
                                        font.letterSpacing: 0.8
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        enabled: root.promptReplyDraft.trim() !== ""
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: root.submitPromptReply()
                                    }
                                }

                                Rectangle {
                                    width: 84
                                    height: 26
                                    radius: 13
                                    color: "#0d1115"
                                    border.width: 1
                                    border.color: "#ffffff08"

                                    Text {
                                        anchors.centerIn: parent
                                        text: "CANCEL"
                                        color: "#a0abb5"
                                        font.family: root.primaryFont
                                        font.pixelSize: 11
                                        font.bold: true
                                        font.letterSpacing: 0.8
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: root.resetPromptReplyState()
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Rectangle {
                id: settingsPanel
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.topMargin: 44
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                visible: settingsOpen
                height: visible ? 124 : 0
                radius: 14
                color: "#0b0f13"
                border.width: 1
                border.color: "#171e25"
                clip: true

                Column {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    anchors.topMargin: 10
                    anchors.bottomMargin: 10
                    spacing: 8

                    Row {
                        width: parent.width
                        spacing: 8

                        Text {
                            text: "TELEGRAM BRIDGE"
                            color: root.inkStrong
                            font.family: root.primaryFont
                            font.pixelSize: 10
                            font.bold: true
                            font.letterSpacing: 1.0
                        }

                        Item {
                            width: Math.max(6, parent.width - 250)
                            height: 1
                        }

                        Rectangle {
                            width: 52
                            height: 18
                            radius: 9
                            color: telegramDraftEnabled ? "#0d1318" : "#090d11"
                            border.width: 1
                            border.color: telegramDraftEnabled ? "#24303b" : "#171e25"

                            Text {
                                anchors.centerIn: parent
                                text: telegramDraftEnabled ? "ON" : "OFF"
                                color: telegramDraftEnabled ? "#d6dfe6" : root.inkMuted
                                font.family: root.primaryFont
                                font.pixelSize: 8
                                font.bold: true
                                font.letterSpacing: 0.8
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: telegramDraftEnabled = !telegramDraftEnabled
                            }
                        }

                        Rectangle {
                            width: 58
                            height: 18
                            radius: 9
                            color: "#0d1318"
                            border.width: 1
                            border.color: "#18212a"

                            Text {
                                anchors.centerIn: parent
                                text: "SAVE"
                                color: "#cad3da"
                                font.family: root.primaryFont
                                font.pixelSize: 8
                                font.bold: true
                                font.letterSpacing: 0.8
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: backend.saveTelegramSettings(telegramDraftToken, telegramDraftEnabled, telegramDraftChatId)
                            }
                        }

                        Rectangle {
                            width: 58
                            height: 18
                            radius: 9
                            color: "#0d1318"
                            border.width: 1
                            border.color: "#18212a"

                            Text {
                                anchors.centerIn: parent
                                text: "TEST"
                                color: "#cad3da"
                                font.family: root.primaryFont
                                font.pixelSize: 8
                                font.bold: true
                                font.letterSpacing: 0.8
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: backend.sendTelegramTest()
                            }
                        }
                    }

                    Row {
                        width: parent.width
                        spacing: 8

                        Rectangle {
                            width: parent.width * 0.64
                            height: 28
                            radius: 14
                            color: "#070a0e"
                            border.width: 1
                            border.color: "#161d24"

                            TextInput {
                                id: telegramTokenInput
                                anchors.fill: parent
                                anchors.leftMargin: 12
                                anchors.rightMargin: 12
                                anchors.topMargin: 6
                                anchors.bottomMargin: 6
                                color: "#eef2f6"
                                font.family: root.monoFont
                                font.pixelSize: 11
                                echoMode: TextInput.Password
                                text: telegramDraftToken
                                onTextChanged: telegramDraftToken = text
                            }

                            Text {
                                visible: telegramTokenInput.text.length === 0
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.left: parent.left
                                anchors.leftMargin: 12
                                text: "Paste Telegram bot token from BotFather"
                                color: "#6f7a84"
                                font.family: root.primaryFont
                                font.pixelSize: 9
                            }
                        }

                        Rectangle {
                            width: parent.width - (parent.width * 0.64) - parent.spacing
                            height: 28
                            radius: 14
                            color: "#070a0e"
                            border.width: 1
                            border.color: "#161d24"

                            TextInput {
                                id: telegramChatInput
                                anchors.fill: parent
                                anchors.leftMargin: 12
                                anchors.rightMargin: 12
                                anchors.topMargin: 6
                                anchors.bottomMargin: 6
                                color: "#eef2f6"
                                font.family: root.monoFont
                                font.pixelSize: 11
                                text: telegramDraftChatId
                                onTextChanged: telegramDraftChatId = text
                            }

                            Text {
                                visible: telegramChatInput.text.length === 0
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.left: parent.left
                                anchors.leftMargin: 12
                                text: "Chat ID auto-fills after /start"
                                color: "#6f7a84"
                                font.family: root.primaryFont
                                font.pixelSize: 9
                            }
                        }
                    }

                    Text {
                        width: parent.width
                        text: backend.telegramStatus
                        color: root.inkMuted
                        font.family: root.primaryFont
                        font.pixelSize: 9
                        elide: Text.ElideRight
                    }

                    Row {
                        width: parent.width
                        spacing: 8

                        Text {
                            text: "AUTO FRONT ON APPROVAL"
                            color: root.inkStrong
                            font.family: root.primaryFont
                            font.pixelSize: 9
                            font.bold: true
                            font.letterSpacing: 0.8
                        }

                        Item {
                            width: Math.max(6, parent.width - 240)
                            height: 1
                        }

                        Rectangle {
                            width: 58
                            height: 18
                            radius: 9
                            color: backend.promptAttentionEnabled ? "#0d1318" : "#090d11"
                            border.width: 1
                            border.color: backend.promptAttentionEnabled ? "#24303b" : "#171e25"

                            Text {
                                anchors.centerIn: parent
                                text: backend.promptAttentionEnabled ? "ON" : "OFF"
                                color: backend.promptAttentionEnabled ? "#d6dfe6" : root.inkMuted
                                font.family: root.primaryFont
                                font.pixelSize: 8
                                font.bold: true
                                font.letterSpacing: 0.8
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: backend.togglePromptAttention()
                            }
                        }
                    }
                }
            }

            Rectangle {
                id: usageBand
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: settingsPanel.visible ? settingsPanel.bottom : parent.top
                anchors.topMargin: settingsPanel.visible ? 10 : 44
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                visible: backend.activeCount > 0
                height: visible ? 20 : 0
                radius: 10
                color: "#0c1014"
                border.width: 1
                border.color: "#151b21"
                clip: true

                Row {
                    anchors.fill: parent
                    anchors.leftMargin: 8
                    anchors.rightMargin: 8
                    spacing: 10

                    Repeater {
                        model: [
                            { "key": "claude", "accent": root.accentRose },
                            { "key": "codex", "accent": root.accentCyan }
                        ]

                        delegate: Rectangle {
                            required property var modelData
                            width: (usageBand.width - 22) / 2
                            height: 16
                            anchors.verticalCenter: parent.verticalCenter
                            radius: 8
                            color: "transparent"
                            border.width: 0

                            Row {
                                anchors.fill: parent
                                anchors.leftMargin: 2
                                anchors.rightMargin: 2
                                spacing: 5

                                Rectangle {
                                    width: 5
                                    height: 5
                                    radius: 2.5
                                    anchors.verticalCenter: parent.verticalCenter
                                    color: modelData.accent
                                    opacity: 0.9
                                }

                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: root.usageValue(modelData.key, "label").toUpperCase()
                                    color: modelData.accent
                                    font.family: root.primaryFont
                                    font.pixelSize: 8
                                    font.bold: true
                                    font.letterSpacing: 0.8
                                }

                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "5H " + root.usageValue(modelData.key, "fiveHour")
                                    color: root.inkMuted
                                    font.family: root.primaryFont
                                    font.pixelSize: 8
                                    elide: Text.ElideRight
                                }

                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "7D " + root.usageValue(modelData.key, "sevenDay")
                                    color: root.inkMuted
                                    font.family: root.primaryFont
                                    font.pixelSize: 8
                                    elide: Text.ElideRight
                                }

                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "RUN " + root.usageSessionTokens(modelData.key)
                                    color: root.inkMuted
                                    font.family: root.primaryFont
                                    font.pixelSize: 8
                                    font.bold: true
                                    elide: Text.ElideRight
                                }
                            }
                        }
                    }
                }
            }

            Rectangle {
                id: replayBand
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: usageBand.bottom
                anchors.topMargin: usageBand.visible ? 10 : 44
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                visible: backend.timeline.length > 0
                height: visible ? (backend.replayExpanded ? (38 + root.timelineEntries().length * 18) : 34) : 0
                radius: 12
                color: "#080b0f"
                border.width: 1
                border.color: "#11161c"
                opacity: visible ? 1 : 0
                clip: true

                Column {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    anchors.topMargin: 8
                    anchors.bottomMargin: 10
                    spacing: 4

                    Item {
                        width: parent.width
                        height: 15

                        Row {
                            anchors.left: parent.left
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 8

                            Text {
                                text: "REPLAY"
                                color: root.inkStrong
                                font.family: root.primaryFont
                                font.pixelSize: 11
                                font.bold: true
                                font.letterSpacing: 1.0
                            }

                            Text {
                                text: backend.timeline.length + " MOMENTS"
                                color: root.inkDim
                                font.family: root.primaryFont
                                font.pixelSize: 10
                                font.letterSpacing: 0.8
                            }
                        }

                        Rectangle {
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            width: 72
                            height: 18
                            radius: 9
                            color: "#0d1217"
                            border.width: 1
                            border.color: "#171e25"

                            Text {
                                anchors.centerIn: parent
                                text: backend.replayExpanded ? "COLLAPSE" : "EXPAND"
                                color: "#9da8b1"
                                font.family: root.primaryFont
                                font.pixelSize: 8
                                font.bold: true
                                font.letterSpacing: 0.8
                                elide: Text.ElideRight
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: backend.toggleReplayExpanded()
                            }
                        }
                    }

                    Repeater {
                        visible: backend.replayExpanded
                        model: root.timelineEntries()

                        delegate: Item {
                            required property var modelData
                            width: parent.width
                            height: 13
                            clip: true

                            Rectangle {
                                anchors.left: parent.left
                                anchors.verticalCenter: parent.verticalCenter
                                width: 5
                                height: 5
                                radius: 2.5
                                color: modelData.accent
                            }

                            Text {
                                anchors.left: parent.left
                                anchors.leftMargin: 12
                                anchors.verticalCenter: parent.verticalCenter
                                width: 94
                                text: root.safeText(modelData.label)
                                color: root.inkStrong
                                font.family: root.primaryFont
                                font.pixelSize: 9
                                font.bold: true
                                font.letterSpacing: 0.7
                                elide: Text.ElideRight
                            }

                            Text {
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                width: 32
                                text: root.safeText(modelData.updated)
                                color: root.inkDim
                                font.family: root.primaryFont
                                font.pixelSize: 9
                                font.letterSpacing: 0.7
                                horizontalAlignment: Text.AlignRight
                                elide: Text.ElideRight
                            }

                            Text {
                                anchors.left: parent.left
                                anchors.leftMargin: 108
                                anchors.right: parent.right
                                anchors.rightMargin: 44
                                anchors.verticalCenter: parent.verticalCenter
                                text: root.safeText(modelData.detail)
                                color: root.inkMuted
                                font.family: root.primaryFont
                                font.pixelSize: 8
                                maximumLineCount: 1
                                elide: Text.ElideRight
                                clip: true
                            }
                        }
                    }
                }
            }

            ListView {
                id: sessionList
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: replayBand.bottom
                anchors.topMargin: 10
                anchors.bottom: parent.bottom
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                anchors.bottomMargin: 8
                clip: true
                spacing: 5
                model: root.sessionModelCache
                reuseItems: true
                cacheBuffer: 560
                flickDeceleration: 520
                maximumFlickVelocity: 3000
                boundsBehavior: Flickable.DragAndOvershootBounds
                boundsMovement: Flickable.FollowBoundsBehavior
                rebound: Transition {
                    NumberAnimation {
                        properties: "x,y"
                        duration: 300
                        easing.type: Easing.OutQuart
                    }
                }
                onContentYChanged: root.rememberSessionScroll(contentY)

                NumberAnimation {
                    id: sessionWheelAnimator
                    target: sessionList
                    property: "contentY"
                    duration: 180
                    easing.type: Easing.OutQuart
                }

                WheelHandler {
                    target: null
                    onWheel: function(event) {
                        var delta = event.angleDelta.y
                        var maxY = Math.max(0, sessionList.contentHeight - sessionList.height)
                        var scrollAmount = delta * 0.34
                        var nextY = Math.max(
                            0,
                            Math.min(maxY, sessionList.contentY - scrollAmount))
                        sessionWheelAnimator.stop()
                        sessionWheelAnimator.from = sessionList.contentY
                        sessionWheelAnimator.to = nextY
                        sessionWheelAnimator.start()
                        root.rememberSessionScroll(nextY)
                        event.accepted = true
                    }
                }

                delegate: Item {
                    id: delegateRoot
                    required property var modelData
                    width: sessionList.width
                    height: delegateRoot.visibleInFocus
                            ? delegateRoot.baseHeight
                                + (delegateRoot.showPeekPanel ? delegateRoot.peekPanelHeight + 8 : 0)
                                + (delegateRoot.showResponsePanel ? delegateRoot.responsePanelHeight + 8 : 0)
                                + (delegateRoot.responding ? 40 : 0)
                            : 0
                    visible: delegateRoot.visibleInFocus

                    property bool urgent: root.isUrgent(modelData.state, modelData.attention) || modelData.stuck || modelData.stale
                    property bool visibleInFocus: root.sessionVisibleInFocus(delegateRoot.modelData)
                    property color accent: root.sessionHealthAccent(delegateRoot.modelData)
                    property color plate: root.sessionPlate(delegateRoot.modelData)
                    property bool needsResponse: !!modelData.needsResponse
                    property bool responding: root.isResponding(modelData.id)
                    property bool showPeekPanel: root.isPeekOpen(modelData.id)
                    property bool showResponsePanel: delegateRoot.needsResponse && !delegateRoot.responding
                    property bool showInlineReply: root.promptNeedsTextReply && root.promptReplyTargetId === modelData.id
                    property bool isCollab: root.sessionIsCollab(delegateRoot.modelData)
                    property bool canSendPeek: delegateRoot.modelData.peekSendable !== false
                    property int responsePanelHeight: root.sessionReviewPanelHeight(delegateRoot.modelData, delegateRoot.showInlineReply)
                    property int peekPanelHeight: 214
                    property string peekLocalDraft: ""
                    property string peekLocalDraftSessionId: ""
                    property bool peekUserTyping: false
                    property int actionWidth: delegateRoot.isCollab ? 206 : 118
                    property int baseHeight: Math.max(80, copyColumn.implicitHeight + 22)

                    function syncPeekLocalDraft() {
                        var sid = root.safeText(delegateRoot.modelData.id)
                        if (sid === "") {
                            return
                        }
                        delegateRoot.peekLocalDraftSessionId = sid
                        delegateRoot.peekLocalDraft = root.peekDraftFor(sid)
                    }

                    function syncPeekInputText() {
                        if (delegateRoot.peekUserTyping || peekInput.activeFocus) {
                            return
                        }
                        if (peekInput.text !== delegateRoot.peekLocalDraft
                                && delegateRoot.peekLocalDraftSessionId !== "") {
                            peekInput.text = delegateRoot.peekLocalDraft
                            peekInput.cursorPosition = peekInput.text.length
                        }
                    }

                    function focusPeekComposer() {
                        var sid = root.safeText(delegateRoot.modelData.id)
                        if (!delegateRoot.showPeekPanel || sid === "") {
                            return
                        }
                        root.activePeekInputSessionId = sid
                        Qt.callLater(function() {
                            if (!delegateRoot.showPeekPanel) {
                                return
                            }
                            peekInput.forceActiveFocus()
                            peekInput.cursorPosition = peekInput.text.length
                        })
                    }

                    Rectangle {
                        anchors.fill: parent
                        radius: 10
                        color: delegateRoot.urgent ? "#070a0d" : "#050709"
                        border.width: 1
                        border.color: delegateRoot.urgent ? "#2a1e23" : "#141a20"
                        opacity: 0.995
                    }

                    onShowPeekPanelChanged: {
                        if (showPeekPanel) {
                            root.sessionSyncPending = true
                            delegateRoot.syncPeekLocalDraft()
                            delegateRoot.syncPeekInputText()
                            delegateRoot.focusPeekComposer()
                        } else if (delegateRoot.peekLocalDraftSessionId !== "") {
                            delegateRoot.peekUserTyping = false
                            root.setPeekDraft(delegateRoot.peekLocalDraftSessionId, delegateRoot.peekLocalDraft)
                            if (root.activePeekInputSessionId === delegateRoot.peekLocalDraftSessionId) {
                                root.activePeekInputSessionId = ""
                            }
                            if (root.typingPeekSessionId === delegateRoot.peekLocalDraftSessionId) {
                                root.typingPeekSessionId = ""
                            }
                            root.flushDeferredSessionSync()
                        }
                    }

                    onModelDataChanged: {
                        if (!delegateRoot.showPeekPanel && !peekInput.activeFocus && !delegateRoot.peekUserTyping) {
                            delegateRoot.syncPeekLocalDraft()
                            delegateRoot.syncPeekInputText()
                        }
                    }

                    onPeekLocalDraftChanged: {
                        if (!delegateRoot.peekUserTyping) {
                            delegateRoot.syncPeekInputText()
                        }
                    }

                    Connections {
                        target: root

                        function onRequestPeekInputFocus(sessionId) {
                            if (root.safeText(sessionId) === root.safeText(delegateRoot.modelData.id) && delegateRoot.showPeekPanel) {
                                delegateRoot.syncPeekInputText()
                                delegateRoot.focusPeekComposer()
                            }
                        }
                    }

                    Rectangle {
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        width: 1.5
                        radius: 1
                        color: delegateRoot.accent
                        opacity: 0.08
                    }

                    Rectangle {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.topMargin: 1
                        anchors.leftMargin: 8
                        anchors.rightMargin: 8
                        height: 1
                        color: "#ffffff"
                        opacity: 0.002
                    }

                    Row {
                        id: rowLayout
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.leftMargin: 12
                        anchors.rightMargin: 13
                        anchors.topMargin: 7
                        height: delegateRoot.baseHeight - 15
                        spacing: 7

                        Rectangle {
                            width: 24
                            height: 24
                            radius: 7
                            color: "#090c10"
                            border.width: 1
                            border.color: "#182028"

                            Rectangle {
                                anchors.fill: parent
                                anchors.margins: 1
                                radius: 7
                                color: "#ffffff"
                                opacity: 0.01
                            }

                            PixelSprite {
                                anchors.centerIn: parent
                                width: 14
                                height: 14
                                kind: root.sessionSpriteKind(delegateRoot.modelData)
                                accent: root.sessionSpriteAccent(delegateRoot.modelData)
                                glow: "#eef3f7"
                                secondary: "#32404a"
                            }
                        }

                        Column {
                            id: copyColumn
                            width: rowLayout.width - delegateRoot.actionWidth - 58
                            clip: true
                            spacing: 2

                            Text {
                                width: parent.width
                                text: root.sessionDisplayTitle(delegateRoot.modelData)
                                color: root.inkStrong
                                font.family: root.primaryFont
                                font.pixelSize: 14
                                font.bold: true
                                font.letterSpacing: 0.1
                                elide: Text.ElideRight
                            }

                            Text {
                                width: parent.width
                                text: root.sessionContextLabel(delegateRoot.modelData)
                                color: root.graphiteSubtle
                                font.pixelSize: 9
                                font.family: root.primaryFont
                                maximumLineCount: 1
                                elide: Text.ElideRight
                                clip: true
                            }

                            Text {
                                width: parent.width
                                text: delegateRoot.modelData.summary
                                color: root.sessionSummaryTone(delegateRoot.modelData)
                                font.pixelSize: 9
                                font.family: root.primaryFont
                                visible: !delegateRoot.isCollab
                                maximumLineCount: 1
                                elide: Text.ElideRight
                                clip: true
                            }

                            Item {
                                visible: delegateRoot.isCollab
                                width: parent.width
                                height: collabDetailColumn.implicitHeight

                                Column {
                                    id: collabDetailColumn
                                    anchors.fill: parent
                                    spacing: 6

                                    Row {
                                        width: parent.width
                                        spacing: 6

                                        Rectangle {
                                            width: Math.floor((parent.width - 12) / 3)
                                            height: 26
                                            radius: 9
                                            color: "#0b0f13"
                                            border.width: 1
                                            border.color: Qt.rgba(root.accentRose.r, root.accentRose.g, root.accentRose.b, 0.08)

                                            Column {
                                                anchors.left: parent.left
                                                anchors.leftMargin: 10
                                                anchors.right: parent.right
                                                anchors.rightMargin: 10
                                                anchors.verticalCenter: parent.verticalCenter
                                                spacing: 0

                                                Text {
                                                    text: "CURRENT"
                                                    color: "#b98892"
                                                    font.family: root.primaryFont
                                                    font.pixelSize: 5
                                                    font.bold: true
                                                    font.letterSpacing: 0.9
                                                }

                                                Text {
                                                    id: currentActorValue
                                                    width: parent.width
                                                    text: root.sessionCollabCurrentActorLabel(delegateRoot.modelData)
                                                    color: root.inkStrong
                                                    font.family: root.primaryFont
                                                    font.pixelSize: 6
                                                    font.bold: true
                                                    elide: Text.ElideRight
                                                }
                                            }
                                        }

                                        Rectangle {
                                            width: Math.floor((parent.width - 12) / 3)
                                            height: 26
                                            radius: 9
                                            color: "#0b0f13"
                                            border.width: 1
                                            border.color: Qt.rgba(root.accentCyan.r, root.accentCyan.g, root.accentCyan.b, 0.08)

                                            Column {
                                                anchors.left: parent.left
                                                anchors.leftMargin: 10
                                                anchors.right: parent.right
                                                anchors.rightMargin: 10
                                                anchors.verticalCenter: parent.verticalCenter
                                                spacing: 0

                                                Text {
                                                    text: "NEXT"
                                                    color: "#85afbf"
                                                    font.family: root.primaryFont
                                                    font.pixelSize: 5
                                                    font.bold: true
                                                    font.letterSpacing: 0.9
                                                }

                                                Text {
                                                    id: nextActorValue
                                                    width: parent.width
                                                    text: root.sessionCollabNextActorLabel(delegateRoot.modelData)
                                                    color: root.inkStrong
                                                    font.family: root.primaryFont
                                                    font.pixelSize: 6
                                                    font.bold: true
                                                    elide: Text.ElideRight
                                                }
                                            }
                                        }

                                        Rectangle {
                                            width: parent.width - 12 - (2 * Math.floor((parent.width - 12) / 3))
                                            height: 26
                                            radius: 9
                                            color: "#0b0f13"
                                            border.width: 1
                                            border.color: root.sessionCollabStrategyLabel(delegateRoot.modelData) === "BRIDGE"
                                                          ? Qt.rgba(root.accentAmber.r, root.accentAmber.g, root.accentAmber.b, 0.06)
                                                          : Qt.rgba(root.accentGreen.r, root.accentGreen.g, root.accentGreen.b, 0.06)

                                                Text {
                                                    id: strategyValue
                                                    anchors.centerIn: parent
                                                    width: parent.width - 12
                                                    text: root.sessionCollabStrategyLabel(delegateRoot.modelData)
                                                    color: root.inkStrong
                                                    font.family: root.primaryFont
                                                    font.pixelSize: 6
                                                    font.bold: true
                                                    font.letterSpacing: 0.8
                                                    horizontalAlignment: Text.AlignHCenter
                                                    elide: Text.ElideRight
                                            }
                                        }
                                    }

                                        Rectangle {
                                            width: parent.width
                                            height: recentHandoffContent.implicitHeight + 12
                                            radius: 9
                                            color: "#080b0f"
                                            border.width: 1
                                            border.color: "#ffffff05"

                                        Column {
                                            id: recentHandoffContent
                                            anchors.left: parent.left
                                            anchors.leftMargin: 10
                                            anchors.right: parent.right
                                            anchors.rightMargin: 10
                                            anchors.top: parent.top
                                            anchors.topMargin: 7
                                            spacing: 2

                                            Row {
                                                width: parent.width
                                                spacing: 7

                                                Text {
                                                    id: recentHandoffTitle
                                                    text: "RECENT HANDOFF"
                                                    color: "#7ea7b7"
                                                    font.family: root.primaryFont
                                                    font.pixelSize: 4
                                                    font.bold: true
                                                    font.letterSpacing: 0.9
                                                }

                                                Text {
                                                    width: Math.max(0, parent.width - recentHandoffTitle.implicitWidth - 7)
                                                    text: root.sessionCollabPhaseLabel(delegateRoot.modelData)
                                                    color: "#7f8b96"
                                                    font.family: root.primaryFont
                                                    font.pixelSize: 4
                                                    font.bold: true
                                                    font.letterSpacing: 0.8
                                                    horizontalAlignment: Text.AlignRight
                                                    elide: Text.ElideRight
                                                }
                                            }

                                            Repeater {
                                                model: root.sessionCollabRecentLines(delegateRoot.modelData)

                                                delegate: Text {
                                                    required property var modelData
                                                    required property int index
                                                    width: parent.width
                                                    text: root.safeText(modelData)
                                                    color: index === 0 ? root.inkStrong : root.inkMuted
                                                    font.family: index === 0 ? root.primaryFont : root.monoFont
                                                    font.pixelSize: 4
                                                    font.bold: index === 0
                                                    maximumLineCount: index === 0 ? 2 : 1
                                                    wrapMode: index === 0 ? Text.WordWrap : Text.NoWrap
                                                    elide: Text.ElideRight
                                                }
                                            }
                                        }
                                    }
                                }
                            }

                            Row {
                                width: parent.width
                                spacing: 6
                                clip: true

                                Rectangle {
                                    width: Math.max(66, healthLabel.implicitWidth + 14)
                                    height: 15
                                    radius: 7.5
                                    color: delegateRoot.modelData.stale ? "#101410"
                                           : (delegateRoot.modelData.stuck ? "#131014" : "#0f1419")
                                    border.width: 1
                                    border.color: delegateRoot.modelData.stale ? "#342f25"
                                                  : (delegateRoot.modelData.stuck ? "#3d2c35" : Qt.rgba(delegateRoot.accent.r, delegateRoot.accent.g, delegateRoot.accent.b, 0.12))

                                    Text {
                                        id: healthLabel
                                        width: parent.width - 10
                                        anchors.centerIn: parent
                                        text: root.sessionHealthTag(delegateRoot.modelData)
                                        color: delegateRoot.accent
                                        font.family: root.primaryFont
                                        font.pixelSize: 6
                                        font.bold: true
                                        font.letterSpacing: 0.8
                                        horizontalAlignment: Text.AlignHCenter
                                        elide: Text.ElideRight
                                    }
                                }

                                Rectangle {
                                    width: Math.max(54, sourceTag.implicitWidth + 14)
                                    height: 15
                                    radius: 7.5
                                    color: "#0f1419"
                                    border.width: 1
                                    border.color: "#182028"

                                    Text {
                                        id: sourceTag
                                        width: parent.width - 10
                                        anchors.centerIn: parent
                                        text: root.safeText(delegateRoot.modelData.source).toUpperCase()
                                        color: root.safeText(delegateRoot.modelData.source).toUpperCase() === "COLLAB" ? root.accentSlate : root.inkDim
                                        font.family: root.primaryFont
                                        font.pixelSize: 6
                                        font.bold: true
                                        font.letterSpacing: 0.8
                                        horizontalAlignment: Text.AlignHCenter
                                        elide: Text.ElideRight
                                    }
                                }

                                Text {
                                    width: Math.max(0, parent.width - 132)
                                    text: delegateRoot.modelData.updated
                                    color: root.inkDim
                                    font.family: root.primaryFont
                                    font.pixelSize: 6
                                    font.letterSpacing: 0.9
                                    horizontalAlignment: Text.AlignRight
                                    elide: Text.ElideRight
                                }
                            }
                        }

                        Item {
                            width: 1
                            height: 1
                        }

                        Row {
                            spacing: 6

                            Rectangle {
                                visible: !delegateRoot.isCollab
                                width: 24
                                height: 24
                                radius: 12
                                color: delegateRoot.showPeekPanel ? "#0d1115" : "#070a0d"
                                border.width: 1
                                border.color: delegateRoot.showPeekPanel ? "#23303a" : "#141a20"
                                opacity: delegateRoot.modelData.peekable ? 1.0 : 0.45

                                PixelSprite {
                                    anchors.centerIn: parent
                                    width: 12
                                    height: 12
                                    kind: "terminal"
                                    accent: delegateRoot.showPeekPanel ? "#8fb5c4" : "#788390"
                                    glow: "#eef3f7"
                                    secondary: "#2d3742"
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    enabled: delegateRoot.modelData.peekable
                                    hoverEnabled: true
                                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                    onClicked: root.togglePeek(delegateRoot.modelData.id)
                                }
                            }

                            Rectangle {
                                visible: delegateRoot.isCollab
                                width: 54
                                height: 20
                                radius: 10
                                color: root.sessionCollabActor(delegateRoot.modelData, "claude") === "claude"
                                       ? Qt.rgba(root.accentRose.r, root.accentRose.g, root.accentRose.b, 0.028)
                                       : "#0b1015"
                                border.width: 1
                                border.color: root.sessionCollabActor(delegateRoot.modelData, "claude") === "claude" ? Qt.rgba(root.accentRose.r, root.accentRose.g, root.accentRose.b, 0.06) : "#ffffff04"
                                opacity: 0.94

                                Text {
                                    anchors.centerIn: parent
                                    text: "CLAUDE"
                                    color: root.inkStrong
                                    font.family: root.primaryFont
                                    font.pixelSize: 7
                                    font.bold: true
                                    font.letterSpacing: 0.8
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: backend.openCollabAgent(delegateRoot.modelData.id, "claude")
                                }
                            }

                            Rectangle {
                                visible: delegateRoot.isCollab
                                width: 54
                                height: 20
                                radius: 10
                                color: root.sessionCollabActor(delegateRoot.modelData, "codex") === "codex"
                                       ? Qt.rgba(root.accentCyan.r, root.accentCyan.g, root.accentCyan.b, 0.028)
                                       : "#0b1015"
                                border.width: 1
                                border.color: root.sessionCollabActor(delegateRoot.modelData, "codex") === "codex" ? Qt.rgba(root.accentCyan.r, root.accentCyan.g, root.accentCyan.b, 0.06) : "#ffffff04"
                                opacity: 0.94

                                Text {
                                    anchors.centerIn: parent
                                    text: "CODEX"
                                    color: root.inkStrong
                                    font.family: root.primaryFont
                                    font.pixelSize: 7
                                    font.bold: true
                                    font.letterSpacing: 0.8
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: backend.openCollabAgent(delegateRoot.modelData.id, "codex")
                                }
                            }

                            Rectangle {
                                width: delegateRoot.isCollab ? 56 : 58
                                height: 20
                                radius: 10
                                color: delegateRoot.modelData.jumpable ? "#0a0d11" : "#080b0f"
                                border.width: 1
                                border.color: delegateRoot.modelData.jumpable ? "#151b21" : "#12171d"
                                opacity: delegateRoot.modelData.jumpable ? 0.92 : 0.52

                                Text {
                                    width: parent.width - 12
                                    anchors.centerIn: parent
                                    text: delegateRoot.isCollab ? "OPEN" : "JUMP"
                                    color: delegateRoot.modelData.jumpable ? "#d0d7de" : "#b0bac3"
                                    font.family: root.primaryFont
                                    font.pixelSize: 8
                                    font.bold: true
                                    font.letterSpacing: 1.1
                                    horizontalAlignment: Text.AlignHCenter
                                    elide: Text.ElideRight
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    enabled: delegateRoot.modelData.jumpable
                                    hoverEnabled: true
                                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                    onClicked: backend.jumpToSession(delegateRoot.modelData.id)
                                }
                            }
                        }
                    }

                    Rectangle {
                        visible: delegateRoot.showPeekPanel
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        anchors.leftMargin: 12
                        anchors.rightMargin: 12
                        anchors.bottomMargin: 8 + (delegateRoot.responding ? 40 : 0) + (delegateRoot.showResponsePanel ? delegateRoot.responsePanelHeight + 8 : 0)
                        height: visible ? delegateRoot.peekPanelHeight : 0
                        radius: 11
                        color: "#05070a"
                        border.width: 1
                        border.color: "#12171d"
                        clip: true

                        Column {
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            anchors.topMargin: 10
                            anchors.bottomMargin: 10
                            spacing: 10

                            Row {
                                width: parent.width
                                spacing: 10

                                Column {
                                    width: parent.width - terminalLiveTag.width - parent.spacing
                                    spacing: 1

                                    Text {
                                        text: "TERMINAL PEEK"
                                        color: "#c3cbd1"
                                        font.family: root.monoFont
                                        font.pixelSize: 9
                                        font.bold: true
                                        font.letterSpacing: 0.9
                                    }

                                    Text {
                                        width: parent.width
                                        text: root.sessionContextLabel(delegateRoot.modelData)
                                        color: "#66717a"
                                        font.family: root.monoFont
                                        font.pixelSize: 9
                                        elide: Text.ElideRight
                                    }
                                }

                                Rectangle {
                                    id: terminalLiveTag
                                    width: 42
                                    height: 15
                                    radius: 7.5
                                    color: "#0f1418"
                                    border.width: 1
                                    border.color: "#182028"

                                    Text {
                                        anchors.centerIn: parent
                                        text: "LIVE"
                                        color: "#80919b"
                                        font.family: root.monoFont
                                        font.pixelSize: 6
                                        font.bold: true
                                        font.letterSpacing: 0.7
                                    }
                                }
                            }

                            Rectangle {
                                width: parent.width
                                height: 112
                                radius: 11
                                color: "#06080b"
                                border.width: 1
                                border.color: "#141a21"

                                Flickable {
                                    id: transcriptFlick
                                    anchors.fill: parent
                                    anchors.leftMargin: 13
                                    anchors.rightMargin: 18
                                    anchors.topMargin: 10
                                    anchors.bottomMargin: 10
                                    clip: true
                                    contentWidth: width
                                    contentHeight: transcriptColumn.implicitHeight
                                    interactive: contentHeight > height
                                    boundsBehavior: Flickable.StopAtBounds

                                    WheelHandler {
                                        target: transcriptFlick
                                        onWheel: function(event) {
                                            transcriptFlick.contentY = Math.max(
                                                        0,
                                                        Math.min(
                                                            transcriptFlick.contentHeight - transcriptFlick.height,
                                                            transcriptFlick.contentY - event.angleDelta.y))
                                        }
                                    }

                                    Column {
                                        id: transcriptColumn
                                        width: transcriptFlick.width
                                        spacing: 5

                                        Repeater {
                                            model: root.sessionPeekLines(delegateRoot.modelData)

                                                delegate: Text {
                                                    required property var modelData
                                                    width: parent.width
                                                    text: root.safeText(modelData)
                                                    color: "#eef2f6"
                                                    font.family: root.monoFont
                                                    font.pixelSize: 12
                                                    lineHeight: 1.10
                                                    wrapMode: Text.Wrap
                                                }
                                        }
                                    }
                                }

                                Rectangle {
                                    visible: transcriptFlick.contentHeight > transcriptFlick.height
                                    anchors.top: parent.top
                                    anchors.bottom: parent.bottom
                                    anchors.right: parent.right
                                    anchors.topMargin: 9
                                    anchors.bottomMargin: 9
                                    anchors.rightMargin: 5
                                    width: 4
                                    radius: 2
                                    color: "#ffffff10"

                                    Rectangle {
                                        width: parent.width
                                        radius: 2
                                        color: root.graphiteMuted
                                        height: Math.max(20, parent.height * (transcriptFlick.height / Math.max(transcriptFlick.contentHeight, 1)))
                                        y: (parent.height - height) * (transcriptFlick.contentY / Math.max(transcriptFlick.contentHeight - transcriptFlick.height, 1))
                                    }
                                }
                            }

                            Row {
                                width: parent.width
                                spacing: 8

                                Rectangle {
                                    width: parent.width - peekSendButton.width - parent.spacing
                                    height: 32
                                    radius: 16
                                    color: "#070a0e"
                                    border.width: 1
                                    border.color: "#131920"

                                    TextInput {
                                        id: peekInput
                                        objectName: "peekInput-" + root.safeText(delegateRoot.modelData.id)
                                        anchors.fill: parent
                                        anchors.leftMargin: 12
                                        anchors.rightMargin: 12
                                        anchors.topMargin: 6
                                        anchors.bottomMargin: 6
                                        color: "#f3f6fa"
                                        font.family: root.monoFont
                                        font.pixelSize: 12
                                        clip: true
                                        readOnly: !delegateRoot.canSendPeek
                                        selectByMouse: true
                                        activeFocusOnTab: true
                                        persistentSelection: true
                                        Component.onCompleted: {
                                            delegateRoot.syncPeekLocalDraft()
                                            delegateRoot.syncPeekInputText()
                                            if (delegateRoot.showPeekPanel) {
                                                delegateRoot.focusPeekComposer()
                                            }
                                        }
                                        onTextEdited: {
                                            if (!delegateRoot.canSendPeek) {
                                                return
                                            }
                                            delegateRoot.peekUserTyping = true
                                            root.typingPeekSessionId = root.safeText(delegateRoot.modelData.id)
                                            delegateRoot.peekLocalDraft = text
                                            peekTypingReleaseTimer.restart()
                                        }
                                        Keys.onReturnPressed: function(event) {
                                            if (!event.isAutoRepeat) {
                                                root.submitPeek(delegateRoot.modelData.id, text)
                                                event.accepted = true
                                            }
                                        }
                                        Keys.onEnterPressed: function(event) {
                                            if (!event.isAutoRepeat) {
                                                root.submitPeek(delegateRoot.modelData.id, text)
                                                event.accepted = true
                                            }
                                        }
                                        onActiveFocusChanged: {
                                            var sid = root.safeText(delegateRoot.modelData.id)
                                            if (activeFocus) {
                                                root.activePeekInputSessionId = sid
                                                root.typingPeekSessionId = sid
                                                if (delegateRoot.peekLocalDraftSessionId !== sid) {
                                                    delegateRoot.syncPeekLocalDraft()
                                                    delegateRoot.syncPeekInputText()
                                                }
                                            } else {
                                                delegateRoot.peekUserTyping = false
                                                delegateRoot.peekLocalDraft = text
                                                if (sid !== "") {
                                                    root.setPeekDraft(sid, delegateRoot.peekLocalDraft)
                                                }
                                                if (root.activePeekInputSessionId === sid) {
                                                    root.activePeekInputSessionId = ""
                                                }
                                                if (root.typingPeekSessionId === sid) {
                                                    root.typingPeekSessionId = ""
                                                }
                                                root.flushDeferredSessionSync()
                                            }
                                        }
                                    }

                                    Text {
                                        anchors.verticalCenter: parent.verticalCenter
                                        anchors.left: parent.left
                                        anchors.leftMargin: 12
                                        width: parent.width - 28
                                        visible: peekInput.text.length === 0
                                        text: delegateRoot.canSendPeek
                                              ? "send an in-session follow-up..."
                                              : "This terminal host does not support native in-island send. Use JUMP."
                                        color: "#67727b"
                                        font.family: root.monoFont
                                        font.pixelSize: 10
                                        elide: Text.ElideRight
                                    }
                                }

                                Rectangle {
                                    id: peekSendButton
                                    objectName: "peekSendButton-" + root.safeText(delegateRoot.modelData.id)
                                    width: 60
                                    height: 32
                                    radius: 16
                                    color: delegateRoot.responding ? "#11161b" : "#131920"
                                    border.width: 1
                                    border.color: "#1a222b"
                                    opacity: (!delegateRoot.canSendPeek || delegateRoot.peekLocalDraft.trim() === "" || delegateRoot.responding) ? 0.4 : 1.0

                                    Text {
                                        anchors.centerIn: parent
                                        text: delegateRoot.responding ? "SENDING" : "SEND"
                                        color: "#c0c8cf"
                                        font.family: root.primaryFont
                                        font.pixelSize: 9
                                        font.bold: true
                                        font.letterSpacing: 0.7
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        enabled: delegateRoot.canSendPeek && delegateRoot.peekLocalDraft.trim() !== "" && !delegateRoot.responding
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: root.submitPeek(delegateRoot.modelData.id, peekInput.text)
                                    }
                                }
                            }
                        }
                    }

                    Rectangle {
                        visible: delegateRoot.showResponsePanel
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        anchors.leftMargin: 14
                        anchors.rightMargin: 14
                        anchors.bottomMargin: 10 + (delegateRoot.responding ? 40 : 0)
                        height: visible ? delegateRoot.responsePanelHeight : 0
                        radius: 11
                        color: "#06080b"
                        border.width: 1
                        border.color: delegateRoot.urgent ? "#51394214" : "#ffffff05"
                        clip: true

                        Column {
                            anchors.fill: parent
                            anchors.leftMargin: 11
                            anchors.rightMargin: 11
                            anchors.topMargin: 9
                            anchors.bottomMargin: 9
                            spacing: 7

                            Row {
                                width: parent.width
                                spacing: 7

                                Rectangle {
                                    width: Math.min(parent.width * 0.64, Math.max(170, reviewHeadline.implicitWidth + 24))
                                    height: 16
                                    radius: 8
                                    color: delegateRoot.urgent ? "#120d10" : "#0d1115"
                                    border.width: 1
                                    border.color: Qt.rgba(delegateRoot.accent.r, delegateRoot.accent.g, delegateRoot.accent.b, 0.10)

                                    Text {
                                        id: reviewHeadline
                                        width: parent.width - 12
                                        anchors.centerIn: parent
                                        text: root.sessionReviewHeadline(delegateRoot.modelData)
                                        color: delegateRoot.accent
                                        font.family: root.primaryFont
                                        font.pixelSize: 8
                                        font.bold: true
                                        font.letterSpacing: 0.7
                                        horizontalAlignment: Text.AlignHCenter
                                        elide: Text.ElideRight
                                    }
                                }
                            }

                            Text {
                                width: Math.max(96, parent.width - 180)
                                text: root.sessionReviewReason(delegateRoot.modelData)
                                color: root.inkMuted
                                font.family: root.primaryFont
                                font.pixelSize: 8
                                elide: Text.ElideRight
                            }

                            Text {
                                width: parent.width
                                text: root.sessionReviewCommand(delegateRoot.modelData)
                                color: root.inkStrong
                                font.family: root.primaryFont
                                font.pixelSize: 11
                                wrapMode: Text.WordWrap
                                maximumLineCount: 2
                                elide: Text.ElideRight
                                clip: true
                            }

                            Row {
                                width: parent.width
                                spacing: 7

                                Rectangle {
                                    width: Math.max(92, scopeValue.implicitWidth + 20)
                                    height: 15
                                    radius: 7.5
                                    color: "#0a0d11"
                                    border.width: 1
                                    border.color: "#ffffff05"

                                    Text {
                                        id: scopeValue
                                        width: parent.width - 12
                                        anchors.centerIn: parent
                                        text: root.sessionReviewScope(delegateRoot.modelData)
                                        color: root.inkDim
                                        font.family: root.primaryFont
                                        font.pixelSize: 5
                                        font.bold: true
                                        font.letterSpacing: 0.7
                                        horizontalAlignment: Text.AlignHCenter
                                        elide: Text.ElideRight
                                    }
                                }

                                Rectangle {
                                    width: Math.max(92, riskValue.implicitWidth + 20)
                                    height: 15
                                    radius: 7.5
                                    color: "#0a0d11"
                                    border.width: 1
                                    border.color: "#ffffff05"

                                    Text {
                                        id: riskValue
                                        width: parent.width - 12
                                        anchors.centerIn: parent
                                        text: root.sessionReviewRisk(delegateRoot.modelData)
                                        color: delegateRoot.accent
                                        font.family: root.primaryFont
                                        font.pixelSize: 5
                                        font.bold: true
                                        font.letterSpacing: 0.7
                                        horizontalAlignment: Text.AlignHCenter
                                        elide: Text.ElideRight
                                    }
                                }
                            }

                            Flow {
                                width: parent.width
                                spacing: 7
                                visible: !delegateRoot.showInlineReply

                                Repeater {
                                    model: root.sessionChoices(delegateRoot.modelData)

                                    delegate: Rectangle {
                                        id: inlineChoiceChip
                                        required property int index
                                        required property var modelData
                                        property int choiceNumber: index + 1
                                        property string choiceText: root.safeText(modelData)
                                        property bool destructive: choiceNumber === 3
                                        property bool secondary: choiceNumber === 2

                                        width: Math.min(delegateRoot.width - 56, Math.max(118, inlineChoiceLabel.implicitWidth + 32))
                                        height: 28
                                        radius: 14
                                        color: inlineChoiceChip.destructive ? "#100d10" : "#0b1015"
                                        border.width: 1
                                        border.color: inlineChoiceChip.destructive ? "#7d4d5a14" : (inlineChoiceChip.secondary ? "#5f95a912" : "#ffffff06")

                                        Text {
                                            id: inlineChoiceLabel
                                            width: parent.width - 20
                                            anchors.centerIn: parent
                                            text: inlineChoiceChip.choiceNumber + ". " + inlineChoiceChip.choiceText
                                            color: inlineChoiceChip.destructive ? root.accentRose : (inlineChoiceChip.secondary ? root.accentCyan : root.inkStrong)
                                            font.family: root.primaryFont
                                            font.pixelSize: 9
                                            font.bold: true
                                            font.letterSpacing: 0.6
                                            horizontalAlignment: Text.AlignHCenter
                                            elide: Text.ElideRight
                                        }

                                        MouseArea {
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: {
                                                if (root.sessionSupportsFollowup(
                                                            delegateRoot.modelData,
                                                            inlineChoiceChip.choiceNumber,
                                                            inlineChoiceChip.choiceText)) {
                                                    root.openPromptReply(inlineChoiceChip.choiceNumber, delegateRoot.modelData.id)
                                                    return
                                                }
                                                root.beginResponse(delegateRoot.modelData.id, root.choiceSubmitLabel(inlineChoiceChip.choiceNumber, inlineChoiceChip.choiceText))
                                                root.resetPromptReplyState()
                                                backend.respondToSession(delegateRoot.modelData.id, inlineChoiceChip.choiceNumber, inlineChoiceChip.choiceText)
                                            }
                                        }
                                    }
                                }
                            }

                            Column {
                                id: inlineReplyPanel
                                visible: delegateRoot.showInlineReply
                                spacing: 7

                                Component.onCompleted: {
                                    if (visible) {
                                        if (inlineReplyInput.text !== root.promptReplyDraft) {
                                            inlineReplyInput.text = root.promptReplyDraft
                                        }
                                        Qt.callLater(function() {
                                            inlineReplyInput.forceActiveFocus()
                                        })
                                    }
                                }

                                onVisibleChanged: {
                                    if (visible) {
                                        if (inlineReplyInput.text !== root.promptReplyDraft) {
                                            inlineReplyInput.text = root.promptReplyDraft
                                        }
                                        Qt.callLater(function() {
                                            inlineReplyInput.forceActiveFocus()
                                        })
                                    }
                                }

                                Text {
                                    width: parent.width
                                    text: root.safeText(delegateRoot.modelData.source).toLowerCase() === "claude"
                                          ? "Tell Claude what to do differently"
                                          : "Tell Codex what to do differently"
                                    color: root.inkStrong
                                    font.family: root.primaryFont
                                    font.pixelSize: 9
                                    font.bold: true
                                    font.letterSpacing: 0.8
                                    elide: Text.ElideRight
                                }

                                Rectangle {
                                    width: parent.width
                                    height: 30
                                    radius: 15
                                    color: "#070a0e"
                                    border.width: 1
                                    border.color: "#151b22"

                                    TextInput {
                                        id: inlineReplyInput
                                        anchors.fill: parent
                                        anchors.leftMargin: 11
                                        anchors.rightMargin: 11
                                        anchors.topMargin: 5
                                        anchors.bottomMargin: 5
                                        color: root.inkStrong
                                        font.family: root.primaryFont
                                        font.pixelSize: 9
                                        clip: true
                                        selectByMouse: true
                                        selectedTextColor: "#0d0e11"
                                        selectionColor: "#8bd3e4"
                                        focus: delegateRoot.showInlineReply
                                        onTextChanged: root.promptReplyDraft = text
                                        Component.onCompleted: {
                                            if (delegateRoot.showInlineReply && text !== root.promptReplyDraft) {
                                                text = root.promptReplyDraft
                                            }
                                        }
                                        Keys.onReturnPressed: function(event) {
                                            if (!event.isAutoRepeat) {
                                                root.submitPromptReply(delegateRoot.modelData.id)
                                                event.accepted = true
                                            }
                                        }
                                        Keys.onEnterPressed: function(event) {
                                            if (!event.isAutoRepeat) {
                                                root.submitPromptReply(delegateRoot.modelData.id)
                                                event.accepted = true
                                            }
                                        }
                                    }

                                    Text {
                                        anchors.verticalCenter: parent.verticalCenter
                                        anchors.left: parent.left
                                        anchors.leftMargin: 11
                                        visible: inlineReplyInput.text.length === 0
                                        text: "Describe what the agent should do instead..."
                                        color: root.inkDim
                                        font.family: root.primaryFont
                                        font.pixelSize: 8
                                    }
                                }

                                Row {
                                    spacing: 7

                                    Rectangle {
                                        width: 102
                                        height: 24
                                        radius: 12
                                        color: "#0d1115"
                                        border.width: 1
                                        border.color: "#4f809214"
                                        opacity: root.promptReplyDraft.trim() === "" ? 0.45 : 1.0

                                        Text {
                                            anchors.centerIn: parent
                                            text: "SEND REPLY"
                                            color: root.graphiteMuted
                                            font.family: root.primaryFont
                                            font.pixelSize: 8
                                            font.bold: true
                                            font.letterSpacing: 0.7
                                        }

                                        MouseArea {
                                            anchors.fill: parent
                                            enabled: root.promptReplyDraft.trim() !== ""
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: root.submitPromptReply(delegateRoot.modelData.id)
                                        }
                                    }

                                    Rectangle {
                                        width: 80
                                        height: 24
                                        radius: 12
                                        color: "#0b0f13"
                                        border.width: 1
                                        border.color: "#ffffff06"

                                        Text {
                                            anchors.centerIn: parent
                                            text: "CANCEL"
                                            color: root.inkMuted
                                            font.family: root.primaryFont
                                            font.pixelSize: 8
                                            font.bold: true
                                            font.letterSpacing: 0.7
                                        }

                                        MouseArea {
                                            anchors.fill: parent
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: root.resetPromptReplyState()
                                        }
                                    }
                                }
                            }

                            Rectangle {
                                visible: delegateRoot.responding
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.bottom: parent.bottom
                                anchors.leftMargin: 14
                                anchors.rightMargin: 14
                                anchors.bottomMargin: 10
                                height: 30
                                radius: 15
                                color: "#070a0e"
                                border.width: 1
                                border.color: Qt.rgba(delegateRoot.accent.r, delegateRoot.accent.g, delegateRoot.accent.b, 0.14)
                                opacity: 0.96

                                Rectangle {
                                    id: sendingDot
                                    width: 7
                                    height: 7
                                    radius: 3.5
                                    anchors.left: parent.left
                                    anchors.leftMargin: 11
                                    anchors.verticalCenter: parent.verticalCenter
                                    color: delegateRoot.accent

                                    SequentialAnimation on opacity {
                                        loops: Animation.Infinite
                                        running: delegateRoot.responding
                                        NumberAnimation { from: 0.35; to: 1.0; duration: 380 }
                                        NumberAnimation { from: 1.0; to: 0.35; duration: 380 }
                                    }
                                }

                                Text {
                                    anchors.left: sendingDot.right
                                    anchors.leftMargin: 9
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: Math.max(0, parent.width - 120)
                                    text: root.responseBadgeLabel(delegateRoot.modelData.id)
                                    color: "#d6dce2"
                                    font.family: root.primaryFont
                                    font.pixelSize: 8
                                    font.bold: true
                                    font.letterSpacing: 0.8
                                    elide: Text.ElideRight
                                }

                                Text {
                                    anchors.right: parent.right
                                    anchors.rightMargin: 11
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "ISLAND LINK"
                                    color: "#66717a"
                                    font.family: root.primaryFont
                                    font.pixelSize: 7
                                    font.letterSpacing: 0.9
                                }
                            }
                        }
                    }
                }
            }

            Item {
                anchors.fill: sessionList
                visible: root.sessionItems().length === 0

                Column {
                    anchors.centerIn: parent
                    spacing: 10

                    Rectangle {
                        width: 42
                        height: 42
                        radius: 15
                        anchors.horizontalCenter: parent.horizontalCenter
                        color: "#ffffff08"
                        border.width: 1
                        border.color: "#ffffff12"

                        Item {
                            anchors.centerIn: parent
                            width: 20
                            height: 14

                            Repeater {
                                model: [
                                    { "x": 0, "y": 0 },
                                    { "x": 6, "y": 0 },
                                    { "x": 12, "y": 0 },
                                    { "x": 18, "y": 0 },
                                    { "x": 0, "y": 6 },
                                    { "x": 12, "y": 6 },
                                    { "x": 18, "y": 6 }
                                ]

                                delegate: Rectangle {
                                    x: modelData.x
                                    y: modelData.y
                                    width: 4
                                    height: 4
                                    radius: 1
                                    color: "#8fe2ff"
                                    opacity: index > 3 ? 0.68 : 1.0
                                }
                            }
                        }
                    }

                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "WAITING FOR YOUR AGENTS"
                        color: "#eaf1f7"
                        font.family: root.primaryFont
                        font.pixelSize: 13
                        font.bold: true
                        font.letterSpacing: 1.3
                    }

                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "Launch Claude Code or Codex and the island will wake up."
                        color: "#7b8189"
                        font.family: root.primaryFont
                        font.pixelSize: 11
                        font.letterSpacing: 0.8
                    }
                }
            }

            MouseArea {
                visible: backend.expanded
                anchors.left: parent.left
                y: bodyPanel.y
                height: Math.max(0, parent.height - bodyPanel.y)
                width: 8
                hoverEnabled: true
                cursorShape: Qt.SizeHorCursor
                onPressed: {
                    root.resizingWindow = root.startSystemResize(Qt.LeftEdge)
                }
                onReleased: {
                    root.resizingWindow = false
                    root.schedulePersist()
                }
            }

            MouseArea {
                visible: backend.expanded
                anchors.right: parent.right
                y: bodyPanel.y
                height: Math.max(0, parent.height - bodyPanel.y)
                width: 8
                hoverEnabled: true
                cursorShape: Qt.SizeHorCursor
                onPressed: {
                    root.resizingWindow = root.startSystemResize(Qt.RightEdge)
                }
                onReleased: {
                    root.resizingWindow = false
                    root.schedulePersist()
                }
            }

            MouseArea {
                visible: backend.expanded
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: 10
                hoverEnabled: true
                cursorShape: Qt.SizeVerCursor
                onPressed: {
                    root.resizingWindow = root.startSystemResize(Qt.BottomEdge)
                }
                onReleased: {
                    root.resizingWindow = false
                    root.schedulePersist()
                }
            }

            MouseArea {
                visible: backend.expanded
                anchors.left: parent.left
                anchors.bottom: parent.bottom
                width: 16
                height: 16
                hoverEnabled: true
                cursorShape: Qt.SizeBDiagCursor
                onPressed: {
                    root.resizingWindow = root.startSystemResize(Qt.LeftEdge | Qt.BottomEdge)
                }
                onReleased: {
                    root.resizingWindow = false
                    root.schedulePersist()
                }
            }

            MouseArea {
                visible: backend.expanded
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                width: 16
                height: 16
                hoverEnabled: true
                cursorShape: Qt.SizeFDiagCursor
                onPressed: {
                    root.resizingWindow = root.startSystemResize(Qt.RightEdge | Qt.BottomEdge)
                }
                onReleased: {
                    root.resizingWindow = false
                    root.schedulePersist()
                }
            }
        }
    }
}
