import { Callout, CodeTabs, CodeBlock, H3, P, Title, Subtitle } from "../components";

export default function QuickstartPage() {
  return (
    <>
      <Title>Quickstart</Title>
      <Subtitle>Three commands to import your bookmarks and start searching.</Subtitle>

      <H3>CLI (recommended)</H3>
      <CodeTabs tabs={[
        { label: "Install + Import", code: "pip install boozle\nboozle register yourname\nboozle import-bookmarks ~/Downloads/bookmarks.html" },
        { label: "Search", code: 'boozle search "that article about transformer architectures"' },
      ]} />
      <P>
        Your bookmarks are scraped (web articles, YouTube transcripts, PDFs) and stored as
        notebook pages. The sleep agent curates them into a categorized wiki overnight.
      </P>

      <H3>Claude Code (MCP)</H3>
      <CodeTabs tabs={[
        { label: "Setup", code: "claude mcp add boozle -- boozle mcp" },
        { label: "Environment", code: "export BOOZLE_API_KEY=your_api_key\nexport BOOZLE_URL=https://getboozle.com" },
      ]} />

      <Callout>
        Once connected, Claude Code can read and write to your knowledge base during sessions.
        Every conversation accumulates as searchable knowledge.
      </Callout>

      <H3>Web</H3>
      <P>
        Sign up at <a href="https://getboozle.com" className="text-brand underline">getboozle.com</a> and
        start using notebooks, search, and chats from the browser.
      </P>
    </>
  );
}
