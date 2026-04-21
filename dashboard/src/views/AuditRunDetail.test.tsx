import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/mocks/server";
import { AuditRunDetail } from "./AuditRunDetail";
import type { RunDetail, RunEvent } from "@/api/types";

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const RUN: RunDetail = {
  id: "run-1",
  work_item_id: "wi-1",
  workflow_step_id: null,
  agent_role: "code-agent",
  execution_backend: "claude-code-cli",
  model: "claude-sonnet-4-6",
  status: "succeeded",
  started_at: "2026-04-21T08:00:00Z",
  finished_at: "2026-04-21T08:15:00Z",
  tokens_total: 12000,
  cost_usd: 0.024,
  created_at: "2026-04-21T08:00:00Z",
  updated_at: null,
  external_run_id: null,
  session_kind: null,
  session_id_before: null,
  session_id_after: null,
  session_metadata: null,
  tokens_input: 8000,
  tokens_output: 4000,
  cost_source: "anthropic",
  stdout_excerpt: "All tests passed.\n3 suites, 15 tests",
  stderr_excerpt: null,
  result_payload: { status: "ok" },
  error_code: null,
  error_message: null,
};

const EVENTS: RunEvent[] = [
  {
    id: "ev-1",
    run_id: "run-1",
    event_index: 0,
    event_type: "tool_call",
    tool_name: "read_file",
    payload: { path: "src/foo.ts" },
    occurred_at: "2026-04-21T08:01:00Z",
    created_at: "2026-04-21T08:01:00Z",
  },
  {
    id: "ev-2",
    run_id: "run-1",
    event_index: 1,
    event_type: "tool_result",
    tool_name: "read_file",
    payload: { content: "export const foo = 1;" },
    occurred_at: "2026-04-21T08:01:05Z",
    created_at: "2026-04-21T08:01:05Z",
  },
  {
    id: "ev-3",
    run_id: "run-1",
    event_index: 2,
    event_type: "model_output",
    tool_name: null,
    payload: { text: "LGTM" },
    occurred_at: "2026-04-21T08:02:00Z",
    created_at: "2026-04-21T08:02:00Z",
  },
];

describe("AuditRunDetail", () => {
  it("renders run header metadata", async () => {
    server.use(
      http.get("/nexus/api/runs/run-1", () => HttpResponse.json(RUN)),
      http.get("/nexus/api/runs/run-1/events", () => HttpResponse.json(EVENTS)),
    );

    render(<AuditRunDetail runId="run-1" />, { wrapper });

    expect(await screen.findByText("code-agent")).toBeInTheDocument();
    expect(screen.getByText("claude-sonnet-4-6")).toBeInTheDocument();
    expect(screen.getByText("claude-code-cli")).toBeInTheDocument();
  });

  it("renders events in event_index order", async () => {
    server.use(
      http.get("/nexus/api/runs/run-1", () => HttpResponse.json(RUN)),
      http.get("/nexus/api/runs/run-1/events", () =>
        HttpResponse.json([...EVENTS].reverse()),
      ),
    );

    render(<AuditRunDetail runId="run-1" />, { wrapper });

    await screen.findByText("code-agent");
    const eventItems = await screen.findAllByRole("listitem");
    // tool_call (ev-1) should appear before model_output (ev-3)
    const toolCallIdx = eventItems.findIndex((el) =>
      el.textContent.includes("tool_call"),
    );
    const modelOutputIdx = eventItems.findIndex((el) =>
      el.textContent.includes("model_output"),
    );
    expect(toolCallIdx).toBeLessThan(modelOutputIdx);
  });

  it("renders tool_name and event_type chip", async () => {
    server.use(
      http.get("/nexus/api/runs/run-1", () => HttpResponse.json(RUN)),
      http.get("/nexus/api/runs/run-1/events", () => HttpResponse.json(EVENTS)),
    );

    render(<AuditRunDetail runId="run-1" />, { wrapper });

    await screen.findByText("code-agent");
    expect((await screen.findAllByText("tool_call")).length).toBeGreaterThan(0);
    expect((await screen.findAllByText("read_file")).length).toBeGreaterThan(0);
  });

  it("renders stdout_excerpt panel", async () => {
    server.use(
      http.get("/nexus/api/runs/run-1", () => HttpResponse.json(RUN)),
      http.get("/nexus/api/runs/run-1/events", () => HttpResponse.json([])),
    );

    render(<AuditRunDetail runId="run-1" />, { wrapper });

    expect(
      await screen.findByText(/All tests passed/),
    ).toBeInTheDocument();
  });

  it("renders cost and token counts", async () => {
    server.use(
      http.get("/nexus/api/runs/run-1", () => HttpResponse.json(RUN)),
      http.get("/nexus/api/runs/run-1/events", () => HttpResponse.json([])),
    );

    render(<AuditRunDetail runId="run-1" />, { wrapper });

    await screen.findByText("code-agent");
    // cost_usd = 0.024 → "$0.024" or "0.024"
    expect(screen.getByText(/0\.024/)).toBeInTheDocument();
    // tokens_total = 12000
    expect(screen.getByText(/12[,.]?000/)).toBeInTheDocument();
  });
});
