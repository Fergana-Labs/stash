import type { ReactNode } from "react";

type SkeletonProps = {
  className?: string;
};

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function SkeletonBlock({ className }: SkeletonProps) {
  return (
    <div
      aria-hidden="true"
      className={cx("animate-pulse rounded-md bg-raised", className)}
    />
  );
}

function SkeletonLine({ className }: SkeletonProps) {
  return <SkeletonBlock className={cx("h-3", className)} />;
}

function SkeletonCard({
  className,
  children,
}: SkeletonProps & {
  children?: ReactNode;
}) {
  return (
    <div className={cx("rounded-lg border border-border bg-surface p-4", className)}>
      {children}
    </div>
  );
}

function HeaderSkeleton() {
  return (
    <header className="sticky top-0 z-30 grid h-11 flex-shrink-0 grid-cols-[minmax(0,1fr)_minmax(220px,460px)_minmax(0,1fr)] items-center gap-3 border-b border-border bg-base/85 px-3 backdrop-blur-md">
      <div className="flex items-center gap-2">
        <SkeletonBlock className="h-6 w-6 rounded" />
        <SkeletonLine className="h-3 w-36" />
      </div>
      <SkeletonBlock className="h-7 w-full" />
      <div className="flex justify-end gap-2">
        <SkeletonBlock className="h-6 w-16" />
        <SkeletonBlock className="h-6 w-6 rounded-full" />
      </div>
    </header>
  );
}

function SidebarSkeleton() {
  return (
    <aside className="hidden min-h-0 border-r border-border bg-surface px-3 py-3 md:block">
      <SkeletonBlock className="mb-4 h-8 w-full" />
      <div className="space-y-5">
        {[0, 1, 2].map((section) => (
          <div key={section} className="space-y-2">
            <SkeletonLine className="h-2.5 w-16" />
            {[0, 1, 2, 3].map((row) => (
              <div key={row} className="flex items-center gap-2 rounded-md px-2 py-1.5">
                <SkeletonBlock className="h-4 w-4 rounded" />
                <SkeletonLine className={row % 2 === 0 ? "w-36" : "w-24"} />
              </div>
            ))}
          </div>
        ))}
      </div>
    </aside>
  );
}

export function AppShellSkeleton({
  children,
  sidebar = true,
}: {
  children?: ReactNode;
  sidebar?: boolean;
}) {
  return (
    <div className="flex h-screen flex-col overflow-hidden bg-base text-foreground">
      <HeaderSkeleton />
      <div
        className="grid min-h-0 flex-1 overflow-hidden"
        style={{ gridTemplateColumns: sidebar ? "300px minmax(0, 1fr)" : "minmax(0, 1fr)" }}
      >
        {sidebar && <SidebarSkeleton />}
        <main className="min-w-0 overflow-y-auto bg-base">
          {children ?? <WorkspaceHomeSkeleton />}
        </main>
      </div>
    </div>
  );
}

export function AppRouteSkeleton() {
  return (
    <AppShellSkeleton>
      <WorkspaceHomeSkeleton />
    </AppShellSkeleton>
  );
}

export function BasicPageSkeleton() {
  return (
    <main className="min-h-screen bg-base px-6 py-8 text-foreground">
      <div className="mx-auto max-w-[920px]">
        <SkeletonLine className="h-2.5 w-20" />
        <SkeletonLine className="mt-4 h-8 w-72 max-w-full" />
        <SkeletonLine className="mt-3 h-4 w-[520px] max-w-full" />
        <div className="mt-8 grid gap-3 sm:grid-cols-2">
          {[0, 1, 2, 3].map((i) => (
            <SkeletonCard key={i}>
              <SkeletonLine className="h-4 w-36" />
              <SkeletonLine className="mt-3 w-full" />
              <SkeletonLine className="mt-2 w-2/3" />
            </SkeletonCard>
          ))}
        </div>
      </div>
    </main>
  );
}

