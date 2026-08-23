import type { User } from "./types";

// Tools and Chat are cut from the product surface (Aug 2026 focus pass):
// Stash does two things — memory for internal coding agents, and the
// Developer Platform for external agents. Heavi's deployment still depends on
// Tools + Chat, so their org keeps both; ferganalabs keeps them to support
// Heavi.
const TOOLS_AND_CHAT_DOMAINS = new Set(["heaviai.com", "ferganalabs.com"]);

export function showToolsAndChat(user: User | null | undefined): boolean {
  const email = user?.email;
  if (!email) return false;
  const domain = email.split("@").pop();
  if (!domain) return false;
  return TOOLS_AND_CHAT_DOMAINS.has(domain.toLowerCase());
}
