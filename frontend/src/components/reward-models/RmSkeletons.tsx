import { SkeletonBlock } from "@/components/SkeletonStates";

export function RmListSkeleton() {
  return (
    <div className="space-y-2">
      <SkeletonBlock className="h-9 w-full rounded-lg" />
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <SkeletonBlock key={i} className="h-12 w-full rounded-lg" />
      ))}
    </div>
  );
}

export function RmPageSkeleton() {
  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl px-10 pt-7">
        <SkeletonBlock className="h-7 w-48" />
        <SkeletonBlock className="mt-2 h-4 w-96" />
        <SkeletonBlock className="mt-6 mb-6 h-px w-full rounded-none" />
        <RmListSkeleton />
      </div>
    </div>
  );
}

export function TraceSkeleton() {
  return (
    <div className="flex h-full min-h-0">
      <div className="flex-1 px-10 pt-7">
        <SkeletonBlock className="h-7 w-80" />
        <SkeletonBlock className="mt-2 h-4 w-56" />
        <div className="mt-8 space-y-4">
          {[0, 1, 2, 3].map((i) => (
            <SkeletonBlock key={i} className="h-24 w-full rounded-lg" />
          ))}
        </div>
      </div>
      <div className="w-[340px] border-l border-border p-4">
        <SkeletonBlock className="h-4 w-24" />
        <div className="mt-4 space-y-3">
          {[0, 1, 2].map((i) => (
            <SkeletonBlock key={i} className="h-20 w-full rounded-lg" />
          ))}
        </div>
      </div>
    </div>
  );
}
