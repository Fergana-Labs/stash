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
        Stash makes it so that every contributor to your repo effectively uses the same coding
        agent, regardless of model, harness, or device.
      </P> 
      <P>
        More concretely, Stash auto-uploads coding
        agent transcripts to a shared store, indexes them,
        and then makes those transcripts accessible to every other coding agent using the repo.

        Every research result, file, and message lands in a shared workspace. Stash
        organizes it into a categorized wiki — with backlinks, summaries, and semantic search
        so contributor to your repo can find and build on what others have learned.
      </P>

      <H3>Example: Don&apos;t Duplicate Development Efforts</H3>
      <P>
        I&apos;m debugging a tricky memory leak with our API gateway. Without Stash, debugging might
        proceed like this:
      </P>
      <ol className="list-decimal pl-6 my-4 space-y-1 text-[15px] text-dim">
        <li>Let me try approach A</li>
        <li>Let me try approach B</li>
        <li>Let me try approach C</li>
      </ol>
      <P>(takes 10 minutes)</P>
      <P>With Stash, debugging will proceed like this:</P>
      <ol className="list-decimal pl-6 my-4 space-y-1 text-[15px] text-dim">
        <li>Let me see if someone else has worked on this</li>
        <li>
          Oh, Sam tried approach A, B, and C and none of them worked. Also, he learned (1) and (2)
        </li>
        <li>Okay, let me proceed with debugging</li>
      </ol>
      <P>(takes 2 minutes)</P>

      <H3>Example: Managing Upwards</H3>
      <P>
        After a long day of working using coding agents, I ask myself &ldquo;what did I get done
        today&rdquo;? To answer this question, I ask Claude Code &ldquo;Can you summarize what we did
        today&rdquo;? Without Stash, we&apos;d see 6 things, each of which got a PR.
      </P>
      <ul className="list-disc pl-6 my-4 space-y-1 text-[15px] text-dim">
        <li>Page graph: d3-force stabilization, pan/zoom/drag, hover links, click fixes</li>
        <li>Notebook navigation: browser back/forward walks reading trail, URL sync</li>
        <li>ID-based page links with autocomplete (Notion-style, dropped WikiLinkNode)</li>
        <li>Fixed embedding space click/drag, agent activity clicks, loading blink</li>
        <li>Workspace dropdown separated from workspace-home link</li>
        <li>Invite code UX: copied feedback, owner-only rotate</li>
      </ul>

      <P>
        With Stash, we see 9 things, because three of my tasks didn&apos;t leave a trace in Git.
      </P>
      <ul className="list-disc pl-6 my-4 space-y-1 text-[15px] text-dim">
        <li>Page graph: d3-force stabilization, pan/zoom/drag, hover links, click fixes</li>
        <li className="font-semibold text-foreground">
          Cleaned up old Render servers in our production workspace
        </li>
        <li>Notebook navigation: browser back/forward walks reading trail, URL sync</li>
        <li>ID-based page links with autocomplete (Notion-style, dropped WikiLinkNode)</li>
        <li>Fixed embedding space click/drag, agent activity clicks, loading blink</li>
        <li className="font-semibold text-foreground">
          Wrote up documentation on how installation works e2e for new users
        </li>
        <li>Workspace dropdown separated from workspace-home link</li>
        <li className="font-semibold text-foreground">
          Helped user sam@joinstash.ai onboard to our enterprise plan
        </li>
        <li>Invite code UX: copied feedback, owner-only rotate</li>
      </ul>

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
