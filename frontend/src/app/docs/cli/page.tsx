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
      <CodeBlock>{`pip install stashai`}</CodeBlock>

      <H3>First-time setup</H3>
      <P>
        Run the interactive setup wizard. It configures the API endpoint, authenticates you
        (login or register), and creates a workspace — all in one shot. No manual config
        editing required.
      </P>
      <CodeBlock>{`stash connect`}</CodeBlock>
      <P>
        The wizard saves everything to <Code>~/.stash/config.json</Code>. Once complete,
        commands like <Code>stash history push</Code> work without extra flags.
      </P>

      <H3>Auth commands</H3>
      <CodeBlock>{`stash login <name> --password <pw>       # Password login
stash signin                            # Sign in through the browser
stash register <name>                   # Create a new account
stash auth <url> --api-key <key>        # Store existing credentials
stash whoami                            # Show the current logged-in user
stash disconnect                        # Sign out and clear config
stash config [key] [value]              # View or update any config value`}</CodeBlock>

      <Callout>
        After <Code>stash connect</Code>, your defaults are stored. You can still override
        any value: e.g. <Code>stash config base_url https://stash.ac</Code> or set{" "}
        <Code>STASH_API_KEY</Code> / <Code>STASH_URL</Code> as environment variables for
        CI and scripts.
      </Callout>

      <H3>Notebooks</H3>
      <CodeBlock>{`stash notebooks list [--ws ID] [--all]
stash notebooks create <name> [--ws ID] [--personal]
stash notebooks pages <notebook_id> [--ws ID]
stash notebooks add-page <nb_id> <name> [--content "..."]
stash notebooks read-page <nb_id> <page_id>
stash notebooks edit-page <nb_id> <page_id> --content "..."`}</CodeBlock>

      <H3>History</H3>
      <CodeBlock>{`stash history push <content> [--ws ID] [--agent cli] [--type message]
stash history query [--ws ID] [--agent X] [--type Y] [-n 50] [--all]
stash history search <query> [--ws ID] [-n 50]
stash history agents [--ws ID]
stash history transcript <session_id> [--ws ID]`}</CodeBlock>

      <H3>Tables</H3>
      <CodeBlock>{`stash tables list [--ws ID] [--all] [--personal]
stash tables create <name> [--ws ID] [--columns JSON]
stash tables rows <table_id> [--sort COL] [--filter COL]
stash tables insert <table_id> <data_json>
stash tables import <table_id> <file> [--format csv|json]
stash tables export <table_id>
stash tables count <table_id>
stash tables update-row <table_id> <row_id> <data_json>
stash tables delete-row <table_id> <row_id>`}</CodeBlock>

      <H3>Files</H3>
      <CodeBlock>{`stash files upload <path> [--ws ID]
stash files list [--ws ID]
stash files rm <file_id>
stash files text <file_id>`}</CodeBlock>

      <H3>Streaming & hooks</H3>
      <P>
        Install Stash hooks for all supported coding agents on your <Code>$PATH</Code>,
        then enable or disable streaming per repo:
      </P>
      <CodeBlock>{`stash install                           # Install hook plugins
stash enable                            # Enable streaming for this repo
stash disable                           # Disable streaming for this repo
stash settings                          # Interactive settings page`}</CodeBlock>
    </>
  );
}
