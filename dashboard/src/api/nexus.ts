// Typed API client for the Nexus dashboard API.
// Proxy: /nexus/api -> Atrium backend (see vite.config.ts).

import { apiFetch } from "./client";
import type {
  AgentStatusRead,
  RunDetail,
  RunEvent,
  RunSummary,
  StatusSummary,
  WorkflowDetail,
  WorkflowRead,
  WorkItemSummary,
} from "./types";

export function getWorkflows(params?: {
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<WorkflowRead[]> {
  const qs = new URLSearchParams();
  if (params?.status) qs.set("status", params.status);
  if (params?.limit != null) qs.set("limit", String(params.limit));
  if (params?.offset != null) qs.set("offset", String(params.offset));
  const query = qs.toString();
  return apiFetch<WorkflowRead[]>(
    `/nexus/api/workflows${query ? `?${query}` : ""}`,
  );
}

export function getWorkflow(workflowId: string): Promise<WorkflowDetail> {
  return apiFetch<WorkflowDetail>(`/nexus/api/workflows/${workflowId}`);
}

export function getStatus(): Promise<StatusSummary> {
  return apiFetch<StatusSummary>("/nexus/api/status");
}

export function getAgents(): Promise<AgentStatusRead[]> {
  return apiFetch<AgentStatusRead[]>("/nexus/api/agents");
}

export function listWorkItems(params?: {
  status?: string | string[];
  agent_role?: string;
  workflow_id?: string;
  limit?: number;
  offset?: number;
}): Promise<WorkItemSummary[]> {
  const qs = new URLSearchParams();
  if (params?.status) {
    const statuses = Array.isArray(params.status)
      ? params.status
      : [params.status];
    statuses.forEach((s) => { qs.append("status", s); });
  }
  if (params?.agent_role) qs.set("agent_role", params.agent_role);
  if (params?.workflow_id) qs.set("workflow_id", params.workflow_id);
  if (params?.limit != null) qs.set("limit", String(params.limit));
  if (params?.offset != null) qs.set("offset", String(params.offset));
  const query = qs.toString();
  return apiFetch<WorkItemSummary[]>(
    `/nexus/api/work_items${query ? `?${query}` : ""}`,
  );
}

export function listRuns(params?: {
  agent_role?: string;
  status?: string;
  work_item_id?: string;
  workflow_step_id?: string;
  limit?: number;
  offset?: number;
}): Promise<RunSummary[]> {
  const qs = new URLSearchParams();
  if (params?.agent_role) qs.set("agent_role", params.agent_role);
  if (params?.status) qs.set("status", params.status);
  if (params?.work_item_id) qs.set("work_item_id", params.work_item_id);
  if (params?.workflow_step_id)
    qs.set("workflow_step_id", params.workflow_step_id);
  if (params?.limit != null) qs.set("limit", String(params.limit));
  if (params?.offset != null) qs.set("offset", String(params.offset));
  const query = qs.toString();
  return apiFetch<RunSummary[]>(`/nexus/api/runs${query ? `?${query}` : ""}`);
}

export function getRun(runId: string): Promise<RunDetail> {
  return apiFetch<RunDetail>(`/nexus/api/runs/${runId}`);
}

export function listRunEvents(
  runId: string,
  params?: { limit?: number; offset?: number },
): Promise<RunEvent[]> {
  const qs = new URLSearchParams();
  if (params?.limit != null) qs.set("limit", String(params.limit));
  if (params?.offset != null) qs.set("offset", String(params.offset));
  const query = qs.toString();
  return apiFetch<RunEvent[]>(
    `/nexus/api/runs/${runId}/events${query ? `?${query}` : ""}`,
  );
}