export function AuthPageSkeleton() {
  return (
    <div className="flex min-h-screen flex-col bg-base text-foreground">
      <div className="border-b border-border bg-surface px-4 py-2">
        <div className="flex justify-end">
          <SkeletonBlock className="h-7 w-24" />
        </div>
      </div>
      <main className="flex flex-1 items-center justify-center px-4 py-12">
        <SkeletonCard className="w-full max-w-sm rounded-2xl p-6">
          <SkeletonLine className="h-5 w-28" />
          <SkeletonBlock className="mt-4 h-10 w-full rounded-lg" />
          <SkeletonBlock className="mt-3 h-10 w-full rounded-lg" />
          <SkeletonBlock className="mt-3 h-10 w-full rounded-xl" />
          <SkeletonLine className="mx-auto mt-4 w-40" />
        </SkeletonCard>
      </main>
    </div>
  );
}

export function AccountSettingsSkeleton() {
  return (
    <div className="flex min-h-screen flex-col bg-base text-foreground">
      <div className="border-b border-border bg-surface px-4 py-2">
        <div className="flex justify-end">
          <SkeletonBlock className="h-7 w-7 rounded-full" />
        </div>
      </div>
      <main className="flex-1 px-4 py-10">
        <div className="mx-auto w-full max-w-2xl space-y-8">
          <SkeletonLine className="h-4 w-16" />
          <div>
            <SkeletonLine className="h-7 w-56" />
            <SkeletonLine className="mt-3 h-4 w-96 max-w-full" />
          </div>
          {[0, 1, 2].map((i) => (
            <SettingsSectionSkeleton key={i} />
          ))}
        </div>
      </main>
    </div>
  );
}

export function ApiKeysSkeleton() {
  return (
    <div className="space-y-2">
      {[0, 1, 2].map((i) => (
        <div key={i} className="flex items-center gap-3 rounded-lg border border-border bg-base p-3">
          <div className="min-w-0 flex-1">
            <SkeletonLine className="h-4 w-40" />
            <SkeletonLine className="mt-2 h-3 w-56 max-w-full" />
          </div>
          <SkeletonBlock className="h-7 w-16" />
        </div>
      ))}
    </div>
  );
}

function SettingsSectionSkeleton() {
  return (
    <SkeletonCard className="rounded-2xl p-6">
      <SkeletonLine className="h-5 w-32" />
      <SkeletonLine className="mt-2 h-3 w-80 max-w-full" />
      <SkeletonBlock className="mt-5 h-10 w-full rounded-lg" />
      <SkeletonBlock className="mt-3 h-10 w-full rounded-lg" />
      <SkeletonBlock className="mt-4 h-9 w-32 rounded-lg" />
    </SkeletonCard>
  );
}

export function HomeSkeleton() {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-8 py-12">
      <SkeletonLine className="h-3 w-20" />
      <SkeletonLine className="h-9 w-80 max-w-full" />
      <div className="space-y-2">
        <SkeletonLine className="h-4 w-full" />
        <SkeletonLine className="h-4 w-4/5" />
      </div>
      <SkeletonCard className="border-dashed p-4">
        <SkeletonLine className="h-5 w-32" />
        <SkeletonBlock className="mt-4 h-9 w-36" />
      </SkeletonCard>
      <SkeletonCard className="p-4">
        <SkeletonLine className="h-5 w-40" />
        <SkeletonLine className="mt-2 w-64 max-w-full" />
        <div className="mt-4 flex gap-2">
          <SkeletonBlock className="h-9 flex-1" />
          <SkeletonBlock className="h-9 w-20" />
        </div>
      </SkeletonCard>
    </div>
  );
}

export function DiscoverSkeleton() {
  return (
    <div className="mx-auto max-w-[1180px] px-12 pb-20 pt-9">
      <div className="flex items-center gap-3">
        <SkeletonBlock className="h-9 max-w-[460px] flex-1 rounded-lg" />
        <SkeletonBlock className="h-8 w-56 rounded-lg" />
        <span className="flex-1" />
        <SkeletonLine className="w-20" />
      </div>
      <CardGridSkeleton className="mt-6" />
    </div>
  );
}

