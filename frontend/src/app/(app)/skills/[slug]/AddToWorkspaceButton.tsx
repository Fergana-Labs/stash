"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import {
  forkSkill,
  ApiError,
  listMyWorkspaces,
  type WorkspaceSkill,
} from "../../../../lib/api";
import type { Workspace } from "../../../../lib/types";
import { useEscapeKey } from "../../../../hooks/useEscapeKey";
import CustomSelect from "../../../../components/CustomSelect";

type Props = { slug: string; sourceWorkspaceId: string };

export default function AddToWorkspaceButton({ slug, sourceWorkspaceId }: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [attached, setAttached] = useState<WorkspaceSkill | null>(null);
  const [error, setError] = useState<string | null>(null);

  const eligibleWorkspaces = useMemo(
    () => workspaces.filter((workspace) => workspace.id !== sourceWorkspaceId),
    [sourceWorkspaceId, workspaces]
  );

  useEscapeKey(open, () => setOpen(false));

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("action") !== "add") return;
    void loadWorkspaces();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function redirectToLogin() {
    const next = `/skills/${slug}?action=add`;
    router.push(`/login?next=${encodeURIComponent(next)}`);
  }

  async function loadWorkspaces() {
    setBusy(true);
    setError(null);
    try {
      const data = await listMyWorkspaces();
      const nextWorkspaces = data.workspaces;
      const eligible = nextWorkspaces.filter((workspace) => workspace.id !== sourceWorkspaceId);
      setWorkspaces(nextWorkspaces);
      setSelectedWorkspaceId(eligible[0]?.id ?? "");
      setOpen(true);
      if (eligible.length === 1) {
        await attachToWorkspace(eligible[0].id);
      }
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        redirectToLogin();
        return;
      }
      const message = e instanceof ApiError ? e.message : "Could not load workspaces";
      setError(message);
    } finally {
      setBusy(false);
    }
  }

  async function attachToWorkspace(workspaceId: string) {
    setBusy(true);
    setError(null);
    try {
      const result = await forkSkill(slug, workspaceId);
      setAttached(result);
      router.refresh();
    } catch (e) {
      const message = e instanceof ApiError ? e.message : "Could not add skill";
      setError(message);
    } finally {
      setBusy(false);
    }
  }

  function onClick() {
    void loadWorkspaces();
  }

  return (
    <div className="relative flex flex-col items-end gap-2">
      <button
        type="button"
        onClick={onClick}
        disabled={busy}
        className="rounded-lg border border-brand bg-brand px-4 py-2 text-[14px] font-medium text-white transition hover:opacity-90 disabled:opacity-50"
      >
        {busy ? "Adding..." : "Add to my files"}
      </button>

      {open ? (
        <div className="absolute right-0 top-12 z-20 w-[300px] rounded-lg border border-border-subtle bg-surface p-3 text-left shadow-lg">
          {attached ? (
            <div className="space-y-2">
              <p className="text-[13px] font-medium text-foreground">Added to your files</p>
              <button
                type="button"
                onClick={() => router.push(`/workspaces/${attached.added_to_workspace_id}`)}
                className="w-full rounded-md border border-border-subtle px-3 py-2 text-[13px] text-foreground hover:border-brand hover:text-brand"
              >
                Open files
              </button>
            </div>
          ) : eligibleWorkspaces.length > 0 ? (
            <div className="space-y-3">
              <div>
                <span className="text-[11px] uppercase tracking-wider text-muted">
                  Workspace
                </span>
                <CustomSelect
                  value={selectedWorkspaceId}
                  options={eligibleWorkspaces.map((workspace) => ({
                    value: workspace.id,
                    label: workspace.name,
                  }))}
                  onChange={setSelectedWorkspaceId}
                  ariaLabel="Workspace"
                  className="mt-1 w-full rounded-md border border-border-subtle bg-raised px-2 py-2 text-[13px] text-foreground"
                  menuClassName="text-[13px]"
                  align="right"
                />
              </div>
              <button
                type="button"
                disabled={busy || !selectedWorkspaceId}
                onClick={() => void attachToWorkspace(selectedWorkspaceId)}
                className="w-full rounded-md bg-brand px-3 py-2 text-[13px] font-medium text-white disabled:opacity-50"
              >
                Add Skill
              </button>
            </div>
          ) : (
            <p className="text-[13px] text-muted">No other workspaces available.</p>
          )}
          {error ? <p className="mt-2 text-[12px] text-red-500">{error}</p> : null}
        </div>
      ) : error ? (
        <p className="max-w-[260px] text-right text-[12px] text-red-500">{error}</p>
      ) : null}
    </div>
  );
}
