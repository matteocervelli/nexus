import { createFileRoute } from "@tanstack/react-router";
import { WorkflowFeed } from "@/views/WorkflowFeed";

export const Route = createFileRoute("/workflows")({
  component: WorkflowFeed,
});
