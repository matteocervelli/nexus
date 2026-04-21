// React hook: connects SSE, invalidates TanStack Query caches on events.

import { useEffect, useRef } from "react";
import type { QueryClient } from "@tanstack/react-query";
import { NexusEventSource } from "./nexus-events";
import type { NexusEventEnvelope } from "./nexus-events";

export function useNexusEvents(queryClient: QueryClient): void {
  const sourceRef = useRef<NexusEventSource | null>(null);

  useEffect(() => {
    const source = new NexusEventSource();
    sourceRef.current = source;

    const invalidateWorkItems = (_env: NexusEventEnvelope) => {
      void queryClient.invalidateQueries({ queryKey: ["work_items"] });
    };
    const invalidateWorkflows = (_env: NexusEventEnvelope) => {
      void queryClient.invalidateQueries({ queryKey: ["workflows"] });
    };
    const invalidateAgents = (_env: NexusEventEnvelope) => {
      void queryClient.invalidateQueries({ queryKey: ["agents"] });
    };

    source.on("work_item_status_changed", (env) => {
      invalidateWorkItems(env);
      invalidateWorkflows(env);
    });
    source.on("workflow_step_updated", invalidateWorkflows);
    source.on("agent_spawned", invalidateAgents);
    source.on("agent_completed", (env) => {
      invalidateAgents(env);
      invalidateWorkItems(env);
    });
    source.on("budget_alert", invalidateAgents);

    source.connect();
    return () => { source.disconnect(); };
  }, [queryClient]);
}
