"use client";

import { Shell } from "@/components/Shell";
import { DataPage } from "@/components/DataPage";

export default function TelemetryPage() {
  return (
    <Shell>
      <DataPage
        title="Telemetry Inventory"
        endpoint="/telemetry-sources"
        emptyMessage="No telemetry sources are configured. Seed baseline telemetry before running workflows."
        columns={[
          { key: "name", label: "Source" },
          { key: "category", label: "Category" },
          { key: "platform", label: "Platform" },
          { key: "enabled", label: "Enabled" },
          { key: "retention_days", label: "Retention" },
          { key: "fields", label: "Fields", render: (item) => Array.isArray(item.fields) ? item.fields.join(", ") : "" },
          { key: "owner", label: "Owner" }
        ]}
      />
    </Shell>
  );
}
