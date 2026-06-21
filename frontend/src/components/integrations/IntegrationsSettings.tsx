"use client";

import SourceConnectorList from "./SourceConnectorList";

type Props = {
  embedded?: boolean;
};

export default function IntegrationsSettings({ embedded = false }: Props) {
  const body = (
    <>
      <div>
        <h2 className="text-base font-semibold text-foreground">Sources</h2>
        <p className="mt-0.5 text-xs text-muted">
          Connect accounts and choose the sources your agent can read.
        </p>
      </div>

      <SourceConnectorList returnTo="/settings" />
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
