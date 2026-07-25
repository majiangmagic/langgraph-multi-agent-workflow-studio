import {
  ActionBarPrimitive,
  AssistantRuntimeProvider,
  AuiIf,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  type AppendMessage,
  type ThreadMessageLike,
  useAuiState,
  useExternalStoreRuntime,
} from "@assistant-ui/react";
import {
  ArrowDown,
  ArrowUp,
  BadgeCheck,
  Blocks,
  Braces,
  Check,
  CircleHelp,
  Copy,
  FileSearch,
  History,
  PencilLine,
  RotateCcw,
  Square,
  Trash2,
  Workflow,
} from "lucide-react";
import { Fragment, useCallback, useEffect, type RefObject } from "react";
import type { ClarificationRequest, Message, Workflow as WorkflowDefinition, WorkflowResultMetadata } from "../types";
import { PromptResult } from "./PromptResult";

function clarificationFor(message: Message): ClarificationRequest | null {
  const result = message.metadata?.workflow_result as WorkflowResultMetadata | undefined;
  const request = result?.clarification_request;
  if (request?.question) {
    return {
      question: request.question,
      options: Array.isArray(request.options) ? request.options.filter(Boolean) : [],
    };
  }
  const prefix = "需要确认：";
  return message.content.startsWith(prefix)
    ? { question: message.content.slice(prefix.length).trim(), options: [] }
    : null;
}

function textFrom(message: AppendMessage) {
  return message.content
    .filter((part) => part.type === "text")
    .map((part) => part.text)
    .join("\n")
    .trim();
}

type Props = {
  messages: Message[];
  pending: boolean;
  disabled: boolean;
  draft: string;
  placeholder: string;
  hint: string;
  emptyTitle: string;
  emptyDescription: string;
  workflow?: WorkflowDefinition;
  composerRef?: RefObject<HTMLTextAreaElement | null>;
  onSend: (message: string) => Promise<void> | void;
  onCancel: () => void;
  onRewind?: (message: Message) => void;
  onDeleteLatestTurn?: () => void;
  onClarificationReply?: (reply: string) => void;
  onClarificationRetry?: () => void;
  onClarificationExplain?: () => void;
};

export function AssistantChat(props: Props) {
  const convertMessage = useCallback((message: Message): ThreadMessageLike => ({
    id: message.id,
    role: message.role === "user" ? "user" : "assistant",
    content: [{ type: "text", text: message.content }],
    createdAt: new Date(message.created_at),
  }), []);

  const onNew = useCallback(async (message: AppendMessage) => {
    const text = textFrom(message);
    if (text) await props.onSend(text);
  }, [props.onSend]);

  const runtime = useExternalStoreRuntime({
    messages: props.messages,
    convertMessage,
    isRunning: props.pending,
    isDisabled: props.disabled,
    onNew,
    onCancel: async () => props.onCancel(),
  });

  useEffect(() => {
    runtime.thread.composer.setText(props.draft);
  }, [props.draft]);

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ChatThread {...props} />
    </AssistantRuntimeProvider>
  );
}

function ChatThread(props: Props) {
  const workflowNodes = props.workflow?.nodes ?? [];
  const previewNodes = workflowNodes.length <= 4
    ? workflowNodes
    : [
        ...workflowNodes.slice(0, 3),
        { name: "workflow-summary", agent: "", display_name: `其余 ${workflowNodes.length - 3} 个节点` },
      ];
  const previewIcons = [FileSearch, Blocks, Braces, BadgeCheck];

  return (
    <ThreadPrimitive.Root className="aui-thread">
      <ThreadPrimitive.Viewport className="aui-viewport" turnAnchor="top">
        <AuiIf condition={(state) => state.thread.isEmpty}>
          <div className="aui-empty-state">
            <div className="empty-blueprint" aria-hidden="true">
              <div className="empty-blueprint-head">
                <span>READY</span>
                <small>FLOW / {String(workflowNodes.length).padStart(2, "0")}</small>
              </div>
              <div className="empty-blueprint-route">
                {previewNodes.map((node, index) => {
                  const Icon = previewIcons[index % previewIcons.length];
                  return (
                    <Fragment key={`${node.name}-${index}`}>
                      {index > 0 && <b />}
                      <div className={`blueprint-stop ${node.name === "workflow-summary" ? "summary" : ""}`}>
                        <i>{String(index + 1).padStart(2, "0")}</i>
                        <Icon size={19} />
                        <span>{node.display_name || node.name}</span>
                      </div>
                    </Fragment>
                  );
                })}
                {!previewNodes.length && <div className="blueprint-stop empty"><span>请选择工作流</span></div>}
              </div>
            </div>
            <div className="empty-state-copy">
              <span className="empty-kicker">WORKFLOW READY</span>
              <h2>{props.emptyTitle}</h2>
              <p>{props.emptyDescription}</p>
            </div>
          </div>
        </AuiIf>

        <div className="aui-message-column">
          <ThreadPrimitive.Messages>
            {({ message }) => message.role === "user"
              ? <UserMessage {...props} />
              : <AssistantMessage {...props} />}
          </ThreadPrimitive.Messages>
        </div>

        <AuiIf condition={(state) => !state.thread.isEmpty}>
          <ThreadPrimitive.ScrollToBottom asChild>
            <button className="aui-scroll-button" title="滚动到底部" type="button">
              <ArrowDown size={16} />
            </button>
          </ThreadPrimitive.ScrollToBottom>
        </AuiIf>

        <ThreadPrimitive.ViewportFooter className="aui-viewport-footer">
          <ComposerPrimitive.Root className="aui-composer">
            <ComposerPrimitive.Input
              autoFocus
              className="aui-composer-input"
              placeholder={props.placeholder}
              ref={props.composerRef}
              rows={1}
            />
            <div className="aui-composer-actions">
              <span>{props.hint}</span>
              <AuiIf condition={(state) => state.thread.isRunning}>
                <ComposerPrimitive.Cancel asChild>
                  <button className="aui-primary-action stop" title="停止运行" type="button">
                    <Square fill="currentColor" size={13} />
                  </button>
                </ComposerPrimitive.Cancel>
              </AuiIf>
              <AuiIf condition={(state) => !state.thread.isRunning}>
                <ComposerPrimitive.Send asChild>
                  <button className="aui-primary-action" title="发送消息" type="button">
                    <ArrowUp size={17} strokeWidth={2.4} />
                  </button>
                </ComposerPrimitive.Send>
              </AuiIf>
            </div>
          </ComposerPrimitive.Root>
          <p className="aui-disclaimer">结果由当前 Crew 与 Workflow 共同生成，请检查重要内容。</p>
        </ThreadPrimitive.ViewportFooter>
      </ThreadPrimitive.Viewport>
    </ThreadPrimitive.Root>
  );
}

