/**
 * Boozle plugin for OpenClaw.
 *
 * Hybrid plugin: memory backend (scored injection, activity streaming)
 * + platform tools (workspaces, chats, DMs, notebooks, memory stores, agents).
 */

import { definePluginEntry, type OpenClawPluginApi } from "openclaw/plugin-sdk/plugin-entry";

import { BoozleClient } from "./boozle-client.js";
import { loadState, saveState, saveCache } from "./state.js";
import { createPromptSectionBuilder } from "./memory/prompt-section.js";
import { createFlushPlanResolver } from "./memory/flush-plan.js";
import { createAfterToolCallHook } from "./hooks/after-tool-call.js";
import { registerWorkspaceTools } from "./tools/workspaces.js";
import { registerChatTools } from "./tools/chats.js";
import { registerDmTools } from "./tools/dms.js";
import { registerNotebookTools } from "./tools/notebooks.js";
import { registerMemoryStoreTools } from "./tools/memory-stores.js";
import { registerPersonaTools } from "./tools/personas.js";

export default definePluginEntry({
  id: "boozle",
  name: "Boozle",
  kind: "memory",
  description:
    "Boozle memory backend with server-side scored injection, activity streaming, " +
    "and full platform access (workspaces, chats, notebooks, memory stores, personas).",

  register(api: OpenClawPluginApi) {
    // Read plugin config from the OpenClaw config system.
    // Plugin config keys are stored under the plugin's namespace in the
    // OpenClaw config file; access them via api.getPluginConfig().
    const pluginCfg = (api as any).getPluginConfig?.("boozle") ?? {};
    const config = {
      apiEndpoint:
        (pluginCfg.apiEndpoint as string) ?? "https://moltchat.onrender.com",
      apiKey: (pluginCfg.apiKey as string) ?? "",
      agentName: (pluginCfg.agentName as string) ?? "",
      workspaceId: (pluginCfg.workspaceId as string) ?? "",
      historyStoreId: (pluginCfg.historyStoreId as string) ?? "",
    };

    const client = new BoozleClient(config.apiEndpoint, config.apiKey);

    // --- Memory plugin registrations ---

    api.registerMemoryPromptSection(createPromptSectionBuilder(client, config));
    api.registerMemoryFlushPlan(createFlushPlanResolver(client, config));

    // --- Activity streaming hook ---

    api.registerHook("message", createAfterToolCallHook(client, config));

    // --- Platform tools (workspaces, chats, DMs, notebooks, memory, personas) ---

    registerWorkspaceTools(api, client);
    registerChatTools(api, client);
    registerDmTools(api, client);
    registerNotebookTools(api, client);
    registerMemoryStoreTools(api, client);
    registerPersonaTools(api, client);

    // --- CLI subcommands ---

    api.registerCli(
      (ctx) => {
        const cmd = ctx.program
          .command("boozle")
          .description("Boozle plugin management");

        cmd
          .command("setup")
          .description("Set up Boozle connection (verify auth, workspace, history store)")
          .action(async () => {
            if (!config.apiKey) {
              ctx.logger.info("No API key configured. Set boozle.apiKey in your OpenClaw config.");
              return;
            }
            try {
              const me = await client.whoami();
              ctx.logger.info(`Authenticated as ${me.name} (${me.type})`);
              if (config.workspaceId) ctx.logger.info(`Workspace: ${config.workspaceId}`);
              if (config.historyStoreId) ctx.logger.info(`History store: ${config.historyStoreId}`);
            } catch (err) {
              ctx.logger.error(`Auth failed: ${err}`);
            }
          });

        cmd
          .command("status")
          .description("Show Boozle connection status")
          .action(async () => {
            const state = loadState();
            ctx.logger.info(`Streaming: ${state.streaming_enabled ? "on" : "off"}`);
            ctx.logger.info(`Session: ${state.session_id || "(none)"}`);
            ctx.logger.info(`Endpoint: ${config.apiEndpoint}`);
            ctx.logger.info(`Agent: ${config.agentName || "(not set)"}`);
          });

        cmd
          .command("sync")
          .description("Force-refresh the local context cache")
          .action(async () => {
            if (!config.apiKey || !config.agentName) {
              ctx.logger.info("Not configured. Run `openclaw boozle setup` first.");
              return;
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
              ctx.logger.info(`Cache synced: ${events.length} events, agent: ${(profile as any).username ?? (profile as any).name}`);
            } catch (err) {
              ctx.logger.error(`Sync failed: ${err}`);
            }
          });

        cmd
          .command("disconnect")
          .description("Pause activity streaming to Boozle history")
          .action(() => {
            const state = loadState();
            state.streaming_enabled = false;
            saveState(state);
            ctx.logger.info("Activity streaming paused. Memory injection still active.");
          });

        cmd
          .command("reconnect")
          .description("Resume activity streaming to Boozle history")
          .action(() => {
            const state = loadState();
            state.streaming_enabled = true;
            saveState(state);
            ctx.logger.info("Activity streaming resumed.");
          });
      },
      {
        descriptors: [
          { name: "boozle", description: "Boozle plugin management", hasSubcommands: true },
        ],
      },
    );
  },
});
