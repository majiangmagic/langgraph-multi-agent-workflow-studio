import {
  Menu,
  Moon,
  PanelRightOpen,
  Plus,
  Sun,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api/client";
import { AssistantChat } from "./components/AssistantChat";
import { ConfirmDialog } from "./components/ConfirmDialog";
import { DslDesigner } from "./components/DslDesigner";
import { ExecutionInspector } from "./components/ExecutionInspector";
import { Sidebar } from "./components/Sidebar";
import { WorkflowControls } from "./components/WorkflowControls";
import { WorkflowInterruptDialog } from "./components/WorkflowInterruptDialog";
import { useWorkflowStream } from "./hooks/useWorkflowStream";
import type {
  Conversation,
  Crew,
  Message,
  Workflow,
  WorkflowControl,
  WorkflowInputs,
  WorkflowInterrupt,
  WorkflowResultMetadata,
} from "./types";

type Confirmation = {
  title: string;
  description: string;
  confirmLabel?: string;
  action: () => Promise<void>;
};

function controlsFor(workflow?: Workflow): WorkflowControl[] {
  if (!workflow) return [];
  if (workflow.ui.controls?.length) return workflow.ui.controls;
  return [];
}

function initialInputs(controls: WorkflowControl[], current: WorkflowInputs = {}) {
  return Object.fromEntries(
    controls.map((control) => {
      const controlOptions = control.options ?? [];
      const options = controlOptions.map((option) => option.value);
      const previous = current[control.key];
      const value = typeof previous === "string" && (!options.length || options.includes(previous))
        ? previous
        : control.default ?? controlOptions[0]?.value ?? "";
      return [control.key, value];
    }),
  );
}

export default function App() {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [crews, setCrews] = useState<Crew[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [workflowName, setWorkflowName] = useState("");
  const [crewId, setCrewId] = useState("");
  const [userId, setUserId] = useState(() => localStorage.getItem("workflow-user-id") || "local-user");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [workflowInputs, setWorkflowInputs] = useState<WorkflowInputs>({});
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(() => window.innerWidth > 1100);
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    const saved = localStorage.getItem("workflow-theme");
    if (saved === "light" || saved === "dark") return saved;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });
  const [view, setView] = useState<"runtime" | "designer">("runtime");
  const [dismissedInterrupt, setDismissedInterrupt] = useState("");
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const stream = useWorkflowStream();

  const selectedWorkflow = workflows.find((workflow) => workflow.name === workflowName);
  const selectedCrew = crews.find((crew) => crew.id === crewId);
  const controls = useMemo(() => controlsFor(selectedWorkflow), [selectedWorkflow]);
  const currentConversation = conversations.find((item) => item.id === conversationId);
  const busy = loading || stream.running;
  const latestAssistant = [...messages].reverse().find((message) => message.role === "assistant");
  const latestWorkflowResult = latestAssistant?.metadata?.workflow_result as WorkflowResultMetadata | undefined;
  const pendingInterrupt: WorkflowInterrupt | null = latestWorkflowResult?.resumable
    ? latestWorkflowResult.interrupt ?? latestWorkflowResult.clarification_request ?? null
    : null;
  const interruptKey = pendingInterrupt
    ? pendingInterrupt.id || pendingInterrupt.question
    : "";
  const visibleInterrupt = pendingInterrupt && interruptKey !== dismissedInterrupt
    ? pendingInterrupt as WorkflowInterrupt
    : null;

  const reportError = useCallback((reason: unknown) => {
    setError(reason instanceof Error ? reason.message : String(reason));
  }, []);

  useEffect(() => {
    async function bootstrap() {
      try {
        const [workflowData, crewData] = await Promise.all([api.workflows(), api.crews()]);
        setWorkflows(workflowData);
        setCrews(crewData);
        const firstCrew = crewData[0];
        const crewWorkflow = firstCrew?.workflow_type || "";
        const defaultWorkflow = workflowData.find((item) => item.name === crewWorkflow)
          ?? workflowData.find((item) => item.is_default)
          ?? workflowData[0];
        setCrewId(firstCrew?.id ?? "");
        setWorkflowName(defaultWorkflow?.name ?? "");
      } catch (reason) {
        reportError(reason);
      } finally {
        setLoading(false);
      }
    }
    void bootstrap();
  }, [reportError]);

  useEffect(() => {
    setWorkflowInputs((current) => initialInputs(controls, current));
  }, [controls]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("workflow-theme", theme);
  }, [theme]);

  const loadConversations = useCallback(async () => {
    if (!crewId || !userId.trim()) {
      setConversations([]);
      return;
    }
    try {
      setConversations(await api.conversations(userId.trim(), crewId));
    } catch (reason) {
      reportError(reason);
    }
  }, [crewId, reportError, userId]);

  const reloadDefinitions = useCallback(async () => {
    const [workflowData, crewData] = await Promise.all([api.workflows(), api.crews()]);
    setWorkflows(workflowData);
    setCrews(crewData);
  }, []);

  useEffect(() => {
    void loadConversations();
  }, [loadConversations]);

  function resetConversation() {
    setConversationId(null);
    setMessages([]);
    setDraft("");
    stream.clear();
    setSidebarOpen(false);
    setDismissedInterrupt("");
  }

  function changeCrew(value: string) {
    const crew = crews.find((item) => item.id === value);
    const crewWorkflow = crew?.workflow_type || "";
    setCrewId(value);
    if (workflows.some((workflow) => workflow.name === crewWorkflow)) {
      setWorkflowName(crewWorkflow);
    } else {
      setWorkflowName("");
    }
    resetConversation();
  }

  async function changeWorkflow(value: string) {
    setWorkflowName(value);
    if (selectedCrew && selectedCrew.workflow_type !== value) {
      try {
        const updated = await api.updateCrewWorkflow(selectedCrew, value);
        setCrews((current) => current.map((crew) => crew.id === updated.id ? updated : crew));
      } catch (reason) {
        reportError(reason);
      }
    }
    resetConversation();
  }

  async function openConversation(id: string) {
    try {
      const history = await api.messages(id);
      setConversationId(id);
      setMessages(history);
      const latestInputs = [...history]
        .reverse()
        .find((message) => message.role === "user")
        ?.metadata?.workflow_inputs;
      if (latestInputs && typeof latestInputs === "object") {
        setWorkflowInputs(initialInputs(controls, latestInputs as WorkflowInputs));
      }
      stream.clear();
      setDismissedInterrupt("");
      setSidebarOpen(false);
    } catch (reason) {
      reportError(reason);
    }
  }

  async function createSampleCrew() {
    if (!workflowName) return;
    try {
      setLoading(true);
      const crew = await api.createSampleCrew(workflowName);
      const crewData = await api.crews();
      setCrews(crewData);
      setCrewId(crew.id);
      resetConversation();
    } catch (reason) {
      reportError(reason);
    } finally {
      setLoading(false);
    }
  }

  function confirmDeleteCrew() {
    if (!selectedCrew) return;
    setConfirmation({
      title: "删除 Crew",
        description: `Crew“${selectedCrew.name}”及其全部会话将被永久删除。`,
      action: async () => {
        await api.deleteCrew(selectedCrew.id);
        const crewData = await api.crews();
        setCrews(crewData);
        setCrewId(crewData[0]?.id ?? "");
        resetConversation();
      },
    });
  }

  function confirmDeleteConversation(id: string) {
    const conversation = conversations.find((item) => item.id === id);
    setConfirmation({
      title: "删除会话",
      description: `会话“${conversation?.title || "未命名会话"}”及全部消息将被永久删除。`,
      action: async () => {
        await api.deleteConversation(id);
        if (conversationId === id) resetConversation();
        await loadConversations();
      },
    });
  }

  function confirmDeleteLatestTurn() {
    if (!conversationId) return;
    setConfirmation({
      title: "删除最后一轮",
      description: "将删除当前会话最后一条用户消息和对应的工作流结果。",
      confirmLabel: "删除本轮",
      action: async () => {
        await api.deleteLatestTurn(conversationId);
        const history = await api.messages(conversationId);
        setMessages(history);
        await loadConversations();
      },
    });
  }

  function confirmRewind(message: Message) {
    if (!conversationId) return;
    setConfirmation({
      title: "回溯到这一轮",
      description: "将删除这条用户消息及其后的所有消息，并同步重置该会话的短期记忆。原问题会放回输入框。",
      confirmLabel: "确认回溯",
      action: async () => {
        await api.rewindConversation(conversationId, message.id);
        setMessages(await api.messages(conversationId));
        setDraft(message.content);
        stream.clear();
        await loadConversations();
      },
    });
  }

  async function executeConfirmation() {
    if (!confirmation) return;
    const action = confirmation.action;
    setConfirmation(null);
    try {
      setLoading(true);
      await action();
    } catch (reason) {
      reportError(reason);
    } finally {
      setLoading(false);
    }
  }

  async function sendMessage(messageOverride?: string) {
    const message = (messageOverride ?? draft).trim();
    if (!message || !selectedCrew || !selectedWorkflow || stream.running) return;
    if (pendingInterrupt && conversationId) {
      setDraft("");
      await resumeWorkflow(message);
      return;
    }
    setError("");
    setDraft("");
    let targetConversationId = conversationId;
    let optimisticAssistantId = "";
    try {
      if (!targetConversationId) {
        let crew = selectedCrew;
        if (crew.workflow_type !== selectedWorkflow.name) {
          crew = await api.updateCrewWorkflow(crew, selectedWorkflow.name);
          setCrews((current) => current.map((item) => item.id === crew.id ? crew : item));
        }
        const conversation = await api.createConversation(userId.trim(), crew.id, message.slice(0, 40));
        targetConversationId = conversation.id;
        setConversationId(conversation.id);
        setConversations((current) => [conversation, ...current]);
      }
      const optimisticUser: Message = {
        id: `local-${crypto.randomUUID()}`,
        conversation_id: targetConversationId,
        role: "user",
        content: message,
        status: "completed",
        metadata: { workflow_inputs: workflowInputs },
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      optimisticAssistantId = `local-result-${crypto.randomUUID()}`;
      const optimisticAssistant: Message = {
        ...optimisticUser,
        id: optimisticAssistantId,
        role: "assistant",
        content: "",
        status: "processing",
      };
      setMessages((current) => [...current, optimisticUser, optimisticAssistant]);
      const result = await stream.run(targetConversationId, message, workflowInputs, false, {
        onDelta: (delta) => setMessages((current) => current.map((item) =>
          item.id === optimisticAssistantId
            ? { ...item, content: item.content + delta }
            : item
        )),
      });
      setMessages((current) => current.map((item) =>
        item.id === optimisticAssistantId
          ? {
              ...item,
              content: result || "工作流已完成，但没有返回内容。",
              status: "completed",
            }
          : item
      ));
      const [history] = await Promise.all([api.messages(targetConversationId), loadConversations()]);
      setMessages(history);
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") {
        setMessages((current) => current.map((item) =>
          item.id === optimisticAssistantId ? { ...item, status: "failed", metadata: { ...item.metadata, cancelled: true } } : item
        ));
        return;
      }
      setMessages((current) => current.map((item) =>
        item.id === optimisticAssistantId ? { ...item, status: "failed" } : item
      ));
      reportError(reason);
    }
  }

  async function resumeWorkflow(response: string) {
    const answer = response.trim();
    if (!answer || !conversationId || stream.running) return;
    setError("");
    setDismissedInterrupt(interruptKey);
    const optimisticUser: Message = {
      id: `local-${crypto.randomUUID()}`,
      conversation_id: conversationId,
      role: "user",
      content: answer,
      status: "completed",
      metadata: { workflow_resume: true },
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    const optimisticAssistantId = `local-result-${crypto.randomUUID()}`;
    const optimisticAssistant: Message = {
      ...optimisticUser,
      id: optimisticAssistantId,
      role: "assistant",
      content: "",
      status: "processing",
    };
    setMessages((current) => [...current, optimisticUser, optimisticAssistant]);
    try {
      const result = await stream.run(conversationId, answer, workflowInputs, true, {
        onDelta: (delta) => setMessages((current) => current.map((item) =>
          item.id === optimisticAssistantId
            ? { ...item, content: item.content + delta }
            : item
        )),
      });
      setMessages((current) => current.map((item) =>
        item.id === optimisticAssistantId
          ? { ...item, content: result, status: "completed" }
          : item
      ));
      const [history] = await Promise.all([
        api.messages(conversationId),
        loadConversations(),
      ]);
      setMessages(history);
      setDismissedInterrupt("");
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") {
        setMessages((current) => current.map((item) =>
          item.id === optimisticAssistantId ? { ...item, status: "failed", metadata: { ...item.metadata, cancelled: true } } : item
        ));
        return;
      }
      setMessages((current) => current.map((item) =>
        item.id === optimisticAssistantId ? { ...item, status: "failed" } : item
      ));
      setDismissedInterrupt("");
      reportError(reason);
    }
  }

  function explainClarification() {
    if (pendingInterrupt) {
      setDismissedInterrupt("");
      return;
    }
    setDraft("补充说明，其他画面内容保持不变：");
    window.setTimeout(() => composerRef.current?.focus(), 0);
  }

  function retryClarification() {
    const latestUserMessage = [...messages]
      .reverse()
      .find((message) => message.role === "user")
      ?.content
      ?.trim();
    if (latestUserMessage) void sendMessage(latestUserMessage);
  }

  if (view === "designer") {
    return <DslDesigner onClose={() => setView("runtime")} onGenerated={reloadDefinitions} />;
  }

  return (
    <main className={`app-shell ${inspectorOpen ? "inspector-visible" : ""}`}>
      <div className={`sidebar-backdrop ${sidebarOpen ? "visible" : ""}`} onClick={() => setSidebarOpen(false)} />
      <div className={`sidebar-wrap ${sidebarOpen ? "open" : ""}`}>
        <Sidebar
          busy={busy}
          conversations={conversations}
          currentConversationId={conversationId}
          onDeleteConversation={confirmDeleteConversation}
          onNewConversation={resetConversation}
          onOpenConversation={(id) => void openConversation(id)}
          onOpenDesigner={() => setView("designer")}
          onRefresh={() => void loadConversations()}
          onUserIdChange={(value) => { setUserId(value); localStorage.setItem("workflow-user-id", value); resetConversation(); }}
          userId={userId}
        />
      </div>

      <section className="workbench">
        <header className="workbench-header">
          <div className="header-primary">
            <div className="header-title">
              <button className="mobile-menu-button" onClick={() => setSidebarOpen(true)} title="打开导航" type="button"><Menu size={19} /></button>
              <div>
                <span className="eyebrow">{selectedWorkflow?.name ?? "WORKFLOW"}</span>
                <h1>{currentConversation?.title || selectedWorkflow?.ui.title || "新建工作流任务"}</h1>
                <p>{conversationId || selectedWorkflow?.ui.description || "选择 Crew 后开始"}</p>
              </div>
            </div>
            <div className="turn-actions">
              <button className="icon-button light" onClick={() => setTheme((current) => current === "dark" ? "light" : "dark")} title={theme === "dark" ? "切换到浅色主题" : "切换到深色主题"} type="button">
                {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
              </button>
              <button className={`icon-button light ${inspectorOpen ? "active" : ""}`} onClick={() => setInspectorOpen((open) => !open)} title="切换运行检查器" type="button"><PanelRightOpen size={16} /></button>
              <button className="icon-button light danger" disabled={!conversationId || busy} onClick={() => conversationId && confirmDeleteConversation(conversationId)} title="删除当前会话" type="button"><Trash2 size={16} /></button>
            </div>
          </div>
          <div className="header-config">
            <div className="workspace-pickers">
              <label>
                <span>Crew</span>
                <select disabled={stream.running} onChange={(event) => changeCrew(event.target.value)} value={crewId}>
                  {!crews.length && <option value="">暂无 Crew</option>}
                  {crews.map((crew) => (
                    <option key={crew.id} value={crew.id}>
                      {crew.name}{crew.workflow_missing ? `（缺失：${crew.workflow_type}）` : ""}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>工作流</span>
                <select disabled={stream.running} onChange={(event) => void changeWorkflow(event.target.value)} value={workflowName}>
                  {!workflowName && crewId && <option value="">请选择可用工作流</option>}
                  {workflows.map((workflow) => (
                    <option key={workflow.name} value={workflow.name}>{workflow.ui.title ?? workflow.name}</option>
                  ))}
                </select>
              </label>
              <button className="icon-button light" disabled={!workflowName || busy} onClick={() => void createSampleCrew()} title="创建示例 Crew" type="button"><Plus size={16} /></button>
              <button className="icon-button light danger" disabled={!crewId || busy} onClick={confirmDeleteCrew} title="删除 Crew" type="button"><Trash2 size={16} /></button>
            </div>
            <WorkflowControls
              controls={controls}
              disabled={stream.running}
              onChange={(key, value) => setWorkflowInputs((current) => ({ ...current, [key]: value }))}
              values={workflowInputs}
            />
          </div>
        </header>

        {error && <div className="error-banner"><span>{error}</span><button onClick={() => setError("")} type="button">关闭</button></div>}
        <AssistantChat
          composerRef={composerRef}
          disabled={!selectedCrew}
          draft={draft}
          emptyDescription={selectedWorkflow?.ui.description || "选择 Crew 和 Workflow 后开始执行任务。"}
          emptyTitle={selectedWorkflow?.ui.title || "从哪里开始？"}
          hint={selectedWorkflow?.ui.input_hint || "消息将按当前工作流执行"}
          messages={messages}
          onClarificationExplain={explainClarification}
          onClarificationReply={(reply) => pendingInterrupt
            ? void resumeWorkflow(reply)
            : void sendMessage(reply)}
          onClarificationRetry={retryClarification}
          onCancel={stream.cancel}
          onDeleteLatestTurn={confirmDeleteLatestTurn}
          onRewind={confirmRewind}
          onSend={sendMessage}
          pending={stream.running}
          placeholder={selectedWorkflow?.ui.input_placeholder || "输入要交给工作流处理的任务…"}
        />
      </section>

      <button className={`inspector-backdrop ${inspectorOpen ? "visible" : ""}`} aria-label="关闭运行检查器" onClick={() => setInspectorOpen(false)} type="button" />
      <ExecutionInspector
        dark={theme === "dark"}
        durations={stream.nodeDurations}
        events={stream.runtimeEvents}
        onClear={stream.clear}
        onClose={() => setInspectorOpen(false)}
        open={inspectorOpen}
        runError={stream.runError}
        runStatus={stream.runStatus}
        selectedEdges={stream.selectedEdges}
        statuses={stream.nodeStatuses}
        workflow={selectedWorkflow}
      />

      <ConfirmDialog
        confirmLabel={confirmation?.confirmLabel}
        description={confirmation?.description ?? ""}
        onCancel={() => setConfirmation(null)}
        onConfirm={() => void executeConfirmation()}
        open={Boolean(confirmation)}
        title={confirmation?.title ?? "确认操作"}
      />
      <WorkflowInterruptDialog
        busy={stream.running}
        interrupt={visibleInterrupt}
        onClose={() => setDismissedInterrupt(interruptKey)}
        onSubmit={(response) => void resumeWorkflow(response)}
      />
    </main>
  );
}
