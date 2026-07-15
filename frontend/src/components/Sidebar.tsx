import {
  Bot,
  Plus,
  RefreshCw,
  Sparkles,
  Trash2,
  Workflow as WorkflowIcon,
} from "lucide-react";
import type { Conversation, Crew, Workflow } from "../types";

function formatTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleString("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
}

type Props = {
  workflows: Workflow[];
  workflowName: string;
  crews: Crew[];
  crewId: string;
  userId: string;
  conversations: Conversation[];
  currentConversationId: string | null;
  busy: boolean;
  onWorkflowChange: (value: string) => void;
  onCrewChange: (value: string) => void;
  onUserIdChange: (value: string) => void;
  onCreateCrew: () => void;
  onDeleteCrew: () => void;
  onNewConversation: () => void;
  onRefresh: () => void;
  onOpenConversation: (id: string) => void;
  onDeleteConversation: (id: string) => void;
};

export function Sidebar(props: Props) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark"><WorkflowIcon size={19} /></div>
        <div>
          <strong>Agent Workflow</strong>
          <span><i className={props.busy ? "busy" : ""} />{props.busy ? "工作流运行中" : "本地服务已连接"}</span>
        </div>
      </div>

      <div className="workspace-settings">
        <label>
          <span>用户标识</span>
          <input autoComplete="off" onChange={(event) => props.onUserIdChange(event.target.value)} value={props.userId} />
        </label>
        <label>
          <span>工作流</span>
          <select onChange={(event) => props.onWorkflowChange(event.target.value)} value={props.workflowName}>
            {!props.workflowName && props.crewId && <option value="">当前 Crew 的工作流缺失，请选择替代项</option>}
            {props.workflows.map((workflow) => (
              <option key={workflow.name} value={workflow.name}>{workflow.ui.title ?? workflow.name}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Crew</span>
          <select onChange={(event) => props.onCrewChange(event.target.value)} value={props.crewId}>
            {!props.crews.length && <option value="">暂无 Crew</option>}
            {props.crews.map((crew) => (
              <option key={crew.id} value={crew.id}>
                {crew.name}{crew.workflow_missing ? `（缺失：${crew.workflow_type}）` : ""}
              </option>
            ))}
          </select>
        </label>
        {props.crews.find((crew) => crew.id === props.crewId)?.workflow_missing && (
          <div className="workflow-missing-notice">本地未注册该 Crew 引用的工作流，选择一个可用工作流后才能运行。</div>
        )}
        <div className="crew-actions">
          <button className="create-crew-button" disabled={!props.workflowName || props.busy} onClick={props.onCreateCrew} type="button">
            <Sparkles size={15} />创建示例 Crew
          </button>
          <button className="icon-button danger" disabled={!props.crewId || props.busy} onClick={props.onDeleteCrew} title="删除 Crew" type="button">
            <Trash2 size={16} />
          </button>
        </div>
      </div>

      <div className="history-heading">
        <div><Bot size={15} /><span>最近会话</span></div>
        <div>
          <button className="icon-button" onClick={props.onNewConversation} title="新建会话" type="button"><Plus size={16} /></button>
          <button className="icon-button" onClick={props.onRefresh} title="刷新会话" type="button"><RefreshCw size={15} /></button>
        </div>
      </div>

      <div className="conversation-list">
        {!props.conversations.length && <div className="sidebar-empty">暂无历史会话</div>}
        {props.conversations.map((conversation) => (
          <div className={`conversation-row ${conversation.id === props.currentConversationId ? "active" : ""}`} key={conversation.id}>
            <button className="conversation-item" onClick={() => props.onOpenConversation(conversation.id)} type="button">
              <span>{conversation.title || "未命名会话"}</span>
              <small>{formatTime(conversation.updated_at || conversation.created_at)}</small>
            </button>
            <button className="delete-conversation-button" onClick={() => props.onDeleteConversation(conversation.id)} title="删除会话" type="button">
              <Trash2 size={14} />
            </button>
          </div>
        ))}
      </div>
    </aside>
  );
}
