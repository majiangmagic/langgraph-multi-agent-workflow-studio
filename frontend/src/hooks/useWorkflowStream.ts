import { useCallback, useEffect, useRef, useState } from "react";
import { streamChat } from "../api/client";
import type { NodeStatus, WorkflowEvent, WorkflowInputs } from "../types";

export function useWorkflowStream() {
  const [running, setRunning] = useState(false);
  const [nodeStatuses, setNodeStatuses] = useState<Record<string, NodeStatus>>({});
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => () => controllerRef.current?.abort(), []);

  const clear = useCallback(() => setNodeStatuses({}), []);
  const cancel = useCallback(() => controllerRef.current?.abort(), []);

  const run = useCallback(
    async (conversationId: string, message: string, inputs: WorkflowInputs) => {
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;
      setRunning(true);
      setNodeStatuses({});
      try {
        return await streamChat(
          conversationId,
          message,
          inputs,
          (rawEvent) => {
            if (rawEvent.object !== "workflow.event") return;
            const event = rawEvent as unknown as WorkflowEvent;
            const node = event.node;
            if (!node) return;
            const status: NodeStatus = event.type.includes("error")
              ? "error"
              : event.type.includes("completed")
                ? "completed"
                : event.type.includes("started") || event.type.includes("assigned")
                  ? "running"
                  : "idle";
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

  return { running, nodeStatuses, run, clear, cancel };
}
