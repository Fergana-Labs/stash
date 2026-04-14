import { Callout, H3, P, Title, Subtitle } from "../components";

export default function WorkspacesPage() {
  return (
    <>
      <Title>Workspaces</Title>
      <Subtitle>
        Permissioned containers for teams. All Octopus resources live inside a workspace.
      </Subtitle>

      <P>
        Create a workspace, invite team members, and everything you
        build — notebooks, chats, history stores, tables, files, pages — is shared and scoped
        to that workspace. Workspaces are isolated: no resource leaks between them.
      </P>

      <H3>Member roles</H3>
      <div className="rounded-2xl border border-border bg-surface divide-y divide-border my-6">
        {[
          { role: "owner", desc: "Full control. Can delete the workspace. Assigned to the creator." },
          { role: "admin", desc: "Manage members, change settings, and invite new users." },
          { role: "member", desc: "Read and write all workspace resources." },
        ].map((r) => (
          <div key={r.role} className="flex gap-5 px-5 py-4">
            <code className="text-brand font-mono text-[13px] w-20 flex-shrink-0">{r.role}</code>
            <p className="text-[14px] text-dim leading-6">{r.desc}</p>
          </div>
        ))}
      </div>

      <H3>Object-level permissions</H3>
      <P>
        Individual objects can override the workspace default. Useful for private research
        or publicly shared pages.
      </P>
      <div className="rounded-2xl border border-border bg-surface divide-y divide-border my-6">
        {[
          { vis: "inherit", desc: "All workspace members have access (default for everything)." },
          { vis: "private", desc: "Only explicitly granted users can see it." },
          { vis: "public", desc: "Anyone can read — no login required." },
        ].map((r) => (
          <div key={r.vis} className="flex gap-5 px-5 py-4">
            <code className="text-brand font-mono text-[13px] w-20 flex-shrink-0">{r.vis}</code>
            <p className="text-[14px] text-dim leading-6">{r.desc}</p>
          </div>
        ))}
      </div>

      <Callout type="tip">
        The curation tool uses <strong>object-level permissions</strong> — it writes
        to a <em>personal</em> notebook (private by default) and only publishes summaries
        to shared workspace notebooks when configured to do so.
      </Callout>

      <H3>Personal resources</H3>
      <P>
        Notebooks, tables, history stores, and files can also exist outside any workspace as
        personal resources. The curation tool writes to the user's personal notebook by default.
        You can query personal resources via the API without specifying a workspace ID.
      </P>
    </>
  );
}
