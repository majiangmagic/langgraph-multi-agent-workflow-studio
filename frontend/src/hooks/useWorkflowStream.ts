import { useCallback, useEffect, useRef, useState } from "react";
import { streamChat } from "../api/client";
import type { EdgeSelection, NodeStatus, WorkflowEvent, WorkflowInputs } from "../types";

export function useWorkflowStream() {
  const [running, setRunning] = useState(false);
  const [nodeStatuses, setNodeStatuses] = useState<Record<string, NodeStatus>>({});
  const [nodeDurations, setNodeDurations] = useState<Record<string, number>>({});
  const [selectedEdges, setSelectedEdges] = useState<Record<string, EdgeSelection>>({});
  const [executionKey, setExecutionKey] = useState(0);
  const controllerRef = useRef<AbortController | null>(null);
  const nodeStartedAt = useRef<Record<string, number>>({});

  useEffect(() => () => {
    controllerRef.current?.abort();
  }, []);

  const clear = useCallback(() => {
    setNodeStatuses({});
    setNodeDurations({});
    setSelectedEdges({});
    setExecutionKey((current) => current + 1);
    nodeStartedAt.current = {};
  }, []);
  const cancel = useCallback(() => controllerRef.current?.abort(), []);

  const run = useCallback(
    async (conversationId: string, message: string, inputs: WorkflowInputs) => {
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;
      setRunning(true);
      setNodeStatuses({});
      setNodeDurations({});
      setSelectedEdges({});
      setExecutionKey((current) => current + 1);
      nodeStartedAt.current = {};
      try {
        return await streamChat(
          conversationId,
          message,
          inputs,
          (rawEvent) => {
            if (rawEvent.object !== "workflow.event") return;
            const event = rawEvent as unknown as WorkflowEvent;
            if (event.type === "workflow.edge.selected" && event.from && event.to && event.branch) {
              const edgeKey = `${event.from}->${event.to}`;
              setSelectedEdges((current) => ({
                ...current,
                [edgeKey]: {
                  from: event.from!,
                  to: event.to!,
                  branch: event.branch!,
                  iteration: event.iteration ?? 0,
                  maxIterations: event.max_iterations,
                },
              }));
              return;
            }
            const node = event.node;
            if (!node) return;
            const status: NodeStatus = event.type.includes("error")
              ? "error"
              : event.type.includes("completed")
                ? "completed"
                : event.type.includes("started") || event.type.includes("assigned")
                  ? "running"
                  : "idle";
            if (status === "running") nodeStartedAt.current[node] = performance.now();
            if (status === "completed" || status === "error") {
              const startedAt = nodeStartedAt.current[node];
              if (startedAt !== undefined) {
                setNodeDurations((current) => ({
                  ...current,
                  [node]: performance.now() - startedAt,
                }));
              }
            }
            setNodeStatuses((current) => ({ ...current, [node]: status }));
          },
          controller.signal,
        );
      } finally {
        if (controllerRef.current === controller) {
          controllerRef.current = null;
          setRunning(false);
        }
      }
    },
    [],
  );

  return {
    running,
    nodeStatuses,
    nodeDurations,
    selectedEdges,
    executionKey,
    run,
    clear,
    cancel,
  };
}
