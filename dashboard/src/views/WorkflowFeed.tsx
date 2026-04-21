import { useQuery } from "@tanstack/react-query";
import { useQueryClient } from "@tanstack/react-query";
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
import { getWorkflows, listWorkItems } from "@/api/nexus";
import { useNexusEvents } from "@/sse/use-nexus-events";
import type { WorkflowStatus, WorkItemStatus } from "@/api/types";

const STATUS_VARIANT: Record<
  WorkflowStatus,
  "primary" | "success" | "error" | "neutral"
> = {
  running: "primary",
  done: "success",
  failed: "error",
  pending: "neutral",
  cancelled: "neutral",
};

const ITEM_VARIANT: Record<
  WorkItemStatus,
  "primary" | "success" | "error" | "neutral"
> = {
  running: "primary",
  done: "success",
  failed: "error",
  pending: "neutral",
};

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export function WorkflowFeed() {
  const queryClient = useQueryClient();
  useNexusEvents(queryClient);

  const {
    data: workflows,
    isLoading: loadingWf,
    isError: errorWf,
  } = useQuery({
    queryKey: ["workflows"],
    queryFn: () => getWorkflows(),
  });

  const {
    data: workItems,
    isLoading: loadingWi,
    isError: errorWi,
  } = useQuery({
    queryKey: ["work_items", { status: ["running", "done", "failed"] }],
    queryFn: () => listWorkItems({ status: ["running", "done", "failed"] }),
  });

  if (loadingWf || loadingWi) {
    return (
      <div className="al-page" data-testid="loading">
        <Skeleton height={32} />
        <Skeleton height={200} style={{ marginTop: "1rem" }} />
      </div>
    );
  }

  return (
    <div className="al-page">
      <h1 className="al-page__title">Workflow Feed</h1>

      <section aria-label="Workflows">
        {errorWf ? (
          <EmptyState title="Error" description="Failed to load workflows." />
        ) : !workflows?.length ? (
          <EmptyState title="No workflows" description="No workflows found." />
        ) : (
          <Table>
            <TableHead>
              <TableRow>
                <TableHeaderCell>Name</TableHeaderCell>
                <TableHeaderCell>Status</TableHeaderCell>
                <TableHeaderCell>Started</TableHeaderCell>
                <TableHeaderCell>Completed</TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {workflows.map((wf) => (
                <TableRow key={wf.id}>
                  <TableCell>{wf.name}</TableCell>
                  <TableCell>
                    <Badge variant={STATUS_VARIANT[wf.status]}>
                      {wf.status}
                    </Badge>
                  </TableCell>
                  <TableCell>{fmtDate(wf.started_at)}</TableCell>
                  <TableCell>{fmtDate(wf.completed_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </section>

      <section aria-label="Work items" style={{ marginTop: "2rem" }}>
        <h2 className="al-section__title">Recent Work Items</h2>
        {errorWi ? (
          <EmptyState title="Error" description="Failed to load work items." />
        ) : !workItems?.length ? (
          <EmptyState
            title="No work items"
            description="No active work items."
          />
        ) : (
          <Table>
            <TableHead>
              <TableRow>
                <TableHeaderCell>Agent Role</TableHeaderCell>
                <TableHeaderCell>Type</TableHeaderCell>
                <TableHeaderCell>Priority</TableHeaderCell>
                <TableHeaderCell>Status</TableHeaderCell>
                <TableHeaderCell>Started</TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {workItems.map((item) => (
                <TableRow key={item.id}>
                  <TableCell>{item.agent_role}</TableCell>
                  <TableCell>{item.type}</TableCell>
                  <TableCell>{item.priority}</TableCell>
                  <TableCell>
                    <Badge variant={ITEM_VARIANT[item.status]}>
                      {item.status}
                    </Badge>
                  </TableCell>
                  <TableCell>{fmtDate(item.started_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </section>
    </div>
  );
}
