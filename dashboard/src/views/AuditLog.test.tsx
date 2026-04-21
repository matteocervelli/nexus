import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/mocks/server";

vi.mock("@tanstack/react-router", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@tanstack/react-router")>();
  return { ...actual, useNavigate: () => vi.fn() };
});
import { AuditLog } from "./AuditLog";
import type { RunSummary } from "@/api/types";

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const RUNS: RunSummary[] = [
  {
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
  },
  {
    id: "run-2",
    work_item_id: "wi-2",
    workflow_step_id: null,
    agent_role: "security-agent",
    execution_backend: "anthropic-sdk",
    model: "claude-sonnet-4-6",
    status: "failed",
    started_at: "2026-04-21T07:00:00Z",
    finished_at: "2026-04-21T07:10:00Z",
    tokens_total: 5000,
    cost_usd: 0.01,
    created_at: "2026-04-21T07:00:00Z",
    updated_at: null,
  },
];

describe("AuditLog", () => {
  it("renders run rows sorted by started_at desc", async () => {
    server.use(http.get("/nexus/api/runs", () => HttpResponse.json(RUNS)));

    render(<AuditLog />, { wrapper });

    const rows = await screen.findAllByRole("row");
    // header row + 2 data rows
    expect(rows.length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText("code-agent")).toBeInTheDocument();
    expect(screen.getByText("security-agent")).toBeInTheDocument();
  });

  it("renders run status in each row", async () => {
    server.use(http.get("/nexus/api/runs", () => HttpResponse.json(RUNS)));

    render(<AuditLog />, { wrapper });

    await screen.findByText("code-agent");
    expect(screen.getByText("succeeded")).toBeInTheDocument();
    expect(screen.getByText("failed")).toBeInTheDocument();
  });

  it("shows empty state when no runs", async () => {
    server.use(http.get("/nexus/api/runs", () => HttpResponse.json([])));

    render(<AuditLog />, { wrapper });

    expect(
      await screen.findByRole("heading", { name: /no runs/i }),
    ).toBeInTheDocument();
  });
});
