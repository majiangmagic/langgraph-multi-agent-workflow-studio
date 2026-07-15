import { Bot, History, Trash2, UserRound } from "lucide-react";
import { useEffect, useRef } from "react";
import type { Message } from "../types";
import { PromptResult } from "./PromptResult";

export function MessageList({
  messages,
  pending,
  onRewind,
  onDeleteLatestTurn,
}: {
  messages: Message[];
  pending: boolean;
  onRewind?: (message: Message) => void;
  onDeleteLatestTurn?: () => void;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const latestUserMessageId = [...messages].reverse().find((message) => message.role === "user")?.id;
  useEffect(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), [messages, pending]);

  if (!messages.length && !pending) {
    return (
      <div className="message-list">
        <div className="empty-workspace">
          <Bot size={28} strokeWidth={1.6} />
          <strong>描述你想生成的画面</strong>
          <p>工作流会理解上下文、验证标签并按目标模型整理 Prompt。</p>
        </div>
      </div>
    );
  }

  return (
    <div className="message-list">
      {messages.map((message) => {
        const user = message.role === "user";
        return (
          <article className={`message ${user ? "user" : "assistant"}`} key={message.id}>
            <div className="message-author">
              {user ? <UserRound size={15} /> : <Bot size={15} />}
              <span>{user ? "你" : "工作流结果"}</span>
            </div>
            <div className="message-surface">
              {user ? <div className="message-text">{message.content}</div> : <PromptResult content={message.content} />}
            </div>
            {user && onRewind && !message.id.startsWith("local-") && (
              <div className="message-actions" aria-label="消息操作">
                <button onClick={() => onRewind(message)} title="回溯到这里并重新编辑" type="button">
                  <History size={14} /><span>回溯</span>
                </button>
                {message.id === latestUserMessageId && onDeleteLatestTurn && (
                  <button className="danger" onClick={onDeleteLatestTurn} title="删除这一轮" type="button">
                    <Trash2 size={14} /><span>删除本轮</span>
                  </button>
                )}
              </div>
            )}
          </article>
        );
      })}
      {pending && (
        <article className="message assistant pending-message">
          <div className="message-author"><Bot size={15} /><span>工作流处理中</span></div>
          <div className="typing-indicator"><i /><i /><i /></div>
        </article>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
