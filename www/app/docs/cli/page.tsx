import { Callout, Code, CodeBlock, CommandRef, H2, P, Title, Subtitle } from "../components";

export default function CLIPage() {
  return (
    <>
      <Title>CLI Reference</Title>
      <Subtitle>
        A command-line interface for managing Stash from your terminal — push session events
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
        commands like <Code>stash sessions push</Code> work without extra flags.
      </P>

      <H2>Virtual filesystem</H2>
      <P>
        Use <Code>stash vfs</Code> when an agent needs to browse Stash through one
        filesystem-shaped interface without mounting anything into the OS. Each
        workspace exposes <Code>files</Code>, <Code>sessions</Code>, <Code>skills</Code>,{" "}
        <Code>tables</Code>, and <Code>sources</Code> — the last surfacing every connected
        integration (Gmail, GitHub, Slack, Jira, …) as read-only documents you can{" "}
        <Code>ls</Code>, <Code>cat</Code>, and <Code>grep</Code>.
      </P>
      <CodeBlock>{`stash vfs ls /
stash vfs "find /workspaces -maxdepth 3 -type f"
stash vfs "rg 'database migration' /workspaces"
stash vfs --cwd "/workspaces/<workspace>/sources" "rg 'incident' ."`}</CodeBlock>
      <CommandRef
        command="stash vfs"
        args={'[--ws ID] [--cwd PATH] "command"'}
        description="Run bash-shaped read and write commands against the virtual Stash tree."
        params={[
          { name: "--ws", type: "string", desc: "Expose one workspace by ID. By default all accessible workspaces are exposed." },
          { name: "--cwd", type: "string", desc: "Virtual working directory. Defaults to /." },
          { name: "command", type: "string", desc: "Bash-shaped command such as ls, find, rg, cat, sed, tee, or redirection." },
        ]}
      />

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
        command="stash settings"
        args="[--json]"
        description="Interactive settings page — change the endpoint, toggle which agents stream, and view config. Pass --json for a read-only snapshot."
        params={[
          { name: "--json", type: "flag", desc: "Print a read-only snapshot instead of the interactive page." },
        ]}
      />

      <Callout>
        After <Code>stash connect</Code>, your defaults are stored. Change the endpoint
        any time from <Code>stash settings</Code>, or set <Code>STASH_API_KEY</Code> /{" "}
        <Code>STASH_URL</Code> as environment variables for CI and scripts.
      </Callout>

      <H2>Files</H2>

      <CommandRef
        command="stash files pages"
        args="[--ws ID] [--all]"
        description="List pages in the current workspace."
        params={[
          { name: "--ws", type: "string", desc: "Workspace ID override." },
          { name: "--all", type: "flag", desc: "Include pages from all workspaces." },
        ]}
      />

      <CommandRef
        command="stash files tree"
        args="[--ws ID]"
        description="Show the folder and page tree for a workspace."
        params={[
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash files create-folder"
        args="<name> [--ws ID] [--parent FOLDER_ID]"
        description="Create a folder in the files."
        params={[
          { name: "<name>", type: "string", desc: "Folder name.", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
          { name: "--parent", type: "string", desc: "Parent folder ID." },
        ]}
      />

      <CommandRef
        command="stash files add-page"
        args="<name> [--ws ID] [--folder FOLDER_ID] [--content '...']"
        description="Add a new page to the files."
        params={[
          { name: "<name>", type: "string", desc: "Page title.", required: true },
          { name: "--folder", type: "string", desc: "Folder ID." },
          { name: "--content", type: "string", desc: "Initial page content." },
        ]}
      />

      <CommandRef
        command="stash files read-page"
        args="<page_id> [--ws ID]"
        description="Read a page."
        params={[
          { name: "<page_id>", type: "string", desc: "ID of the page.", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash files edit-page"
        args="<page_id> [--ws ID] --content '...'"
        description="Update a page. Reads from stdin if --content is not given."
        params={[
          { name: "<page_id>", type: "string", desc: "ID of the page.", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
          { name: "--content", type: "string", desc: "New page content. Reads from stdin if omitted." },
        ]}
      />

      <H2>Sessions</H2>

      <CommandRef
        command="stash sessions push"
        args="<content> [--agent cli] [--type message] [--session ID] [--attach FILE]"
        description="Push a new event to the workspace session stream."
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
        command="stash sessions query"
        args="[--agent X] [--type Y] [-n 50] [--all]"
        description="Query recent session events with optional filters."
        params={[
          { name: "--ws", type: "string", desc: "Workspace ID override." },
          { name: "--agent", type: "string", desc: "Filter by agent identifier." },
          { name: "--type", type: "string", desc: "Filter by event type." },
          { name: "-n, --limit", type: "number", desc: "Maximum number of results. Defaults to 50." },
          { name: "--all", type: "flag", desc: "Query across all workspaces." },
        ]}
      />

      <Callout type="tip">
        To search sessions, use the unified <Code>stash search</Code> with{" "}
        <Code>--source sessions</Code> (see <strong>Sources &amp; search</strong> below). It replaces
        the old per-resource search commands.
      </Callout>

      <CommandRef
        command="stash sessions folders"
        args="[--ws ID]"
        description="List session folders — shareable groupings of sessions."
        params={[
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash sessions new-folder"
        args="<name> [--ws ID]"
        description="Create a session folder."
        params={[
          { name: "<name>", type: "string", desc: "Folder name.", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash sessions agents"
        args="[--ws ID]"
        description="List distinct agent names that have logged events in this workspace."
        params={[
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash sessions transcript"
        args="<session_id> [--ws ID] [--save PATH]"
        description="Fetch a full session transcript and print or save it. Transcripts are stored gzipped on the server and decompressed automatically."
        params={[
          { name: "<session_id>", type: "string", desc: "ID of the session.", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
          { name: "--save", type: "path", desc: "Save the transcript to a file instead of printing." },
        ]}
      />

      <H2>Sources &amp; search</H2>
      <P>
        A <strong>source</strong> is anything the agent can read, exposed as a virtual file
        system: the two native sources — <Code>files</Code> and <Code>sessions</Code> — plus your
        connected sources (GitHub, Google Drive, Gmail, Notion, Slack, Granola). Pick a source like a
        drive, browse it by path, read a document, or search one source — or everything at once.
      </P>

      <CommandRef
        command="stash sources ls"
        args="[--ws ID]"
        description="List every source you can read here: the native files and sessions sources plus your connected sources. Each row prints a source handle to use with the other commands."
        params={[
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash sources add"
        args="<source_type> [--ref REF] [--name NAME]"
        description="Connect a source. Slack and Granola resolve their reference from your connected token; Gmail uses the mailbox email as --ref; the others need a --ref (e.g. a repo 'owner/name')."
        params={[
          { name: "<source_type>", type: "string", desc: "github_repo | google_drive | gmail | notion | slack | granola.", required: true },
          { name: "--ref", type: "string", desc: "External reference, e.g. a repo 'owner/name' or Gmail address." },
          { name: "--name", type: "string", desc: "Display name for the source." },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash sources browse"
        args="<source> [path] [--ws ID]"
        description="List a source's entries like a file system."
        params={[
          { name: "<source>", type: "string", desc: "A source handle from stash sources ls.", required: true },
          { name: "path", type: "string", desc: "Path prefix (connected sources only)." },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash sources read"
        args="<source> <ref> [--ws ID]"
        description="Read one document from a source."
        params={[
          { name: "<source>", type: "string", desc: "A source handle from stash sources ls.", required: true },
          { name: "<ref>", type: "string", desc: "Page id (files), session id (sessions), or document path (connected sources).", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash sources sync"
        args="<source_id> [--ws ID]"
        description="Trigger an immediate re-index of a connected source you own."
        params={[
          { name: "<source_id>", type: "string", desc: "ID of the connected source.", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash sources rm"
        args="<source_id> [--ws ID]"
        description="Disconnect a source you own. Its indexed documents are removed."
        params={[
          { name: "<source_id>", type: "string", desc: "ID of the connected source.", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash search"
        args="<query> [--source HANDLE] [--ws ID] [-n 20]"
        description="Search across everything you can see — files, sessions, and connected sources. Pass --source to scope to one; omit it to search everything."
        params={[
          { name: "<query>", type: "string", desc: "Search query.", required: true },
          { name: "--source", type: "string", desc: "Scope to one source handle (from stash sources ls). Omit to search everything." },
          { name: "-n, --limit", type: "number", desc: "Maximum number of results. Defaults to 20." },
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

      <H2>Uploaded Files</H2>

      <CommandRef
        command="stash upload"
        args="<path> [--skill TITLE] [--ws ID]"
        description="Upload a single file (Markdown/HTML become pages, everything else a binary file) or a folder into a workspace. Pass --skill to also bundle it into a shareable Skill."
        params={[
          { name: "<path>", type: "path", desc: "File or directory to upload.", required: true },
          { name: "--skill", type: "string", desc: "Also publish the upload as a Skill with this title." },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
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
        command="stash files text"
        args="<file_id>"
        description="Print extracted text for a file (PDF, image OCR, or plain text)."
        params={[
          { name: "<file_id>", type: "string", desc: "ID of the file.", required: true },
        ]}
      />

      <H2>Object operations</H2>
      <P>
        One set of verbs across every object type. Pass items as{" "}
        <Code>type:id</Code> tokens (e.g. <Code>page:abc</Code>, <Code>file:def</Code>,{" "}
        <Code>session:ghi</Code>); each verb accepts several at once.
      </P>

      <CommandRef
        command="stash rm"
        args="<type:id>... [--permanent] [--ws ID]"
        description="Move pages, files, or sessions to trash. Pass --permanent to skip the trash window and delete immediately."
        params={[
          { name: "<type:id>", type: "string", desc: "Items to delete, e.g. page:<id> session:<id>.", required: true },
          { name: "--permanent", type: "flag", desc: "Delete immediately instead of trashing." },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash restore"
        args="<type:id>... [--ws ID]"
        description="Restore pages, files, or sessions from trash."
        params={[
          { name: "<type:id>", type: "string", desc: "Items to restore, e.g. page:<id> file:<id>.", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash mv"
        args="<type:id>... (--to-folder ID | --to-root) [--ws ID]"
        description="Move pages, files, folders, tables, or sessions into a folder, or to the workspace root."
        params={[
          { name: "<type:id>", type: "string", desc: "Items to move.", required: true },
          { name: "--to-folder", type: "string", desc: "Target folder id." },
          { name: "--to-root", type: "flag", desc: "Move to the workspace root." },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash cp"
        args="<type:id>... [--to-folder ID] [--ws ID]"
        description="Duplicate pages, files, or folders as 'Copy of <name>'."
        params={[
          { name: "<type:id>", type: "string", desc: "Items to copy.", required: true },
          { name: "--to-folder", type: "string", desc: "Target folder id for the copies." },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <H2>Skills</H2>
      <P>
        A <strong>Skill</strong> is a special folder — one containing a <Code>SKILL.md</Code> —
        of pages, files, and tables. Publishing a skill makes it publicly readable at its link (optionally listed
        in Discover); to share privately with a specific person, share its folder
        like any other folder. (The <Code>stash</Code> CLI name is unchanged.)
      </P>

      <CommandRef
        command="stash skills list"
        args="[--ws ID]"
        description="List Skills in the workspace."
        params={[
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash skills create"
        args="<name> [--public] [--discover]"
        description="Create a skill: a folder with a SKILL.md template. Pass --public to publish immediately."
        params={[
          { name: "<name>", type: "string", desc: "Skill name (becomes the folder name).", required: true },
          { name: "--public", type: "flag", desc: "Publish immediately and mint a shareable link." },
          { name: "--discover", type: "flag", desc: "List the public Skill in the Discover catalog (requires --public)." },
          { name: "--workspace", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash skills publish"
        args="<folder_id> [--discover]"
        description="Publish an existing skill folder: mint its share record and print the public URL."
        params={[
          { name: "<folder_id>", type: "string", desc: "The skill folder to publish.", required: true },
          { name: "--discover", type: "flag", desc: "List the public Skill in Discover." },
        ]}
      />

      <CommandRef
        command="stash skills snapshot-source"
        args="<skill_id> --source ID --path PATH [--ws ID]"
        description="Copy a point-in-time snapshot of one connected-source document into the Skill as a page, so the skill stays self-contained."
        params={[
          { name: "<skill_id>", type: "string", desc: "ID of the Skill.", required: true },
          { name: "--source", type: "string", desc: "Connected-source id (from stash sources ls).", required: true },
          { name: "--path", type: "string", desc: "Document path within the source.", required: true },
          { name: "--ws", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash skills fork"
        args="<slug> [--workspace ID]"
        description="Fork a public Skill: deep-copy its folder into your workspace."
        params={[
          { name: "<slug>", type: "string", desc: "Public Skill slug.", required: true },
          { name: "--workspace", type: "string", desc: "Workspace ID override." },
        ]}
      />

      <CommandRef
        command="stash skills unpublish"
        args="<skill_id>"
        description="Stop sharing a Skill: delete its publish record. The folder stays."
        params={[
          { name: "<skill_id>", type: "string", desc: "ID of the published Skill.", required: true },
        ]}
      />

      <H2>Shares</H2>
      <P>
        Share a single object — a folder, page, file, session, or table — with a specific person by
        email. If they don&apos;t have an account yet the share is recorded as pending and converts
        when they sign up. (To share a whole folder of related work, convert it to a <strong>Skill</strong>.)
      </P>

      <CommandRef
        command="stash shares ls"
        args="<object_type> <object_id>"
        description="List who an object is shared with."
        params={[
          { name: "<object_type>", type: "string", desc: "folder | page | file | session | table.", required: true },
          { name: "<object_id>", type: "string", desc: "ID of the object.", required: true },
        ]}
      />

      <CommandRef
        command="stash shares add"
        args="<object_type> <object_id> <email> [--permission read]"
        description="Share an object with a person by email."
        params={[
          { name: "<object_type>", type: "string", desc: "folder | page | file | session | table.", required: true },
          { name: "<object_id>", type: "string", desc: "ID of the object.", required: true },
          { name: "<email>", type: "string", desc: "Recipient email (pending until they sign up).", required: true },
          { name: "--permission", type: "string", desc: "read | write | admin. Defaults to read." },
        ]}
      />

      <CommandRef
        command="stash shares rm"
        args="<object_type> <object_id> <principal_id> [--principal-type user]"
        description="Revoke a person's access to an object."
        params={[
          { name: "<object_type>", type: "string", desc: "folder | page | file | session | table.", required: true },
          { name: "<object_id>", type: "string", desc: "ID of the object.", required: true },
          { name: "<principal_id>", type: "string", desc: "The user id to revoke (from stash shares ls).", required: true },
          { name: "--principal-type", type: "string", desc: 'Principal kind. Defaults to "user".' },
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
