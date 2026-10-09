import type { RmSectionCopy } from "@/lib/api";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

export default function TraceSectionScore({ section, range, loading, hasActions }: {
  section: RmSectionCopy | undefined; range: string; loading: boolean; hasActions: boolean;
}) {
  if (!hasActions) return <div aria-label={`Ungraded context for ${range}`} title="This section contains only context, with no agent actions to assess." className="absolute top-1/2 right-3 flex -translate-y-1/2 items-center px-1 py-1 text-right text-muted-foreground">
    <span className="text-xs">Ungraded</span>
  </div>;
  const value = section ? section.score == null ? "Unscored" : section.score.toFixed(2) : loading ? "Scoring…" : "Unavailable";
  return <TooltipProvider><Tooltip><TooltipTrigger asChild>
    <button type="button" aria-label={`Section score ${value} for ${range}`} className="absolute top-1/2 right-3 flex h-6 -translate-y-1/2 cursor-help items-center rounded px-1 text-right focus-visible:outline-2 focus-visible:outline-brand-500">
      <span className={section?.score != null ? "text-[13px] font-medium tabular-nums" : "text-xs text-muted-foreground"}>{value}</span>
    </button>
  </TooltipTrigger><TooltipContent side="left" sideOffset={8} className="block max-w-80 leading-relaxed">
    {section ? <><p className="m-0 font-medium">{section.objective}</p><p className="m-0 mt-1">{section.score_reason}</p><p className="m-0 mt-2 opacity-70">Estimated success at this section’s local objectives, from 0 to 1.</p></> : <p className="m-0">{loading ? "Assessing this section’s local objectives…" : "The section assessment is unavailable."}</p>}
  </TooltipContent></Tooltip></TooltipProvider>;
}
