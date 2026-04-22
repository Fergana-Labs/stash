import { Callout, Code, CodeBlock, CommandRef, H2, P, Title, Subtitle } from "../components";

export default function CLIPage() {
  return (
    <>
      <Title>CLI Reference</Title>
      <Subtitle>
        A command-line interface for managing Stash from your terminal — push history events
        and manage all resources.
      </Subtitle>

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
        description="Open the browser for OAuth sign-in."
      />

      <CommandRef
        command="stash register"
        args="<name>"
        description="Create a new Stash account."
        params={[
          { name: "<name>", type: "string", desc: "Username for the new account.", required: true },
        ]}
      />

      <CommandRef
        command="stash auth"
        args="<url> --api-key <key>"
        description="Store existing credentials for a Stash instance."
        params={[
          { name: "<url>", type: "string", desc: "Base URL of the Stash server.", required: true },
          { name: "--api-key", type: "string", desc: "Your API key.", required: true },
        ]}
      />

      <CommandRef
        command="stash whoami"
        description="Display the currently authenticated user."
      />

      <CommandRef
        command="stash disconnect"
        description="Sign out and clear all stored credentials and config."
      />

      <CommandRef
        command="stash config"
        args="[key] [value]"
        description="View or update a configuration value. Run without arguments to show all config."
        params={[
          { name: "key", type: "string", desc: "Config key to read or write." },
          { name: "value", type: "string", desc: "New value. Omit to read the current value." },
        ]}
      />

      <Callout>
        After <Code>stash connect</Code>, your defaults are stored. You can still override
        any value: e.g. <Code>stash config base_url https://joinstash.ai</Code> or set{" "}
        <Code>STASH_API_KEY</Code> / <Code>STASH_URL</Code> as environment variables for
        CI and scripts.
      </Callout>

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
        description="Create a new notebook."
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
        description="Update the content of a notebook page."
        params={[
          { name: "<notebook_id>", type: "string", desc: "ID of the notebook.", required: true },
          { name: "<page_id>", type: "string", desc: "ID of the page.", required: true },
          { name: "--content", type: "string", desc: "New page content.", required: true },
        ]}
      />

      <H2>History</H2>

      <CommandRef
        command="stash history push"
        args="<content> [--ws ID] [--agent cli] [--type message]"
        description="Push a new event to the workspace history stream."
        params={[
          { name: "<content>", type: "string", desc: "Event content to push.", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
          { name: "--agent", type: "string", desc: 'Agent identifier. Defaults to "cli".' },
          { name: "--type", type: "string", desc: 'Event type. Defaults to "message".' },
        ]}
      />

      <CommandRef
        command="stash history query"
        args="[--ws ID] [--agent X] [--type Y] [-n 50] [--all]"
        description="Query recent history events with optional filters."
        params={[
          { name: "--ws", type: "string", desc: "Workspace ID override." },
          { name: "--agent", type: "string", desc: "Filter by agent identifier." },
          { name: "--type", type: "string", desc: "Filter by event type." },
          { name: "-n", type: "number", desc: "Maximum number of results. Defaults to 50." },
          { name: "--all", type: "flag", desc: "Return all matching events." },
        ]}
      />

      <CommandRef
        command="stash history search"
        args="<query> [--ws ID] [-n 50]"
        description="Full-text search across workspace history."
        params={[
          { name: "<query>", type: "string", desc: "Search query.", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
          { name: "-n", type: "number", desc: "Maximum number of results. Defaults to 50." },
        ]}
      />

      <CommandRef
        command="stash history agents"
        args="[--ws ID]"
        description="List all agents that have pushed events to the workspace."
        params={[
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash history transcript"
        args="<session_id> [--ws ID]"
        description="Retrieve the full transcript for a session."
        params={[
          { name: "<session_id>", type: "string", desc: "ID of the session.", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
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
        description="Create a new table."
        params={[
          { name: "<name>", type: "string", desc: "Name for the table.", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
          { name: "--columns", type: "JSON", desc: "Column definitions as a JSON array." },
        ]}
      />

      <CommandRef
        command="stash tables rows"
        args="<table_id> [--sort COL] [--filter COL]"
        description="Fetch rows from a table with optional sorting and filtering."
        params={[
          { name: "<table_id>", type: "string", desc: "ID of the table.", required: true },
          { name: "--sort", type: "string", desc: "Column name to sort by." },
          { name: "--filter", type: "string", desc: "Column name to filter on." },
        ]}
      />

      <CommandRef
        command="stash tables insert"
        args="<table_id> <data_json>"
        description="Insert a new row into a table."
        params={[
          { name: "<table_id>", type: "string", desc: "ID of the table.", required: true },
          { name: "<data_json>", type: "JSON", desc: "Row data as a JSON object.", required: true },
        ]}
      />

      <CommandRef
        command="stash tables import"
        args="<table_id> <file> [--format csv|json]"
        description="Bulk import rows from a file."
        params={[
          { name: "<table_id>", type: "string", desc: "ID of the table.", required: true },
          { name: "<file>", type: "path", desc: "Path to the import file.", required: true },
          { name: "--format", type: "string", desc: 'File format: "csv" or "json". Auto-detected if omitted.' },
        ]}
      />

      <CommandRef
        command="stash tables export"
        args="<table_id>"
        description="Export all rows from a table."
        params={[
          { name: "<table_id>", type: "string", desc: "ID of the table.", required: true },
        ]}
      />

      <CommandRef
        command="stash tables count"
        args="<table_id>"
        description="Return the row count for a table."
        params={[
          { name: "<table_id>", type: "string", desc: "ID of the table.", required: true },
        ]}
      />

      <CommandRef
        command="stash tables update-row"
        args="<table_id> <row_id> <data_json>"
        description="Update an existing row."
        params={[
          { name: "<table_id>", type: "string", desc: "ID of the table.", required: true },
          { name: "<row_id>", type: "string", desc: "ID of the row to update.", required: true },
          { name: "<data_json>", type: "JSON", desc: "Updated row data as a JSON object.", required: true },
        ]}
      />

      <CommandRef
        command="stash tables delete-row"
        args="<table_id> <row_id>"
        description="Delete a row from a table."
        params={[
          { name: "<table_id>", type: "string", desc: "ID of the table.", required: true },
          { name: "<row_id>", type: "string", desc: "ID of the row to delete.", required: true },
        ]}
      />

      <H2>Files</H2>

      <CommandRef
        command="stash files upload"
        args="<path> [--ws ID]"
        description="Upload a file to the workspace."
        params={[
          { name: "<path>", type: "path", desc: "Path to the file.", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash files list"
        args="[--ws ID]"
        description="List all uploaded files in the workspace."
        params={[
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash files rm"
        args="<file_id>"
        description="Delete an uploaded file."
        params={[
          { name: "<file_id>", type: "string", desc: "ID of the file to delete.", required: true },
        ]}
      />

      <CommandRef
        command="stash files text"
        args="<file_id>"
        description="Extract text content from an uploaded file."
        params={[
          { name: "<file_id>", type: "string", desc: "ID of the file.", required: true },
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
        description="Enable activity streaming for the current repository."
      />

      <CommandRef
        command="stash disable"
        description="Disable activity streaming for the current repository."
      />

      <CommandRef
        command="stash settings"
        description="Open the interactive settings page."
      />
    </>
  );
}
