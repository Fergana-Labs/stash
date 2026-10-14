"use client";

import { useState } from "react";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useWizard } from "../wizard-ui";

/** Quick replies: one click answers the wizard's question with the option text. */
export default function ChoicesCard({ question, options, multi = false }: { question: string; options: string[]; multi?: boolean }) {
  const { send, busy } = useWizard();
  const [picked, setPicked] = useState<string[]>([]);
  const [sent, setSent] = useState(false);
  const answer = (values: string[]) => { setSent(true); send(values.join(", ")); };
  return (
    <div className="my-2 rounded-lg border border-border bg-surface/40 p-3">
      <p className="m-0 mb-2 text-[12.5px] font-medium">{question}</p>
      <div className="flex flex-wrap gap-1.5">
        {options.map((option) => {
          const on = picked.includes(option);
          return (
            <Button
              key={option}
              size="sm"
              variant={on ? "secondary" : "outline"}
              disabled={sent || busy}
              aria-pressed={multi ? on : undefined}
              className={cn("h-auto min-h-8 whitespace-normal py-1.5 text-left", on && "ring-1 ring-brand-500/40")}
              onClick={() => (multi ? setPicked((p) => (on ? p.filter((x) => x !== option) : [...p, option])) : answer([option]))}
            >
              {multi && on && <Check className="size-3" />}
              {option}
            </Button>
          );
        })}
      </div>
      {multi && !sent && <Button size="sm" className="mt-2" disabled={!picked.length || busy} onClick={() => answer(picked)}>Send</Button>}
    </div>
  );
}
