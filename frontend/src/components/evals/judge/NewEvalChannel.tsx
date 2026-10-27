"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { errorMessage } from "@/components/reward-models/rm-text";
import EvalChannel, { type Send } from "./EvalChannel";
import { evalCreate, evalPost } from "@/lib/evals-api";
import { wzCreate } from "@/lib/wizard-api";

/** New eval: an empty channel. The first message creates the eval, then opens it, where the
 * agent reads what was dropped in. A send that fails after the eval exists retries into it. */
export default function NewEvalChannel() {
  const router = useRouter();
  const [name, setName] = useState("");
  const created = useRef<string | null>(null);
  const send = async ({ text, files }: Send, onProgress: (sent: number) => void) => {
    created.current ??= (await evalCreate(name.trim())).id;
    await evalPost(created.current, { text, files, onProgress });
    router.push(`/reward-models/evals/${created.current}`);
  };
  return (
    <div className="max-w-3xl space-y-2">
      <input value={name} onChange={(e) => setName(e.target.value)} maxLength={160}
        placeholder="Name (optional)" aria-label="Eval name"
        className="w-full rounded border border-border bg-background px-3 py-1.5 text-[13px]" />
      <EvalChannel evalId="" messages={[]} onSend={send} onLabel={async () => {}} onRemove={async () => {}} />
    </div>
  );
}

/** The other way in: the conversational wizard, which talks the eval through first. */
export function SetUpInChat() {
  const router = useRouter();
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const start = () => {
    setStarting(true); setError("");
    wzCreate()
      .then((session) => router.push(`/reward-models/wizard/${session.id}`))
      .catch((e) => { setError(errorMessage(e)); setStarting(false); });
  };
  return <span className="flex items-center gap-2">
    {error && <span role="alert" className="text-[12px] text-destructive">{error}</span>}
    <button type="button" disabled={starting} onClick={start}
      className="h-[26px] rounded-[4px] border border-border px-2 text-[11px] hover:bg-surface disabled:opacity-50">
      Set up in chat
    </button>
  </span>;
}
