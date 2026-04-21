import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import {
  Badge,
  EmptyState,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "@adlimen/ui-react";
import { listRuns } from "@/api/nexus";
import type { RunStatus } from "@/api/types";

const STATUS_VARIANT: Record<
  RunStatus,
  "primary" | "success" | "error" | "neutral"
> = {
  running: "primary",
  succeeded: "success",
  failed: "error",
  cancelled: "neutral",
  timed_out: "error",
  budget_blocked: "neutral",
  environment_error: "error",
};

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export function AuditLog() {
  const navigate = useNavigate();

  const {
    data: runs,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["runs"],
    queryFn: () => listRuns({ limit: 100 }),
  });

  if (isLoading) {
    return (
      <div className="al-page" data-testid="loading">
        <Skeleton height={32} />
        <Skeleton height={300} style={{ marginTop: "1rem" }} />
      </div>
    );
  }

  const sorted = runs
    ? [...runs].sort(
        (a, b) =>
          new Date(b.started_at).getTime() - new Date(a.started_at).getTime(),
      )
    : [];

  return (
    <div className="al-page">
      <h1 className="al-page__title">Audit Log</h1>

      {isError ? (
        <EmptyState title="Error" description="Failed to load audit runs." />
      ) : !sorted.length ? (
        <EmptyState title="No runs" description="No agent runs recorded yet." />
      ) : (
        <Table>
          <TableHead>
            <TableRow>
              <TableHeaderCell>Agent Role</TableHeaderCell>
              <TableHeaderCell>Model</TableHeaderCell>
              <TableHeaderCell>Status</TableHeaderCell>
              <TableHeaderCell>Started</TableHeaderCell>
              <TableHeaderCell>Finished</TableHeaderCell>
              <TableHeaderCell>Tokens</TableHeaderCell>
              <TableHeaderCell>Cost</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {sorted.map((run) => (
              <TableRow
                key={run.id}
                style={{ cursor: "pointer" }}
                onClick={() => void navigate({ to: `/audit/${run.id}` })}
              >
                <TableCell>{run.agent_role}</TableCell>
                <TableCell>{run.model}</TableCell>
                <TableCell>
                  <Badge variant={STATUS_VARIANT[run.status]}>
                    {run.status}
                  </Badge>
                </TableCell>
                <TableCell>{fmtDate(run.started_at)}</TableCell>
                <TableCell>{fmtDate(run.finished_at)}</TableCell>
                <TableCell>
                  {run.tokens_total?.toLocaleString() ?? "—"}
                </TableCell>
                <TableCell>
                  {run.cost_usd != null ? `$${run.cost_usd.toFixed(4)}` : "—"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
