"use client";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { useEffect, useState } from "react";
import JudgeWorkspace from "./JudgeWorkspace";
import WebsiteEvalCard from "@/components/wizard/cards/WebsiteEvalCard";
import { tasteGet, tasteReset, type TasteWorkspace } from "@/lib/taste-api";
import { EvalPageFrame } from "@/components/evals/eval-ui";
import { CheckinsSection, ImproveSection, LearnedSection } from "@/components/taste/TasteSections";
import HillClimbSection from "@/components/taste/HillClimbSection";
export default function EvalDestination({ id }: { id: string }) {
  const router = useRouter();
  const [resetting, setResetting] = useState(false);
  const [error, setError] = useState("");
  const [website, setWebsite] = useState<TasteWorkspace | null | undefined>(
    undefined,
  );
  useEffect(() => {
    let active = true;
    const load = () =>
      tasteGet()
        .then((value) => {
          if (active) setWebsite(value);
        })
        .catch(() => {
          if (active) setWebsite((prev) => prev ?? null);
        });
    void load();
    // Check-ins arrive while the user's agent works; keep the timeline live.
    const timer = setInterval(() => void load(), 3000);
    return () => {
      active = false;
      clearInterval(timer);
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
      <div className="mx-auto max-w-5xl">
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        {website.demo && website.endpoint.ready && <div className="mb-6"><HillClimbSection data={website} /></div>}
        <WebsiteEvalCard section="connect" readOnly />
        <div className="mt-6 space-y-6">
          <LearnedSection data={website} />
          <CheckinsSection data={website} />
          {website.demo && website.endpoint.ready && <ImproveSection data={website} />}
        </div>
      </div>
    </EvalPageFrame>
  );
}
