import { useQuery } from "@tanstack/react-query";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
  Badge,
  Skeleton,
} from "@adlimen/ui-react";
import { getRun, listRunEvents } from "@/api/nexus";
import type { RunStatus, RunEventType } from "@/api/types";

interface Props {
  runId: string;
}

const STATUS_VARIANT: Record<RunStatus, "primary" | "success" | "error" | "neutral"> = {
  running: "primary",
  succeeded: "success",
  failed: "error",
  cancelled: "neutral",
  timed_out: "error",
  budget_blocked: "neutral",
  environment_error: "error",
};

const EVENT_VARIANT: Record<RunEventType, "primary" | "success" | "error" | "neutral"> = {
  tool_call: "primary",
  tool_result: "neutral",
  model_output: "success",
  stderr_line: "error",
  status_change: "neutral",
};

function fmtDuration(start: string, end: string | null): string {
  if (!end) return "—";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${String(Math.floor(ms / 60_000))}m ${String(Math.round((ms % 60_000) / 1000))}s`;
}

export function AuditRunDetail({ runId }: Props) {
  const { data: run, isLoading: loadingRun } = useQuery({
    queryKey: ["run", runId],
    queryFn: () => getRun(runId),
  });

  const { data: events, isLoading: loadingEvents } = useQuery({
    queryKey: ["run_events", runId],
    queryFn: () => listRunEvents(runId),
    enabled: !!run,
  });

  if (loadingRun) {
    return (
      <div className="al-page" data-testid="loading">
        <Skeleton height={48} />
        <Skeleton height={300} style={{ marginTop: "1rem" }} />
      </div>
    );
  }

  if (!run) {
    return (
      <div className="al-page">
        <p>Run not found.</p>
      </div>
    );
  }

  const sorted = events
    ? [...events].sort((a, b) => a.event_index - b.event_index)
    : [];

  return (
    <div className="al-page">
      <h1 className="al-page__title">Run Detail</h1>

      <section className="al-card" aria-label="Run metadata">
        <dl className="al-description-list">
          <div>
            <dt>Agent Role</dt>
            <dd>{run.agent_role}</dd>
          </div>
          <div>
            <dt>Model</dt>
            <dd>{run.model}</dd>
          </div>
          <div>
            <dt>Backend</dt>
            <dd>{run.execution_backend}</dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd>
              <Badge variant={STATUS_VARIANT[run.status]}>{run.status}</Badge>
            </dd>
          </div>
          <div>
            <dt>Duration</dt>
            <dd>{fmtDuration(run.started_at, run.finished_at)}</dd>
          </div>
          <div>
            <dt>Tokens</dt>
            <dd>{run.tokens_total?.toLocaleString() ?? "—"}</dd>
          </div>
          <div>
            <dt>Cost</dt>
            <dd>{run.cost_usd != null ? `$${run.cost_usd.toFixed(4)}` : "—"}</dd>
          </div>
        </dl>
      </section>

      {run.stdout_excerpt && (
        <Accordion style={{ marginTop: "1rem" }}>
          <AccordionItem itemId="stdout">
            <AccordionTrigger>stdout</AccordionTrigger>
            <AccordionContent>
              <pre className="al-code">{run.stdout_excerpt}</pre>
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      )}

      {run.stderr_excerpt && (
        <Accordion style={{ marginTop: "0.5rem" }}>
          <AccordionItem itemId="stderr">
            <AccordionTrigger>stderr</AccordionTrigger>
            <AccordionContent>
              <pre className="al-code al-code--error">{run.stderr_excerpt}</pre>
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      )}

      <section style={{ marginTop: "1.5rem" }}>
        <h2 className="al-section__title">Event Timeline</h2>
        {loadingEvents ? (
          <Skeleton height={200} />
        ) : (
          <ol className="al-timeline">
            {sorted.map((ev) => (
              <li key={ev.id} className="al-timeline__item">
                <div className="al-timeline__header">
                  <Badge variant={EVENT_VARIANT[ev.event_type]}>
                    {ev.event_type}
                  </Badge>
                  {ev.tool_name && (
                    <span className="al-text--small al-text--mono">
                      {ev.tool_name}
                    </span>
                  )}
                  <span className="al-text--muted al-text--small">
                    #{ev.event_index}
                  </span>
                </div>
                <pre className="al-code al-code--small">
                  {JSON.stringify(ev.payload, null, 2)}
                </pre>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
