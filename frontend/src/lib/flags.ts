import type { User } from "./types";

// Tools is cut from the product surface (Aug 2026 focus pass): Stash does two
// things — memory for internal coding agents, and the Developer Platform for
// external agents. Heavi's deployment still depends on Tools, so their org
// keeps it; ferganalabs keeps it to support Heavi.
const TOOLS_DOMAINS = new Set(["heaviai.com", "ferganalabs.com"]);

export function showTools(user: User | null | undefined): boolean {
  const email = user?.email;
  if (!email) return false;
  const domain = email.split("@").pop();
  if (!domain) return false;
  return TOOLS_DOMAINS.has(domain.toLowerCase());
}
