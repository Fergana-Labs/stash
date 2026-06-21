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
        Most commands accept <Code>--json</Code> for machine-readable output.
      </Callout>

      <H2>Install</H2>
      <CodeBlock>{`pip install stashai`}</CodeBlock>

      <H2>First-time setup</H2>
      <P>
        Run the interactive setup wizard. It configures the API endpoint, authenticates you
        through the browser, and sets up your Stash — all in one shot. No manual config
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
        filesystem-shaped interface without mounting anything into the OS. Your Stash
        exposes <Code>files</Code>, <Code>sessions</Code>, <Code>skills</Code>,{" "}
        <Code>tables</Code>, and <Code>sources</Code> — the last surfacing every connected
        integration (Gmail, GitHub, Slack, Jira, …) as read-only documents you can{" "}
        <Code>ls</Code>, <Code>cat</Code>, and <Code>grep</Code>.
      </P>
      <CodeBlock>{`stash vfs ls /
stash vfs "find /me -maxdepth 3 -type f"
stash vfs "rg 'database migration' /me"
stash vfs --cwd "/me/sources" "rg 'incident' ."`}</CodeBlock>
      <CommandRef
        command="stash vfs"
        args={'[--cwd PATH] "command"'}
        description="Run bash-shaped read and write commands against the virtual Stash tree."
        params={[
          { name: "--cwd", type: "string", desc: "Virtual working directory. Defaults to /." },
          { name: "command", type: "string", desc: "Bash-shaped command such as ls, find, rg, cat, sed, tee, or redirection." },
        ]}
      />

      <H2>Authentication</H2>

      <CommandRef
        command="stash signin"
        args=""
        description="Authenticate this machine through the browser. On first run it also picks the endpoint (managed or self-host) and offers to install streaming hooks for your coding agents. On SSH/headless it prints a URL to open instead of launching a browser."
        params={[]}
      />

      <CommandRef
        command="stash auth"
        args="<base_url> --api-key <key>"
        description="Niche tool — not part of normal setup; use signin. Stores a pre-existing API key into ~/.stash/config.json for an unattended, browser-less machine (typically a self-hosted CI runner or server), so its streaming hooks can authenticate. Get the key from your self-hosted instance's API-key page."
        params={[
          { name: "<base_url>", type: "string", desc: "Base URL of the Stash server.", required: true },
          { name: "--api-key", type: "string", desc: "A pre-existing API key from your self-hosted instance.", required: true },
        ]}
      />

      <Callout>
        Setting <Code>STASH_API_KEY</Code> / <Code>STASH_URL</Code> in the environment
        authenticates <em>CLI commands</em> for CI and scripts — but it does{" "}
        <strong>not</strong> reach the streaming hooks, which read{" "}
        <Code>~/.stash/config.json</Code>. To make an unattended machine stream, use{" "}
        <Code>stash auth</Code>. Change the endpoint or streaming agents later from{" "}
        <Code>stash settings</Code>.
      </Callout>

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
        args=""
        description="List pages in your Stash."
        params={[]}
      />

      <CommandRef
        command="stash files tree"
        args=""
        description="Show the folder and page tree for your Stash."
        params={[]}
      />

      <CommandRef
        command="stash files create-folder"
        args="<name> [--parent FOLDER_ID]"
        description="Create a folder in the files."
        params={[
          { name: "<name>", type: "string", desc: "Folder name.", required: true },
          { name: "--parent", type: "string", desc: "Parent folder ID." },
        ]}
      />

      <CommandRef
        command="stash files add-page"
        args="<name> [--folder FOLDER_ID] [--content '...']"
        description="Add a new page to the files."
        params={[
          { name: "<name>", type: "string", desc: "Page title.", required: true },
          { name: "--folder", type: "string", desc: "Folder ID." },
          { name: "--content", type: "string", desc: "Initial page content." },
        ]}
      />

      <CommandRef
        command="stash files read-page"
        args="<page_id>"
        description="Read a page."
        params={[
          { name: "<page_id>", type: "string", desc: "ID of the page.", required: true },
        ]}
      />

      <CommandRef
        command="stash files edit-page"
        args="<page_id> --content '...'"
        description="Update a page. Reads from stdin if --content is not given."
        params={[
          { name: "<page_id>", type: "string", desc: "ID of the page.", required: true },
          { name: "--content", type: "string", desc: "New page content. Reads from stdin if omitted." },
        ]}
      />

      <H2>Sessions</H2>

      <CommandRef
        command="stash sessions push"
        args="<content> [--agent cli] [--type message] [--session ID] [--attach FILE]"
        description="Push a new event to your session stream."
        params={[
          { name: "<content>", type: "string", desc: "Event content to push.", required: true },
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
        args="[--agent X] [--type Y] [-n 50]"
        description="Query recent session events with optional filters."
        params={[
          { name: "--agent", type: "string", desc: "Filter by agent identifier." },
          { name: "--type", type: "string", desc: "Filter by event type." },
          { name: "-n, --limit", type: "number", desc: "Maximum number of results. Defaults to 50." },
        ]}
      />

      <Callout type="tip">
        To search sessions, use the unified <Code>stash search</Code> with{" "}
        <Code>--source sessions</Code> (see <strong>Sources &amp; search</strong> below). It replaces
        the old per-resource search commands.
      </Callout>

      <CommandRef
        command="stash sessions folders"
        args=""
        description="List session folders — shareable groupings of sessions."
        params={[]}
      />

      <CommandRef
        command="stash sessions new-folder"
        args="<name>"
        description="Create a session folder."
        params={[
          { name: "<name>", type: "string", desc: "Folder name.", required: true },
        ]}
      />

      <CommandRef
        command="stash sessions agents"
        args=""
        description="List distinct agent names that have logged events in your Stash."
        params={[]}
      />

      <CommandRef
        command="stash sessions transcript"
        args="<session_id> [--save PATH]"
        description="Fetch a full session transcript and print or save it. Transcripts are stored gzipped on the server and decompressed automatically."
        params={[
          { name: "<session_id>", type: "string", desc: "ID of the session.", required: true },
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
        args=""
        description="List every source you can read here: the native files and sessions sources plus your connected sources. Each row prints a source handle to use with the other commands."
        params={[]}
      />

      <CommandRef
        command="stash sources add"
        args="<source_type> [--ref REF] [--name NAME]"
        description="Connect a source. Slack and Granola resolve their reference from your connected token; Gmail uses the mailbox email as --ref; the others need a --ref (e.g. a repo 'owner/name')."
        params={[
          { name: "<source_type>", type: "string", desc: "github_repo | google_drive | gmail | notion | slack | granola.", required: true },
          { name: "--ref", type: "string", desc: "External reference, e.g. a repo 'owner/name' or Gmail address." },
          { name: "--name", type: "string", desc: "Display name for the source." },
        ]}
      />

      <CommandRef
        command="stash sources browse"
        args="<source> [path]"
        description="List a source's entries like a file system."
        params={[
          { name: "<source>", type: "string", desc: "A source handle from stash sources ls.", required: true },
          { name: "path", type: "string", desc: "Path prefix (connected sources only)." },
        ]}
      />

      <CommandRef
        command="stash sources read"
        args="<source> <ref>"
        description="Read one document from a source."
        params={[
          { name: "<source>", type: "string", desc: "A source handle from stash sources ls.", required: true },
          { name: "<ref>", type: "string", desc: "Page id (files), session id (sessions), or document path (connected sources).", required: true },
        ]}
      />

      <CommandRef
        command="stash sources sync"
        args="<source_id>"
        description="Trigger an immediate re-index of a connected source you own."
        params={[
          { name: "<source_id>", type: "string", desc: "ID of the connected source.", required: true },
        ]}
      />

      <CommandRef
        command="stash sources rm"
        args="<source_id>"
        description="Disconnect a source you own. Its indexed documents are removed."
        params={[
          { name: "<source_id>", type: "string", desc: "ID of the connected source.", required: true },
        ]}
      />

      <CommandRef
        command="stash search"
        args="<query> [--source HANDLE] [-n 20]"
        description="Search across everything you can see — files, sessions, and connected sources. Pass --source to scope to one; omit it to search everything."
        params={[
          { name: "<query>", type: "string", desc: "Search query.", required: true },
          { name: "--source", type: "string", desc: "Scope to one source handle (from stash sources ls). Omit to search everything." },
          { name: "-n, --limit", type: "number", desc: "Maximum number of results. Defaults to 20." },
        ]}
      />

      <H2>Tables</H2>

      <CommandRef
        command="stash tables list"
        args=""
        description="List tables in your Stash."
        params={[]}
      />

      <CommandRef
        command="stash tables create"
        args="<name> [--columns JSON]"
        description="Create a new table with optional column definitions."
        params={[
          { name: "<name>", type: "string", desc: "Name for the table.", required: true },
          { name: "--columns", type: "JSON", desc: 'Column definitions as a JSON array of {name, type, options?}.' },
        ]}
      />

      <CommandRef
        command="stash tables update"
        args="<table_id> [--name TEXT] [--description TEXT]"
        description="Update a table's name or description."
        params={[
          { name: "<table_id>", type: "string", desc: "ID of the table.", required: true },
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
        ]}
      />

      <CommandRef
        command="stash tables insert"
        args="<table_id> <data_json>"
        description="Insert a new row. Data is a JSON object with column names as keys."
        params={[
          { name: "<table_id>", type: "string", desc: "ID of the table.", required: true },
          { name: "<data_json>", type: "JSON", desc: "Row data as a JSON object.", required: true },
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

      <CommandRef
        command="stash tables add-column"
        args="<table_id> <name> [--type text] [--options TEXT]"
        description="Add a column to a table."
        params={[
          { name: "<table_id>", type: "string", desc: "ID of the table.", required: true },
          { name: "<name>", type: "string", desc: "Column name.", required: true },
          { name: "--type", type: "string", desc: 'Column type. Defaults to "text".' },
          { name: "--options", type: "string", desc: "Comma-separated options for select/multiselect columns." },
        ]}
      />

      <CommandRef
        command="stash tables delete-column"
        args="<table_id> <column_id>"
        description="Delete a column from a table."
        params={[
          { name: "<table_id>", type: "string", desc: "ID of the table.", required: true },
          { name: "<column_id>", type: "string", desc: "Column ID (col_xxx) or column name.", required: true },
        ]}
      />

      <CommandRef
        command="stash tables count"
        args="<table_id>"
        description="Count rows in a table, optionally with filters."
        params={[
          { name: "<table_id>", type: "string", desc: "ID of the table.", required: true },
        ]}
      />

      <CommandRef
        command="stash tables export"
        args="<table_id>"
        description="Export all rows from a table as CSV."
        params={[
          { name: "<table_id>", type: "string", desc: "ID of the table.", required: true },
        ]}
      />

      <CommandRef
        command="stash tables delete"
        args="<table_id> [-y]"
        description="Delete a table and all its data."
        params={[
          { name: "<table_id>", type: "string", desc: "ID of the table.", required: true },
          { name: "-y, --yes", type: "flag", desc: "Skip confirmation prompt." },
        ]}
      />

      <H2>Uploaded Files</H2>

      <CommandRef
        command="stash upload"
        args="<path> [--skill TITLE]"
        description="Upload a single file (Markdown/HTML become pages, everything else a binary file) or a folder into your Stash. Pass --skill to also bundle it into a shareable Skill."
        params={[
          { name: "<path>", type: "path", desc: "File or directory to upload.", required: true },
          { name: "--skill", type: "string", desc: "Also publish the upload as a Skill with this title." },
        ]}
      />

      <CommandRef
        command="stash files list"
        args=""
        description="List your files."
        params={[]}
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
        args="<type:id>... [--permanent]"
        description="Move pages, files, or sessions to trash. Pass --permanent to skip the trash window and delete immediately."
        params={[
          { name: "<type:id>", type: "string", desc: "Items to delete, e.g. page:<id> session:<id>.", required: true },
          { name: "--permanent", type: "flag", desc: "Delete immediately instead of trashing." },
        ]}
      />

      <CommandRef
        command="stash restore"
        args="<type:id>..."
        description="Restore pages, files, or sessions from trash."
        params={[
          { name: "<type:id>", type: "string", desc: "Items to restore, e.g. page:<id> file:<id>.", required: true },
        ]}
      />

      <CommandRef
        command="stash mv"
        args="<type:id>... (--to-folder ID | --to-root)"
        description="Move pages, files, folders, tables, or sessions into a folder, or to the root."
        params={[
          { name: "<type:id>", type: "string", desc: "Items to move.", required: true },
          { name: "--to-folder", type: "string", desc: "Target folder id." },
          { name: "--to-root", type: "flag", desc: "Move to the root." },
        ]}
      />

      <CommandRef
        command="stash cp"
        args="<type:id>... [--to-folder ID]"
        description="Duplicate pages, files, or folders as 'Copy of <name>'."
        params={[
          { name: "<type:id>", type: "string", desc: "Items to copy.", required: true },
          { name: "--to-folder", type: "string", desc: "Target folder id for the copies." },
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
        args=""
        description="List Skills in your Stash."
        params={[]}
      />

      <CommandRef
        command="stash skills create"
        args="<name> [--public] [--discover]"
        description="Create a skill: a folder with a SKILL.md template. Pass --public to publish immediately."
        params={[
          { name: "<name>", type: "string", desc: "Skill name (becomes the folder name).", required: true },
          { name: "--public", type: "flag", desc: "Publish immediately and mint a shareable link." },
          { name: "--discover", type: "flag", desc: "List the public Skill in the Discover catalog (requires --public)." },
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
        args="<skill_id> --source ID --path PATH"
        description="Copy a point-in-time snapshot of one connected-source document into the Skill as a page, so the skill stays self-contained."
        params={[
          { name: "<skill_id>", type: "string", desc: "ID of the Skill.", required: true },
          { name: "--source", type: "string", desc: "Connected-source id (from stash sources ls).", required: true },
          { name: "--path", type: "string", desc: "Document path within the source.", required: true },
        ]}
      />

      <CommandRef
        command="stash skills fork"
        args="<slug>"
        description="Fork a public Skill: deep-copy its folder into your Stash."
        params={[
          { name: "<slug>", type: "string", desc: "Public Skill slug.", required: true },
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
