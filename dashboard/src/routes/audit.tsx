import { createFileRoute } from "@tanstack/react-router";
import { AuditLog } from "@/views/AuditLog";

export const Route = createFileRoute("/audit")({
  component: AuditLog,
});
