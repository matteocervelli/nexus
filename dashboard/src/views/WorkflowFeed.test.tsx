import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/mocks/server";
import { WorkflowFeed } from "./WorkflowFeed";
import type { WorkflowRead, WorkItemSummary } from "@/api/types";

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const WORKFLOWS: WorkflowRead[] = [
  {
    id: "wf-1",
    name: "Alpha Pipeline",
    status: "running",
    created_at: "2026-04-21T08:00:00Z",
    started_at: "2026-04-21T08:01:00Z",
    completed_at: null,
  },
  {
    id: "wf-2",
    name: "Beta Pipeline",
    status: "done",
    created_at: "2026-04-20T10:00:00Z",
    started_at: "2026-04-20T10:01:00Z",
    completed_at: "2026-04-20T11:00:00Z",
  },
  {
    id: "wf-3",
    name: "Gamma Pipeline",
    status: "failed",
    created_at: "2026-04-19T09:00:00Z",
    started_at: "2026-04-19T09:01:00Z",
    completed_at: "2026-04-19T09:05:00Z",
  },
];

const WORK_ITEMS: WorkItemSummary[] = [
  {
    id: "wi-1",
    type: "code_review",
    agent_role: "code-agent",
    priority: "P1",
    status: "running",
    context: {},
    result: null,
    token_cost: 0,
    created_at: "2026-04-21T08:00:00Z",
    updated_at: null,
    started_at: "2026-04-21T08:01:00Z",
    completed_at: null,
  },
  {
    id: "wi-2",
    type: "security_scan",
    agent_role: "security-agent",
    priority: "P2",
    status: "done",
    context: {},
    result: null,
    token_cost: 1200,
    created_at: "2026-04-21T07:00:00Z",
    updated_at: null,
    started_at: "2026-04-21T07:01:00Z",
    completed_at: "2026-04-21T07:30:00Z",
  },
];

describe("WorkflowFeed", () => {
  it("renders workflow table rows", async () => {
    server.use(
      http.get("/nexus/api/workflows", () => HttpResponse.json(WORKFLOWS)),
      http.get("/nexus/api/work_items", () => HttpResponse.json(WORK_ITEMS)),
    );

    render(<WorkflowFeed />, { wrapper });

    expect(await screen.findByText("Alpha Pipeline")).toBeInTheDocument();
    expect(screen.getByText("Beta Pipeline")).toBeInTheDocument();
    expect(screen.getByText("Gamma Pipeline")).toBeInTheDocument();
  });

  it("renders status chips with correct variant", async () => {
    server.use(
      http.get("/nexus/api/workflows", () => HttpResponse.json(WORKFLOWS)),
      http.get("/nexus/api/work_items", () => HttpResponse.json([])),
    );

    render(<WorkflowFeed />, { wrapper });

    await screen.findByText("Alpha Pipeline");

    // running row should have a badge with 'running'
    const rows = screen.getAllByRole("row");
    const runningRow = rows.find((r) => within(r).queryByText("Alpha Pipeline"));
    expect(runningRow).toBeDefined();
    expect(within(runningRow as HTMLElement).getByText("running")).toBeInTheDocument();

    const doneRow = rows.find((r) => within(r).queryByText("Beta Pipeline"));
    expect(within(doneRow as HTMLElement).getByText("done")).toBeInTheDocument();

    const failedRow = rows.find((r) => within(r).queryByText("Gamma Pipeline"));
    expect(within(failedRow as HTMLElement).getByText("failed")).toBeInTheDocument();
  });

  it("renders work items feed", async () => {
    server.use(
      http.get("/nexus/api/workflows", () => HttpResponse.json([])),
      http.get("/nexus/api/work_items", () => HttpResponse.json(WORK_ITEMS)),
    );

    render(<WorkflowFeed />, { wrapper });

    expect(await screen.findByText("code-agent")).toBeInTheDocument();
    expect(screen.getByText("security-agent")).toBeInTheDocument();
  });

  it("shows empty state when no workflows", async () => {
    server.use(
      http.get("/nexus/api/workflows", () => HttpResponse.json([])),
      http.get("/nexus/api/work_items", () => HttpResponse.json([])),
    );

    render(<WorkflowFeed />, { wrapper });

    expect(
      await screen.findByRole("heading", { name: /no workflows/i }),
    ).toBeInTheDocument();
  });

  it("shows loading skeleton while fetching", () => {
    // Never resolves — stays loading
    server.use(
      http.get("/nexus/api/workflows", () => new Promise(() => {})),
      http.get("/nexus/api/work_items", () => new Promise(() => {})),
    );

    render(<WorkflowFeed />, { wrapper });

    expect(document.querySelector(".al-skeleton, [data-testid='loading']")).toBeDefined();
  });
});
