import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/mocks/server";
import { AgentStatus } from "./AgentStatus";
import type { AgentStatusRead } from "@/api/types";

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const AGENTS: AgentStatusRead[] = [
  {
    agent_role: "code-agent",
    execution_backend: "claude-code-cli",
    model: "claude-sonnet-4-6",
    running_work_items: 2,
    monthly_token_budget: 100_000,
    tokens_used_this_month: 40_000,
  },
  {
    agent_role: "security-agent",
    execution_backend: "anthropic-sdk",
    model: "claude-sonnet-4-6",
    running_work_items: 0,
    monthly_token_budget: 50_000,
    tokens_used_this_month: 45_000,
  },
  {
    agent_role: "ops-agent",
    execution_backend: "openai-sdk",
    model: "gpt-4o",
    running_work_items: 1,
    monthly_token_budget: 200_000,
    tokens_used_this_month: 200_000,
  },
];

describe("AgentStatus", () => {
  it("renders agent rows", async () => {
    server.use(http.get("/nexus/api/agents", () => HttpResponse.json(AGENTS)));

    render(<AgentStatus />, { wrapper });

    expect(await screen.findByText("code-agent")).toBeInTheDocument();
    expect(screen.getByText("security-agent")).toBeInTheDocument();
    expect(screen.getByText("ops-agent")).toBeInTheDocument();
  });

  it("renders model and backend columns", async () => {
    server.use(http.get("/nexus/api/agents", () => HttpResponse.json(AGENTS)));

    render(<AgentStatus />, { wrapper });

    await screen.findByText("code-agent");
    expect(screen.getAllByText("claude-sonnet-4-6").length).toBeGreaterThan(0);
    expect(screen.getByText("claude-code-cli")).toBeInTheDocument();
  });

  it("renders running work item count", async () => {
    server.use(http.get("/nexus/api/agents", () => HttpResponse.json(AGENTS)));

    render(<AgentStatus />, { wrapper });

    await screen.findByText("code-agent");
    const rows = screen.getAllByRole("row");
    const codeRow = rows.find((r) => within(r).queryByText("code-agent"));
    expect(within(codeRow as HTMLElement).getByText("2")).toBeInTheDocument();
  });

  it("marks row with aria-invalid when usage >= 80%", async () => {
    server.use(http.get("/nexus/api/agents", () => HttpResponse.json(AGENTS)));

    render(<AgentStatus />, { wrapper });

    await screen.findByText("security-agent");
    const rows = screen.getAllByRole("row");

    // security-agent: 45000/50000 = 90% → aria-invalid
    const securityRow = rows.find((r) => within(r).queryByText("security-agent"));
    expect(securityRow).toHaveAttribute("aria-invalid", "true");

    // ops-agent: 200000/200000 = 100% → aria-invalid
    const opsRow = rows.find((r) => within(r).queryByText("ops-agent"));
    expect(opsRow).toHaveAttribute("aria-invalid", "true");

    // code-agent: 40000/100000 = 40% → no aria-invalid
    const codeRow = rows.find((r) => within(r).queryByText("code-agent"));
    expect(codeRow).not.toHaveAttribute("aria-invalid");
  });

  it("shows empty state when no agents", async () => {
    server.use(http.get("/nexus/api/agents", () => HttpResponse.json([])));

    render(<AgentStatus />, { wrapper });

    expect(
      await screen.findByRole("heading", { name: /no agents/i }),
    ).toBeInTheDocument();
  });
});
