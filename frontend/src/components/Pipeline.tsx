import { Check, Circle, LoaderCircle, RotateCcw, TriangleAlert } from "lucide-react";
import type { NodeStatus, Workflow, WorkflowNode } from "../types";

function levelsFor(workflow?: Workflow): WorkflowNode[][] {
  if (!workflow) return [];
  const names = new Set(workflow.nodes.map((node) => node.name));
  const ranks = Object.fromEntries(workflow.nodes.map((node) => [node.name, 0]));
  for (let pass = 0; pass < workflow.nodes.length; pass += 1) {
    for (const edge of workflow.edges) {
      if (edge.to === "END" || !names.has(edge.to)) continue;
      const sources = Array.isArray(edge.from) ? edge.from : [edge.from];
      const sourceRank = Math.max(0, ...sources.map((source) => ranks[source] ?? 0));
      ranks[edge.to] = Math.max(ranks[edge.to] ?? 0, sourceRank + 1);
    }
  }
  const levels: WorkflowNode[][] = [];
  workflow.nodes.forEach((node) => {
    const rank = ranks[node.name] ?? 0;
    levels[rank] ??= [];
    levels[rank].push(node);
  });
  return levels.filter(Boolean);
}

function StatusIcon({ status }: { status: NodeStatus }) {
  if (status === "running") return <LoaderCircle className="spin" size={15} />;
  if (status === "completed") return <Check size={15} />;
  if (status === "error") return <TriangleAlert size={15} />;
  return <Circle size={11} />;
}

export function Pipeline({
  workflow,
  statuses,
  onClear,
}: {
  workflow?: Workflow;
  statuses: Record<string, NodeStatus>;
  onClear: () => void;
}) {
  const levels = levelsFor(workflow);
  return (
    <section className="pipeline" aria-label="工作流执行进度">
      <div className="pipeline-head">
        <div>
          <span className="section-label">执行链</span>
          <small>{workflow?.nodes.length ?? 0} 个节点</small>
        </div>
        <button className="quiet-button" onClick={onClear} title="清空执行状态" type="button">
          <RotateCcw size={14} />
          清空状态
        </button>
      </div>
      {levels.length ? (
        <div
          className="pipeline-track"
          style={{ "--pipeline-columns": levels.length } as React.CSSProperties}
        >
          {levels.map((nodes, levelIndex) => (
            <div className="stage-column" key={levelIndex}>
              {nodes.map((node) => {
                const status = statuses[node.name] ?? "idle";
                return (
                  <div className={`stage ${status}`} key={node.name} title={node.agent}>
                    <StatusIcon status={status} />
                    <span>{node.display_name ?? node.name.replaceAll("_", " ")}</span>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      ) : (
        <div className="pipeline-empty">该工作流未提供拓扑元数据</div>
      )}
    </section>
  );
}