export function ActivitySkeleton() {
  return (
    <div className="mx-auto max-w-[920px] px-12 pb-20 pt-9">
      <SkeletonLine className="h-3 w-20" />
      <SkeletonLine className="mt-3 h-8 w-[520px] max-w-full" />
      <SkeletonLine className="mt-3 h-4 w-[620px] max-w-full" />
      <div className="mt-5 grid grid-cols-2 gap-2.5 md:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <SkeletonCard key={i} className="p-3.5">
            <SkeletonLine className="h-7 w-12" />
            <SkeletonLine className="mt-2 h-3 w-24" />
          </SkeletonCard>
        ))}
      </div>
      <SkeletonBlock className="mt-8 h-px w-full rounded-none" />
      <ActivityFeedSkeleton />
    </div>
  );
}

export function ActivityFeedSkeleton() {
  return (
    <div className="mt-3.5 flex flex-col gap-2.5">
      {[0, 1, 2, 3, 4].map((i) => (
        <SkeletonCard key={i} className="flex items-start gap-3 px-4 py-3.5">
          <SkeletonBlock className="h-7 w-7 rounded-full" />
          <div className="min-w-0 flex-1">
            <SkeletonLine className="h-3 w-64 max-w-full" />
            <SkeletonLine className="mt-3 h-5 w-80 max-w-full" />
            <SkeletonLine className="mt-2 h-3 w-full" />
          </div>
        </SkeletonCard>
      ))}
    </div>
  );
}

export function WorkspaceHomeSkeleton() {
  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <SkeletonBlock className="h-[72px] w-full rounded-none bg-brand-100" />
      <div className="mx-auto max-w-[920px] px-12 pb-20">
        <div className="flex items-start justify-between gap-3 pt-4">
          <div className="flex min-w-0 items-center gap-3">
            <SkeletonBlock className="-mt-9 h-12 w-12 rounded-[10px] border-2 border-base" />
            <div className="min-w-0">
              <SkeletonLine className="h-6 w-56 max-w-full" />
              <SkeletonLine className="mt-2 h-3 w-44" />
            </div>
          </div>
          <SkeletonBlock className="h-7 w-7" />
        </div>
        <SkeletonCard className="mt-6 p-3">
          <SkeletonLine className="h-3 w-56" />
          <SkeletonBlock className="mt-2 h-10 w-full" />
        </SkeletonCard>
        <DocumentBodySkeleton className="mt-6" />
        <VisualizationSkeleton className="mt-8" />
        <VisualizationSkeleton className="mt-6" />
      </div>
    </div>
  );
}

export function VisualizationSkeleton({ className }: SkeletonProps) {
  return (
    <section className={className}>
      <SkeletonLine className="mb-1.5 h-3 w-56" />
      <SkeletonCard className="p-3">
        <SkeletonBlock className="h-40 w-full" />
      </SkeletonCard>
    </section>
  );
}

export function WorkspaceFormSkeleton() {
  return (
    <div className="mx-auto max-w-2xl px-8 py-12">
      <SkeletonLine className="h-3 w-28" />
      <SkeletonLine className="mt-3 h-9 w-72 max-w-full" />
      <SkeletonLine className="mt-4 h-4 w-full" />
      <SkeletonLine className="mt-2 h-4 w-4/5" />
      <div className="mt-8 space-y-4">
        <SkeletonBlock className="h-16 w-full rounded-lg" />
        <SkeletonBlock className="h-28 w-full rounded-lg" />
        <div className="flex justify-between">
          <SkeletonBlock className="h-8 w-16" />
          <SkeletonBlock className="h-9 w-36" />
        </div>
      </div>
      <SkeletonCard className="mt-12 rounded-2xl p-5">
        <SkeletonLine className="h-3 w-48" />
        <div className="mt-4 space-y-3">
          <SkeletonLine className="w-full" />
          <SkeletonLine className="w-5/6" />
          <SkeletonLine className="w-2/3" />
        </div>
      </SkeletonCard>
    </div>
  );
}

export function WorkspaceSettingsSkeleton() {
  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-2xl px-8 py-10">
        <SkeletonLine className="h-8 w-36" />
        <SkeletonLine className="mt-3 h-3 w-40" />
        {[0, 1, 2].map((i) => (
          <SkeletonCard key={i} className="mt-6 p-4">
            <SkeletonLine className="h-5 w-28" />
            <div className="mt-4 space-y-2">
              {[0, 1, 2].map((row) => (
                <SkeletonBlock key={row} className="h-12 w-full rounded-lg" />
              ))}
            </div>
          </SkeletonCard>
        ))}
      </div>
    </div>
  );
}

