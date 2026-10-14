"use client";

import { useCallback, useEffect, useState } from "react";
import { Copy, Scale, UserPlus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import ItemView from "@/components/intuitions/ItemView";
import { errorMessage } from "@/components/reward-models/rm-text";
import { reviewLinkUrl, wzAgreement, wzCalibration, wzCreateLink, wzLinks, wzRevokeLink, type Agreement, type ReviewLink } from "@/lib/wizard-api";
import { CardShell, NeedsModel, pct, Stat, useWizard } from "../wizard-ui";

const kappa = (k: number | null | undefined) => (k == null ? "" : `κ ${k.toFixed(2)}`);

function CopyLink({ url }: { url: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <span className="flex min-w-0 items-center gap-1">
      <code className="min-w-0 truncate rounded bg-raised px-1.5 py-0.5 text-[11px]">{url}</code>
      <Button size="xs" variant="ghost" aria-label="Copy link" onClick={() => void navigator.clipboard?.writeText(url).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); })}><Copy />{copied ? "Copied" : ""}</Button>
    </span>
  );
}

/**
 * Calibration: other people label the same examples blind through private links.
 * How often people agree with each other is the ceiling for how often the judge
 * can agree with any one of them.
 */
export default function AgreementCard({ invited }: { invited?: string }) {
  const { modelId, send, refresh, version } = useWizard();
  const [data, setData] = useState<Agreement | null>(null);
  const [links, setLinks] = useState<ReviewLink[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!modelId) return;
    try {
      const [a, l] = await Promise.all([wzAgreement(modelId), wzLinks(modelId)]);
      setData(a); setLinks(l.links);
    } catch (e) { setError(errorMessage(e)); }
  }, [modelId]);
  useEffect(() => { void load(); }, [load, version]);

  if (!modelId) return <CardShell icon={Scale} title="Agreement"><NeedsModel /></CardShell>;

  async function invite() {
    if (!modelId || !name.trim()) return;
    try {
      await wzCreateLink(modelId, name.trim());
      setName(""); await load(); refresh();
    } catch (e) { setError(errorMessage(e)); }
  }
  const run = (fn: () => Promise<unknown>) => fn().then(load).catch((e) => setError(errorMessage(e)));

  return (
    <CardShell icon={Scale} title="Agreement" subtitle={data ? `${data.calibration_items} calibration examples · ${links.length} reviewer${links.length === 1 ? "" : "s"}` : "Loading…"}>
      {error && <p role="alert" className="m-0 mb-2 text-[11.5px] text-destructive">{error}</p>}
      {data && (
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-2">
            <Stat label="Judge vs. you" value={pct(data.judge?.agreement)} hint={data.judge ? `${data.judge.n} held-out · ${kappa(data.judge.kappa)}` : "train first"} />
            <Stat label="People vs. each other" value={pct(data.human?.agreement)} hint={data.human ? `${data.human.n} shared · ${kappa(data.human.kappa)}` : "invite a reviewer"} />
          </div>
          {data.verdict && <p className="m-0 text-[12.5px]">{data.verdict}</p>}
          {!data.human && <p className="m-0 text-[12px] text-muted-foreground">People rarely agree 100%. Ask someone who makes this call to label the calibration set; their agreement with you is the most the judge can reach.</p>}

          <section>
            <h4 className="m-0 mb-1.5 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">Reviewers</h4>
            {invited && !links.some((l) => invited.endsWith(l.token)) && <div className="mb-1.5"><CopyLink url={invited} /></div>}
            <ul className="m-0 list-none space-y-1.5 p-0">
              {links.map((l) => (
                <li key={l.token} className="flex items-center gap-2 text-[12px]">
                  <span className="w-24 shrink-0 truncate font-medium">{l.reviewer}</span>
                  <span className="w-16 shrink-0 tabular-nums text-muted-foreground">{l.rated}/{data.calibration_items}</span>
                  <CopyLink url={reviewLinkUrl(l.token)} />
                  <Button size="xs" variant="ghost" aria-label={`Revoke ${l.reviewer}'s link`} onClick={() => void run(() => wzRevokeLink(modelId, l.token))}><X /></Button>
                </li>
              ))}
            </ul>
            <form className="mt-2 flex gap-1.5" onSubmit={(e) => { e.preventDefault(); void invite(); }}>
              <input aria-label="Reviewer name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Name or role, e.g. Dana (support lead)" className="min-w-0 flex-1 rounded-md border border-border bg-background px-2.5 py-1 text-[12px] outline-none focus:border-foreground/40" />
              <Button size="sm" variant="outline" type="submit" disabled={!name.trim()}><UserPlus />Invite</Button>
            </form>
            <p className="m-0 mt-1 text-[11px] text-muted-foreground">Anyone with a link can label the calibration set without an account, and can’t see anyone else’s labels.{data.calibration_items === 0 && <> <button type="button" className="underline" onClick={() => void run(() => wzCalibration(modelId))}>Pick a calibration set</button>.</>}</p>
          </section>

          {data.pairs.length > 1 && (
            <ul className="m-0 list-none space-y-0.5 p-0 text-[12px]">
              {data.pairs.map((p) => <li key={p.a + p.b}>{p.a} vs. {p.b}: <b>{pct(p.agreement)}</b> on {p.n} <span className="text-muted-foreground">{kappa(p.kappa)}</span></li>)}
            </ul>
          )}

          {data.disagreements.length > 0 && (
            <section>
              <h4 className="m-0 mb-1.5 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">Where people disagree</h4>
              <ul className="m-0 list-none space-y-2 p-0">
                {data.disagreements.slice(0, 4).map((d) => (
                  <li key={d.example_id} className="rounded-md border border-border p-2.5">
                    <ItemView item={d.item} />
                    <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[11.5px]">
                      {d.labels.map((l) => <span key={l.rater}>{l.rater}: <b className="font-mono">{l.label}</b>{l.note && <span className="text-muted-foreground"> — {l.note}</span>}</span>)}
                    </div>
                  </li>
                ))}
              </ul>
              <Button className="mt-2" size="sm" variant="outline" onClick={() => send("Reviewers disagree on some calibration examples. Help me sharpen the label definitions so we agree, then update the brief and the judge's description.")}>Sharpen the label definitions</Button>
            </section>
          )}
        </div>
      )}
    </CardShell>
  );
}
