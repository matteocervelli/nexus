import { createFileRoute } from "@tanstack/react-router";
import { AgentStatus } from "@/views/AgentStatus";

export const Route = createFileRoute("/agents")({
  component: AgentStatus,
});
