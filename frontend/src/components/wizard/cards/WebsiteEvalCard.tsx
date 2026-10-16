"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Sparkles } from "lucide-react";
import { tasteGet, type TasteWorkspace } from "@/lib/taste-api";
import { CopyText } from "@/components/taste/website-eval-ui";
import { errorMessage } from "@/components/reward-models/rm-text";
import { CardShell, useWizard } from "../wizard-ui";
import TraceSourcesCard from "./TraceSourcesCard";
import PreferencesCard from "./PreferencesCard";

/** A single setup result. Older research cards resolve to this same surface. */
export default function WebsiteEvalCard({
  section,
  ...props
}: {
  section?: string;
  jobId?: string;
  exampleIds?: string[];
  readOnly?: boolean;
}) {
  if (section === "sources") return <TraceSourcesCard />;
  if (section === "preferences") return <PreferencesCard />;
  return <EvalProgress {...props} />;
}

function EvalProgress({
  jobId,
  readOnly = false,
}: {
  jobId?: string;
  readOnly?: boolean;
}) {
  const { send } = useWizard();
  const router = useRouter();
  const [data, setData] = useState<TasteWorkspace | null>(null);
  const [error, setError] = useState("");
  const [origin, setOrigin] = useState("");
  const notified = useRef(false);
  useEffect(() => {
    let live = true;
    setOrigin(window.location.origin);
    const reload = async () => {
      try {
        const next = await tasteGet();
        if (live) {
          setData(next);
          setError("");
        }
      } catch (e) {
        if (live) setError(errorMessage(e));
      }
    };
    void reload();
    const timer = setInterval(() => void reload(), 3000);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, []);
  useEffect(() => {
    if (!readOnly && data?.published && data.endpoint?.ready && data.model_id) {
      router.replace(`/reward-models/evals/${data.model_id}`);
    }
  }, [data, readOnly, router]);
  useEffect(() => {
    if (data?.published && data.endpoint?.ready) return;
    if (readOnly || !jobId || !data || notified.current) return;
    const job = data.jobs.find((j) => j.id === jobId);
    if (!job || !["succeeded", "failed"].includes(job.status)) return;
    const key = "website-eval-job:" + jobId;
    if (sessionStorage.getItem(key)) return;
    notified.current = true;
    sessionStorage.setItem(key, "seen");
    send(
      job.status === "succeeded" ? "Finished reading your sessions." : "Reading your sessions failed.",
      "event",
    );
  }, [data, jobId, readOnly, send]);
  const ready = data?.endpoint?.ready && !!data.endpoint.path;
  const job =
    data?.jobs.find((j) => j.id === jobId) ??
    data?.jobs.find((j) => ["queued", "running"].includes(j.status));
  const endpoint = ready ? origin + data.endpoint.path : "";
  return (
    <CardShell
      icon={Sparkles}
      title={ready ? "Your eval is ready" : "Learning from your traces"}
    >
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      {ready ? (
        <div className="space-y-3">
          <p className="text-sm">
            Give this to your agent so it can check its work while it builds.
            Over MCP, it’s the <code>check_website_taste</code> tool.
          </p>
          <CopyText text={endpoint} />
          <CopyText
            text={`curl '${endpoint}' \\\n  -H "Authorization: Bearer $STASH_API_KEY" \\\n  -H 'Content-Type: application/json' \\\n  --data @input.json`}
          />
          {data.endpoint.quality_note && (
            <p className="text-xs text-muted-foreground">
              {data.endpoint.quality_note}
            </p>
          )}
          <details className="text-xs">
            <summary className="cursor-pointer">Request format</summary>
            <p className="mt-2 text-muted-foreground">
              Send the task, public agent trace, and the finished output. Use
              your existing Stash API key.
            </p>
            <CopyText
              text={JSON.stringify(
                {
                  item: {
                    brief: "The website the agent was asked to build",
                    trace: [
                      { id: "1", role: "user", text: "Build the website" },
                      {
                        id: "2",
                        role: "assistant",
                        text: "What the agent did",
                      },
                    ],
                    html: "<html>...</html>",
                    screenshot_base64: "BASE64_PNG_OR_JPEG",
                    trace_complete: true,
                  },
                },
                null,
                2,
              )}
            />
          </details>
        </div>
      ) : (
        <p role="status" className="text-sm text-muted-foreground">
          {job?.status === "failed"
            ? "I couldn’t finish creating the eval. I’ll explain what’s missing in the conversation."
            : job?.status === "running" || job?.status === "queued"
              ? "I’m reading your feedback and creating your eval. You can leave this page and come back."
              : "I’ll use the feedback in your traces and ask only if something essential is unclear."}
        </p>
      )}
    </CardShell>
  );
}
