"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { forkSkill, ApiError } from "@/lib/api";

type Props = { slug: string };

export default function AddToStashButton({ slug }: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [attached, setAttached] = useState<
    { folderId: string; name: string } | null
  >(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("action") !== "add") return;
    void addSkill();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function redirectToLogin() {
    const next = `/skills/${slug}?action=add`;
    router.push(`/login?next=${encodeURIComponent(next)}`);
  }

  async function addSkill() {
    setBusy(true);
    setError(null);
    try {
      const result = await forkSkill(slug);
      setAttached({ folderId: result.folder_id, name: result.name });
      router.refresh();
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        redirectToLogin();
        return;
      }
      const message = e instanceof ApiError ? e.message : "Could not add skill";
      setError(message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative flex flex-col items-end gap-2">
      {attached ? (
        <button
          type="button"
          onClick={() => router.push(`/skills/${attached.folderId}`)}
          className="cursor-pointer rounded-lg border border-border-subtle px-4 py-2 text-[14px] font-medium text-foreground transition hover:border-brand hover:text-brand"
        >
          Open {attached.name}
        </button>
      ) : (
        <button
          type="button"
          onClick={() => void addSkill()}
          disabled={busy}
          className="cursor-pointer rounded-lg border border-brand bg-brand px-4 py-2 text-[14px] font-medium text-white transition hover:opacity-90 disabled:opacity-50"
        >
          {busy ? "Adding..." : "Add to my files"}
        </button>
      )}

      {error ? (
        <p className="max-w-[260px] text-right text-[12px] text-red-500">{error}</p>
      ) : null}
    </div>
  );
}
