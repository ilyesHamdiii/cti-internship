"use client";

import { Shell } from "@/components/Shell";
import { DataPage } from "@/components/DataPage";

export default function ProposalsPage() {
  return (
    <Shell>
      <DataPage
        title="Proposal Details"
        endpoint="/proposals"
        emptyMessage="No proposal details exist because no validated candidate has entered review."
        columns={[
          { key: "id", label: "Proposal", render: (item) => <span className="font-mono text-xs">{String(item.id)}</span> },
          { key: "behavior_id", label: "Behavior ID", render: (item) => <span className="font-mono text-xs">{String(item.behavior_id)}</span> },
          { key: "behavior_summary", label: "Behavior" },
          { key: "attack_techniques", label: "ATT&CK", render: (item) => Array.isArray(item.attack_techniques) ? item.attack_techniques.join(", ") : "" },
          { key: "current_revision_number", label: "Revision" },
          { key: "quality_score", label: "Quality" },
          { key: "confidence", label: "Confidence" },
          { key: "status", label: "Status" }
        ]}
      />
    </Shell>
  );
}
