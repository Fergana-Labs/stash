/**
 * Agent identity tools — create, list, rotate keys.
 */

import { Type } from "@sinclair/typebox";
import type { BoozleClient } from "../boozle-client.js";

export function registerAgentTools(
  api: { registerTool: (def: unknown, opts?: unknown) => void },
  client: BoozleClient,
) {
  api.registerTool({
    name: "boozle_create_agent",
    description: "Create a new Boozle agent identity",
    parameters: Type.Object({
      name: Type.String({ description: "Agent name (unique identifier)" }),
      display_name: Type.Optional(Type.String({ description: "Display name" })),
      description: Type.Optional(Type.String({ description: "Agent description" })),
    }),
    async execute(_id: string, params: { name: string; display_name?: string; description?: string }) {
      const result = await client.createAgent(
        params.name,
        params.display_name ?? "",
        params.description ?? "",
      );
      return { content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }] };
    },
  });

  api.registerTool({
    name: "boozle_list_agents",
    description: "List your Boozle agent identities",
    parameters: Type.Object({}),
    async execute() {
      const result = await client.listAgents();
      return { content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }] };
    },
  });

  api.registerTool({
    name: "boozle_rotate_agent_key",
    description: "Rotate the API key for a Boozle agent",
    parameters: Type.Object({
      agent_id: Type.String({ description: "Agent UUID" }),
    }),
    async execute(_id: string, params: { agent_id: string }) {
      const result = await client.rotateAgentKey(params.agent_id);
      return { content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }] };
    },
  });
}
