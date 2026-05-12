"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import ActivityFeed from "../../components/ActivityFeed";
import AppShell from "../../components/AppShell";
import { useAuth } from "../../hooks/useAuth";
import { listActivity, type ActivityEvent } from "../../lib/api";

export default function ActivityPage() {
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    if (!user) return;

    let cancelled = false;
    listActivity(100)
      .then((nextEvents) => {
        if (!cancelled) setEvents(nextEvents);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setFetching(false);
      });

    return () => {
      cancelled = true;
    };
  }, [user]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  if (loading) return <div className="flex h-screen items-center justify-center text-muted">Loading…</div>;
  if (!user) return null;

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="mx-auto max-w-3xl px-12 py-10">
        <h1 className="font-display text-[30px] font-bold tracking-tight text-foreground">
          Activity
        </h1>
        <p className="mt-1 text-[13px] text-muted">
          Recent changes across your stashes.
        </p>

        {fetching ? (
          <p className="mt-8 text-[13px] text-muted">Loading…</p>
        ) : events.length === 0 ? (
          <p className="mt-8 text-[13px] text-muted">
            No activity yet. Push a transcript, edit a page, or upload a file.
          </p>
        ) : (
          <ActivityFeed events={events} showStash />
        )}
      </div>
    </AppShell>
  );
}
