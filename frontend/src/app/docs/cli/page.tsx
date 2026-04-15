import { Callout, Code, CodeBlock, H3, P, Title, Subtitle } from "../components";

export default function CLIPage() {
  return (
    <>
      <Title>CLI Reference</Title>
      <Subtitle>
        A command-line interface for managing Octopus from your terminal — push history events
        and manage all resources.
      </Subtitle>

      <H3>Install</H3>
      <CodeBlock>{`pip install octopus`}</CodeBlock>

      <H3>First-time setup</H3>
      <P>
        Run the interactive setup wizard. It configures the API endpoint, authenticates you
        (login or register), creates a workspace, and creates a default history store — all in
        one shot. No manual config editing required.
      </P>
      <CodeBlock>{`octopus connect`}</CodeBlock>
      <P>
        The wizard saves everything to <Code>~/.octopus/config.json</Code>. Once complete,
        commands like <Code>octopus history push</Code> work without extra flags.
      </P>

      <H3>Auth commands</H3>
      <CodeBlock>{`octopus login                             # Password login
octopus auth <url> --api-key <key>        # Authenticate using an existing API key
octopus whoami                            # Show the current logged-in user
octopus config [key] [value]              # View or update any config value`}</CodeBlock>

      <Callout>
        After <Code>octopus connect</Code>, your defaults are stored. You can still override
        any value: e.g. <Code>octopus config base_url https://getoctopus.com</Code> or set{" "}
        <Code>OCTOPUS_API_KEY</Code> / <Code>OCTOPUS_URL</Code> as environment variables for
        CI and scripts.
      </Callout>

      <H3>Search</H3>
      <CodeBlock>{`# Universal search across all data types
octopus search <query>
  --ws <workspace_id>          Scope to a workspace
  --types history,notebook,table   Filter by resource type`}</CodeBlock>

      <H3>Notebooks</H3>
      <CodeBlock>{`octopus notebooks list [--ws ID] [--all]
octopus notebooks create <name> [--ws ID] [--personal]
octopus notebooks pages <notebook_id> [--ws ID]
octopus notebooks add-page <nb_id> <name> [--content "..."]
octopus notebooks read-page <nb_id> <page_id>
octopus notebooks edit-page <nb_id> <page_id> --content "..."`}</CodeBlock>

      <H3>History stores</H3>
      <CodeBlock>{`octopus history list [--ws ID] [--all]
octopus history create <name> [--ws ID]
octopus history push <content> [--store ID] [--agent cli] [--type message]
octopus history query [--store ID] [--agent X] [--type Y] [-n 50]
octopus history search <query> [--store ID]`}</CodeBlock>

      <H3>Tables</H3>
      <P>
        Full CRUD for tables is available. Run{" "}
        <Code>octopus --help</Code> for the complete command tree, or{" "}
        <Code>octopus &lt;command&gt; --help</Code> for options on any subcommand.
      </P>
    </>
  );
}
