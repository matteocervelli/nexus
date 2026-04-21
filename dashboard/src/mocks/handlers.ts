import { http, HttpResponse } from "msw";
import type {
  AgentStatusRead,
  RunEvent,
  RunSummary,
  StatusSummary,
  WorkflowRead,
  WorkItemSummary,
} from "@/api/types";

export const handlers = [
  http.get("/nexus/api/workflows", () => {
    const workflows: WorkflowRead[] = [];
    return HttpResponse.json(workflows);
  }),

  http.get("/nexus/api/workflows/:id", () => {
    return HttpResponse.json(null, { status: 404 });
  }),

  http.get("/nexus/api/status", () => {
    const status: StatusSummary = {
      running_count: 0,
      queue_depth: 0,
      budget_alerts: [],
    };
    return HttpResponse.json(status);
  }),

  http.get("/nexus/api/agents", () => {
    const agents: AgentStatusRead[] = [];
    return HttpResponse.json(agents);
  }),

  http.get("/nexus/api/work_items", () => {
    const items: WorkItemSummary[] = [];
    return HttpResponse.json(items);
  }),

  http.get("/nexus/api/runs", () => {
    const runs: RunSummary[] = [];
    return HttpResponse.json(runs);
  }),

  http.get("/nexus/api/runs/:runId/events", () => {
    const events: RunEvent[] = [];
    return HttpResponse.json(events);
  }),

  http.get("/nexus/api/runs/:runId", () => {
    return HttpResponse.json(null, { status: 404 });
  }),

  // SSE endpoint — returns empty stream in tests
  http.get("/nexus/api/events", () => {
    return new HttpResponse(null, {
      headers: { "Content-Type": "text/event-stream" },
    });
  }),
];