export function SessionsListSkeleton() {
  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-5xl px-12 py-8">
        <div className="flex items-baseline justify-between">
          <SkeletonLine className="h-8 w-32" />
          <SkeletonLine className="h-3 w-20" />
        </div>
        <SkeletonBlock className="mt-5 h-24 w-full rounded-lg" />
        <SkeletonBlock className="mb-3 mt-4 h-px w-full rounded-none" />
        <div className="space-y-2">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <SkeletonBlock key={i} className="h-14 w-full rounded-lg" />
          ))}
        </div>
      </div>
    </div>
  );
}

export function FileBrowserSkeleton() {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-3 border-b border-border bg-surface px-4 py-2.5">
        <SkeletonLine className="h-4 w-24" />
        <span className="flex-1" />
        <SkeletonBlock className="h-7 w-40" />
        <SkeletonBlock className="h-7 w-20" />
        <SkeletonBlock className="h-7 w-24" />
      </div>
      <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
          <SkeletonCard key={i} className="p-3">
            <SkeletonBlock className="h-8 w-8 rounded" />
            <SkeletonLine className="mt-4 h-4 w-36" />
            <SkeletonLine className="mt-2 h-3 w-24" />
          </SkeletonCard>
        ))}
      </div>
    </div>
  );
}

export function StashesGridSkeleton() {
  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[1120px] px-12 pb-20 pt-8">
        <div className="flex items-center justify-between gap-4">
          <SkeletonLine className="h-9 w-36" />
          <SkeletonBlock className="h-8 w-24" />
        </div>
        <SkeletonBlock className="mt-5 h-10 w-full rounded-lg" />
        <SkeletonBlock className="mt-4 h-24 w-full rounded-lg" />
        <CardGridSkeleton className="mt-4" />
      </div>
    </div>
  );
}

export function CardGridSkeleton({ className }: SkeletonProps) {
  return (
    <div className={cx("grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3", className)}>
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <SkeletonCard key={i} className="overflow-hidden p-0">
          <SkeletonBlock className="h-28 w-full rounded-none" />
          <div className="p-4">
            <SkeletonLine className="h-5 w-3/4" />
            <SkeletonLine className="mt-3 w-full" />
            <SkeletonLine className="mt-2 w-2/3" />
            <div className="mt-4 flex justify-between">
              <SkeletonLine className="w-24" />
              <SkeletonBlock className="h-6 w-16" />
            </div>
          </div>
        </SkeletonCard>
      ))}
    </div>
  );
}

export function DocumentPageSkeleton() {
  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <ViewerHeaderSkeleton />
      <div className="mx-auto mt-6 grid max-w-[1100px] gap-7 px-12 pb-20 lg:grid-cols-[minmax(0,1fr)_240px]">
        <main className="min-w-0">
          <DocumentBodySkeleton />
        </main>
        <aside className="mt-20 hidden lg:block">
          <SkeletonCard className="sticky top-16 p-3.5">
            <SkeletonLine className="h-3 w-20" />
            <SkeletonLine className="mt-4 w-full" />
            <SkeletonLine className="mt-2 w-2/3" />
          </SkeletonCard>
        </aside>
      </div>
    </div>
  );
}

export function DocumentBodySkeleton({ className }: SkeletonProps) {
  return (
    <article className={cx("rounded-lg border border-border bg-base px-5 py-5", className)}>
      <SkeletonLine className="h-8 w-2/3" />
      <SkeletonLine className="mt-6 w-full" />
      <SkeletonLine className="mt-3 w-11/12" />
      <SkeletonLine className="mt-3 w-10/12" />
      <SkeletonLine className="mt-8 h-6 w-1/2" />
      <SkeletonLine className="mt-4 w-full" />
      <SkeletonLine className="mt-3 w-4/5" />
      <SkeletonBlock className="mt-6 h-32 w-full rounded-lg" />
    </article>
  );
}

