import { Callout, Code, CodeBlock, H3, P, Title, Subtitle } from "../components";

export default function CLIPage() {
  return (
    <>
      <Title>CLI Reference</Title>
      <Subtitle>
        A command-line interface for managing Stash from your terminal — push history events
        and manage all resources.
      </Subtitle>

      <H3>Install</H3>
      <CodeBlock>{`pip install stash`}</CodeBlock>

      <H3>First-time setup</H3>
      <P>
        Run the interactive setup wizard. It configures the API endpoint, authenticates you
        (login or register), creates a workspace, and creates a default history store — all in
        one shot. No manual config editing required.
      </P>
      <CodeBlock>{`stash connect`}</CodeBlock>
      <P>
        The wizard saves everything to <Code>~/.stash/config.json</Code>. Once complete,
        commands like <Code>stash history push</Code> work without extra flags.
      </P>

      <H3>Auth commands</H3>
      <CodeBlock>{`stash login                             # Password login
stash auth <url> --api-key <key>        # Authenticate using an existing API key
stash whoami                            # Show the current logged-in user
stash config [key] [value]              # View or update any config value`}</CodeBlock>

      <Callout>
        After <Code>stash connect</Code>, your defaults are stored. You can still override
        any value: e.g. <Code>stash config base_url https://stash.ac</Code> or set{" "}
        <Code>STASH_API_KEY</Code> / <Code>STASH_URL</Code> as environment variables for
        CI and scripts.
      </Callout>

      <H3>Search</H3>
      <CodeBlock>{`# Universal search across all data types
stash search <query>
  --ws <workspace_id>          Scope to a workspace
  --types history,notebook,table   Filter by resource type`}</CodeBlock>

      <H3>Notebooks</H3>
      <CodeBlock>{`stash notebooks list [--ws ID] [--all]
stash notebooks create <name> [--ws ID] [--personal]
stash notebooks pages <notebook_id> [--ws ID]
stash notebooks add-page <nb_id> <name> [--content "..."]
stash notebooks read-page <nb_id> <page_id>
stash notebooks edit-page <nb_id> <page_id> --content "..."`}</CodeBlock>

      <H3>History stores</H3>
      <CodeBlock>{`stash history list [--ws ID] [--all]
stash history create <name> [--ws ID]
stash history push <content> [--store ID] [--agent cli] [--type message]
stash history query [--store ID] [--agent X] [--type Y] [-n 50]
stash history search <query> [--store ID]`}</CodeBlock>

      <H3>Tables</H3>
      <P>
        Full CRUD for tables is available. Run{" "}
        <Code>stash --help</Code> for the complete command tree, or{" "}
        <Code>stash &lt;command&gt; --help</Code> for options on any subcommand.
      </P>
    </>
  );
}
