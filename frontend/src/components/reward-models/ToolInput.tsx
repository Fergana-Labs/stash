"use client";

import { useState } from "react";
import { ChevronRight, Copy, Check } from "lucide-react";
import { toast } from "sonner";
import SyntaxCode from "./SyntaxCode";
import { codeLanguage } from "./trace-syntax";

function InputField({ name, value, tool }: { name: string; value: unknown; tool: string }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return <div className="group/field border-b border-border-subtle last:border-0">
    <div className="flex min-h-7 items-center gap-2">
      <button type="button" aria-expanded={open} aria-label={`${open ? "Collapse" : "Expand"} input ${name}`} onClick={() => setOpen(!open)} className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 text-left text-xs">
        <ChevronRight aria-hidden="true" className={`size-3 shrink-0 text-muted-foreground ${open ? "rotate-90" : ""}`} />
        <span className="shrink-0 text-xs font-medium text-foreground">{name}</span>
        {!open && <span className="truncate font-mono text-muted-foreground">{text.replace(/\s+/g, " ")}</span>}
      </button>
      <button type="button" aria-label={`Copy input ${name}`} title={`Copy ${name} value`} onClick={() => void navigator.clipboard.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1200); }).catch(() => toast.error("Couldn’t copy this input."))} className="cursor-pointer p-1 text-muted-foreground opacity-0 group-hover/field:opacity-100 focus:opacity-100">{copied ? <Check className="size-3" /> : <Copy className="size-3" />}</button>
    </div>
    {open && <div className="mb-2 rounded-md bg-surface/60 px-3 py-2"><SyntaxCode text={text} language={typeof value === "string" ? codeLanguage(text, name, tool) : "json"} /></div>}
  </div>;
}

export default function ToolInput({ input, tool = "" }: { input: Record<string, unknown>; tool?: string }) {
  if (!Object.keys(input).length) return null;
  return <div aria-label="Tool inputs" className="flex items-start gap-3">
    <span className="w-8 shrink-0 pt-1.5 text-[11px] text-muted-foreground">Inputs</span>
    <div className="min-w-0 flex-1">{Object.entries(input).map(([name, value]) => <InputField key={name} name={name} value={value} tool={tool} />)}</div>
  </div>;
}