export function FileViewerSkeleton() {
  return (
    <div className="scroll-thin flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="flex-1 overflow-auto bg-base">
        <ViewerHeaderSkeleton />
        <div className="p-8">
          <SkeletonBlock className="h-full min-h-[420px] w-full rounded-lg" />
        </div>
      </div>
    </div>
  );
}

function ViewerHeaderSkeleton() {
  return (
    <div className="border-b border-border bg-surface px-5 py-4">
      <div className="flex items-center gap-3">
        <SkeletonBlock className="h-10 w-10 rounded-lg" />
        <div className="min-w-0 flex-1">
          <SkeletonLine className="h-5 w-64 max-w-full" />
          <SkeletonLine className="mt-2 h-3 w-40" />
        </div>
        <SkeletonBlock className="h-8 w-24" />
      </div>
    </div>
  );
}

export function SessionDetailSkeleton() {
  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto grid max-w-[1100px] gap-7 px-12 pb-20 pt-7 lg:grid-cols-[minmax(0,1fr)_260px]">
        <main className="min-w-0">
          <div className="mb-2 border-b border-border pb-3.5">
            <SkeletonBlock className="h-5 w-36" />
            <SkeletonLine className="mt-3 h-8 w-60" />
            <SkeletonLine className="mt-3 h-3 w-48" />
          </div>
          <TranscriptSkeleton />
        </main>
        <aside className="hidden lg:block">
          <SkeletonCard className="sticky top-16 p-3.5">
            <SkeletonLine className="h-3 w-20" />
            <SkeletonLine className="mt-4 w-full" />
            <SkeletonLine className="mt-2 w-2/3" />
          </SkeletonCard>
        </aside>
      </div>
    </div>
  );
}

function TranscriptSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="flex gap-3 border-b border-border-subtle py-4">
          <SkeletonBlock className="h-8 w-8 rounded-full" />
          <div className="min-w-0 flex-1">
            <SkeletonLine className="h-3 w-32" />
            <SkeletonLine className="mt-3 w-full" />
            <SkeletonLine className="mt-2 w-11/12" />
            <SkeletonLine className="mt-2 w-3/4" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function SearchSkeleton() {
  return (
    <div className="mx-auto w-full max-w-[1180px] px-6 py-8">
      <header className="border-b border-border-subtle pb-6">
        <SkeletonLine className="h-3 w-20" />
        <SkeletonLine className="mt-4 h-9 w-[520px] max-w-full" />
        <SkeletonLine className="mt-4 h-4 w-[700px] max-w-full" />
        <SkeletonLine className="mt-2 h-4 w-[520px] max-w-full" />
      </header>
      <div className="mt-6 grid gap-5 lg:grid-cols-[280px_minmax(0,1fr)]">
        <SkeletonCard className="p-4">
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="mb-4 last:mb-0">
              <SkeletonLine className="h-3 w-20" />
              <SkeletonBlock className="mt-2 h-9 w-full" />
            </div>
          ))}
        </SkeletonCard>
        <main>
          <SkeletonBlock className="h-12 w-full rounded-lg" />
          <SearchResultsSkeleton />
        </main>
      </div>
    </div>
  );
}

export function SearchResultsSkeleton() {
  return (
    <div className="mt-5 flex flex-col gap-2">
      {[0, 1, 2, 3].map((i) => (
        <SkeletonCard key={i} className="px-4 py-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <SkeletonBlock className="h-5 w-14" />
                <SkeletonLine className="h-4 w-56 max-w-full" />
              </div>
              <SkeletonLine className="mt-3 w-full" />
              <SkeletonLine className="mt-2 w-2/3" />
            </div>
            <SkeletonLine className="w-20" />
          </div>
        </SkeletonCard>
      ))}
    </div>
  );
}

