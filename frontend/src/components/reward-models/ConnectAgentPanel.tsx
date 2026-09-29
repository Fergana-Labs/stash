"use client";

import Link from "next/link";
import { useState } from "react";
import { Check, ChevronDown, Copy, Radio } from "lucide-react";
import { Button } from "@/components/ui/button";
import { usePublicApiBase } from "@/hooks/usePublicApiBase";
import { cn } from "@/lib/utils";

const API_KEY_PLACEHOLDER = "<your API key>";

/** How to point an OpenTelemetry-instrumented agent at the /api/v1/rm/otel receiver. */
export default function ConnectAgentPanel({ collapsible }: { collapsible: boolean }) {
  const apiBase = usePublicApiBase();
  const [open, setOpen] = useState(!collapsible);
  const [copied, setCopied] = useState(false);
  const expanded = open || !collapsible;

  const endpointLine = `export OTEL_EXPORTER_OTLP_ENDPOINT=${apiBase}/api/v1/rm/otel`;
  // opentelemetry-instrument defaults to the gRPC exporter; the receiver speaks OTLP/HTTP only.
  const protocolLine = "export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf";
  const headersPrefix = 'export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer%20';
  const runLine = "opentelemetry-instrument python agent.py";
  const commands = `${endpointLine}\n${protocolLine}\n${headersPrefix}${API_KEY_PLACEHOLDER}"\n\n${runLine}`;

  async function copy() {
    await navigator.clipboard.writeText(commands);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <section className="mb-6 rounded-lg border border-border bg-surface/50">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        disabled={!collapsible}
        className="flex w-full items-center gap-2 px-4 py-3 text-left disabled:cursor-default"
      >
        <Radio className="h-4 w-4 text-brand-500" />
        <span className="text-[13.5px] font-semibold text-foreground">Connect your agent</span>
        <span className="text-[12px] text-muted-foreground">Traces arrive automatically over OpenTelemetry.</span>
        <span className="flex-1" />
        {collapsible && (
          <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition-transform", expanded && "rotate-180")} />
        )}
      </button>

      {expanded && (
        <div className="border-t border-border-subtle px-4 pt-3 pb-4">
          <div className="relative">
            <pre className="scroll-thin m-0 overflow-x-auto rounded-md border border-border bg-background px-3.5 py-3 pr-24 font-mono text-[12px] leading-relaxed text-foreground">
              {endpointLine}
              {"\n"}
              {protocolLine}
              {"\n"}
              {headersPrefix}
              <Link href="/developer/keys" className="text-brand-600 underline decoration-brand-300 underline-offset-2 hover:text-brand-700">
                {API_KEY_PLACEHOLDER}
              </Link>
              {'"\n\n'}
              {runLine}
            </pre>
            <Button variant="outline" size="xs" onClick={() => void copy()} className="absolute top-2 right-2">
              {copied ? <Check /> : <Copy />}
              {copied ? "Copied" : "Copy"}
            </Button>
          </div>
          <p className="m-0 mt-2.5 text-[12px] leading-relaxed text-muted-foreground">
            Works with any OpenTelemetry or OpenInference instrumentation: OpenAI, Anthropic, OpenAI Agents SDK,
            LangChain, LlamaIndex, CrewAI, DSPy, Vercel AI SDK. New runs appear here automatically.
          </p>
          <p className="m-0 mt-1 text-[12px] leading-relaxed text-muted-foreground/80">
            Calling a model SDK directly in a loop? Wrap each run in one span so its calls share a trace.
          </p>
        </div>
      )}
    </section>
  );
}
