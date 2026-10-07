"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { Button } from "@/components/ui/button";
import { EmptyState, Field, RmPage } from "@/components/reward-models/rm-ui";
import { errorMessage, relativeTime } from "@/components/reward-models/rm-text";
import GraderConfigEditor, { initialGraderConfig, validGraderConfig } from "@/components/workbench/GraderConfigEditor";
import { ErrorNotice, inputClass, JsonDetails, RecordBadge, RecordPanel, useWorkbenchLoad } from "@/components/workbench/workbench-ui";
import { wbCreateGrader, wbCreateVersion, wbGetGrader, wbListGraders, wbRollbackGrader, wbStatus, wbUpdateGrader, type Grader, type GraderConfig, type GraderDetail, type WorkbenchScope } from "@/lib/workbench-api";

const loadGraders = async () => { const [graders, status] = await Promise.all([wbListGraders(), wbStatus()]); return { graders, status }; };

export default function GradersPage() {
  useBreadcrumbs([{ label: "Graders" }], "workbench-graders");
  const { data, loading, error, reload } = useWorkbenchLoad(loadGraders);
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  async function toggle(grader: Grader) {
    setBusyId(grader.id); setMutationError(null);
    try { await wbUpdateGrader(grader.id, { enabled: !grader.enabled }); await reload(); }
    catch (e) { setMutationError(errorMessage(e)); }
    finally { setBusyId(null); }
  }
  return <RmPage title="Graders" description="Define the criteria once. Matching recorded runs are assessed automatically; no task assignment is required." actions={<Button onClick={() => { setCreating(!creating); setSelected(null); }}>{creating ? "Cancel" : "New grader"}</Button>}>
    <ErrorNotice error={error ?? mutationError} onRetry={() => void reload()} />
    {data && !data.status.configured && <div role="status" className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 text-[13px]">JEV is not configured on this server. You can prepare graders, but assessments cannot run until an administrator configures the provider.</div>}
    {creating && <div className="mb-6"><CreateGrader model={data?.status.model} onCreated={async (grader) => { setCreating(false); setSelected(grader.id); await reload(); }} /></div>}
    {loading && <p className="text-[13px] text-muted-foreground">Loading graders…</p>}
    {data?.graders.length === 0 && !creating && <EmptyState title="No graders yet">Create a grader for the coding runs you want to assess. Start with a concrete criterion such as accurate test reporting.</EmptyState>}
    <div className="space-y-3">{data?.graders.map((grader) => <RecordPanel key={grader.id} title={<button type="button" className="cursor-pointer text-left hover:underline" onClick={() => setSelected(selected === grader.id ? null : grader.id)}>{grader.name}</button>} actions={<div className="flex items-center gap-2"><RecordBadge value={grader.enabled ? "active" : "paused"} /><Button size="sm" variant="outline" disabled={busyId === grader.id} onClick={() => void toggle(grader)}>{grader.enabled ? "Pause grading" : "Resume grading"}</Button></div>}>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-muted-foreground"><span>{grader.scope.repository || "All repositories"}</span><span>{grader.scope.source_format || "All captured harnesses"}</span><span>{grader.active_version ? `Version ${grader.active_version.version}` : grader.active_version_id ? "Active version available" : "No active version"}</span><span>Created {relativeTime(grader.created_at)}</span></div>
      <Button variant="link" size="sm" className="mt-2 px-0" onClick={() => setSelected(selected === grader.id ? null : grader.id)}>{selected === grader.id ? "Close configuration" : "Inspect criteria and versions"}</Button>
      {selected === grader.id && <GraderVersions graderId={grader.id} />}
    </RecordPanel>)}</div>
  </RmPage>;
}

function CreateGrader({ onCreated, model }: { onCreated: (grader: Grader) => Promise<void>; model?: string }) {
  const [name, setName] = useState("");
  const [repository, setRepository] = useState("");
  const [sourceFormat, setSourceFormat] = useState("");
  const [config, setConfig] = useState<GraderConfig>({ ...initialGraderConfig, model: model ?? initialGraderConfig.model });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    const scope: WorkbenchScope = {};
    if (repository.trim()) scope.repository = repository.trim();
    if (sourceFormat) scope.source_format = sourceFormat;
    try { await onCreated(await wbCreateGrader({ name: name.trim(), scope, config })); }
    catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }
  return <RecordPanel title="Configure automatic grading"><form onSubmit={(event) => void submit(event)} className="max-w-3xl space-y-4">
    <Field label="Grader name"><input required value={name} onChange={(e) => setName(e.target.value)} placeholder="Coding test reports" className={inputClass} /></Field>
    <div className="grid gap-3 sm:grid-cols-2"><Field label="Repository directory" hint="Exact working directory recorded by the harness. Leave empty for all your repositories."><input value={repository} onChange={(e) => setRepository(e.target.value)} placeholder="/path/to/stash" className={inputClass} /></Field><Field label="Captured harness"><select value={sourceFormat} onChange={(e) => setSourceFormat(e.target.value)} className={inputClass}><option value="">All captured harnesses</option><option value="codex">Codex</option><option value="claude_code">Claude Code</option></select></Field></div>
    <GraderConfigEditor value={config} onChange={setConfig} disabled={busy} />
    <p className="m-0 text-[12px] text-muted-foreground">Creating this grader enables its first version for matching saved and incoming runs. Later configuration changes are saved as candidates and released separately.</p>
    <ErrorNotice error={error} /><Button type="submit" disabled={busy || !name.trim() || !validGraderConfig(config)}>{busy ? "Creating…" : "Create and enable automatic grading"}</Button>
  </form></RecordPanel>;
}

