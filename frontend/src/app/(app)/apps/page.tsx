"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Bookmark, LayoutGrid, Plus } from "lucide-react";

import { installApp, listApps } from "@/lib/api";
import type { MiniProgramApp } from "@/lib/types";

const ICONS: Record<string, typeof Bookmark> = { bookmark: Bookmark };

/** The app gallery: what the user has, and what they could add. Installing is
 *  a one-click seed of the manifest's table — there is no configuration step,
 *  because a template the user has to configure is a form, not an app. */
export default function AppsRoute() {
  const router = useRouter();
  const [apps, setApps] = useState<MiniProgramApp[]>([]);
  const [loading, setLoading] = useState(true);
  const [installing, setInstalling] = useState<string | null>(null);

  useEffect(() => {
    listApps()
      .then((res) => setApps(res.apps))
      .catch(() => setApps([]))
      .finally(() => setLoading(false));
  }, []);

  const handleInstall = async (slug: string) => {
    setInstalling(slug);
    try {
      await installApp(slug);
      router.push(`/apps/${slug}`);
    } finally {
      setInstalling(null);
    }
  };

  const installed = apps.filter((a) => a.installed);
  const available = apps.filter((a) => !a.installed);

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-3xl px-8 py-10">
        <h1 className="font-display text-[26px] font-bold tracking-tight text-foreground">Apps</h1>

        {loading ? (
          <p className="mt-8 text-[13px] text-muted-foreground">Loading…</p>
        ) : (
          <>
            {installed.length > 0 && (
              <section className="mt-8">
                <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-dim">
                  Your apps
                </h2>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {installed.map((app) => {
                    const Icon = ICONS[app.icon] ?? LayoutGrid;
                    return (
                      <Link
                        key={app.slug}
                        href={`/apps/${app.slug}`}
                        className="rounded-xl border border-border bg-base p-4 transition-colors hover:border-brand/40 hover:bg-raised"
                      >
                        <Icon className="h-4.5 w-4.5 text-brand" />
                        <div className="mt-2.5 text-[14px] font-semibold text-foreground">
                          {app.title}
                        </div>
                        <div className="mt-0.5 text-[12px] text-muted-foreground">
                          {app.row_count} item{app.row_count === 1 ? "" : "s"}
                        </div>
                      </Link>
                    );
                  })}
                </div>
              </section>
            )}

            {available.length > 0 && (
              <section className="mt-8">
                <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-dim">
                  Add an app
                </h2>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {available.map((app) => {
                    const Icon = ICONS[app.icon] ?? LayoutGrid;
                    return (
                      <div key={app.slug} className="rounded-xl border border-border bg-base p-4">
                        <Icon className="h-4.5 w-4.5 text-brand" />
                        <div className="mt-2.5 text-[14px] font-semibold text-foreground">
                          {app.title}
                        </div>
                        <button
                          type="button"
                          onClick={() => handleInstall(app.slug)}
                          disabled={installing === app.slug}
                          className="mt-3 inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-[12.5px] font-medium text-foreground hover:bg-raised disabled:text-dim"
                        >
                          <Plus className="h-3.5 w-3.5" />
                          {installing === app.slug ? "Setting up…" : "Add"}
                        </button>
                      </div>
                    );
                  })}
                </div>
              </section>
            )}
          </>
        )}
      </div>
    </div>
  );
}
