"use client";

import { Shell } from "@/components/Shell";
import { DataPage } from "@/components/DataPage";

export default function RunsPage() {
  return (
    <Shell>
      <DataPage
        title="Automation Runs"
        endpoint="/automation-runs"
        emptyMessage="No graph executions exist because no CTI workflow has started."
        columns={[
          { key: "workflow_id", label: "Workflow", render: (item) => <span className="font-mono text-xs">{String(item.workflow_id)}</span> },
          { key: "id", label: "Graph Run", render: (item) => <span className="font-mono text-xs">{String(item.id)}</span> },
          { key: "cti_event_id", label: "CTI Event", render: (item) => <span className="font-mono text-xs">{String(item.cti_event_id ?? "")}</span> },
          { key: "status", label: "Status" },
          { key: "trigger_source", label: "Trigger" },
          { key: "selected_route", label: "Route" },
          { key: "current_node", label: "Current Node" },
          { key: "duration_ms", label: "Duration ms" },
          { key: "retry_count", label: "Retries" },
          { key: "total_tokens", label: "Tokens" },
          { key: "estimated_cost", label: "Cost" },
          { key: "terminal_result", label: "Terminal" },
          { key: "terminal_reason", label: "Reason" },
          { key: "failure_reason", label: "Failure" }
        ]}
      />
    </Shell>
  );
}
