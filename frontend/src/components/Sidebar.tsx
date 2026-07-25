import { Bot, Code2, MessageSquare, Plus, RefreshCw, Trash2 } from "lucide-react";
import type { Conversation } from "../types";

function formatTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleString("zh-CN", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

type Props = {
  userId: string;
  conversations: Conversation[];
  currentConversationId: string | null;
  busy: boolean;
  onUserIdChange: (value: string) => void;
  onNewConversation: () => void;
  onRefresh: () => void;
  onOpenDesigner: () => void;
  onOpenConversation: (id: string) => void;
  onDeleteConversation: (id: string) => void;
};

export function Sidebar(props: Props) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark"><strong>LG</strong><i /></div>
        <div>
          <strong>LANGGRAPH</strong>
          <small>WORKFLOW STUDIO</small>
          <span><i className={props.busy ? "busy" : ""} />{props.busy ? "工作流运行中" : "本地服务已连接"}</span>
        </div>
      </div>

      <nav className="primary-navigation" aria-label="工作区导航">
        <button className="active" type="button"><small>01</small><MessageSquare size={16} /><span>运行台</span></button>
        <button onClick={props.onOpenDesigner} type="button"><small>02</small><Code2 size={16} /><span>DSL 设计器</span></button>
      </nav>

      <button className="new-chat-button" onClick={props.onNewConversation} type="button"><Plus size={16} /><span>新建任务</span><small>NEW RUN</small></button>

      <div className="history-heading">
        <div><Bot size={15} /><span>最近会话</span></div>
        <button className="icon-button" onClick={props.onRefresh} title="刷新会话" type="button"><RefreshCw size={15} /></button>
      </div>

      <div className="conversation-list">
        {!props.conversations.length && <div className="sidebar-empty">暂无历史会话</div>}
        {props.conversations.map((conversation) => (
          <div className={`conversation-row ${conversation.id === props.currentConversationId ? "active" : ""}`} key={conversation.id}>
            <button className="conversation-item" onClick={() => props.onOpenConversation(conversation.id)} type="button">
              <span>{conversation.title || "未命名会话"}</span>
              <small>{formatTime(conversation.updated_at || conversation.created_at)}</small>
            </button>
            <button className="delete-conversation-button" onClick={() => props.onDeleteConversation(conversation.id)} title="删除会话" type="button"><Trash2 size={14} /></button>
          </div>
        ))}
      </div>

      <label className="sidebar-user">
        <span>用户标识</span>
        <input autoComplete="off" onChange={(event) => props.onUserIdChange(event.target.value)} value={props.userId} />
      </label>
    </aside>
  );
}
