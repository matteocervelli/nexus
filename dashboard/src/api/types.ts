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
  | "openai-sdk"
  | "process";

export type RunStatus =
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "timed_out"
  | "budget_blocked"
  | "environment_error";

export type RunEventType =
  | "tool_call"
  | "tool_result"
  | "model_output"
  | "stderr_line"
  | "status_change";

export type WorkItemStatus = "pending" | "running" | "done" | "failed";

export interface WorkflowRead {
  id: string;
  name: string;
  status: WorkflowStatus;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface WorkflowStep {
  id: string;
  step_index: number;
  agent_role: string;
  status: string;
  depends_on: string[];
  started_at: string | null;
  completed_at: string | null;
}

export interface WorkflowDetail extends WorkflowRead {
  dag: Record<string, unknown>;
  updated_at: string | null;
  steps: WorkflowStep[];
}

export interface AgentStatusRead {
  agent_role: string;
  execution_backend: AgentExecutionBackend;
  model: string;
  running_work_items: number;
  monthly_token_budget: number;
  tokens_used_this_month: number;
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

export interface WorkItemSummary {
  id: string;
  type: string;
  agent_role: string;
  priority: string;
  status: WorkItemStatus;
  context: Record<string, unknown>;
  result: Record<string, unknown> | null;
  token_cost: number;
  created_at: string;
  updated_at: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface RunSummary {
  id: string;
  work_item_id: string | null;
  workflow_step_id: string | null;
  agent_role: string;
  execution_backend: string;
  model: string;
  status: RunStatus;
  started_at: string;
  finished_at: string | null;
  tokens_total: number | null;
  cost_usd: number | null;
  created_at: string;
  updated_at: string | null;
}

export interface RunDetail extends RunSummary {
  external_run_id: string | null;
  session_kind: string | null;
  session_id_before: string | null;
  session_id_after: string | null;
  session_metadata: Record<string, unknown> | null;
  tokens_input: number | null;
  tokens_output: number | null;
  cost_source: string | null;
  stdout_excerpt: string | null;
  stderr_excerpt: string | null;
  result_payload: Record<string, unknown> | null;
  error_code: string | null;
  error_message: string | null;
}

export interface RunEvent {
  id: string;
  run_id: string;
  event_index: number;
  event_type: RunEventType;
  tool_name: string | null;
  payload: Record<string, unknown>;
  occurred_at: string;
  created_at: string;
}
