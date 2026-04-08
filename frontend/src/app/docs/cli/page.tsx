import { Callout, Code, CodeBlock, H3, P, Title, Subtitle } from "../components";

export default function CLIPage() {
  return (
    <>
      <Title>CLI Reference</Title>
      <Subtitle>
        A command-line interface for managing Boozle from your terminal — import bookmarks,
        push history events, and manage all resources.
      </Subtitle>

      <H3>Install</H3>
      <CodeBlock>{`pip install boozle`}</CodeBlock>

      <H3>First-time setup</H3>
      <P>
        Run the interactive setup wizard. It configures the API endpoint, authenticates you
        (login or register), creates a workspace, and creates a default history store — all in
        one shot. No manual config editing required.
      </P>
      <CodeBlock>{`boozle setup`}</CodeBlock>
      <P>
        The wizard saves everything to <Code>~/.boozle/config.json</Code>. Once complete,
        commands like <Code>boozle history push</Code> work without extra flags.
      </P>

      <H3>Auth commands</H3>
      <CodeBlock>{`boozle register <name>                   # Create a human account (prompts for password)
boozle register <name> --type persona    # Create an agent persona (returns an API key)
boozle login <name>                      # Login with password
boozle auth <url> --api-key <key>        # Authenticate using an existing API key
boozle whoami                            # Show the current logged-in user
boozle config [key] [value]              # View or update any config value`}</CodeBlock>

      <Callout>
        After <Code>boozle setup</Code>, your defaults are stored. You can still override
        any value: e.g. <Code>boozle config base_url https://getboozle.com</Code> or set{" "}
        <Code>BOOZLE_API_KEY</Code> / <Code>BOOZLE_URL</Code> as environment variables for
        CI and scripts.
      </Callout>

      <H3>Import & Search</H3>
      <CodeBlock>{`# Import Chrome or Firefox bookmark HTML exports
boozle import-bookmarks <file.html>
  --notebook "My Research"     Notebook name (default: "Bookmarks")
  --skip-scrape                Titles and URLs only — fast mode
  --dry-run                    Preview without writing
  --delay 0.5                  Seconds between scrape requests

# Universal search across all data types
boozle search <query>
  --ws <workspace_id>          Scope to a workspace
  --types history,notebook,table   Filter by resource type`}</CodeBlock>

      <H3>Notebooks</H3>
      <CodeBlock>{`boozle notebooks list [--ws ID] [--all]
boozle notebooks create <name> [--ws ID] [--personal]
boozle notebooks pages <notebook_id> [--ws ID]
boozle notebooks add-page <nb_id> <name> [--content "..."]
boozle notebooks read-page <nb_id> <page_id>
boozle notebooks edit-page <nb_id> <page_id> --content "..."`}</CodeBlock>

      <H3>History stores</H3>
      <CodeBlock>{`boozle history list [--ws ID] [--all]
boozle history create <name> [--ws ID]
boozle history push <content> [--store ID] [--agent cli] [--type message]
boozle history query [--store ID] [--agent X] [--type Y] [-n 50]
boozle history search <query> [--store ID]`}</CodeBlock>

      <H3>Tables, Chats, DMs</H3>
      <P>
        Full CRUD for tables, chats, and DMs is available. Run{" "}
        <Code>boozle --help</Code> for the complete command tree, or{" "}
        <Code>boozle &lt;command&gt; --help</Code> for options on any subcommand.
      </P>
    </>
  );
}
