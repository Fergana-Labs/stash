"use client";

import { useEffect, useState } from "react";

import { listMyWorkspaces } from "@/lib/api";

import McpConnectorList from "./McpConnectorList";
import SourceConnectorList from "./SourceConnectorList";

type Props = {
  embedded?: boolean;
};

export default function IntegrationsSettings({ embedded = false }: Props) {
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listMyWorkspaces()
      .then(({ workspaces }) => {
        const primary = workspaces.find((workspace) => workspace.is_primary) ?? workspaces[0];
        setWorkspaceId(primary?.id ?? null);
      })
      .catch(() => setWorkspaceId(null))
      .finally(() => setLoading(false));
  }, []);

  const body = (
    <>
      <div>
        <h2 className="text-base font-semibold text-foreground">Sources</h2>
        <p className="mt-0.5 text-xs text-muted">
          Connect accounts and choose the sources your agent can read.
        </p>
      </div>

      {loading ? (
        <div className="text-xs text-muted">Loading...</div>
      ) : workspaceId ? (
        <SourceConnectorList workspaceId={workspaceId} returnTo="/settings" />
      ) : (
        <div className="text-xs text-muted">No workspace is available for sources.</div>
      )}

      <div className="pt-2">
        <h2 className="text-base font-semibold text-foreground">Agent tools</h2>
        <p className="mt-0.5 text-xs text-muted">
          Give your agents read-only access to outside services through Stash. Credentials stay
          encrypted on the server; agents connect with the Stash auth they already have.
        </p>
      </div>

      {!loading && workspaceId && <McpConnectorList workspaceId={workspaceId} />}
    </>
  );

  if (embedded) {
    return (
      <section className="space-y-4 rounded-2xl border border-border bg-surface p-6">
        {body}
      </section>
    );
  }

  return (
    <div className="flex min-h-screen flex-col">
      <main className="flex-1 px-4 py-10">
        <div className="mx-auto w-full max-w-2xl space-y-4">{body}</div>
      </main>
    </div>
  );
}
