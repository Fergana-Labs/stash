import Link from "next/link";
import { Callout, H3, P, Title, Subtitle } from "./components";

export default function DocsOverview() {
  return (
    <>
      <Title>Stash Overview</Title>
      <Subtitle> Stash is shared memory for your repositories. Agents push in their work automatically. Stash indexes it into a shared, searchable knowledge base. </Subtitle>

      <Callout type="tip">
        <strong>Ready to get started?</strong> Go straight to the{" "}
        <Link href="/docs/quickstart" className="text-brand underline underline-offset-2">
          Quickstart
        </Link>{" "}
        to install in one click.
      </Callout>

      <H3>How Stash Works</H3>
      <P>
        Stash makes it so that <strong>every contributor to your repo effectively uses the same coding agent</strong> 
   
        , regardless of model, harness, or device.
      </P> 
      <P>
        More concretely, Stash auto-uploads coding
        agent transcripts to a shared store, indexes them,
        and then makes those transcripts accessible to every other coding agent using the repo.

        Every research result, file, and message lands in a shared workspace. Stash
        organizes this information into a categorized wiki, with backlinks, summaries, and semantic search
        so contributor to your repo can find and build on what others have learned.
      </P>

      <H3>Example: Don&apos;t Duplicate Work</H3>
      <P>
        Henry asks his coding agent to investigate a memory leak. His teammate Sam
        already spent hours debugging the same issue the night before. Without Stash,
        the agent starts from scratch. With Stash, it picks up where Sam left off.
      </P>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 my-6">
        {/* Without Stash */}
        <div className="rounded-2xl border border-border overflow-hidden flex flex-col">
          <div className="bg-surface px-4 py-2.5 border-b border-border">
            <span className="text-xs font-medium text-muted uppercase tracking-wider">Without Stash</span>
          </div>
          <div className="bg-[#1a1a1a] font-mono text-[12px] leading-[1.7] flex-1 flex flex-col max-h-[280px]">
            <div className="px-4 pt-4 pb-3">
              <span className="text-zinc-500">&gt;</span>{" "}
              <span className="text-zinc-200">Investigate the memory leak with our calendar service</span>
            </div>
            <div className="px-4 py-1 space-y-3 overflow-y-auto flex-1">
              <div className="text-zinc-400">
                <span className="text-zinc-500">●</span> Reading server logs and source code...
              </div>
              <div className="text-zinc-400">
                <span className="text-zinc-500">●</span> Found 11 CalendarClient creation sites, only 1 has cleanup
              </div>
              <div className="text-zinc-400">
                <span className="text-zinc-500">●</span> Found 10 GmailClient creation sites, only 3 have close()
              </div>
              <div className="text-zinc-400">
                <span className="text-zinc-500">●</span> Hypothesis: unclosed httplib2 connections from build() calls
              </div>
              <div className="text-zinc-400">
                <span className="text-zinc-500">●</span> Testing whether webhooks or draft_refresh_loop is the source...
              </div>
              <div className="text-zinc-400">
                <span className="text-zinc-500">●</span> Confirmed: draft_refresh_loop creates 10 build() calls/min
              </div>
              <div className="text-zinc-300 mt-1">
                The root cause is unclosed httplib2+SSL connections. Each build() call
                leaks ~100KB. At 2-3/sec over 2 hours = ~1.15GB.
              </div>
            </div>
            <div className="px-4 pt-2 pb-4 border-t border-zinc-800">
              <div className="text-zinc-600 text-[12px]">
                <span className="text-zinc-500">✱</span> Sautéed for 12m 42s
              </div>
            </div>
          </div>
        </div>

        {/* With Stash */}
        <div className="rounded-2xl border border-brand/30 overflow-hidden flex flex-col">
          <div className="bg-brand/10 px-4 py-2.5 border-b border-brand/20">
            <span className="text-xs font-medium text-brand uppercase tracking-wider">With Stash</span>
          </div>
          <div className="bg-[#1a1a1a] font-mono text-[12px] leading-[1.7] flex-1 flex flex-col max-h-[280px]">
            <div className="px-4 pt-4 pb-3">
              <span className="text-zinc-500">&gt;</span>{" "}
              <span className="text-zinc-200">Investigate the memory leak with our calendar service</span>
            </div>
            <div className="px-4 py-1 space-y-3 overflow-y-auto flex-1">
              <div className="text-zinc-400">
                <span className="text-zinc-500">●</span>{" "}
                <span className="text-zinc-500">stash history search</span>{" "}
                <span className="text-zinc-300">&quot;memory leak build gmail calendar&quot;</span>
              </div>
              <div className="pl-3 border-l border-zinc-700 text-zinc-400 space-y-1">
                <div className="text-zinc-500 text-[11px]">Sam&apos;s session from last night (22 events):</div>
                <div>Sam identified 10 build() calls/min from _draft_refresh_loop, not webhooks.</div>
                <div>Sam fixed GmailClient with lazy init + context managers.</div>
                <div>Leak is still active post-fix: CalendarClient has no close() in any path.</div>
              </div>
              <div className="text-zinc-400">
                <span className="text-zinc-500">●</span> Checking Sam&apos;s commit 4bc908f...
              </div>
              <div className="text-zinc-400">
                <span className="text-zinc-500">●</span> Adding __del__ and context managers to CalendarClient across 11 sites
              </div>
              <div className="text-zinc-300 mt-1">
                Done. Sam&apos;s fix covered GmailClient. Applied the same pattern
                to CalendarClient to close the remaining leak.
              </div>
            </div>
            <div className="px-4 pt-2 pb-4 border-t border-zinc-800">
              <div className="text-zinc-600 text-[12px]">
                <span className="text-zinc-500">✱</span> Crunched for 2m 55s
              </div>
            </div>
          </div>
        </div>
      </div>

      <H3>Example: Managing Upwards</H3>
      <P>
        After a long day of working with coding agents, I ask &ldquo;what did I get done
        today?&rdquo;
      </P>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 my-6">
        {/* Without Stash */}
        <div className="rounded-2xl border border-border overflow-hidden flex flex-col">
          <div className="bg-surface px-4 py-2.5 border-b border-border">
            <span className="text-xs font-medium text-muted uppercase tracking-wider">Without Stash</span>
          </div>
          <div className="bg-[#1a1a1a] font-mono text-[12px] leading-[1.7] flex-1 flex flex-col max-h-[280px]">
            <div className="px-4 pt-4 pb-3">
              <span className="text-zinc-500">&gt;</span>{" "}
              <span className="text-zinc-200">What did I get done today?</span>
            </div>
            <div className="px-4 py-1 space-y-3 overflow-y-auto flex-1">
              <div className="text-zinc-400">
                <span className="text-zinc-500">●</span> Reading git log for today&apos;s commits...
              </div>
              <div className="text-zinc-400">
                <span className="text-zinc-500">●</span> Found 6 commits across 3 PRs
              </div>
              <div className="text-zinc-300 mt-1 space-y-1">
                <div>Today you shipped:</div>
                <div className="pl-2 text-zinc-400 space-y-0.5">
                  <div>• Page graph: d3-force stabilization, pan/zoom/drag, hover links</div>
                  <div>• Notebook navigation: browser back/forward, URL sync</div>
                  <div>• ID-based page links with autocomplete</div>
                  <div>• Fixed embedding space click/drag, loading blink</div>
                  <div>• Workspace dropdown separated from workspace-home link</div>
                  <div>• Invite code UX: copied feedback, owner-only rotate</div>
                </div>
              </div>
            </div>
            <div className="px-4 pt-2 pb-4 border-t border-zinc-800">
              <div className="text-zinc-600 text-[12px]">
                <span className="text-zinc-500">✱</span> Sautéed for 8s
              </div>
            </div>
          </div>
        </div>

        {/* With Stash */}
        <div className="rounded-2xl border border-brand/30 overflow-hidden flex flex-col">
          <div className="bg-brand/10 px-4 py-2.5 border-b border-brand/20">
            <span className="text-xs font-medium text-brand uppercase tracking-wider">With Stash</span>
          </div>
          <div className="bg-[#1a1a1a] font-mono text-[12px] leading-[1.7] flex-1 flex flex-col max-h-[280px]">
            <div className="px-4 pt-4 pb-3">
              <span className="text-zinc-500">&gt;</span>{" "}
              <span className="text-zinc-200">What did I get done today?</span>
            </div>
            <div className="px-4 py-1 space-y-3 overflow-y-auto flex-1">
              <div className="text-zinc-400">
                <span className="text-zinc-500">●</span>{" "}
                <span className="text-zinc-500">stash history query</span>{" "}
                <span className="text-zinc-300">--since today</span>
              </div>
              <div className="pl-3 border-l border-zinc-700 text-zinc-400 space-y-1">
                <div className="text-zinc-500 text-[11px]">Found 14 sessions across git, ops, and collaboration</div>
              </div>
              <div className="text-zinc-400">
                <span className="text-zinc-500">●</span> Cross-referencing with git log...
              </div>
              <div className="text-zinc-300 mt-1 space-y-1">
                <div>Today you shipped:</div>
                <div className="pl-2 space-y-0.5">
                  <div className="text-zinc-500 text-[11px] mt-1 mb-0.5">From git:</div>
                  <div className="text-zinc-400">• Page graph: d3-force stabilization, pan/zoom/drag, hover links</div>
                  <div className="text-zinc-400">• Notebook navigation: browser back/forward, URL sync</div>
                  <div className="text-zinc-400">• ID-based page links with autocomplete</div>
                  <div className="text-zinc-400">• Fixed embedding space click/drag, loading blink</div>
                  <div className="text-zinc-400">• Workspace dropdown separated from workspace-home link</div>
                  <div className="text-zinc-400">• Invite code UX: copied feedback, owner-only rotate</div>
                  <div className="text-zinc-500 text-[11px] mt-1 mb-0.5">From stash:</div>
                  <div className="text-zinc-400">• Cleaned up old Render servers in production</div>
                  <div className="text-zinc-400">• Wrote installation docs for new users</div>
                  <div className="text-zinc-400">• Helped sam@joinstash.ai onboard to enterprise</div>
                </div>
              </div>
            </div>
            <div className="px-4 pt-2 pb-4 border-t border-zinc-800">
              <div className="text-zinc-600 text-[12px]">
                <span className="text-zinc-500">✱</span> Crunched for 12s
              </div>
            </div>
          </div>
        </div>
      </div>

      <H3>FAQ</H3>
      <p className="text-[15px] font-semibold text-foreground leading-7 mb-2">Do I have to upload my transcripts?</p>
      <P>
        Transcript upload is opt-in. If you want, you can choose to give your coding agent shared
        access to the repository memory without uploading anything.
      </P>

      <H3>Quick links</H3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 my-4">
        {[
          { href: "/docs/quickstart", label: "Quickstart", desc: "Connect your coding agent and start in 5 minutes." },
          { href: "/docs/concepts", label: "Concepts", desc: "What workspaces, agent names, and history are." },
          { href: "/docs/cli", label: "CLI", desc: "Push events and manage resources from the terminal." },
          { href: "/docs/self-hosting", label: "Self-Hosting", desc: "Run Stash on your own infra with Postgres + pgvector." },
        ].map((l) => (
          <Link
            key={l.href}
            href={l.href}
            className="group rounded-2xl border border-border bg-surface px-5 py-4 hover:border-brand/40 hover:bg-brand/3 transition-colors"
          >
            <div className="text-[14px] font-semibold text-foreground group-hover:text-brand transition-colors mb-1">
              {l.label}
            </div>
            <div className="text-[13px] text-dim">{l.desc}</div>
          </Link>
        ))}
      </div>
    </>
  );
}
