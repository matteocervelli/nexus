import { http, HttpResponse } from "msw";
import type { AgentStatusRead, WorkflowRead } from "@/api/types";

export const handlers = [
  http.get("/nexus/api/workflows", () => {
    const workflows: WorkflowRead[] = [];
    return HttpResponse.json(workflows);
  }),

  http.get("/nexus/api/status", () => {
    const status: AgentStatusRead[] = [];
    return HttpResponse.json(status);
  }),
];
