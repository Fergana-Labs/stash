"use client";

// The third VFS surface: one mount, full-page, in the same browser every
// folder uses. The lens (/files) answers "what is in my stash"; this answers
// "what does /sessions actually look like as a filesystem".
//
// /files renders the real FileBrowser, because it is a real filesystem and
// gets the whole toolkit — views, sort, upload, preview. The other mounts are
// not files (sessions, skills, source documents), so they render the same
// rows through ItemsList but pass no reparent/pin/delete capability: the list
// looks identical and offers only what actually exists for them.

import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Skeleton } from "@/components/ui/skeleton";
import FileBrowser from "@/components/content/file-browser/FileBrowser";
import ItemsList from "@/components/content/file-browser/ItemsList";
import type { GridItem, ItemKind } from "@/components/content/file-browser/kind";
import type { VNode, VNodeKind } from "@/components/content/files-overview/build";
import { useVfsMounts, type Mount } from "@/components/content/files-overview/useVfsMounts";

const KIND: Record<VNodeKind, ItemKind> = {
  folder: "folder",
  page: "page",
  file: "file",
  table: "datatable",
  session: "session",
  skill: "skill",
  "source-doc": "source-doc",
};

function vfsHref(segments: string[]): string {
  return `/vfs/${segments.map(encodeURIComponent).join("/")}`;
}

type Resolved =
  | { ok: true; nodes: VNode[]; emptyLabel: string; mount: Mount }
  | { ok: false; missing: string };

/** Walk `segments` from the mount roots. Names are the path, which is what
 *  makes the URL read like the filesystem it is describing. */
function resolve(mounts: Mount[], segments: string[]): Resolved {
  const mount = mounts.find((m) => m.path === `/${segments[0]}`);
  if (!mount) return { ok: false, missing: `/${segments[0]}` };

  let nodes = mount.nodes;
  for (const segment of segments.slice(1)) {
    const next = nodes.find((n) => n.name === segment);
    if (!next || !next.children) return { ok: false, missing: segment };
    nodes = next.children;
  }
  // The mount's empty label speaks for the mount ("no sources connected"); a
  // directory inside it is just empty, and saying otherwise misreports why.
  const emptyLabel = segments.length === 1 ? mount.emptyLabel : "empty";
  return { ok: true, nodes, emptyLabel, mount };
}

function Breadcrumbs({ segments }: { segments: string[] }) {
  return (
    <div className="flex flex-wrap items-center font-mono text-[15px]">
      {segments.map((segment, i) => {
        const last = i === segments.length - 1;
        return (
          <span key={segment} className="flex items-center">
            <span className="text-muted-foreground/40">/</span>
            {last ? (
              <span className="font-semibold text-foreground">{segment}</span>
            ) : (
              <Link
                href={vfsHref(segments.slice(0, i + 1))}
                className="rounded px-0.5 text-dim hover:bg-raised hover:text-brand-700"
              >
                {segment}
              </Link>
            )}
          </span>
        );
      })}
    </div>
  );
}

export default function VfsBrowser() {
  const params = useParams();
  const router = useRouter();
  const raw = params.path;
  const segments = (Array.isArray(raw) ? raw : raw ? [raw] : []).map((s) => decodeURIComponent(s));

  const { mounts, coreLoaded, coreError, sourcesPending } = useVfsMounts();

  if (segments.length === 1 && segments[0] === "files") {
    return (
      <div className="h-full overflow-y-auto px-8 py-6">
        <Breadcrumbs segments={segments} />
        <FileBrowser folderId={null} />
      </div>
    );
  }

  if (coreError) {
    return <div className="px-8 py-6 font-mono text-[13px] text-error">✗ {coreError}</div>;
  }
  // /sources arrives on its own clock, so a bare /vfs/sources is still loading
  // while the native mounts are ready.
  if (!coreLoaded || (segments[0] === "sources" && sourcesPending)) {
    return (
      <div className="space-y-2 px-8 py-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-6 w-64" />
        ))}
      </div>
    );
  }

  const resolved = resolve(mounts, segments);

  // A directory drills deeper into this view; a leaf opens its own page. That
  // split is what keeps /sources/gmail browsing the filesystem instead of
  // jumping to the Gmail integration screen.
  const destinations = new Map<string, string>();
  const items: GridItem[] = !resolved.ok
    ? []
    : resolved.nodes.map((node) => {
        const dir = node.children !== undefined;
        const destination = dir ? vfsHref([...segments, node.name]) : node.href;
        if (destination) destinations.set(node.key, destination);
        return {
          kind: dir ? "folder" : KIND[node.kind],
          id: node.key,
          name: node.name,
          subtitle: node.annotation ?? "",
          updatedAt: node.updatedAt,
          detail: node.detail,
          icon: node.icon,
          movable: false,
        };
      });

  function navigate(item: GridItem, options?: { newTab?: boolean }) {
    // Source documents live in the provider, not in Stash: they are real VFS
    // entries with no page of ours to open, so their rows do not navigate.
    const destination = destinations.get(item.id);
    if (!destination) return;
    if (options?.newTab) window.open(destination, "_blank");
    else router.push(destination);
  }

  return (
    <div className="h-full overflow-y-auto px-8 py-6">
      <Breadcrumbs segments={segments} />
      <div className="mt-5">
        {!resolved.ok ? (
          <div className="font-mono text-[13px] text-muted-foreground">
            no such path: {resolved.missing}
          </div>
        ) : resolved.nodes.length === 0 ? (
          <div className="font-mono text-[13px] italic text-muted-foreground">
            {resolved.emptyLabel}
          </div>
        ) : (
          <ItemsList
            items={items}
            onNavigate={navigate}
            detailColumn={resolved.mount.detailLabel}
          />
        )}
      </div>
      {resolved.ok && resolved.mount.footer && (
        <Link
          href={resolved.mount.footer.href}
          className="mt-4 inline-flex items-center gap-1 font-mono text-[12.5px] text-dim hover:text-brand-700"
        >
          {resolved.mount.footer.label} →
        </Link>
      )}
    </div>
  );
}
