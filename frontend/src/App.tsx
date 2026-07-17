import {
  Menu,
  Code2,
  Send,
  Square,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api/client";
import { ConfirmDialog } from "./components/ConfirmDialog";
import { DslDesigner } from "./components/DslDesigner";
import { MessageList } from "./components/MessageList";
import { Pipeline } from "./components/Pipeline";
import { Sidebar } from "./components/Sidebar";
import { WorkflowControls } from "./components/WorkflowControls";
import { useWorkflowStream } from "./hooks/useWorkflowStream";
import type {
  Conversation,
  Crew,
  Message,
  Workflow,
  WorkflowControl,
  WorkflowInputs,
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
  if (workflow.ui.target_models?.length) {
    return [{
      key: "target_model",
      label: "目标模型",
      type: "select",
      default: workflow.ui.default_target_model,
      options: workflow.ui.target_models,
    }];
  }
  return [];
}

function initialInputs(controls: WorkflowControl[], current: WorkflowInputs = {}) {
  return Object.fromEntries(
    controls.map((control) => {
      const options = control.options.map((option) => option.value);
      const previous = current[control.key];
      const value = options.includes(previous)
        ? previous
        : control.default ?? control.options[0]?.value ?? "";
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
  const [view, setView] = useState<"runtime" | "designer">("runtime");
  const stream = useWorkflowStream();

  const selectedWorkflow = workflows.find((workflow) => workflow.name === workflowName);
  const selectedCrew = crews.find((crew) => crew.id === crewId);
  const controls = useMemo(() => controlsFor(selectedWorkflow), [selectedWorkflow]);
  const currentConversation = conversations.find((item) => item.id === conversationId);
  const busy = loading || stream.running;

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

  async function sendMessage() {
    const message = draft.trim();
    if (!message || !selectedCrew || !selectedWorkflow || stream.running) return;
    setError("");
    setDraft("");
    let targetConversationId = conversationId;
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
      setMessages((current) => [...current, optimisticUser]);
      const result = await stream.run(targetConversationId, message, workflowInputs);
      setMessages((current) => [
        ...current,
        {
          ...optimisticUser,
          id: `local-result-${crypto.randomUUID()}`,
          role: "assistant",
          content: result || "工作流已完成，但没有返回提示词。",
        },
      ]);
      const [history] = await Promise.all([api.messages(targetConversationId), loadConversations()]);
      setMessages(history);
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      reportError(reason);
    }
  }

  if (view === "designer") {
    return <DslDesigner onClose={() => setView("runtime")} onGenerated={reloadDefinitions} />;
  }

  return (
    <main className="app-shell">
      <div className={`sidebar-backdrop ${sidebarOpen ? "visible" : ""}`} onClick={() => setSidebarOpen(false)} />
      <div className={`sidebar-wrap ${sidebarOpen ? "open" : ""}`}>
        <Sidebar
          busy={busy}
          conversations={conversations}
          crewId={crewId}
          crews={crews}
          currentConversationId={conversationId}
          onCreateCrew={() => void createSampleCrew()}
          onCrewChange={changeCrew}
          onDeleteConversation={confirmDeleteConversation}
          onDeleteCrew={confirmDeleteCrew}
          onNewConversation={resetConversation}
          onOpenConversation={(id) => void openConversation(id)}
          onRefresh={() => void loadConversations()}
          onUserIdChange={(value) => { setUserId(value); localStorage.setItem("workflow-user-id", value); resetConversation(); }}
          onWorkflowChange={(value) => void changeWorkflow(value)}
          userId={userId}
          workflowName={workflowName}
          workflows={workflows}
        />
      </div>

      <section className="workbench">
        <header className="workbench-header">
          <div className="header-title">
            <button className="mobile-menu-button" onClick={() => setSidebarOpen(true)} title="打开导航" type="button"><Menu size={19} /></button>
            <div>
              <span className="eyebrow">{selectedWorkflow?.name ?? "WORKFLOW"}</span>
              <h1>{currentConversation?.title || selectedWorkflow?.ui.title || "新建工作流任务"}</h1>
              <p>{conversationId || selectedWorkflow?.ui.description || "选择 Crew 后开始"}</p>
            </div>
          </div>
          <div className="header-tools">
            <WorkflowControls
              controls={controls}
              disabled={stream.running}
              onChange={(key, value) => setWorkflowInputs((current) => ({ ...current, [key]: value }))}
              values={workflowInputs}
            />
            <div className="turn-actions">
              <button className="icon-button light" onClick={() => setView("designer")} title="打开 DSL 设计器" type="button"><Code2 size={16} /></button>
              <button className="icon-button light danger" disabled={!conversationId || busy} onClick={() => conversationId && confirmDeleteConversation(conversationId)} title="删除当前会话" type="button"><Trash2 size={16} /></button>
            </div>
          </div>
        </header>

        {error && <div className="error-banner"><span>{error}</span><button onClick={() => setError("")} type="button">关闭</button></div>}
        <Pipeline
          durations={stream.nodeDurations}
          executionKey={stream.executionKey}
          onClear={stream.clear}
          selectedEdges={stream.selectedEdges}
          statuses={stream.nodeStatuses}
          workflow={selectedWorkflow}
        />
        <MessageList
          messages={messages}
          onDeleteLatestTurn={confirmDeleteLatestTurn}
          onRewind={confirmRewind}
          pending={stream.running}
        />

        <form className="composer" onSubmit={(event) => { event.preventDefault(); void sendMessage(); }}>
          <textarea
            disabled={!selectedCrew}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                void sendMessage();
              }
            }}
            placeholder={selectedWorkflow?.ui.input_placeholder || "输入要交给工作流处理的任务……"}
            rows={3}
            value={draft}
          />
          <div className="composer-footer">
            <span>{selectedWorkflow?.ui.input_hint || "消息将按当前工作流执行"}</span>
            {stream.running ? (
              <button className="stop-button" onClick={stream.cancel} type="button"><Square size={14} fill="currentColor" />停止</button>
            ) : (
              <button className="send-button" disabled={!draft.trim() || !selectedCrew || loading} type="submit">运行工作流<Send size={15} /></button>
            )}
          </div>
        </form>
      </section>

      <ConfirmDialog
        confirmLabel={confirmation?.confirmLabel}
        description={confirmation?.description ?? ""}
        onCancel={() => setConfirmation(null)}
        onConfirm={() => void executeConfirmation()}
        open={Boolean(confirmation)}
        title={confirmation?.title ?? "确认操作"}
      />
    </main>
  );
}