function UserMessage(props: Props) {
  const messageId = useAuiState((state) => state.message.id);
  const source = props.messages.find((message) => message.id === messageId);
  const latestUser = [...props.messages].reverse().find((message) => message.role === "user");
  const persisted = source && !source.id.startsWith("local-");

  return (
    <MessagePrimitive.Root className="aui-message aui-user-message">
      <span className="aui-lane-label">INPUT</span>
      <div className="aui-user-bubble"><i aria-hidden="true" /><MessagePrimitive.Parts /></div>
      <ActionBarPrimitive.Root className="aui-message-actions" autohide="always">
        <ActionBarPrimitive.Copy asChild>
          <button title="复制" type="button"><Copy size={14} /></button>
        </ActionBarPrimitive.Copy>
        {persisted && props.onRewind && (
          <button onClick={() => props.onRewind?.(source)} title="从这里回溯" type="button">
            <History size={14} />
          </button>
        )}
        {persisted && source.id === latestUser?.id && props.onDeleteLatestTurn && (
          <button className="danger" onClick={props.onDeleteLatestTurn} title="删除本轮" type="button">
            <Trash2 size={14} />
          </button>
        )}
      </ActionBarPrimitive.Root>
    </MessagePrimitive.Root>
  );
}

function AssistantMessage(props: Props) {
  const messageId = useAuiState((state) => state.message.id);
  const status = useAuiState((state) => state.message.status?.type ?? "complete");
  const source = props.messages.find((message) => message.id === messageId);
  const latestAssistant = [...props.messages].reverse().find((message) => message.role === "assistant");
  const clarification = source ? clarificationFor(source) : null;
  const clarificationActive = source?.id === latestAssistant?.id && !props.pending;
  const streaming = source?.status === "processing";
  const cancelled = source?.status === "failed" && source.metadata?.cancelled === true;
  const failed = source?.status === "failed" && !cancelled;

  return (
    <MessagePrimitive.Root className="aui-message aui-assistant-message">
      <span className="aui-lane-label">OUTPUT</span>
      <div className="aui-assistant-heading"><Workflow size={15} /><span>工作流结果</span><i aria-hidden="true" /></div>
      <div className="aui-assistant-content">
        {(!source && status === "running") || (streaming && !source.content) ? (
          <div className="aui-thinking"><i /><i /><i /><span>工作流处理中</span></div>
        ) : streaming ? (
          <div className="aui-streaming-text">{source.content}<span aria-hidden className="aui-stream-cursor" /></div>
        ) : cancelled ? (
          <div className="aui-cancelled-result">
            {source.content && <p>{source.content}</p>}
            <span>已停止本轮执行</span>
          </div>
        ) : failed ? (
          <div className="aui-failed-result">
            <strong>本轮执行失败</strong>
            {source.content && <p>{source.content}</p>}
          </div>
        ) : clarification ? (
          <div className="aui-clarification">
            <header><CircleHelp size={17} /><strong>需要确认本轮修改</strong></header>
            <p>{clarification.question}</p>
            {clarificationActive && (
              <div className="aui-clarification-actions">
                {clarification.options.map((option) => (
                  <button key={option} onClick={() => props.onClarificationReply?.(option)} type="button">
                    <Check size={14} />{option}
                  </button>
                ))}
                {!clarification.options.length && (
                  <button onClick={props.onClarificationRetry} type="button"><RotateCcw size={14} />重新尝试</button>
                )}
                <button className="secondary" onClick={props.onClarificationExplain} type="button"><PencilLine size={14} />补充说明</button>
                <button className="secondary danger" onClick={props.onDeleteLatestTurn} type="button"><Trash2 size={14} />取消本轮</button>
              </div>
            )}
          </div>
        ) : source ? (
          <PromptResult content={source.content} />
        ) : null}
      </div>
      {source && !clarification && (
        <ActionBarPrimitive.Root className="aui-assistant-actions">
          <ActionBarPrimitive.Copy asChild>
            <button title="复制结果" type="button"><Copy size={14} /><span>复制</span></button>
          </ActionBarPrimitive.Copy>
        </ActionBarPrimitive.Root>
      )}
    </MessagePrimitive.Root>
  );
}
