export type WorkflowControlOption = {
  value: string;
  label?: string;
};

export type WorkflowControl = {
  key: string;
  label?: string;
  type?: string;
  default?: string;
  options?: WorkflowControlOption[];
  placeholder?: string;
  min?: number | string;
  max?: number | string;
  step?: number | string;
};

export type WorkflowNode = {
  name: string;
  agent: string;
  display_name?: string;
  on_error?: string;
};

export type WorkflowEdge = {
  from: string | string[];
  to: string;
  conditional?: boolean;
  branch?: "then" | "otherwise";
};

export type Workflow = {
  name: string;
  is_default: boolean;
  entrypoint?: string;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  ui: {
    title?: string;
    description?: string;
    input_placeholder?: string;
    input_hint?: string;
    controls?: WorkflowControl[];
  };
};

export type Crew = {
  id: string;
  name: string;
  description?: string;
  status: string;
  settings: Record<string, unknown>;
  workflow_type: string;
  workflow_missing: boolean;
  created_at: string;
  updated_at: string;
};

export type Conversation = {
  id: string;
  crew_id: string;
  user_id: string;
  title?: string;
  metadata: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type Message = {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system" | "agent";
  content: string;
  status: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type ClarificationRequest = {
  question: string;
  options: string[];
};

export type WorkflowInterrupt = ClarificationRequest & {
  id?: string;
  kind?: string;
  context?: string;
};

export type WorkflowResultMetadata = {
  status?: "valid" | "degraded" | "failed" | "needs_clarification";
  clarification_request?: ClarificationRequest | null;
  resumable?: boolean;
  interrupt?: WorkflowInterrupt | null;
};

export type WorkflowEvent = {
  object: "workflow.event";
  type: string;
  node?: string;
  error?: string;
  from?: string;
  to?: string;
  branch?: "then" | "otherwise" | "exhausted";
  iteration?: number;
  max_iterations?: number | null;
};

export type StreamProtocolEvent = {
  object: "agent.workflow.stream";
  version: "1.0";
  type:
    | "run.started"
    | "workflow.progress"
    | "message.started"
    | "message.delta"
    | "message.completed"
    | "run.completed"
    | "run.failed"
    | "run.cancelled";
  run_id: string;
  conversation_id: string;
  message_id: string;
  sequence: number;
  delta?: string;
  status?: string;
  error?: string;
  event?: WorkflowEvent;
  metadata?: Record<string, unknown>;
};

export type NodeStatus = "idle" | "running" | "completed" | "error";
export type EdgeSelection = {
  from: string;
  to: string;
  branch: "then" | "otherwise" | "exhausted";
  iteration: number;
  maxIterations?: number | null;
};
export type RuntimeEvent = {
  id: string;
  type: string;
  node?: string;
  label: string;
  timestamp: number;
};
export type WorkflowInputs = Record<string, string>;

export type DslKind = "agent" | "workflow";

export type DslSummary = {
  kind: DslKind;
  name: string;
  display_name: string;
};

export type DslData = Record<string, unknown> & {
  kind: DslKind;
  name: string;
  entrypoint?: string;
  nodes?: Record<string, Record<string, unknown>> | Array<Record<string, unknown>>;
  edges?: Array<{
    from: string | string[];
    to: string | string[];
    otherwise?: string;
    condition?: Record<string, unknown>;
    loop?: Record<string, unknown>;
  }>;
};
