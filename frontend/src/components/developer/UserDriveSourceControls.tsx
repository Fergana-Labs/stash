"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { addSource } from "@/lib/api";
import { listIntegrations, type IntegrationStatus } from "@/lib/integrations";

import { DriveFolderControls } from "../integrations/pickers";

export default function UserDriveSourceControls({
  externalUserId,
  onAdded,
}: {
  externalUserId: string;
  onAdded: () => void;
}) {
  const [google, setGoogle] = useState<IntegrationStatus | null | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    listIntegrations()
      .then((result) => {
        const provider = result.providers.find((item) => item.provider === "google");
        setGoogle(provider === undefined ? null : provider);
      })
      .catch((cause) => {
        if (!(cause instanceof Error)) throw cause;
        setError(cause.message);
      });
  }, []);

  async function addFolder(folderId: string, displayName: string): Promise<boolean> {
    setBusy(true);
    setError("");
    try {
      await addSource({
        source_type: "google_drive_folder",
        external_ref: folderId,
        ...(displayName ? { display_name: displayName } : {}),
        user_id: externalUserId,
      });
      onAdded();
      return true;
    } catch (cause) {
      if (!(cause instanceof Error)) throw cause;
      setError(cause.message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  if (google === undefined) {
    if (error) {
      return <div className="mt-3 text-[12.5px] text-error">{error}</div>;
    }
    return <div className="mt-3 text-[12.5px] text-muted-foreground">Checking Google Drive…</div>;
  }

  if (google === null) {
    return (
      <div className="mt-3 text-[12.5px] text-muted-foreground">
        Google Drive is not available for this workspace.
      </div>
    );
  }

  if (!google.enabled) {
    if (google.disabled_reason === null) {
      throw new Error("Disabled Google Drive integration has no reason");
    }
    return <div className="mt-3 text-[12.5px] text-muted-foreground">{google.disabled_reason}</div>;
  }

  if (!google.connected) {
    return (
      <div className="mt-3 text-[12.5px] text-muted-foreground">
        <Link href="/integrations/google" className="font-medium text-brand hover:underline">
          Connect Google Drive
        </Link>{" "}
        before assigning a folder to this user.
      </div>
    );
  }

  return (
    <div className="mt-3">
      <DriveFolderControls busy={busy} onAddFolder={addFolder} />
      {error && <div className="mt-2 text-[12.5px] text-error">{error}</div>}
    </div>
  );
}
