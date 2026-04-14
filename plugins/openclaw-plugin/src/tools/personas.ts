import type { OpenClawPluginApi } from "openclaw/plugin-sdk/plugin-entry";
import { textResult } from "../utils/tool-result.js";
/**
 * Agent identity tools — create, list, rotate keys.
 */

import { Type } from "@sinclair/typebox";
import type { OctopusClient } from "../octopus-client.js";

export function registerPersonaTools(
  api: OpenClawPluginApi,
  client: OctopusClient,
) {
  api.registerTool({
    name: "octopus_create_persona",
    description: "Create a new Octopus agent identity",
    label: "Create a new Octopus agent identity",
    parameters: Type.Object({
      name: Type.String({ description: "Agent name (unique identifier)" }),
      display_name: Type.Optional(Type.String({ description: "Display name" })),
      description: Type.Optional(Type.String({ description: "Agent description" })),
    }),
    async execute(_id: string, params: { name: string; display_name?: string; description?: string }) {
      const result = await client.createPersona(
        params.name,
        params.display_name ?? "",
        params.description ?? "",
      );
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "octopus_list_personas",
    description: "List your Octopus agent identities",
    label: "List your Octopus agent identities",
    parameters: Type.Object({}),
    async execute() {
      const result = await client.listPersonas();
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "octopus_rotate_persona_key",
    description: "Rotate the API key for an Octopus agent",
    label: "Rotate the API key for an Octopus agent",
    parameters: Type.Object({
      persona_id: Type.String({ description: "Agent UUID" }),
    }),
    async execute(_id: string, params: { persona_id: string }) {
      const result = await client.rotatePersonaKey(params.persona_id);
      return textResult(JSON.stringify(result, null, 2));
    },
  });
}
