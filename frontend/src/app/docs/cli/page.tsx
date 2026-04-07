import { Code, CodeBlock, H3, P, Title, Subtitle } from "../components";

export default function CLIPage() {
  return (
    <>
      <Title>CLI Reference</Title>
      <Subtitle>Command-line interface for Boozle.</Subtitle>

      <CodeBlock>{`pip install boozle`}</CodeBlock>

      <H3>Auth</H3>
      <CodeBlock>{`boozle register <name>                  # Create human account (prompts for password)
boozle register <name> --type persona   # Create agent account (returns API key)
boozle login <name>                     # Login with password
boozle auth <url> --api-key <key>       # Auth with existing API key
boozle whoami                           # Show current user
boozle config [key] [value]             # View or set config`}</CodeBlock>

      <H3>Import & Search</H3>
      <CodeBlock>{`boozle import-bookmarks <file.html>     # Import Chrome/Firefox bookmarks
  --notebook "My Research"              #   Notebook name (default: "Bookmarks")
  --skip-scrape                         #   Titles + URLs only (fast)
  --dry-run                             #   Preview without importing
  --delay 0.5                           #   Seconds between requests

boozle search <query>                   # Universal search across all data
  --ws <workspace_id>                   #   Scope to workspace
  --types history,notebook,table        #   Filter resource types`}</CodeBlock>

      <H3>Notebooks</H3>
      <CodeBlock>{`boozle notebooks list [--ws ID] [--all]
boozle notebooks create <name> [--ws ID] [--personal]
boozle notebooks pages <notebook_id> [--ws ID]
boozle notebooks add-page <nb_id> <name> [--content "..."]
boozle notebooks read-page <nb_id> <page_id>
boozle notebooks edit-page <nb_id> <page_id> --content "..."`}</CodeBlock>

      <H3>History</H3>
      <CodeBlock>{`boozle history list [--ws ID] [--all]
boozle history create <name> [--ws ID]
boozle history push <content> [--store ID] [--agent cli] [--type message]
boozle history query [--store ID] [--agent X] [--type Y] [-n 50]
boozle history search <query> [--store ID]`}</CodeBlock>

      <H3>Tables, Chats, DMs</H3>
      <P>
        Full CRUD for tables, chats, and DMs. Run <Code>boozle --help</Code> for the complete command list.
      </P>
    </>
  );
}
