import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { Check, Circle, LoaderCircle, RotateCcw, TriangleAlert } from "lucide-react";
import { useMemo } from "react";
import type {
  EdgeSelection,
  NodeStatus,
  Workflow,
  WorkflowEdge,
  WorkflowNode,
} from "../types";

type RuntimeNodeData = Record<string, unknown> & {
  workflowNode: WorkflowNode;
  status: NodeStatus;
  duration?: number;
};

function StatusIcon({ status }: { status: NodeStatus }) {
  if (status === "running") return <LoaderCircle className="spin" size={15} />;
  if (status === "completed") return <Check size={15} />;
  if (status === "error") return <TriangleAlert size={15} />;
  return <Circle size={11} />;
}

function formatDuration(duration?: number) {
  if (duration === undefined) return "";
  return duration < 1000 ? `${Math.round(duration)} ms` : `${(duration / 1000).toFixed(1)} s`;
}

function RuntimeNode({ data }: NodeProps<Node<RuntimeNodeData>>) {
  const { workflowNode, status, duration } = data;
  return (
    <div className={`runtime-node ${status}`} title={workflowNode.agent}>
      <Handle className="runtime-handle" position={Position.Left} type="target" />
      <StatusIcon status={status} />
      <div>
        <strong>{workflowNode.display_name ?? workflowNode.name.replaceAll("_", " ")}</strong>
        <span>{formatDuration(duration) || workflowNode.agent}</span>
      </div>
      <Handle className="runtime-handle" position={Position.Right} type="source" />
    </div>
  );
}

const nodeTypes = { runtime: RuntimeNode };

function expandedEdges(workflow: Workflow) {
  return workflow.edges.flatMap((edge, edgeIndex) =>
    (Array.isArray(edge.from) ? edge.from : [edge.from]).map((source) => ({
      edge,
      edgeIndex,
      source,
      target: edge.to,
    })),
  );
}

function shortestRanks(workflow: Workflow): Record<string, number> {
  const names = new Set(workflow.nodes.map((node) => node.name));
  const entrypoint = workflow.entrypoint && names.has(workflow.entrypoint)
    ? workflow.entrypoint
    : workflow.nodes[0]?.name;
  const ranks: Record<string, number> = entrypoint ? { [entrypoint]: 0 } : {};
  const queue = entrypoint ? [entrypoint] : [];
  const edges = expandedEdges(workflow);
  for (let index = 0; index < queue.length; index += 1) {
    const source = queue[index];
    edges.forEach((edge) => {
      if (edge.source !== source || edge.target === "END" || !names.has(edge.target)) return;
      const nextRank = (ranks[source] ?? 0) + 1;
      if (ranks[edge.target] === undefined || nextRank < ranks[edge.target]) {
        ranks[edge.target] = nextRank;
        queue.push(edge.target);
      }
    });
  }
  return ranks;
}

function branchLabel(edge: WorkflowEdge, selection?: EdgeSelection) {
  if (!edge.conditional) return "";
  if (selection?.branch === "exhausted") return "修复上限";
  return edge.branch === "then" ? "需要修复" : "通过";
}

function buildGraph(
  workflow: Workflow,
  statuses: Record<string, NodeStatus>,
  durations: Record<string, number>,
  selectedEdges: Record<string, EdgeSelection>,
): { nodes: Node<RuntimeNodeData>[]; edges: Edge[] } {
  const ranks = shortestRanks(workflow);
  const fallbackRank = Math.max(0, ...Object.values(ranks)) + 1;
  const rowsByRank: Record<number, number> = {};
  const nodes = workflow.nodes.map((workflowNode) => {
    const rank = ranks[workflowNode.name] ?? fallbackRank;
    const row = rowsByRank[rank] ?? 0;
    rowsByRank[rank] = row + 1;
    return {
      id: workflowNode.name,
      type: "runtime",
      position: { x: 36 + rank * 224, y: 26 + row * 86 },
      data: {
        workflowNode,
        status: statuses[workflowNode.name] ?? "idle",
        duration: durations[workflowNode.name],
      },
      draggable: false,
      selectable: false,
    } satisfies Node<RuntimeNodeData>;
  });
  const graphEdges = expandedEdges(workflow)
    .filter(({ target }) => target !== "END")
    .map(({ edge, edgeIndex, source, target }) => {
      const selection = selectedEdges[`${source}->${target}`];
      const conditional = Boolean(edge.conditional);
      const traversed = conditional
        ? Boolean(selection)
        : statuses[source] === "completed" && ["running", "completed", "error"].includes(statuses[target]);
      const loop = (ranks[target] ?? 0) <= (ranks[source] ?? 0);
      const stroke = traversed ? (loop ? "#c67b2d" : "#288d63") : loop ? "#c89a68" : "#aab5b0";
      return {
        id: `runtime-${edgeIndex}-${source}-${target}-${edge.branch ?? "normal"}`,
        source,
        target,
        type: loop ? "default" : "smoothstep",
        animated: traversed && statuses[target] === "running",
        label: loop ? "回到编译" : branchLabel(edge, selection),
        markerEnd: { type: MarkerType.ArrowClosed, color: stroke, width: 16, height: 16 },
        style: {
          stroke,
          strokeWidth: traversed ? 2.4 : 1.4,
          strokeDasharray: conditional || loop ? "6 4" : undefined,
        },
        labelStyle: { fill: traversed ? "#176b49" : "#6f7d76", fontSize: 10, fontWeight: 700 },
        labelBgStyle: { fill: "#edf2ef", fillOpacity: 0.96 },
        labelBgPadding: [4, 3] as [number, number],
        labelBgBorderRadius: 3,
        selectable: false,
      } satisfies Edge;
    });
  return { nodes, edges: graphEdges };
}

export function Pipeline({
  workflow,
  statuses,
  durations,
  selectedEdges,
  executionKey,
  onClear,
}: {
  workflow?: Workflow;
  statuses: Record<string, NodeStatus>;
  durations: Record<string, number>;
  selectedEdges: Record<string, EdgeSelection>;
  executionKey: number;
  onClear: () => void;
}) {
  const graph = useMemo(
    () => workflow ? buildGraph(workflow, statuses, durations, selectedEdges) : { nodes: [], edges: [] },
    [workflow, statuses, durations, selectedEdges],
  );
  return (
    <section className="pipeline" aria-label="工作流执行拓扑">
      <div className="pipeline-head">
        <div>
          <span className="section-label">执行拓扑</span>
          <small>{workflow?.nodes.length ?? 0} 个节点</small>
        </div>
        <button className="quiet-button" onClick={onClear} title="清空执行状态" type="button">
          <RotateCcw size={14} />
          清空状态
        </button>
      </div>
      {graph.nodes.length ? (
        <div className="runtime-graph">
          <ReactFlow
            key={`${workflow?.name ?? "workflow"}:${executionKey}`}
            edges={graph.edges}
            elementsSelectable={false}
            fitView
            fitViewOptions={{ padding: 0.18, maxZoom: 1.15 }}
            maxZoom={1.5}
            minZoom={0.35}
            nodeTypes={nodeTypes}
            nodes={graph.nodes}
            nodesConnectable={false}
            nodesDraggable={false}
            panOnDrag
            proOptions={{ hideAttribution: true }}
            zoomOnDoubleClick={false}
          >
            <Background color="#d3dbd7" gap={20} size={1} />
            <Controls position="bottom-right" showInteractive={false} />
          </ReactFlow>
        </div>
      ) : (
        <div className="pipeline-empty">该工作流未提供拓扑元数据</div>
      )}
    </section>
  );
}
