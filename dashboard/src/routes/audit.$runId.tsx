import { createFileRoute } from "@tanstack/react-router";
import { AuditRunDetail } from "@/views/AuditRunDetail";

export const Route = createFileRoute("/audit/$runId")({
  component: function AuditRunDetailPage() {
    const { runId } = Route.useParams();
    return <AuditRunDetail runId={runId} />;
  },
});
