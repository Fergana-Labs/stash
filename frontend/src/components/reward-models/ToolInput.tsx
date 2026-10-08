import styles from "./TraceMarkdown.module.css";

const label = (key: string) => key.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

/** Strings are already decoded by JSON parsing; show commands as actual lines. */
export default function ToolInput({ input }: { input: Record<string, unknown> }) {
  const entries = Object.entries(input);
  if (!entries.length) return <p className="text-sm text-muted-foreground">No arguments</p>;
  return <div className="space-y-3">{entries.map(([key, value]) => <div key={key}>
    {entries.length > 1 && <div className="mb-1 text-xs text-muted-foreground">{label(key)}</div>}
    <pre className={`${styles.out} m-0 rounded-md bg-surface/60 p-3 text-foreground!`}>{typeof value === "string" ? value : JSON.stringify(value, null, 2)}</pre>
  </div>)}</div>;
}
