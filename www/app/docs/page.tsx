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
        organizes this information into a categorized wiki — with backlinks, summaries, and semantic search
        so contributor to your repo can find and build on what others have learned.
      </P>

      <H3>Example: Don&apos;t Duplicate Development Efforts</H3>
      <P>
        I&apos;m debugging a tricky memory leak with our API gateway.
      </P>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 my-6">
        <div className="rounded-2xl border border-border bg-surface px-5 py-4">
          <div className="text-xs font-medium text-muted uppercase tracking-wider mb-3">Without Stash</div>
          <ol className="list-decimal pl-5 space-y-1.5 text-[14px] text-dim">
            <li>Try approach A</li>
            <li>Try approach B</li>
            <li>Try approach C</li>
          </ol>
          <div className="mt-3 text-xs text-muted">~10 minutes</div>
        </div>
        <div className="rounded-2xl border border-brand/30 bg-brand/5 px-5 py-4">
          <div className="text-xs font-medium text-brand uppercase tracking-wider mb-3">With Stash</div>
          <ol className="list-decimal pl-5 space-y-1.5 text-[14px] text-dim">
            <li>Check if someone else has worked on this</li>
            <li>Sam tried A, B, and C — none worked. He also learned (1) and (2)</li>
            <li>Proceed with debugging, informed</li>
          </ol>
          <div className="mt-3 text-xs text-muted">~2 minutes</div>
        </div>
      </div>

      <H3>Example: Managing Upwards</H3>
      <P>
        After a long day of working with coding agents, I ask &ldquo;what did I get done
        today?&rdquo;
      </P>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 my-6">
        <div className="rounded-2xl border border-border bg-surface px-5 py-4">
          <div className="text-xs font-medium text-muted uppercase tracking-wider mb-3">Without Stash &middot; 6 items</div>
          <ul className="space-y-1.5 text-[14px] text-dim">
            <li>Page graph: d3-force stabilization, pan/zoom/drag, hover links</li>
            <li>Notebook navigation: browser back/forward, URL sync</li>
            <li>ID-based page links with autocomplete</li>
            <li>Fixed embedding space click/drag, loading blink</li>
            <li>Workspace dropdown separated from workspace-home link</li>
            <li>Invite code UX: copied feedback, owner-only rotate</li>
          </ul>
          <div className="mt-3 text-xs text-muted">Only shows work that landed in Git</div>
        </div>
        <div className="rounded-2xl border border-brand/30 bg-brand/5 px-5 py-4">
          <div className="text-xs font-medium text-brand uppercase tracking-wider mb-3">With Stash &middot; 9 items</div>
          <ul className="space-y-1.5 text-[14px] text-dim">
            <li>Page graph: d3-force stabilization, pan/zoom/drag, hover links</li>
            <li className="font-semibold text-foreground">Cleaned up old Render servers in production</li>
            <li>Notebook navigation: browser back/forward, URL sync</li>
            <li>ID-based page links with autocomplete</li>
            <li>Fixed embedding space click/drag, loading blink</li>
            <li className="font-semibold text-foreground">Wrote installation docs for new users</li>
            <li>Workspace dropdown separated from workspace-home link</li>
            <li className="font-semibold text-foreground">Helped sam@joinstash.ai onboard to enterprise</li>
            <li>Invite code UX: copied feedback, owner-only rotate</li>
          </ul>
          <div className="mt-3 text-xs text-muted">Captures work that never touched Git</div>
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
