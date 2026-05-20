"use client";

import { useCallback, useState } from "react";

import {
  getGooglePickerToken,
  importGoogleDrive,
} from "@/lib/integrations";

declare global {
  interface Window {
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
  Feature?: { MULTISELECT_ENABLED: string };
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
  setCallback: (
    cb: (data: { action: string; docs?: Array<{ id: string }> }) => void,
  ) => PickerBuilder;
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

type Options = {
  workspaceId: string;
  folderId?: string | null;
  /** Fired with the task ids returned by the import endpoint. The caller is
   *  responsible for polling each task's status. */
  onDispatched?: (taskIds: string[]) => void;
};

export function useGoogleDrivePicker({
  workspaceId,
  folderId,
  onDispatched,
}: Options) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const openPicker = useCallback(
    async (folderOverride?: string | null) => {
      const targetFolderId =
        folderOverride !== undefined ? folderOverride : folderId ?? null;
      setBusy(true);
      setError(null);
      try {
        const token = await getGooglePickerToken().catch((e) => {
          if (e instanceof Error && e.message.toLowerCase().includes("not connected")) {
            throw new Error(
              "Connect Google in Settings → Integrations, then try again.",
            );
          }
          throw e;
        });
        if (!token.api_key) {
          throw new Error("GOOGLE_PICKER_API_KEY is not configured on the server.");
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
        if (token.app_id) builder.setAppId(token.app_id);

        const picker = builder
          .enableFeature(ns.Feature?.MULTISELECT_ENABLED ?? "MULTISELECT_ENABLED")
          .setCallback(async (data) => {
            if (data.action !== ns.Action.PICKED) return;
            const ids = (data.docs || []).map((d) => d.id);
            if (ids.length === 0) return;
            try {
              const { task_ids } = await importGoogleDrive(workspaceId, {
                file_ids: ids,
                folder_id: targetFolderId || undefined,
              });
              onDispatched?.(task_ids);
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
    },
    [workspaceId, folderId, onDispatched],
  );

  return { openPicker, busy, error };
}
