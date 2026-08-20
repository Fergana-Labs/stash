"use client";

import { useState } from "react";

import { updateTenant } from "@/lib/api";
import type { Tenant } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Whether this tenant's sessions feed the shared anonymized wiki. Shared by the
 *  tenant list and the tenant detail page so the control behaves identically in both. */
export default function WikiToggle({ tenant, onChanged }: { tenant: Tenant; onChanged: () => void }) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    setSaving(true);
    setError(null);
    try {
      await updateTenant(tenant.id, { share_wiki: !tenant.share_wiki });
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not change the wiki setting");
    } finally {
      setSaving(false);
    }
  }

  return (
    <span className="shrink-0">
      <button
        onClick={(e) => {
          // The row around this is a link to the tenant.
          e.preventDefault();
          e.stopPropagation();
          void toggle();
        }}
        disabled={saving}
        title="Whether this tenant's sessions feed the shared anonymized wiki"
        className={cn(
          "rounded-sm px-3 py-1.5 text-[13px] transition-colors disabled:opacity-50",
          tenant.share_wiki
            ? "bg-brand-500/10 font-medium text-brand-500"
            : "border border-border text-muted-foreground hover:bg-raised",
        )}
      >
        {tenant.share_wiki ? "Feeds wiki" : "Wiki opt-out"}
      </button>
      {error && <span className="mt-1 block text-[12px] text-error">{error}</span>}
    </span>
  );
}
