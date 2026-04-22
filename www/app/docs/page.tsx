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
        <div className="rounded-xl border border-zinc-200 overflow-hidden flex flex-col shadow-sm">
          <div className="bg-[#e4e4e4] px-4 py-2.5 border-b border-zinc-300 relative flex items-center">
            <div className="flex gap-1.5">
              <span className="w-[10px] h-[10px] rounded-full bg-[#ff5f57]" />
              <span className="w-[10px] h-[10px] rounded-full bg-[#febc2e]" />
              <span className="w-[10px] h-[10px] rounded-full bg-[#28c840]" />
            </div>
            <span className="absolute inset-0 flex items-center justify-center text-[11px] font-medium text-zinc-500">Without Stash</span>
          </div>
          <div className="bg-white font-mono text-[12px] leading-[1.7] flex-1 max-h-[280px] overflow-y-auto">
            <div className="sticky top-0 bg-white z-10 px-4 pt-4 pb-3">
              <span className="text-zinc-400">&gt;</span>{" "}
              <span className="text-zinc-900">Investigate the memory leak with our calendar service</span>
            </div>
            <div className="px-4 py-1 space-y-3">
              <div className="text-zinc-600">
                <span className="text-zinc-400">●</span> Reading server logs and source code...
              </div>
              <div className="text-zinc-600">
                <span className="text-zinc-400">●</span> Found 11 <span className="text-blue-600">CalendarClient</span> creation sites, only 1 has cleanup
              </div>
              <div className="text-zinc-600">
                <span className="text-zinc-400">●</span> Found 10 <span className="text-blue-600">GmailClient</span> creation sites, only 3 have <span className="text-blue-600">close()</span>
              </div>
              <div className="text-zinc-600">
                <span className="text-zinc-400">●</span> Hypothesis: unclosed <span className="text-blue-600">httplib2</span> connections from <span className="text-blue-600">build()</span> calls
              </div>
              <div className="text-zinc-600">
                <span className="text-zinc-400">●</span> Testing whether webhooks or <span className="text-blue-600">_draft_refresh_loop</span> is the source...
              </div>
              <div className="text-zinc-600">
                <span className="text-zinc-400">●</span> Confirmed: <span className="text-blue-600">_draft_refresh_loop</span> creates 10 <span className="text-blue-600">build()</span> calls/min
              </div>
              <div className="text-zinc-800 mt-1">
                The root cause is unclosed <span className="text-blue-600">httplib2</span>+SSL connections. Each <span className="text-blue-600">build()</span> call
                leaks ~100KB. At 2-3/sec over 2 hours = ~1.15GB.
              </div>
            </div>
            <div className="sticky bottom-0 bg-white z-10 px-4 pt-2 pb-4 border-t border-zinc-200">
              <div className="text-zinc-400 text-[12px]">
                <span className="text-zinc-400">✱</span> Sautéed for 12m 42s
              </div>
            </div>
          </div>
        </div>

        {/* With Stash */}
        <div className="rounded-xl border border-zinc-200 overflow-hidden flex flex-col shadow-sm">
          <div className="bg-[#e4e4e4] px-4 py-2.5 border-b border-zinc-300 relative flex items-center">
            <div className="flex gap-1.5">
              <span className="w-[10px] h-[10px] rounded-full bg-[#ff5f57]" />
              <span className="w-[10px] h-[10px] rounded-full bg-[#febc2e]" />
              <span className="w-[10px] h-[10px] rounded-full bg-[#28c840]" />
            </div>
            <span className="absolute inset-0 flex items-center justify-center text-[11px] font-medium text-zinc-500">With Stash</span>
          </div>
          <div className="bg-white font-mono text-[12px] leading-[1.7] flex-1 max-h-[280px] overflow-y-auto">
            <div className="sticky top-0 bg-white z-10 px-4 pt-4 pb-3">
              <span className="text-zinc-400">&gt;</span>{" "}
              <span className="text-zinc-900">Investigate the memory leak with our calendar service</span>
            </div>
            <div className="px-4 py-1 space-y-3">
              <div className="text-zinc-600">
                <span className="text-zinc-400">●</span>{" "}
                <span className="text-zinc-500">stash history search</span>{" "}
                <span className="text-blue-600">&quot;memory leak build gmail calendar&quot;</span>
              </div>
              <div className="pl-3 border-l border-zinc-300 text-zinc-600 space-y-1">
                <div className="text-zinc-400 text-[11px]">Sam&apos;s session from last night (22 events):</div>
                <div>Sam identified 10 <span className="text-blue-600">build()</span> calls/min from <span className="text-blue-600">_draft_refresh_loop</span>, not webhooks.</div>
                <div>Sam fixed <span className="text-blue-600">GmailClient</span> with lazy init + context managers.</div>
                <div>Leak is still active post-fix: <span className="text-blue-600">CalendarClient</span> has no <span className="text-blue-600">close()</span> in any path.</div>
              </div>
              <div className="text-zinc-600">
                <span className="text-zinc-400">●</span> Checking Sam&apos;s commit <span className="text-blue-600">4bc908f</span>...
              </div>
              <div className="text-zinc-600">
                <span className="text-zinc-400">●</span> Adding <span className="text-blue-600">__del__</span> and context managers to <span className="text-blue-600">CalendarClient</span> across 11 sites
              </div>
              <div className="text-zinc-800 mt-1">
                Done. Sam&apos;s fix covered <span className="text-blue-600">GmailClient</span>. Applied the same pattern
                to <span className="text-blue-600">CalendarClient</span> to close the remaining leak.
              </div>
            </div>
            <div className="sticky bottom-0 bg-white z-10 px-4 pt-2 pb-4 border-t border-zinc-200">
              <div className="text-zinc-400 text-[12px]">
                <span className="text-zinc-400">✱</span> Crunched for 2m 55s
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
        <div className="rounded-xl border border-zinc-200 overflow-hidden flex flex-col shadow-sm">
          <div className="bg-[#e4e4e4] px-4 py-2.5 border-b border-zinc-300 relative flex items-center">
            <div className="flex gap-1.5">
              <span className="w-[10px] h-[10px] rounded-full bg-[#ff5f57]" />
              <span className="w-[10px] h-[10px] rounded-full bg-[#febc2e]" />
              <span className="w-[10px] h-[10px] rounded-full bg-[#28c840]" />
            </div>
            <span className="absolute inset-0 flex items-center justify-center text-[11px] font-medium text-zinc-500">Without Stash</span>
          </div>
          <div className="bg-white font-mono text-[12px] leading-[1.7] flex-1 max-h-[280px] overflow-y-auto">
            <div className="sticky top-0 bg-white z-10 px-4 pt-4 pb-3">
              <span className="text-zinc-400">&gt;</span>{" "}
              <span className="text-zinc-900">What did I get done today?</span>
            </div>
            <div className="px-4 py-1 space-y-3">
              <div className="text-zinc-600">
                <span className="text-zinc-400">●</span> Reading git log for today&apos;s commits...
              </div>
              <div className="text-zinc-600">
                <span className="text-zinc-400">●</span> Found 6 commits across 3 PRs
              </div>
              <div className="text-zinc-800 mt-1 space-y-1">
                <div>Today you shipped:</div>
                <div className="pl-2 text-zinc-600 space-y-0.5">
                  <div>• Page graph: d3-force stabilization, pan/zoom/drag, hover links</div>
                  <div>• Notebook navigation: browser back/forward, URL sync</div>
                  <div>• ID-based page links with autocomplete</div>
                  <div>• Fixed embedding space click/drag, loading blink</div>
                  <div>• Workspace dropdown separated from workspace-home link</div>
                  <div>• Invite code UX: copied feedback, owner-only rotate</div>
                </div>
              </div>
            </div>
            <div className="sticky bottom-0 bg-white z-10 px-4 pt-2 pb-4 border-t border-zinc-200">
              <div className="text-zinc-400 text-[12px]">
                <span className="text-zinc-400">✱</span> Sautéed for 8s
              </div>
            </div>
          </div>
        </div>

        {/* With Stash */}
        <div className="rounded-xl border border-zinc-200 overflow-hidden flex flex-col shadow-sm">
          <div className="bg-[#e4e4e4] px-4 py-2.5 border-b border-zinc-300 relative flex items-center">
            <div className="flex gap-1.5">
              <span className="w-[10px] h-[10px] rounded-full bg-[#ff5f57]" />
              <span className="w-[10px] h-[10px] rounded-full bg-[#febc2e]" />
              <span className="w-[10px] h-[10px] rounded-full bg-[#28c840]" />
            </div>
            <span className="absolute inset-0 flex items-center justify-center text-[11px] font-medium text-zinc-500">With Stash</span>
          </div>
          <div className="bg-white font-mono text-[12px] leading-[1.7] flex-1 max-h-[280px] overflow-y-auto">
            <div className="sticky top-0 bg-white z-10 px-4 pt-4 pb-3">
              <span className="text-zinc-400">&gt;</span>{" "}
              <span className="text-zinc-900">What did I get done today?</span>
            </div>
            <div className="px-4 py-1 space-y-3">
              <div className="text-zinc-600">
                <span className="text-zinc-400">●</span>{" "}
                <span className="text-zinc-500">stash history query</span>{" "}
                <span className="text-blue-600">--since today</span>
              </div>
              <div className="pl-3 border-l border-zinc-300 text-zinc-600 space-y-1">
                <div className="text-zinc-400 text-[11px]">Found 14 sessions across git, ops, and collaboration</div>
              </div>
              <div className="text-zinc-600">
                <span className="text-zinc-400">●</span> Cross-referencing with git log...
              </div>
              <div className="text-zinc-800 mt-1 space-y-1">
                <div>Today you shipped:</div>
                <div className="pl-2 space-y-0.5">
                  <div className="text-zinc-400 text-[11px] mt-1 mb-0.5">From git:</div>
                  <div className="text-zinc-600">• Page graph: d3-force stabilization, pan/zoom/drag, hover links</div>
                  <div className="text-zinc-600">• Notebook navigation: browser back/forward, URL sync</div>
                  <div className="text-zinc-600">• ID-based page links with autocomplete</div>
                  <div className="text-zinc-600">• Fixed embedding space click/drag, loading blink</div>
                  <div className="text-zinc-600">• Workspace dropdown separated from workspace-home link</div>
                  <div className="text-zinc-600">• Invite code UX: copied feedback, owner-only rotate</div>
                  <div className="text-zinc-400 text-[11px] mt-1 mb-0.5">From stash:</div>
                  <div className="text-zinc-600">• Cleaned up old Render servers in production</div>
                  <div className="text-zinc-600">• Wrote installation docs for new users</div>
                  <div className="text-zinc-600">• Helped sam@joinstash.ai onboard to enterprise</div>
                </div>
              </div>
            </div>
            <div className="sticky bottom-0 bg-white z-10 px-4 pt-2 pb-4 border-t border-zinc-200">
              <div className="text-zinc-400 text-[12px]">
                <span className="text-zinc-400">✱</span> Crunched for 12s
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
