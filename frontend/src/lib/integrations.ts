/**
 * Client for /api/v1/integrations + /api/v1/tasks/{id}.
 *
 * One client for every provider — provider-specific UI components
 * (Drive picker button, git dialog) only need to know the provider's
 * URL segment ("google", "github") to drive the OAuth flow.
 */

import { apiFetch } from "./api";

export type IntegrationProvider = "google" | "github" | "notion";

export type IntegrationStatus = {
  provider: string;
  display_name: string;
  scopes: string[];
  connected: boolean;
  account_email: string | null;
  account_display_name: string | null;
  expires_at: string | null;
  connected_at: string | null;
};

export type IntegrationsList = {
  providers: IntegrationStatus[];
};

export async function listIntegrations(): Promise<IntegrationsList> {
  return apiFetch<IntegrationsList>("/api/v1/integrations");
}

/**
 * Returns the absolute URL to redirect the browser to for OAuth consent.
 * We don't fetch this — the user must follow the redirect themselves so
 * the auth flow lands on the provider with its session cookies intact.
 */
export function connectUrl(provider: IntegrationProvider): string {
  // The browser hits /connect with the user's session cookie / token.
  // The backend issues a 302 to the provider. We can't `fetch` and
  // redirect because fetch follows cross-origin redirects opaquely.
  // Instead, navigate the top window.
  return `/api/v1/integrations/${provider}/connect`;
}

export async function disconnectIntegration(provider: IntegrationProvider): Promise<void> {
  await apiFetch(`/api/v1/integrations/${provider}/disconnect`, { method: "POST" });
}

// --- Task polling ---

export type TaskStatus = {
  task_id: string;
  state: "PENDING" | "STARTED" | "SUCCESS" | "FAILURE" | "RETRY" | "REVOKED";
  result: unknown;
  error: string | null;
};

export async function getTaskStatus(taskId: string): Promise<TaskStatus> {
  return apiFetch<TaskStatus>(`/api/v1/tasks/${encodeURIComponent(taskId)}`);
}

/**
 * Poll a task until it reaches a terminal state (SUCCESS or FAILURE),
 * yielding intermediate statuses to `onTick` so the UI can update a
 * spinner. Returns the final TaskStatus.
 */
export async function waitForTask(
  taskId: string,
  onTick?: (s: TaskStatus) => void,
  intervalMs = 1500,
): Promise<TaskStatus> {
  for (;;) {
    const s = await getTaskStatus(taskId);
    onTick?.(s);
    if (s.state === "SUCCESS" || s.state === "FAILURE" || s.state === "REVOKED") {
      return s;
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

// --- Git import ---

export type GitImportRequest = {
  url: string;
  ref?: string;
  subpath?: string;
  pat?: string;
  folder_id?: string;
};

export type GitImportResponse = { task_id: string };

export async function importGitRepo(
  workspaceId: string,
  body: GitImportRequest,
): Promise<GitImportResponse> {
  return apiFetch<GitImportResponse>(
    `/api/v1/workspaces/${workspaceId}/imports/git`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

// --- Google Drive import (Picker flow) ---

export type GooglePickerToken = {
  access_token: string;
  api_key: string | null;
  client_id: string | null;
};

export async function getGooglePickerToken(): Promise<GooglePickerToken> {
  return apiFetch<GooglePickerToken>("/api/v1/integrations/google/picker-token");
}

export type GoogleDriveImportRequest = {
  file_ids: string[];
  folder_id?: string;
};

export type GoogleDriveImportResponse = { task_ids: string[] };

export async function importGoogleDrive(
  workspaceId: string,
  body: GoogleDriveImportRequest,
): Promise<GoogleDriveImportResponse> {
  return apiFetch<GoogleDriveImportResponse>(
    `/api/v1/workspaces/${workspaceId}/imports/google-drive`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

// --- Notion import ---

export type NotionImportRequest = {
  page_ids: string[];
  folder_id?: string;
};

export type NotionImportResponse = { task_ids: string[] };

export async function importNotion(
  workspaceId: string,
  body: NotionImportRequest,
): Promise<NotionImportResponse> {
  return apiFetch<NotionImportResponse>(
    `/api/v1/workspaces/${workspaceId}/imports/notion`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

// --- Slide deck export ---

export type ExportFormat = "pdf" | "pptx" | "gslides";
export type ExportResponse = { task_id: string };

export async function exportPage(
  pageId: string,
  format: ExportFormat,
): Promise<ExportResponse> {
  return apiFetch<ExportResponse>(`/api/v1/pages/${pageId}/export`, {
    method: "POST",
    body: JSON.stringify({ format }),
  });
}