export function TableEditorSkeleton() {
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <ViewerHeaderSkeleton />
      <div className="mt-2 flex items-center gap-2 border-y border-border bg-surface px-4 py-2.5">
        <SkeletonBlock className="h-8 w-72 max-w-full" />
        <span className="flex-1" />
        {[0, 1, 2, 3, 4].map((i) => (
          <SkeletonBlock key={i} className="h-7 w-20" />
        ))}
      </div>
      <div className="flex-1 overflow-auto">
        <div className="min-w-[900px]">
          <div className="grid grid-cols-[48px_56px_repeat(6,160px)] border-b border-border bg-surface">
            {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
              <div key={i} className="border-r border-border p-2">
                <SkeletonLine className="h-4 w-full" />
              </div>
            ))}
          </div>
          {[0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map((row) => (
            <div key={row} className="grid grid-cols-[48px_56px_repeat(6,160px)] border-b border-border/50">
              {[0, 1, 2, 3, 4, 5, 6, 7].map((col) => (
                <div key={col} className="border-r border-border/50 p-2">
                  <SkeletonLine className={col < 2 ? "h-4 w-5" : "h-4 w-full"} />
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function PublicCartridgeSkeleton() {
  return (
    <div className="scroll-thin min-h-screen bg-background">
      <SkeletonBlock className="h-[72px] w-full rounded-none bg-brand-100" />
      <div className="mx-auto max-w-[920px] px-12 pb-20">
        <div className="flex items-start justify-between gap-3 pt-4">
          <div className="flex min-w-0 items-center gap-3">
            <SkeletonBlock className="-mt-9 h-12 w-12 rounded-[10px] border-2 border-base" />
            <div className="min-w-0">
              <SkeletonLine className="h-6 w-56 max-w-full" />
              <SkeletonLine className="mt-2 h-3 w-64 max-w-full" />
            </div>
          </div>
          <SkeletonBlock className="h-8 w-24" />
        </div>
        <DocumentBodySkeleton className="mt-6" />
        <div className="mt-6 flex flex-col gap-3">
          {[0, 1, 2, 3].map((i) => (
            <SkeletonBlock key={i} className="h-12 w-full rounded-lg" />
          ))}
        </div>
        <VisualizationSkeleton className="mt-8" />
      </div>
    </div>
  );
}

export function CartridgeItemSkeleton() {
  return (
    <div className="scroll-thin min-h-screen bg-background">
      <div className="mx-auto max-w-[920px] px-12 pb-20 pt-6">
        <SkeletonLine className="h-4 w-32" />
        <SkeletonLine className="mt-4 h-7 w-72 max-w-full" />
        <SkeletonLine className="mt-2 h-3 w-20" />
        <DocumentBodySkeleton className="mt-6" />
      </div>
    </div>
  );
}

export function JoinWorkspaceSkeleton() {
  return (
    <div className="flex min-h-screen flex-col bg-base text-foreground">
      <div className="border-b border-border bg-surface px-4 py-2">
        <div className="flex justify-end">
          <SkeletonBlock className="h-7 w-24" />
        </div>
      </div>
      <main className="flex flex-1 items-center justify-center px-4">
        <SkeletonCard className="w-full max-w-sm p-6 text-center">
          <SkeletonLine className="mx-auto h-5 w-48" />
          <SkeletonLine className="mx-auto mt-3 w-64 max-w-full" />
          <SkeletonBlock className="mx-auto mt-5 h-9 w-36" />
        </SkeletonCard>
      </main>
    </div>
  );
}

export function DocsPageSkeleton() {
  return (
    <div className="min-h-screen bg-base text-foreground">
      <header className="sticky top-0 z-30 border-b border-border bg-base/95">
        <div className="mx-auto flex h-14 max-w-[1440px] items-center justify-between px-6 lg:px-8">
          <SkeletonLine className="h-5 w-40" />
          <SkeletonLine className="h-4 w-28" />
        </div>
      </header>
      <div className="mx-auto max-w-[1440px] px-6 py-8 lg:px-8">
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-[240px_minmax(0,1fr)] xl:grid-cols-[240px_minmax(0,1fr)_220px]">
          <SkeletonCard className="hidden p-4 lg:block">
            {[0, 1, 2, 3, 4].map((i) => (
              <SkeletonLine key={i} className="mb-4 w-32" />
            ))}
          </SkeletonCard>
          <DocumentBodySkeleton />
          <SkeletonCard className="hidden p-4 xl:block">
            {[0, 1, 2, 3].map((i) => (
              <SkeletonLine key={i} className="mb-4 w-28" />
            ))}
          </SkeletonCard>
        </div>
      </div>
    </div>
  );
}
