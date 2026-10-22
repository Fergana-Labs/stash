"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { evalSurfaceClass } from "@/components/evals/eval-ui";
import { CopyBlock, origin, snippets } from "./UseIt";
import { cn } from "@/lib/utils";

export function editPrompt(id: string, name: string, task?: string) {
  return `Edit my Stash eval ${JSON.stringify(name)} (intuition_id="${id}") through MCP.
Connect to ${origin()}/mcp/intuitions using my Stash API key.
Read its current definition, criteria, examples and results with get_intuition and list_examples.
${task || "Make the changes I request to this eval."}
Use update_intuition, save_brief, set_criteria, add_examples or label_example as appropriate.
Keep human-confirmed labels; ask me to label ambiguous examples rather than inventing decisions.
After changing the eval, use train and report held-out agreement with its sample size.
Use ship to publish only when the validation gate passes.`;
}

export default function EditViaMcp({ id, name, request }: { id: string; name: string; request: { id: number; text: string } | null }) {
  const [open, setOpen] = useState(false);
  useEffect(() => { if (request) setOpen(true); }, [request]);
  return <Dialog open={open} onOpenChange={setOpen}>
    <DialogTrigger asChild><Button size="sm" variant="outline">Edit via MCP</Button></DialogTrigger>
    <DialogContent className={cn(evalSurfaceClass, "max-h-[calc(100dvh-2rem)] overflow-y-auto rounded-[4px] sm:max-w-2xl")}>
      <DialogHeader><DialogTitle className="text-sm">Edit with your agent</DialogTitle><DialogDescription className="text-xs">Paste these instructions into your agent connected to Stash.</DialogDescription></DialogHeader>
      <CopyBlock label="edit instructions" text={editPrompt(id, name, request?.text)} />
      <details className="text-xs"><summary className="cursor-pointer text-muted-foreground">MCP connection</summary><div className="mt-2"><CopyBlock label="MCP config" text={snippets(id, name).mcp} /></div></details>
    </DialogContent>
  </Dialog>;
}
