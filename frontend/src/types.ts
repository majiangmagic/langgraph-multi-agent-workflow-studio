export type WorkflowControlOption = {
  value: string;
  label?: string;
};

export type WorkflowControl = {
  key: string;
  label?: string;
  type?: "select" | "segmented";
  default?: string;
  options: WorkflowControlOption[];
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
    target_models?: WorkflowControlOption[];
    default_target_model?: string;
  };
};

export type Crew = {
  id: string;
  name: string;
  description?: string;
  status: string;
  settings: Record<string, unknown>;
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

export type WorkflowEvent = {
  object: "workflow.event";
  type: string;
  node?: string;
  error?: string;
};

export type NodeStatus = "idle" | "running" | "completed" | "error";
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
  edges?: Array<{ from: string | string[]; to: string | string[] }>;
};
