/**
 * Boozle plugin for OpenClaw.
 *
 * Hybrid plugin: memory backend (scored injection, activity streaming)
 * + platform tools (workspaces, chats, DMs, notebooks, memory stores, agents).
 */

import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

import { BoozleClient } from "./boozle-client.js";
import { loadState, saveState, saveCache } from "./state.js";
import { createPromptSectionBuilder } from "./memory/prompt-section.js";
import { createMemoryRuntime } from "./memory/runtime.js";
import { createFlushPlan } from "./memory/flush-plan.js";
import { createAfterToolCallHook } from "./hooks/after-tool-call.js";
import { registerWorkspaceTools } from "./tools/workspaces.js";
import { registerChatTools } from "./tools/chats.js";
import { registerDmTools } from "./tools/dms.js";
import { registerNotebookTools } from "./tools/notebooks.js";
import { registerMemoryStoreTools } from "./tools/memory-stores.js";
import { registerAgentTools } from "./tools/agents.js";
import { createSetupCommand } from "./commands/setup.js";
import { createStatusCommand } from "./commands/status.js";

export default definePluginEntry({
  id: "boozle",
  name: "Boozle",
  kind: "memory",
  description:
    "Boozle memory backend with server-side scored injection, activity streaming, " +
    "and full platform access (workspaces, chats, notebooks, memory stores).",

  register(api) {
    const config = {
      apiEndpoint:
        (api.config.apiEndpoint as string) ?? "https://moltchat.onrender.com",
      apiKey: (api.config.apiKey as string) ?? "",
      agentName: (api.config.agentName as string) ?? "",
      workspaceId: (api.config.workspaceId as string) ?? "",
      historyStoreId: (api.config.historyStoreId as string) ?? "",
    };

    const client = new BoozleClient(config.apiEndpoint, config.apiKey);

    // --- Memory plugin registrations ---

    api.registerMemoryPromptSection(createPromptSectionBuilder(client, config));
    api.registerMemoryRuntime(createMemoryRuntime(client, config));
    api.registerMemoryFlushPlan(createFlushPlan(client, config));

    // --- Activity streaming hook ---

    api.registerHook("after_tool_call", createAfterToolCallHook(client, config));

    // --- Platform tools (workspaces, chats, DMs, notebooks, memory, agents) ---

    registerWorkspaceTools(api, client);
    registerChatTools(api, client);
    registerDmTools(api, client);
    registerNotebookTools(api, client);
    registerMemoryStoreTools(api, client);
    registerAgentTools(api, client);

    // --- CLI subcommands ---

    api.registerCli("boozle", {
      description: "Boozle plugin management",
      subcommands: {
        setup: {
          description: "Set up Boozle connection (verify auth, workspace, history store)",
          execute: createSetupCommand(client, config),
        },
        status: {
          description: "Show Boozle connection status",
          execute: createStatusCommand(client, config),
        },
        sync: {
          description: "Force-refresh the local context cache",
          async execute() {
            if (!config.apiKey || !config.agentName) {
              return "Not configured. Run `openclaw boozle setup` first.";
            }

            try {
              const profile = await client.whoami();
              let events: Record<string, unknown>[] = [];
              if (config.workspaceId && config.historyStoreId) {
                events = (await client.queryEvents({
                  workspaceId: config.workspaceId,
                  storeId: config.historyStoreId,
                  limit: 20,
                })) as Record<string, unknown>[];
              }
              saveCache(profile, events);
              return `Cache synced: ${events.length} events, agent: ${profile.username ?? profile.name}`;
            } catch (err) {
              return `Sync failed: ${err}`;
            }
          },
        },
        disconnect: {
          description: "Pause activity streaming to Boozle history",
          async execute() {
            const state = loadState();
            state.streaming_enabled = false;
            saveState(state);
            return "Activity streaming paused. Memory injection still active.";
          },
        },
        reconnect: {
          description: "Resume activity streaming to Boozle history",
          async execute() {
            const state = loadState();
            state.streaming_enabled = true;
            saveState(state);
            return "Activity streaming resumed.";
          },
        },
      },
    });
  },
});