function GraderVersions({ graderId }: { graderId: string }) {
  const loader = useCallback(() => wbGetGrader(graderId), [graderId]);
  const { data, loading, error, reload } = useWorkbenchLoad(loader);
  return <div className="mt-3 border-t border-border pt-4"><ErrorNotice error={error} onRetry={() => void reload()} />{loading && <p className="text-[12px] text-muted-foreground">Loading version history…</p>}{data && <GraderVersionEditor detail={data} onSaved={reload} />}</div>;
}

function GraderVersionEditor({ detail, onSaved }: { detail: GraderDetail; onSaved: () => Promise<void> }) {
  const active = detail.versions.find((v) => v.id === detail.grader.active_version_id) ?? detail.versions[0];
  const [config, setConfig] = useState<GraderConfig>(active?.config ?? initialGraderConfig);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  async function save() {
    setBusy(true); setError(null);
    try { await wbCreateVersion(detail.grader.id, config); setSaved(true); setEditing(false); await onSaved(); }
    catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }
  async function restore(versionId: string) {
    setBusy(true); setError(null);
    try { await wbRollbackGrader(detail.grader.id, versionId); await onSaved(); }
    catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }
  return <div className="space-y-3"><ErrorNotice error={error} />
    {saved && <p role="status" className="text-[12px] text-muted-foreground">Candidate saved. Current grading is unchanged. <Link href="/reward-models/changes" className="underline">Open Changes to check and release it</Link>.</p>}
    {!editing && <Button size="sm" variant="outline" onClick={() => { setConfig(active?.config ?? initialGraderConfig); setEditing(true); setSaved(false); }}>Propose a new version</Button>}
    {editing && <div className="space-y-4 rounded-md bg-surface/50 p-4"><GraderConfigEditor value={config} onChange={setConfig} disabled={busy} /><div className="flex gap-2"><Button size="sm" disabled={busy || !validGraderConfig(config)} onClick={() => void save()}>{busy ? "Saving…" : "Save candidate version"}</Button><Button size="sm" variant="ghost" disabled={busy} onClick={() => setEditing(false)}>Cancel</Button></div></div>}
    {detail.versions.map((version) => <div key={version.id} className="space-y-1"><JsonDetails title={`Version ${version.version}${version.id === detail.grader.active_version_id ? " · active" : " · previously released"} · ${relativeTime(version.created_at)}`} value={version.config} />{version.id !== detail.grader.active_version_id && <Button size="xs" variant="ghost" disabled={busy} onClick={() => void restore(version.id)}>Restore version {version.version} for future grading</Button>}</div>)}
    {detail.history && <JsonDetails title="Grader configuration and release history" value={detail.history} />}
  </div>;
}
