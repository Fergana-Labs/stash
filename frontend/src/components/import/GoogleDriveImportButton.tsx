"use client";

import { useCallback, useEffect, useState } from "react";

import {
  TaskStatus,
  getGooglePickerToken,
  importGoogleDrive,
  waitForTask,
} from "@/lib/integrations";

type Props = {
  workspaceId: string;
  folderId?: string | null;
  onDone?: (statuses: TaskStatus[]) => void;
  /** Button label override. */
  label?: string;
  className?: string;
};

declare global {
  interface Window {
    // The Google Picker SDK is loaded lazily on demand. Typing it
    // fully would pull in @types/google.picker — we just need enough
    // shape here to call into it safely.
    gapi?: {
      load: (mod: string, cb: () => void) => void;
    };
    google?: {
      picker?: PickerNamespace;
    };
  }
}

type PickerNamespace = {
  DocsView: new () => PickerDocsView;
  PickerBuilder: new () => PickerBuilder;
  ViewId: Record<string, string>;
  Action: { PICKED: string; CANCEL: string };
};

type PickerDocsView = {
  setIncludeFolders: (b: boolean) => PickerDocsView;
  setSelectFolderEnabled: (b: boolean) => PickerDocsView;
  setMimeTypes: (s: string) => PickerDocsView;
};

type PickerBuilder = {
  addView: (v: PickerDocsView) => PickerBuilder;
  setOAuthToken: (t: string) => PickerBuilder;
  setDeveloperKey: (k: string) => PickerBuilder;
  setAppId: (s: string) => PickerBuilder;
  enableFeature: (f: string) => PickerBuilder;
  setCallback: (cb: (data: { action: string; docs?: Array<{ id: string }> }) => void) => PickerBuilder;
  build: () => { setVisible: (v: boolean) => void };
};

const PICKER_API_URL = "https://apis.google.com/js/api.js";

const DRIVE_MIME_DOC = "application/vnd.google-apps.document";
const DRIVE_MIME_SHEET = "application/vnd.google-apps.spreadsheet";
const DRIVE_MIME_PPTX =
  "application/vnd.openxmlformats-officedocument.presentationml.presentation";

let _gapiLoadPromise: Promise<void> | null = null;

function loadGapi(): Promise<void> {
  if (_gapiLoadPromise) return _gapiLoadPromise;
  _gapiLoadPromise = new Promise<void>((resolve, reject) => {
    if (window.gapi) {
      resolve();
      return;
    }
    const script = document.createElement("script");
    script.src = PICKER_API_URL;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Failed to load Google API loader"));
    document.head.appendChild(script);
  });
  return _gapiLoadPromise;
}

function loadPicker(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (!window.gapi) {
      reject(new Error("gapi missing"));
      return;
    }
    if (window.google?.picker) {
      resolve();
      return;
    }
    window.gapi.load("picker", () => resolve());
  });
}

/**
 * Drive Picker button. Opens Google's native Picker (filtered to
 * Docs / Sheets / PPTX), passes the chosen file ids to
 * /imports/google-drive, then polls each dispatched task.
 *
 * If the user hasn't connected Google yet, the picker-token endpoint
 * returns 401 and we surface a "Connect Google first" link.
 */
export default function GoogleDriveImportButton({
  workspaceId,
  folderId,
  onDone,
  label = "Import from Drive",
  className,
}: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statuses, setStatuses] = useState<TaskStatus[]>([]);

  // Touch this so we ping the picker-token endpoint at mount time and
  // can pre-warn the user if they need to connect; we DON'T actually
  // require the call to succeed until they click.
  useEffect(() => {
    setError(null);
  }, []);

  const openPicker = useCallback(async () => {
    setBusy(true);
    setError(null);
    setStatuses([]);
    try {
      const token = await getGooglePickerToken().catch((e) => {
        if (e instanceof Error && e.message.toLowerCase().includes("not connected")) {
          throw new Error(
            "Connect Google first in Settings → Integrations, then try again.",
          );
        }
        throw e;
      });
      if (!token.api_key) {
        throw new Error(
          "GOOGLE_PICKER_API_KEY is not configured on the server. Drive Picker requires a browser API key from the Google Cloud Console.",
        );
      }

      await loadGapi();
      await loadPicker();

      const ns = window.google?.picker;
      if (!ns) throw new Error("Google Picker SDK failed to load");

      const view = new ns.DocsView()
        .setIncludeFolders(false)
        .setSelectFolderEnabled(false)
        .setMimeTypes(
          [DRIVE_MIME_DOC, DRIVE_MIME_SHEET, DRIVE_MIME_PPTX].join(","),
        );

      const builder = new ns.PickerBuilder()
        .addView(view)
        .setOAuthToken(token.access_token)
        .setDeveloperKey(token.api_key);
      // app_id is the GCP project number. Optional — picker still
      // works without it for many setups, but Google recommends it.
      if (token.app_id) builder.setAppId(token.app_id);
      const picker = builder
        .enableFeature("MULTISELECT_ENABLED")
        .setCallback(async (data) => {
          if (data.action !== ns.Action.PICKED) return;
          const ids = (data.docs || []).map((d) => d.id);
          if (ids.length === 0) return;
          try {
            const { task_ids } = await importGoogleDrive(workspaceId, {
              file_ids: ids,
              folder_id: folderId || undefined,
            });
            const finals = await Promise.all(
              task_ids.map((tid, i) =>
                waitForTask(tid, (s) => {
                  setStatuses((prev) => {
                    const next = [...prev];
                    next[i] = s;
                    return next;
                  });
                }),
              ),
            );
            onDone?.(finals);
          } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
          }
        })
        .build();
      picker.setVisible(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [workspaceId, folderId, onDone]);

  return (
    <div>
      <button
        type="button"
        onClick={openPicker}
        disabled={busy}
        className={className}
        style={{
          padding: "8px 14px",
          borderRadius: 6,
          border: "1px solid var(--accent, #2563eb)",
          background: "var(--accent, #2563eb)",
          color: "white",
          cursor: busy ? "wait" : "pointer",
        }}
      >
        {busy ? "Opening…" : label}
      </button>
      {error && (
        <div
          style={{
            fontSize: 13,
            marginTop: 8,
            padding: 8,
            borderRadius: 6,
            background: "rgba(220,38,38,0.08)",
            color: "rgb(185,28,28)",
          }}
        >
          {error}
        </div>
      )}
      {statuses.length > 0 && (
        <div
          style={{
            fontSize: 13,
            marginTop: 8,
            padding: 8,
            borderRadius: 6,
            background: "var(--info-bg, rgba(37,99,235,0.08))",
            maxHeight: 160,
            overflow: "auto",
          }}
        >
          {statuses.map((s, i) =>
            s ? (
              <div key={i}>
                #{i + 1}: <strong>{s.state}</strong>
                {s.error ? <span> — {s.error}</span> : null}
              </div>
            ) : (
              <div key={i}>
                #{i + 1}: pending…
              </div>
            ),
          )}
        </div>
      )}
    </div>
  );
}
