import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { ArrowLeft, Bot, Check, Code2, FilePlus2, Save, Sparkles, Trash2, Workflow } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { DslData, DslKind, DslSummary } from "../types";
import { ConfirmDialog } from "./ConfirmDialog";

type FlowNodeData = { label: string; config: Record<string, unknown> };
type GenerationConfirmation = { name: string; files: string[] };

function blankDsl(kind: DslKind): DslData {
  return kind === "workflow"
    ? {
        version: 1,
        kind,
        name: "new_workflow",
        entrypoint: "start",
        ui: { title: "新工作流", description: "" },
        nodes: { start: { agent: "new_agent", display_name: "开始" } },
        edges: [{ from: "start", to: "END" }],
      }
    : {
        version: 1,
        kind,
        name: "new_agent",
        display_name: "新 Agent",
        entrypoint: "start",
        nodes: { start: { handler: "start_node" } },
        edges: [{ from: "start", to: "END" }],
        state: {},
        config: { system_prompt: "" },
      };
}

function nodeEntries(data: DslData): Array<[string, Record<string, unknown>]> {
  if (Array.isArray(data.nodes)) {
    return data.nodes.map((item) => [String(item.name), { ...item }]);
  }
  return Object.entries(data.nodes ?? {});
}

function toFlow(data: DslData): { nodes: Node<FlowNodeData>[]; edges: Edge[] } {
  const entries = nodeEntries(data);
  const edges: Edge[] = [];
  (data.edges ?? []).forEach((edge, groupIndex) => {
    const targets = Array.isArray(edge.to) ? edge.to : [edge.to];
    const sources = Array.isArray(edge.from) ? edge.from : [edge.from];
    for (const source of sources) {
      for (const target of targets) {
        if (target === "END") continue;
        edges.push({
          id: `e-${groupIndex}-${source}-${target}`,
          source,
          target,
          data: { group: groupIndex },
        });
      }
    }
  });
  const ids = new Set(entries.map(([id]) => id));
  const incoming = Object.fromEntries(entries.map(([id]) => [id, 0]));
  const outgoing = Object.fromEntries(entries.map(([id]) => [id, [] as string[]]));
  edges.forEach((edge) => {
    if (!ids.has(edge.source) || !ids.has(edge.target)) return;
    incoming[edge.target] += 1;
    outgoing[edge.source].push(edge.target);
  });
  const ranks = Object.fromEntries(entries.map(([id]) => [id, 0]));
  const queue = entries.map(([id]) => id).filter((id) => incoming[id] === 0);
  for (let index = 0; index < queue.length; index += 1) {
    const source = queue[index];
    outgoing[source].forEach((target) => {
      ranks[target] = Math.max(ranks[target], ranks[source] + 1);
      incoming[target] -= 1;
      if (incoming[target] === 0) queue.push(target);
    });
  }
  const rankCounts: Record<number, number> = {};
  const nodes = entries.map(([id, config]) => {
    const rank = ranks[id];
    const row = rankCounts[rank] ?? 0;
    rankCounts[rank] = row + 1;
    return {
      id,
      position: { x: 80 + rank * 230, y: 140 + row * 115 },
      data: { label: String(config.display_name || id), config },
    };
  });
  return { nodes, edges };
}

function graphIntoDsl(data: DslData, nodes: Node<FlowNodeData>[], edges: Edge[]): DslData {
  const nodeMap = Object.fromEntries(nodes.map((node) => [node.id, node.data.config]));
  const originalEndEdges = (data.edges ?? []).filter((edge) => edge.to === "END");
  const grouped = new Map<string, { from: string[]; to: string }>();
  edges.forEach((edge) => {
    const key = String(edge.data?.group ?? edge.id);
    const item = grouped.get(key) ?? { from: [], to: edge.target };
    if (!item.from.includes(edge.source)) item.from.push(edge.source);
    grouped.set(key, item);
  });
  const graphEdges = [...grouped.values()].map((edge) => ({
    from: edge.from.length === 1 ? edge.from[0] : edge.from,
    to: edge.to,
  }));
  return { ...data, nodes: nodeMap, edges: [...graphEdges, ...originalEndEdges] };
}

