"use client";

import { Inbox } from "lucide-react";
import InboxPanel from "@/components/judge/InboxPanel";
import { CardShell, NeedsModel, useWizard } from "../wizard-ui";

/** The inbox, inline in the chat: the least confident real decisions to confirm or correct. */
export default function InboxCard() {
  const { modelId } = useWizard();
  return (
    <CardShell icon={Inbox} title="Inbox" subtitle="Real decisions, least confident first, confirm or correct">
      {modelId ? <InboxPanel compact /> : <NeedsModel />}
    </CardShell>
  );
}
