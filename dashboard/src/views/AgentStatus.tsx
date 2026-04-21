import { useQuery } from "@tanstack/react-query";
import { useQueryClient } from "@tanstack/react-query";
import {
  EmptyState,
  Progress,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "@adlimen/ui-react";
import { getAgents } from "@/api/nexus";
import { useNexusEvents } from "@/sse/use-nexus-events";

export function AgentStatus() {
  const queryClient = useQueryClient();
  useNexusEvents(queryClient);

  const {
    data: agents,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["agents"],
    queryFn: getAgents,
  });

  if (isLoading) {
    return (
      <div className="al-page" data-testid="loading">
        <Skeleton height={32} />
        <Skeleton height={200} style={{ marginTop: "1rem" }} />
      </div>
    );
  }

  return (
    <div className="al-page">
      <h1 className="al-page__title">Agent Status</h1>

      {isError ? (
        <EmptyState title="Error" description="Failed to load agent status." />
      ) : !agents?.length ? (
        <EmptyState title="No agents" description="No agents registered." />
      ) : (
        <Table>
          <TableHead>
            <TableRow>
              <TableHeaderCell>Agent Role</TableHeaderCell>
              <TableHeaderCell>Model</TableHeaderCell>
              <TableHeaderCell>Backend</TableHeaderCell>
              <TableHeaderCell>Running</TableHeaderCell>
              <TableHeaderCell>Token Usage</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {agents.map((agent) => {
              const pct =
                agent.monthly_token_budget > 0
                  ? Math.round(
                      (agent.tokens_used_this_month /
                        agent.monthly_token_budget) *
                        100,
                    )
                  : 0;
              const overBudget = pct >= 80;

              return (
                <TableRow
                  key={agent.agent_role}
                  aria-invalid={overBudget ? "true" : undefined}
                  className={overBudget ? "al-table-row--warning" : undefined}
                >
                  <TableCell>{agent.agent_role}</TableCell>
                  <TableCell>{agent.model}</TableCell>
                  <TableCell>{agent.execution_backend}</TableCell>
                  <TableCell>{agent.running_work_items}</TableCell>
                  <TableCell>
                    <Progress
                      value={pct}
                      label={`${String(pct)}% of monthly budget used`}
                    />
                    <span className="al-text--small">
                      {agent.tokens_used_this_month.toLocaleString()} /{" "}
                      {agent.monthly_token_budget.toLocaleString()}
                    </span>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