export function DslDesigner({ onClose }: { onClose: () => void }) {
  const [kind, setKind] = useState<DslKind>("workflow");
  const [items, setItems] = useState<DslSummary[]>([]);
  const [data, setData] = useState<DslData>(() => blankDsl("workflow"));
  const [nodes, setNodes] = useState<Node<FlowNodeData>[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [source, setSource] = useState("");
  const [sourceDirty, setSourceDirty] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [generation, setGeneration] = useState<GenerationConfirmation | null>(null);

  const selectedNode = nodes.find((node) => node.id === selectedId);
  const documentName = String(data.name || "");

  const setDocument = useCallback((next: DslData) => {
    const flow = toFlow(next);
    setData(next);
    setNodes(flow.nodes);
    setEdges(flow.edges);
    setSelectedId(flow.nodes[0]?.id ?? "");
    setSource(JSON.stringify(next, null, 2));
    setSourceDirty(false);
  }, []);

  const loadList = useCallback(async (nextKind: DslKind) => {
    const list = await api.dslList(nextKind);
    setItems(list);
    return list;
  }, []);

  const loadDocument = useCallback(async (nextKind: DslKind, name: string) => {
    setBusy(true);
    setError("");
    try {
      const document = await api.dsl(nextKind, name);
      setDocument(document.data);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }, [setDocument]);

  useEffect(() => {
    void loadList(kind).then((list) => {
      if (list[0]) void loadDocument(kind, list[0].name);
      else setDocument(blankDsl(kind));
    });
  }, [kind, loadDocument, loadList, setDocument]);

  useEffect(() => {
    if (sourceDirty) return;
    const next = graphIntoDsl(data, nodes, edges);
    setData(next);
    setSource(JSON.stringify(next, null, 2));
  }, [nodes, edges]); // eslint-disable-line react-hooks/exhaustive-deps

  const onNodesChange = useCallback((changes: NodeChange<Node<FlowNodeData>>[]) => {
    setNodes((current) => applyNodeChanges(changes, current));
  }, []);
  const onEdgesChange = useCallback((changes: EdgeChange<Edge>[]) => {
    setEdges((current) => applyEdgeChanges(changes, current));
  }, []);
  const onConnect = useCallback((connection: Connection) => {
    setEdges((current) => addEdge({ ...connection, id: crypto.randomUUID() }, current));
  }, []);

  function updateRoot(key: string, value: unknown) {
    const next = { ...data, [key]: value } as DslData;
    setData(next);
    setSource(JSON.stringify(next, null, 2));
  }

  function updateSelectedConfig(key: string, value: unknown) {
    setNodes((current) => current.map((node) => node.id === selectedId
      ? { ...node, data: { ...node.data, label: key === "display_name" ? String(value || node.id) : node.data.label, config: { ...node.data.config, [key]: value } } }
      : node));
  }

  function addNode() {
    let index = nodes.length + 1;
    let id = `node_${index}`;
    while (nodes.some((node) => node.id === id)) id = `node_${++index}`;
    const config = kind === "workflow" ? { agent: "new_agent", display_name: `节点 ${index}` } : { handler: `${id}_node` };
    setNodes((current) => [...current, { id, position: { x: 100 + index * 24, y: 100 + index * 18 }, data: { label: String(config.display_name || id), config } }]);
    setSelectedId(id);
  }

  function deleteSelectedNode() {
    if (!selectedId) return;
    setNodes((current) => current.filter((node) => node.id !== selectedId));
    setEdges((current) => current.filter((edge) => edge.source !== selectedId && edge.target !== selectedId));
    setSelectedId("");
  }

  function applySource() {
    try {
      const parsed = JSON.parse(source) as DslData;
      if (parsed.kind !== kind) throw new Error(`kind 必须是 ${kind}`);
      setDocument(parsed);
      setNotice("源码已应用到画布");
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  async function validate() {
    setBusy(true);
    try {
      const result = await api.validateDsl(kind, data);
      setNotice(`校验通过：${result.nodes.length} 个节点，入口 ${result.entrypoint}`);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    setBusy(true);
    try {
      const result = await api.saveDsl(kind, documentName, data);
      setNotice(`已保存 ${result.path}`);
      setError("");
      await loadList(kind);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function prepareGeneration() {
    try {
      await api.validateDsl(kind, data);
      const base = kind === "agent" ? `app/agents/${String(data.package || documentName)}` : `app/core/langgraph/workflows/${documentName}`;
      setGeneration({ name: documentName, files: [base] });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  async function generate() {
    setGeneration(null);
    setBusy(true);
    try {
      const result = await api.generateDsl(kind, documentName, data);
      setNotice(`已生成 ${result.generated_files.length} 个文件；重启服务后加载新代码`);
      setError("");
      await loadList(kind);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }

  const nodeFields = useMemo(() => kind === "workflow"
    ? ["display_name", "agent", "agent_package", "extension", "on_error"]
    : ["handler"], [kind]);

  return (
    <main className="designer-shell">
      <header className="designer-header">
        <div>
          <button className="icon-button light" onClick={onClose} title="返回运行工作台" type="button"><ArrowLeft size={17} /></button>
          <Code2 size={20} />
          <div><strong>DSL 设计器</strong><span>Agent 与 Workflow 骨架生成</span></div>
        </div>
        <div className="designer-actions">
          <button className="secondary-button" disabled={busy} onClick={() => void validate()} type="button"><Check size={15} />校验</button>
          <button className="secondary-button" disabled={busy || !documentName} onClick={() => void save()} type="button"><Save size={15} />保存 DSL</button>
          <button className="send-button" disabled={busy || !documentName} onClick={() => void prepareGeneration()} type="button"><Sparkles size={15} />生成代码</button>
        </div>
      </header>

      {(notice || error) && <div className={`designer-notice ${error ? "error" : ""}`}>{error || notice}</div>}

      <section className="designer-body">
        <aside className="dsl-library">
          <div className="designer-kind-switch">
            <button className={kind === "workflow" ? "active" : ""} onClick={() => setKind("workflow")} type="button"><Workflow size={15} />Workflow</button>
            <button className={kind === "agent" ? "active" : ""} onClick={() => setKind("agent")} type="button"><Bot size={15} />Agent</button>
          </div>
          <button className="new-dsl-button" onClick={() => setDocument(blankDsl(kind))} type="button"><FilePlus2 size={15} />新建 {kind === "agent" ? "Agent" : "Workflow"}</button>
          <div className="dsl-list">
            {items.map((item) => (
              <button className={item.name === documentName ? "active" : ""} key={item.name} onClick={() => void loadDocument(kind, item.name)} type="button">
                <strong>{item.display_name}</strong><span>{item.name}</span>
              </button>
            ))}
          </div>
        </aside>

        <section className="designer-canvas">
          <div className="canvas-toolbar">
            <div><strong>{documentName || "未命名 DSL"}</strong><span>{kind === "agent" ? "Agent 内部节点图" : "工作流连接图"}</span></div>
            <button className="secondary-button" onClick={addNode} type="button"><FilePlus2 size={14} />添加节点</button>
          </div>
          <ReactFlow
            edges={edges}
            fitView
            nodes={nodes}
            onConnect={onConnect}
            onEdgesChange={onEdgesChange}
            onNodeClick={(_, node) => setSelectedId(node.id)}
            onNodesChange={onNodesChange}
          >
            <Background gap={18} size={1} />
            <MiniMap pannable zoomable />
            <Controls />
          </ReactFlow>
        </section>

        <aside className="dsl-inspector">
          <div className="inspector-tabs"><strong>属性与源码</strong></div>
          <label>DSL 名称<input value={documentName} onChange={(event) => updateRoot("name", event.target.value)} /></label>
          <label>入口节点<select value={String(data.entrypoint || "")} onChange={(event) => updateRoot("entrypoint", event.target.value)}>{nodes.map((node) => <option key={node.id}>{node.id}</option>)}</select></label>
          {selectedNode && (
            <div className="node-properties">
              <div className="property-heading"><strong>节点：{selectedNode.id}</strong><button onClick={deleteSelectedNode} title="删除节点" type="button"><Trash2 size={14} /></button></div>
              {nodeFields.map((field) => (
                <label key={field}>{field}<input value={String(selectedNode.data.config[field] ?? "")} onChange={(event) => updateSelectedConfig(field, event.target.value)} /></label>
              ))}
            </div>
          )}
          <div className="source-heading"><strong>JSON DSL</strong><button onClick={applySource} type="button">应用源码</button></div>
          <textarea className="dsl-source" spellCheck={false} value={source} onChange={(event) => { setSource(event.target.value); setSourceDirty(true); }} />
        </aside>
      </section>

      <ConfirmDialog
        confirmLabel="确认生成"
        description={`将根据 ${generation?.name ?? ""} 刷新 ${generation?.files.join("、") ?? ""}。Agent 中被 DSL 删除的节点代码块也会被删除。`}
        onCancel={() => setGeneration(null)}
        onConfirm={() => void generate()}
        open={Boolean(generation)}
        title="生成并刷新代码骨架"
      />
    </main>
  );
}
