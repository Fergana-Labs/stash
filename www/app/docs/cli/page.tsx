import { Callout, Code, CodeBlock, CommandRef, H2, P, Title, Subtitle } from "../components";

export default function CLIPage() {
  return (
    <>
      <Title>CLI Reference</Title>
      <Subtitle>
        A command-line interface for managing Stash from your terminal — push history events
        and manage all resources.
      </Subtitle>

      <Callout type="tip">
        Most commands accept <Code>--json</Code> for machine-readable output
        and <Code>--ws ID</Code> to target a specific workspace.
      </Callout>

      <H2>Install</H2>
      <CodeBlock>{`pip install stashai`}</CodeBlock>

      <H2>First-time setup</H2>
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

      <H2>Authentication</H2>

      <CommandRef
        command="stash login"
        args="<name> --password <pw>"
        description="Authenticate with username and password."
        params={[
          { name: "<name>", type: "string", desc: "Your username.", required: true },
          { name: "--password", type: "string", desc: "Your password.", required: true },
        ]}
      />

      <CommandRef
        command="stash signin"
        args="[--api URL] [--no-browser] [--timeout N]"
        description="Open the browser for OAuth sign-in. Blocks until the user authorizes. Writes credentials on success and auto-selects the default workspace if there is exactly one."
        params={[
          { name: "--api", type: "string", desc: "Stash API base URL. Override for self-hosted deployments. Defaults to https://api.stash.ac." },
          { name: "--page", type: "string", desc: "Sign-in page URL. Defaults to the /connect-token page matching --api." },
          { name: "--no-browser", type: "flag", desc: "Skip auto-opening the browser; just print the URL. Use on SSH or headless machines." },
          { name: "--timeout", type: "number", desc: "Seconds to wait for sign-in. Defaults to 120." },
        ]}
      />

      <CommandRef
        command="stash register"
        args="<name> [--password <pw>]"
        description="Create a new Stash account and store the API key."
        params={[
          { name: "<name>", type: "string", desc: "Username for the new account.", required: true },
          { name: "--password", type: "string", desc: "Password for the account." },
        ]}
      />

      <CommandRef
        command="stash auth"
        args="<base_url> --api-key <key>"
        description="Store existing credentials for a Stash instance."
        params={[
          { name: "<base_url>", type: "string", desc: "Base URL of the Stash server.", required: true },
          { name: "--api-key", type: "string", desc: "Your API key.", required: true },
        ]}
      />

      <CommandRef
        command="stash whoami"
        description="Display the currently authenticated user."
      />

      <CommandRef
        command="stash disconnect"
        description="Sign out and clear all stored credentials so the next stash connect re-onboards."
      />

      <CommandRef
        command="stash config"
        args="[key] [value] [--project]"
        description="View or update a configuration value. Keys: base_url, default_workspace, output_format. Run without arguments to show all config."
        params={[
          { name: "key", type: "string", desc: "Config key to read or write." },
          { name: "value", type: "string", desc: "New value. Omit to read the current value." },
          { name: "--project", type: "flag", desc: "Write to project-level config (.stash/config.json in the repo) instead of user config." },
        ]}
      />

      <Callout>
        After <Code>stash connect</Code>, your defaults are stored. You can still override
        any value: e.g. <Code>stash config base_url https://joinstash.ai</Code> or set{" "}
        <Code>STASH_API_KEY</Code> / <Code>STASH_URL</Code> as environment variables for
        CI and scripts.
      </Callout>

      <H2>Workspaces</H2>

      <CommandRef
        command="stash workspaces list"
        args="[--mine]"
        description="List workspaces you belong to."
        params={[
          { name: "--mine", type: "flag", desc: "Show only workspaces you own." },
        ]}
      />

      <CommandRef
        command="stash workspaces create"
        args="<name> [--description TEXT] [--public]"
        description="Create a new workspace."
        params={[
          { name: "<name>", type: "string", desc: "Name for the workspace.", required: true },
          { name: "--description", type: "string", desc: "Workspace description." },
          { name: "--public", type: "flag", desc: "Make the workspace publicly visible." },
        ]}
      />

      <CommandRef
        command="stash workspaces join"
        args="<invite_code>"
        description="Join a workspace by invite code."
        params={[
          { name: "<invite_code>", type: "string", desc: "Invite code or magic link token.", required: true },
        ]}
      />

      <CommandRef
        command="stash workspaces use"
        args="<workspace> [--scope user|project]"
        description="Set the default workspace for future commands. Accepts a workspace ID or name."
        params={[
          { name: "<workspace>", type: "string", desc: "Workspace ID or name to set as default.", required: true },
          { name: "--scope", type: "string", desc: 'Where to write config: "user" or "project". Defaults to "user".' },
        ]}
      />

      <CommandRef
        command="stash workspaces info"
        args="<workspace_id>"
        description="Show workspace details."
        params={[
          { name: "<workspace_id>", type: "string", desc: "ID of the workspace.", required: true },
        ]}
      />

      <CommandRef
        command="stash workspaces members"
        args="<workspace_id>"
        description="List members of a workspace."
        params={[
          { name: "<workspace_id>", type: "string", desc: "ID of the workspace.", required: true },
        ]}
      />

      <H2>Notebooks</H2>

      <CommandRef
        command="stash notebooks list"
        args="[--ws ID] [--all]"
        description="List notebooks in the current workspace."
        params={[
          { name: "--ws", type: "string", desc: "Workspace ID override." },
          { name: "--all", type: "flag", desc: "Include notebooks from all workspaces." },
        ]}
      />

      <CommandRef
        command="stash notebooks create"
        args="<name> [--ws ID] [--personal]"
        description="Create a new notebook collection."
        params={[
          { name: "<name>", type: "string", desc: "Name for the notebook.", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
          { name: "--personal", type: "flag", desc: "Create as a personal notebook." },
        ]}
      />

      <CommandRef
        command="stash notebooks pages"
        args="<notebook_id> [--ws ID]"
        description="List all pages in a notebook."
        params={[
          { name: "<notebook_id>", type: "string", desc: "ID of the notebook.", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash notebooks add-page"
        args="<notebook_id> <name> [--content '...']"
        description="Add a new page to a notebook."
        params={[
          { name: "<notebook_id>", type: "string", desc: "ID of the notebook.", required: true },
          { name: "<name>", type: "string", desc: "Page title.", required: true },
          { name: "--content", type: "string", desc: "Initial page content." },
        ]}
      />

      <CommandRef
        command="stash notebooks read-page"
        args="<notebook_id> <page_id>"
        description="Read the content of a notebook page."
        params={[
          { name: "<notebook_id>", type: "string", desc: "ID of the notebook.", required: true },
          { name: "<page_id>", type: "string", desc: "ID of the page.", required: true },
        ]}
      />

      <CommandRef
        command="stash notebooks edit-page"
        args="<notebook_id> <page_id> --content '...'"
        description="Update the content of a notebook page. Reads from stdin if --content is not given."
        params={[
          { name: "<notebook_id>", type: "string", desc: "ID of the notebook.", required: true },
          { name: "<page_id>", type: "string", desc: "ID of the page.", required: true },
          { name: "--content", type: "string", desc: "New page content. Reads from stdin if omitted." },
        ]}
      />

      <H2>History</H2>

      <CommandRef
        command="stash history push"
        args="<content> [--agent cli] [--type message] [--session ID] [--attach FILE]"
        description="Push a new event to the workspace history stream."
        params={[
          { name: "<content>", type: "string", desc: "Event content to push.", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
          { name: "--agent", type: "string", desc: 'Agent identifier. Defaults to "cli".' },
          { name: "--type", type: "string", desc: 'Event type. Defaults to "message".' },
          { name: "--session", type: "string", desc: "Session ID to group events under." },
          { name: "--tool", type: "string", desc: "Tool identifier." },
          { name: "--attach", type: "path", desc: "Local file path to upload and attach. Repeatable." },
          { name: "--attach-id", type: "string", desc: "Pre-uploaded file ID to attach. Repeatable." },
        ]}
      />

      <CommandRef
        command="stash history query"
        args="[--agent X] [--type Y] [-n 50] [--all]"
        description="Query recent history events with optional filters."
        params={[
          { name: "--ws", type: "string", desc: "Workspace ID override." },
          { name: "--agent", type: "string", desc: "Filter by agent identifier." },
          { name: "--type", type: "string", desc: "Filter by event type." },
          { name: "-n, --limit", type: "number", desc: "Maximum number of results. Defaults to 50." },
          { name: "--all", type: "flag", desc: "Query across all workspaces." },
        ]}
      />

      <CommandRef
        command="stash history search"
        args="<query> [--ws ID] [-n 50]"
        description="Full-text search across workspace history."
        params={[
          { name: "<query>", type: "string", desc: "Search query.", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
          { name: "-n, --limit", type: "number", desc: "Maximum number of results. Defaults to 50." },
        ]}
      />

      <CommandRef
        command="stash history agents"
        args="[--ws ID]"
        description="List distinct agent names that have logged events in this workspace."
        params={[
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash history transcript"
        args="<session_id> [--ws ID] [--save PATH]"
        description="Fetch a full session transcript and print or save it. Transcripts are stored gzipped on the server and decompressed automatically."
        params={[
          { name: "<session_id>", type: "string", desc: "ID of the session.", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
          { name: "--save", type: "path", desc: "Save the transcript to a file instead of printing." },
        ]}
      />

      <H2>Tables</H2>

      <CommandRef
        command="stash tables list"
        args="[--ws ID] [--all] [--personal]"
        description="List tables in the current workspace."
        params={[
          { name: "--ws", type: "string", desc: "Workspace ID override." },
          { name: "--all", type: "flag", desc: "Include tables from all workspaces." },
          { name: "--personal", type: "flag", desc: "Show only personal tables." },
        ]}
      />

      <CommandRef
        command="stash tables create"
        args="<name> [--ws ID] [--columns JSON]"
        description="Create a new table with optional column definitions."
        params={[
          { name: "<name>", type: "string", desc: "Name for the table.", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
          { name: "--columns", type: "JSON", desc: 'Column definitions as a JSON array of {name, type, options?}.' },
        ]}
      />

      <CommandRef
        command="stash tables update"
        args="<table_id> [--name TEXT] [--description TEXT]"
        description="Update a table's name or description."
        params={[
          { name: "<table_id>", type: "string", desc: "ID of the table.", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
          { name: "--name", type: "string", desc: "New table name." },
          { name: "--description", type: "string", desc: "New table description." },
        ]}
      />

      <CommandRef
        command="stash tables schema"
        args="<table_id>"
        description="Show a table's column schema."
        params={[
          { name: "<table_id>", type: "string", desc: "ID of the table.", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash tables rows"
        args="<table_id> [--sort COL] [--filter COL]"
        description="Fetch rows from a table. Sort and filter accept column names, which are auto-resolved."
        params={[
          { name: "<table_id>", type: "string", desc: "ID of the table.", required: true },
          { name: "--sort", type: "string", desc: "Column name to sort by." },
          { name: "--filter", type: "string", desc: "Column name to filter on." },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash tables insert"
        args="<table_id> <data_json>"
        description="Insert a new row. Data is a JSON object with column names as keys."
        params={[
          { name: "<table_id>", type: "string", desc: "ID of the table.", required: true },
          { name: "<data_json>", type: "JSON", desc: "Row data as a JSON object.", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash tables import"
        args="<table_id> <file> [--format csv|json]"
        description="Bulk import rows from a file. Auto-chunks into batches of 5000. CSV uses the first row as column headers. Supports piping: cat data.csv | stash tables import <id> --format csv."
        params={[
          { name: "<table_id>", type: "string", desc: "ID of the table.", required: true },
          { name: "<file>", type: "path", desc: "Path to the import file.", required: true },
          { name: "--format", type: "string", desc: 'File format: "csv" or "json". Auto-detected if omitted.' },
        ]}
      />

      <CommandRef
        command="stash tables update-row"
        args="<table_id> <row_id> <data_json>"
        description="Update an existing row with a partial merge. Data is a JSON object with column names as keys."
        params={[
          { name: "<table_id>", type: "string", desc: "ID of the table.", required: true },
          { name: "<row_id>", type: "string", desc: "ID of the row to update.", required: true },
          { name: "<data_json>", type: "JSON", desc: "Updated row data as a JSON object.", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash tables delete-row"
        args="<table_id> <row_id>"
        description="Delete a row from a table."
        params={[
          { name: "<table_id>", type: "string", desc: "ID of the table.", required: true },
          { name: "<row_id>", type: "string", desc: "ID of the row to delete.", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash tables add-column"
        args="<table_id> <name> [--type text] [--options TEXT]"
        description="Add a column to a table."
        params={[
          { name: "<table_id>", type: "string", desc: "ID of the table.", required: true },
          { name: "<name>", type: "string", desc: "Column name.", required: true },
          { name: "--type", type: "string", desc: 'Column type. Defaults to "text".' },
          { name: "--options", type: "string", desc: "Comma-separated options for select/multiselect columns." },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash tables delete-column"
        args="<table_id> <column_id>"
        description="Delete a column from a table."
        params={[
          { name: "<table_id>", type: "string", desc: "ID of the table.", required: true },
          { name: "<column_id>", type: "string", desc: "Column ID (col_xxx) or column name.", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash tables count"
        args="<table_id>"
        description="Count rows in a table, optionally with filters."
        params={[
          { name: "<table_id>", type: "string", desc: "ID of the table.", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash tables export"
        args="<table_id>"
        description="Export all rows from a table as CSV."
        params={[
          { name: "<table_id>", type: "string", desc: "ID of the table.", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash tables delete"
        args="<table_id> [-y]"
        description="Delete a table and all its data."
        params={[
          { name: "<table_id>", type: "string", desc: "ID of the table.", required: true },
          { name: "-y, --yes", type: "flag", desc: "Skip confirmation prompt." },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <H2>Files</H2>

      <CommandRef
        command="stash files upload"
        args="<path> [--ws ID]"
        description="Upload a file to a workspace or to your personal files."
        params={[
          { name: "<path>", type: "path", desc: "Path to the file.", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID. Omit to upload as a personal file." },
        ]}
      />

      <CommandRef
        command="stash files list"
        args="[--ws ID]"
        description="List files in a workspace or your personal files."
        params={[
          { name: "--ws", type: "string", desc: "Workspace ID. Omit to list personal files." },
        ]}
      />

      <CommandRef
        command="stash files rm"
        args="<file_id>"
        description="Delete a file."
        params={[
          { name: "<file_id>", type: "string", desc: "ID of the file to delete.", required: true },
        ]}
      />

      <CommandRef
        command="stash files text"
        args="<file_id>"
        description="Print extracted text for a file (PDF, image OCR, or plain text)."
        params={[
          { name: "<file_id>", type: "string", desc: "ID of the file.", required: true },
        ]}
      />

      <H2>Invites</H2>

      <CommandRef
        command="stash invite"
        args="[--ws ID] [--uses N] [--days N]"
        description="Create a magic-link invite — a single-use, TTL-bounded token for zero-friction workspace onboarding."
        params={[
          { name: "--ws", type: "string", desc: "Workspace ID to create the invite for." },
          { name: "--uses", type: "number", desc: "Maximum times the link can be redeemed. Defaults to 1." },
          { name: "--days", type: "number", desc: "Days until the link expires. Defaults to 7." },
        ]}
      />

      <CommandRef
        command="stash invite list"
        args="[--ws ID]"
        description="List active invite tokens for a workspace."
        params={[
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash invite revoke"
        args="<token_id> [--ws ID]"
        description="Revoke an invite token so it can no longer be redeemed."
        params={[
          { name: "<token_id>", type: "string", desc: "ID of the invite token to revoke.", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <H2>Keys</H2>

      <CommandRef
        command="stash keys list"
        description="List your active API keys (one per device / login)."
      />

      <CommandRef
        command="stash keys revoke"
        args="<key_id>"
        description="Revoke an API key by ID. Any device using it will receive a 401 on the next call."
        params={[
          { name: "<key_id>", type: "string", desc: "ID of the key to revoke.", required: true },
        ]}
      />

      <H2>Streaming & hooks</H2>
      <P>
        Install Stash hooks for all supported coding agents on your <Code>$PATH</Code>,
        then enable or disable streaming per repo.
      </P>

      <CommandRef
        command="stash install"
        description="Install hook plugins for all supported coding agents on your PATH."
      />

      <CommandRef
        command="stash enable"
        description="Re-enable activity streaming for the current repository."
      />

      <CommandRef
        command="stash disable"
        description="Stop streaming for this repo without touching the committed manifest."
      />

      <CommandRef
        command="stash settings"
        args="[--json]"
        description="Open the interactive settings page."
        params={[
          { name: "--json", type: "flag", desc: "Print a read-only snapshot of settings instead of opening the interactive page." },
        ]}
      />
    </>
  );
}
