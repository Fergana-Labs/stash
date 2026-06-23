"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import DescriptionEditor, {
  isBlankDescription,
} from "@/components/DescriptionEditor";
import { generateWelcomeHtml } from "@/lib/onboarding/welcomeContent";
import { ScopeHomeSkeleton } from "@/components/SkeletonStates";
import { StashIcon } from "@/components/SkillIcons";
import { useAuth } from "@/hooks/useAuth";
import { createPage, updateMe } from "@/lib/api";
import type { User } from "@/lib/types";

function relativeTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return "just now";
  const m = Math.floor(ms / 60_000);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} h ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d} d ago`;
  return new Date(iso).toLocaleDateString();
}

export default function HomePage() {
  const router = useRouter();
  const { user, loading } = useAuth();

  const [profile, setProfile] = useState<User | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setProfile(user);
  }, [user]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  // A fresh space lands empty; seed the "what to do next" welcome doc as the
  // default description (idempotent — only writes when still blank). The user
  // can edit or delete it like any page.
  useEffect(() => {
    if (!profile) return;
    if (!isBlankDescription(profile.description ?? "")) return;
    const html = generateWelcomeHtml({
      displayName: profile.display_name || profile.name,
    });
    updateMe({ description: html })
      .then(setProfile)
      .catch(() => {});
  }, [profile]);

  async function handleNewPage() {
    try {
      const page = await createPage("Untitled");
      router.push(`/p/${page.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create page");
    }
  }

  if (loading) return <ScopeHomeSkeleton />;
  if (!user) return null;
  if (!profile) return <ScopeHomeSkeleton />;

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="h-[72px] w-full bg-gradient-to-r from-[var(--color-brand-200)] via-amber-100 to-rose-100" />

      <div className="mx-auto max-w-[920px] px-12 pb-20">
        {/* Identity strip: icon + name + meta + actions */}
        <div className="flex items-start justify-between gap-3 pt-4">
          <div className="flex min-w-0 items-center gap-3">
            <span className="-mt-9 flex h-12 w-12 flex-shrink-0 items-center justify-center overflow-hidden rounded-[10px] border-2 border-base bg-base text-[28px] text-[var(--color-brand-700)] shadow-sm">
              <StashIcon />
            </span>
            <div className="min-w-0">
              <h2 className="m-0 truncate font-display text-[20px] font-bold leading-tight tracking-[-0.015em] text-foreground">
                {profile.display_name || profile.name}
              </h2>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-[12px] text-muted">
                {profile.last_seen && (
                  <>
                    <span className="text-muted/60">·</span>
                    <span>updated {relativeTime(profile.last_seen)}</span>
                  </>
                )}
              </div>
            </div>
          </div>
          <div className="flex flex-shrink-0 items-center gap-1.5 pt-1">
            <button
              type="button"
              onClick={handleNewPage}
              className="cursor-pointer rounded-md border border-border-subtle bg-raised px-2.5 py-1 text-[12px] font-medium text-foreground hover:bg-raised-2"
            >
              + New page
            </button>
          </div>
        </div>

        {error && (
          <div className="mt-4 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
            {error}
          </div>
        )}

        <section className="mt-5">
          <DescriptionEditor
            value={profile.description ?? ""}
            canEdit={true}
            placeholder="Describe your space…"
            ariaLabel="Description"
            onSave={async (html) => {
              setProfile(await updateMe({ description: html }));
            }}
          />
        </section>
      </div>
    </div>
  );
}
