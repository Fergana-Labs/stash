/**
 * Client for /api/v1/integrations + /api/v1/tasks/{id}.
 *
 * One client for every provider — provider-specific UI components
 * (Drive picker button, git dialog) only need to know the provider's
 * URL segment ("google", "github") to drive the OAuth flow.
 */

import { apiFetch } from "./api";

export type IntegrationProvider =
  | "google"
  | "gmail"
  | "github"
  | "notion"
  | "slack"
  | "granola"
  | "jira"
  | "linear"
  | "asana"
  | "gong"
  | "posthog";

export type CredentialField = {
  name: string;
  label: string;
  secret: boolean;
  placeholder: string;
  optional?: boolean;
  help?: string;
};

export type IntegrationAccount = {
  account_key: string;
  account_email: string | null;
  account_display_name: string | null;
  scopes: string[];
  expires_at: string | null;
  connected_at: string | null;
  // True when the stored token no longer works (revoked access or an expired
  // refresh token) — the account is listed as connected but must be reconnected.
  needs_reconnect: boolean;
};

export type IntegrationStatus = {
  provider: string;
  display_name: string;
  scopes: string[];
  connected: boolean;
  enabled: boolean;
  disabled_reason: string | null;
  account_email: string | null;
  account_display_name: string | null;
  expires_at: string | null;
  connected_at: string | null;
  accounts: IntegrationAccount[];
  // "oauth" (redirect flow), "mcp_oauth" (DCR+PKCE via an MCP server, e.g.
  // Granola), or "api_key" (pasted credentials).
  auth_kind: "oauth" | "mcp_oauth" | "api_key";
  // Present only for api_key providers — the fields to render in the connect form.
  credential_fields: CredentialField[] | null;
};

export type IntegrationsList = {
  providers: IntegrationStatus[];
};

export async function listIntegrations(): Promise<IntegrationsList> {
  return apiFetch<IntegrationsList>("/api/v1/integrations");
}

/**
 * Start the OAuth flow for a provider.
 *
 * The app authenticates with a Bearer token in localStorage — a plain
 * `window.location.href = '/api/v1/.../connect'` navigation would NOT
 * include that header, so the backend can't 302 us. Instead the backend
 * returns `{authorize_url}` as JSON; we fetch it (Bearer carried by
 * `apiFetch`), then navigate the top window to the provider's URL.
 */
export async function startConnect(
  provider: IntegrationProvider,
  returnTo?: string,
): Promise<void> {
  const query = returnTo ? `?return_to=${encodeURIComponent(returnTo)}` : "";
  const { authorize_url } = await apiFetch<{ authorize_url: string }>(
    `/api/v1/integrations/${provider}/connect${query}`,
  );
  window.location.href = authorize_url;
}

export async function disconnectIntegration(provider: IntegrationProvider): Promise<void> {
  await apiFetch(`/api/v1/integrations/${provider}/disconnect`, { method: "POST" });
}

/**
 * Connect an api_key provider by POSTing the pasted credential values. The
 * backend validates them upstream and stores them encrypted.
 */
export async function submitCredentials(
  provider: IntegrationProvider,
  values: Record<string, string>,
): Promise<void> {
  await apiFetch(`/api/v1/integrations/${provider}/credentials`, {
    method: "POST",
    body: JSON.stringify(values),
  });
}

export type GitHubRepoSummary = {
  full_name: string;
  description: string | null;
  private: boolean;
  html_url: string;
  updated_at: string | null;
};

export async function listGitHubRepos(q: string = ""): Promise<GitHubRepoSummary[]> {
  const query = q.trim() ? `?q=${encodeURIComponent(q.trim())}` : "";
  return apiFetch<GitHubRepoSummary[]>(`/api/v1/integrations/github/repos${query}`);
}

export type GitHubRepoAccess = {
  all_repos: boolean;
  // Only present right after a PUT that enabled all-repos mode.
  total: number | null;
  created: number | null;
};

export async function getGitHubRepoAccess(): Promise<GitHubRepoAccess> {
  return apiFetch<GitHubRepoAccess>("/api/v1/integrations/github/repo-access");
}

export async function setGitHubRepoAccess(allRepos: boolean): Promise<GitHubRepoAccess> {
  return apiFetch<GitHubRepoAccess>("/api/v1/integrations/github/repo-access", {
    method: "PUT",
    body: JSON.stringify({ all_repos: allRepos }),
  });
}

export type NotionPageSummary = {
  id: string;
  title: string;
  url: string;
  icon: string | null;
  last_edited_time: string | null;
};

export async function listNotionPages(q: string = ""): Promise<NotionPageSummary[]> {
  const query = q.trim() ? `?q=${encodeURIComponent(q.trim())}` : "";
  return apiFetch<NotionPageSummary[]>(`/api/v1/integrations/notion/pages${query}`);
}

export type JiraProjectSummary = {
  external_ref: string;
  key: string;
  name: string;
  site_name: string;
};

export async function listJiraProjects(): Promise<JiraProjectSummary[]> {
  return apiFetch<JiraProjectSummary[]>("/api/v1/integrations/jira/projects");
}

export type AsanaProjectSummary = {
  gid: string;
  name: string;
  workspace_name: string;
};

export async function listAsanaProjects(): Promise<AsanaProjectSummary[]> {
  return apiFetch<AsanaProjectSummary[]>("/api/v1/integrations/asana/projects");
}

export type SlackChannelSummary = {
  id: string;
  name: string;
  is_private: boolean;
};

export async function listSlackChannels(): Promise<SlackChannelSummary[]> {
  return apiFetch<SlackChannelSummary[]>("/api/v1/integrations/slack/channels");
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
