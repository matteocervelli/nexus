// Typed stubs for the Nexus API (routes implemented in #22).
// Proxy: /nexus/api -> Atrium backend (see vite.config.ts).

import { apiFetch } from "./client";
import type { AgentStatusRead, StatusSummary, WorkflowRead } from "./types";

export function getWorkflows(): Promise<WorkflowRead[]> {
  return apiFetch<WorkflowRead[]>("/nexus/api/workflows");
}

export function getStatus(): Promise<StatusSummary> {
  return apiFetch<StatusSummary>("/nexus/api/status");
}

export function getAgents(): Promise<AgentStatusRead[]> {
  return apiFetch<AgentStatusRead[]>("/nexus/api/agents");
}
