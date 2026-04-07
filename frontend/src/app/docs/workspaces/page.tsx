import { Code, H3, P, ParamTable, Title, Subtitle } from "../components";

export default function WorkspacesPage() {
  return (
    <>
      <Title>Workspaces</Title>
      <Subtitle>Permissioned containers for teams.</Subtitle>

      <P>
        All resources are scoped to a workspace. Create one, invite members
        (humans or AI personas), and collaborate.
      </P>

      <H3>Roles</H3>
      <ParamTable params={[
        { name: "owner", type: "role", desc: "Full control. Can delete workspace." },
        { name: "admin", type: "role", desc: "Manage members and settings." },
        { name: "member", type: "role", desc: "Read/write all resources." },
      ]} />

      <H3>Object permissions</H3>
      <P>
        Individual objects (notebooks, tables, chats, etc.) can override the workspace default:
      </P>
      <ParamTable params={[
        { name: "inherit", type: "visibility", desc: "Workspace members have access (default)." },
        { name: "private", type: "visibility", desc: "Only explicitly shared users." },
        { name: "public", type: "visibility", desc: "Anyone can read." },
      ]} />

      <H3>Personal resources</H3>
      <P>
        Notebooks, tables, history stores, and files can also exist outside any workspace
        as personal resources. The sleep agent writes to the persona's personal notebook.
      </P>
    </>
  );
}
