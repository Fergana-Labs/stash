"use client";

import Link from "next/link";
import { useState } from "react";
import { Check, Copy, Plug } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import { usePublicApiBase } from "@/hooks/usePublicApiBase";
import { errorMessage } from "./rm-text";

export default function ConnectAgentDialog() {
  const apiBase = usePublicApiBase();
  const [method, setMethod] = useState<"otel" | "http">("otel");
  const [copied, setCopied] = useState(false);
  const commands = method === "otel"
    ? `export OTEL_EXPORTER_OTLP_ENDPOINT=${apiBase}/api/v1/rm/otel
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer%20<your API key>"

opentelemetry-instrument python agent.py`
    : `export STASH_API_KEY="<your API key>"

jq -Rs '{format: "auto", data: .}' traces.jsonl \\
  | curl --fail-with-body "${apiBase}/api/v1/rm/traces/import" \\
      -H "Authorization: Bearer $STASH_API_KEY" \\
      -H "Content-Type: application/json" \\
      --data-binary @-`;

  async function copy() {
    try {
      await navigator.clipboard.writeText(commands);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (error) {
      toast.error(errorMessage(error));
    }
  }

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline">
          <Plug />Connect your agent
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Connect your agent</DialogTitle>
          <DialogDescription>Send runs automatically. New traces appear here as they arrive.</DialogDescription>
        </DialogHeader>
        <div className="flex gap-2" aria-label="Connection method">
          <Button
            variant={method === "otel" ? "default" : "outline"}
            size="sm"
            aria-pressed={method === "otel"}
            onClick={() => { setMethod("otel"); setCopied(false); }}
          >
            OpenTelemetry
          </Button>
          <Button
            variant={method === "http" ? "default" : "outline"}
            size="sm"
            aria-pressed={method === "http"}
            onClick={() => { setMethod("http"); setCopied(false); }}
          >
            HTTP API
          </Button>
        </div>
        <p className="m-0 text-[13px] leading-relaxed text-muted-foreground">
          {method === "otel"
            ? "For agents with OpenTelemetry or OpenInference instrumentation installed. Configure the OTLP exporter, then run your agent. Keep each run under one root span to preserve tool timing and subagent relationships."
            : "Call this endpoint from your agent after each run. This example sends a JSONL file; the API accepts supported trace payloads as the data string and detects their format."}
        </p>
        <div className="min-w-0 overflow-hidden rounded-md border border-border">
          <div className="flex items-center justify-between border-b border-border px-3 py-2">
            <span className="text-[12px] text-muted-foreground">{method === "otel" ? "Agent environment" : "Upload a completed run"}</span>
            <Button variant="ghost" size="xs" onClick={() => void copy()}>
              {copied ? <Check /> : <Copy />}{copied ? "Copied" : "Copy"}
            </Button>
          </div>
          <pre className="m-0 overflow-x-auto p-3 font-mono text-[12px] leading-relaxed">{commands}</pre>
        </div>
        <div className="flex items-center justify-between text-[13px]">
          <Link href="/settings#api-keys" className="text-brand-600 hover:underline">Create a Full access API key</Link>
          <a href="https://www.joinstash.ai/docs/api" target="_blank" rel="noreferrer" className="text-muted-foreground hover:text-foreground">Integration guide ↗</a>
        </div>
      </DialogContent>
    </Dialog>
  );
}
