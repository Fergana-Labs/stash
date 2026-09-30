import { errorSummary } from "./rm-text";

// A failed job's error text is the tail of its worker log. Lead with the line
// that says what went wrong and keep the rest one click away.
export function JobError({ error, className }: { error: string; className?: string }) {
  return (
    <div className={`rounded-md border border-border bg-muted/40 px-3 py-2 text-[12.5px] ${className ?? ""}`}>
      <p className="m-0 font-mono break-words text-foreground">{errorSummary(error)}</p>
      <details className="mt-1.5">
        <summary className="cursor-pointer text-[12px] text-muted-foreground">Show log</summary>
        <pre className="m-0 mt-1.5 max-h-60 overflow-auto font-mono text-[11.5px] whitespace-pre-wrap text-muted-foreground">
          {error}
        </pre>
      </details>
    </div>
  );
}
