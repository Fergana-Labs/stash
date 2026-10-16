"use client";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { useEffect, useState } from "react";
import JudgeWorkspace from "./JudgeWorkspace";
import WebsiteEvalCard from "@/components/wizard/cards/WebsiteEvalCard";
import { tasteGet, tasteReset, type TasteWorkspace } from "@/lib/taste-api";
import { EvalPageFrame } from "@/components/evals/eval-ui";
export default function EvalDestination({ id }: { id: string }) {
  const router = useRouter();
  const [resetting, setResetting] = useState(false);
  const [error, setError] = useState("");
  const [website, setWebsite] = useState<TasteWorkspace | null | undefined>(
    undefined,
  );
  useEffect(() => {
    let active = true;
    void tasteGet()
      .then((value) => {
        if (active) setWebsite(value);
      })
      .catch(() => {
        if (active) setWebsite(null);
      });
    return () => {
      active = false;
    };
  }, [id]);
  if (website === undefined)
    return (
      <p role="status" className="p-6 text-sm">
        Loading eval…
      </p>
    );
  if (website?.model_id !== id) return <JudgeWorkspace id={id} />;
  return (
    <EvalPageFrame
      title={website.name}
      description="Grade your agent’s work through your API."
      actions={<Button variant="outline" size="sm" disabled={resetting} onClick={async () => {
        if (!website.wizard_session_id) return;
        setResetting(true);
        try {
          const result = await tasteReset(website.wizard_session_id);
          router.replace(`/reward-models/wizard/${result.session_id}`);
        } catch (e) { setError(errorMessage(e)); setResetting(false); }
      }}>{resetting ? "Resetting…" : "Reset demo"}</Button>}
    >
      <div className="mx-auto max-w-4xl">
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <WebsiteEvalCard section="connect" readOnly />
      </div>
    </EvalPageFrame>
  );
}
