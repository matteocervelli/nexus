// Local type stubs — will be replaced by @atrium/types when dashboard moves to atrium/apps/.

export type WorkflowStatus =
  | "pending"
  | "running"
  | "done"
  | "failed"
  | "cancelled";
export type AgentExecutionBackend =
  | "codex-cli"
  | "claude-code-cli"
  | "anthropic-sdk"
  | "openai-sdk";

export interface WorkflowRead {
  id: string;
  name: string;
  status: WorkflowStatus;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface AgentStatusRead {
  agent_role: string;
  execution_backend: AgentExecutionBackend;
  model: string;
  running_work_items: number;
  monthly_token_budget: number;
  tokens_used_this_month: number;
}

export interface AuditEvent {
  id: string;
  work_item_id: string;
  agent_role: string;
  event: string;
  created_at: string;
}

export interface BudgetAlert {
  agent_role: string;
  tokens_used: number;
  monthly_budget: number;
  percent: number;
}

export interface StatusSummary {
  running_count: number;
  queue_depth: number;
  budget_alerts: BudgetAlert[];
}
