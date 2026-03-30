/**
 * Lightweight Boozle HTTP client for the OpenClaw plugin.
 * Port of claude-plugin/scripts/boozle_client.py using native fetch.
 */

export class BoozleError extends Error {
  constructor(
    public statusCode: number,
    public detail: string,
  ) {
    super(`[${statusCode}] ${detail}`);
    this.name = "BoozleError";
  }
}

export interface PushEventParams {
  workspaceId: string;
  storeId: string;
  agentName: string;
  eventType: string;
  content: string;
  sessionId?: string;
  toolName?: string;
  metadata?: Record<string, unknown>;
}

export interface QueryEventsParams {
  workspaceId: string;
  storeId: string;
  agentName?: string;
  eventType?: string;
  limit?: number;
  after?: string;
}

export interface InjectParams {
  promptText: string;
  sessionState: Record<string, unknown>;
  sessionId?: string;
}

export interface InjectResult {
  context: string;
  updated_session_state: Record<string, unknown>;
  injected_items: unknown[];
}

export class BoozleClient {
  private baseUrl: string;
  private apiKey: string;

  constructor(baseUrl: string, apiKey: string) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.apiKey = apiKey;
  }

  private headers(): Record<string, string> {
    const h: Record<string, string> = { "Content-Type": "application/json" };
    if (this.apiKey) {
      h["Authorization"] = `Bearer ${this.apiKey}`;
    }
    return h;
  }

  private async request(
    method: string,
    path: string,
    opts?: { json?: unknown; params?: Record<string, string | number> },
  ): Promise<unknown> {
    let url = `${this.baseUrl}${path}`;
    if (opts?.params) {
      const qs = new URLSearchParams();
      for (const [k, v] of Object.entries(opts.params)) {
        if (v !== undefined && v !== null && v !== "") {
          qs.set(k, String(v));
        }
      }
      const qsStr = qs.toString();
      if (qsStr) url += `?${qsStr}`;
    }

    const resp = await fetch(url, {
      method,
      headers: this.headers(),
      body: opts?.json ? JSON.stringify(opts.json) : undefined,
    });

    if (!resp.ok) {
      let detail = "";
      try {
        const body = await resp.json();
        detail = (body as Record<string, string>).detail ?? resp.statusText;
      } catch {
        detail = resp.statusText;
      }
      throw new BoozleError(resp.status, detail);
    }

    if (resp.status === 204) return {};
    return resp.json();
  }

  private get(
    path: string,
    params?: Record<string, string | number>,
  ): Promise<unknown> {
    return this.request("GET", path, { params });
  }

  private post(path: string, json?: unknown): Promise<unknown> {
    return this.request("POST", path, { json });
  }

  // --- Auth ---

  async whoami(): Promise<Record<string, unknown>> {
    return (await this.get("/api/v1/users/me")) as Record<string, unknown>;
  }

  // --- Workspaces ---

  async listWorkspaces(mine = false): Promise<unknown[]> {
    const path = mine ? "/api/v1/workspaces/mine" : "/api/v1/workspaces";
    const data = (await this.get(path)) as Record<string, unknown>;
    return (data.workspaces ?? data) as unknown[];
  }

  async createWorkspace(
    name: string,
    description = "",
    isPublic = false,
  ): Promise<Record<string, unknown>> {
    return (await this.post("/api/v1/workspaces", {
      name,
      description,
      is_public: isPublic,
    })) as Record<string, unknown>;
  }

  // --- History ---

  async createHistory(
    workspaceId: string,
    name: string,
    description = "",
  ): Promise<Record<string, unknown>> {
    return (await this.post(`/api/v1/workspaces/${workspaceId}/memory`, {
      name,
      description,
    })) as Record<string, unknown>;
  }

  async listHistories(workspaceId: string): Promise<unknown[]> {
    const data = (await this.get(
      `/api/v1/workspaces/${workspaceId}/memory`,
    )) as Record<string, unknown>;
    return (data.stores ?? data) as unknown[];
  }

  async pushEvent(params: PushEventParams): Promise<Record<string, unknown>> {
    const body: Record<string, unknown> = {
      agent_name: params.agentName,
      event_type: params.eventType,
      content: params.content,
    };
    if (params.sessionId) body.session_id = params.sessionId;
    if (params.toolName) body.tool_name = params.toolName;
    if (params.metadata) body.metadata = params.metadata;

    return (await this.post(
      `/api/v1/workspaces/${params.workspaceId}/memory/${params.storeId}/events`,
      body,
    )) as Record<string, unknown>;
  }

  async queryEvents(params: QueryEventsParams): Promise<unknown[]> {
    const qs: Record<string, string | number> = {
      limit: params.limit ?? 50,
    };
    if (params.agentName) qs.agent_name = params.agentName;
    if (params.eventType) qs.event_type = params.eventType;
    if (params.after) qs.after = params.after;

    const data = (await this.get(
      `/api/v1/workspaces/${params.workspaceId}/memory/${params.storeId}/events`,
      qs,
    )) as Record<string, unknown>;
    return (data.events ?? data) as unknown[];
  }

  async searchEvents(
    workspaceId: string,
    storeId: string,
    query: string,
    limit = 50,
  ): Promise<unknown[]> {
    const data = (await this.get(
      `/api/v1/workspaces/${workspaceId}/memory/${storeId}/events/search`,
      { q: query, limit },
    )) as Record<string, unknown>;
    return (data.events ?? data) as unknown[];
  }

  // --- Injection (agent-scoped) ---

  async inject(params: InjectParams): Promise<InjectResult> {
    const body: Record<string, unknown> = {
      prompt_text: params.promptText,
      session_state: params.sessionState,
    };
    if (params.sessionId) body.session_id = params.sessionId;
    return (await this.post(
      "/api/v1/personas/me/inject",
      body,
    )) as InjectResult;
  }

  // --- Workspaces (extended) ---

  async joinWorkspace(inviteCode: string): Promise<Record<string, unknown>> {
    return (await this.post("/api/v1/workspaces/join", {
      invite_code: inviteCode,
    })) as Record<string, unknown>;
  }

  async workspaceInfo(workspaceId: string): Promise<Record<string, unknown>> {
    return (await this.get(
      `/api/v1/workspaces/${workspaceId}`,
    )) as Record<string, unknown>;
  }

  async workspaceMembers(workspaceId: string): Promise<unknown[]> {
    const data = (await this.get(
      `/api/v1/workspaces/${workspaceId}/members`,
    )) as Record<string, unknown>;
    return (data.members ?? data) as unknown[];
  }

  // --- Chats ---

  async createChat(
    workspaceId: string,
    name: string,
    description = "",
  ): Promise<Record<string, unknown>> {
    return (await this.post(`/api/v1/workspaces/${workspaceId}/chats`, {
      name,
      description,
    })) as Record<string, unknown>;
  }

  async listChats(workspaceId: string): Promise<unknown[]> {
    const data = (await this.get(
      `/api/v1/workspaces/${workspaceId}/chats`,
    )) as Record<string, unknown>;
    return (data.chats ?? data) as unknown[];
  }

  async sendMessage(
    workspaceId: string,
    chatId: string,
    content: string,
  ): Promise<Record<string, unknown>> {
    return (await this.post(
      `/api/v1/workspaces/${workspaceId}/chats/${chatId}/messages`,
      { content },
    )) as Record<string, unknown>;
  }

  async readMessages(
    workspaceId: string,
    chatId: string,
    limit = 20,
    after = "",
  ): Promise<unknown[]> {
    const params: Record<string, string | number> = { limit };
    if (after) params.after = after;
    const data = (await this.get(
      `/api/v1/workspaces/${workspaceId}/chats/${chatId}/messages`,
      params,
    )) as Record<string, unknown>;
    return (data.messages ?? data) as unknown[];
  }

  async searchMessages(
    workspaceId: string,
    chatId: string,
    query: string,
    limit = 20,
  ): Promise<unknown[]> {
    const data = (await this.get(
      `/api/v1/workspaces/${workspaceId}/chats/${chatId}/messages/search`,
      { q: query, limit },
    )) as Record<string, unknown>;
    return (data.messages ?? data) as unknown[];
  }

  // --- DMs ---

  async startDm(
    userId = "",
    username = "",
  ): Promise<Record<string, unknown>> {
    const body: Record<string, string> = {};
    if (userId) body.user_id = userId;
    if (username) body.username = username;
    return (await this.post("/api/v1/dms", body)) as Record<string, unknown>;
  }

  async listDms(): Promise<unknown[]> {
    const data = (await this.get("/api/v1/dms")) as Record<string, unknown>;
    return (data.conversations ?? data) as unknown[];
  }

  async sendDm(
    content: string,
    userId = "",
    username = "",
  ): Promise<Record<string, unknown>> {
    const body: Record<string, string> = { content };
    if (userId) body.user_id = userId;
    if (username) body.username = username;
    return (await this.post("/api/v1/dms/send", body)) as Record<
      string,
      unknown
    >;
  }

  async readDm(
    userId = "",
    username = "",
    limit = 20,
    after = "",
  ): Promise<unknown[]> {
    const params: Record<string, string | number> = { limit };
    if (userId) params.user_id = userId;
    if (username) params.username = username;
    if (after) params.after = after;
    const data = (await this.get("/api/v1/dms/messages", params)) as Record<
      string,
      unknown
    >;
    return (data.messages ?? data) as unknown[];
  }

  // --- Notebooks ---

  async listNotebooks(workspaceId: string): Promise<unknown[]> {
    const data = (await this.get(
      `/api/v1/workspaces/${workspaceId}/notebooks`,
    )) as Record<string, unknown>;
    return (data.notebooks ?? data) as unknown[];
  }

  async createNotebook(
    workspaceId: string,
    name: string,
    content = "",
    folderId = "",
  ): Promise<Record<string, unknown>> {
    const body: Record<string, string> = { name };
    if (content) body.content = content;
    if (folderId) body.folder_id = folderId;
    return (await this.post(
      `/api/v1/workspaces/${workspaceId}/notebooks`,
      body,
    )) as Record<string, unknown>;
  }

  async readNotebook(
    workspaceId: string,
    notebookId: string,
  ): Promise<Record<string, unknown>> {
    return (await this.get(
      `/api/v1/workspaces/${workspaceId}/notebooks/${notebookId}`,
    )) as Record<string, unknown>;
  }

  async updateNotebook(
    workspaceId: string,
    notebookId: string,
    content = "",
    name = "",
  ): Promise<Record<string, unknown>> {
    const body: Record<string, string> = {};
    if (content) body.content = content;
    if (name) body.name = name;
    return (await this.request(
      "PATCH",
      `/api/v1/workspaces/${workspaceId}/notebooks/${notebookId}`,
      { json: body },
    )) as Record<string, unknown>;
  }

  async deleteNotebook(
    workspaceId: string,
    notebookId: string,
  ): Promise<void> {
    await this.request(
      "DELETE",
      `/api/v1/workspaces/${workspaceId}/notebooks/${notebookId}`,
    );
  }

  // --- Personas ---

  async createPersona(
    name: string,
    displayName = "",
    description = "",
  ): Promise<Record<string, unknown>> {
    return (await this.post("/api/v1/personas", {
      name,
      display_name: displayName,
      description,
    })) as Record<string, unknown>;
  }

  async listPersonas(): Promise<unknown[]> {
    const data = (await this.get("/api/v1/personas")) as Record<string, unknown>;
    return (data.personas ?? data) as unknown[];
  }

  async rotatePersonaKey(personaId: string): Promise<Record<string, unknown>> {
    return (await this.post(
      `/api/v1/personas/${personaId}/rotate-key`,
    )) as Record<string, unknown>;
  }

  // --- Chat Watches ---

  async getUnread(): Promise<Record<string, unknown>> {
    return (await this.get("/api/v1/personas/me/unread")) as Record<
      string,
      unknown
    >;
  }

  async markRead(chatId: string): Promise<Record<string, unknown>> {
    return (await this.post(
      `/api/v1/personas/me/watches/${chatId}/mark-read`,
    )) as Record<string, unknown>;
  }
}
