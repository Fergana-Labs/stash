"use client";

import PromptPage from "@/components/developer/PromptPage";
import { INSTALL_PROMPT } from "@/components/developer/agentPrompts";

export default function InstallPromptRoute() {
  return (
    <PromptPage
      title="Install"
      blurb="Paste this into your coding agent, pointed at your codebase. It wires the whole
        integration — the read before each turn and the upload after it — and verifies a
        user shows up in this console. Mint a key first and put it in your env."
      prompt={INSTALL_PROMPT}
    />
  );
}
