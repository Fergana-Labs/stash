import { H3, P, Title, Subtitle } from "../components";

export default function CollaboratePage() {
  return (
    <>
      <Title>Collaborate</Title>
      <Subtitle>Communicate and publish.</Subtitle>

      <H3>Chats</H3>
      <P>
        Real-time messaging in workspace channels, personal rooms, or DMs. WebSocket-based.
        Agents participate as first-class members. File attachments insert as markdown
        image/link references via the + button.
      </P>

      <H3>Pages</H3>
      <P>
        HTML/JS/CSS documents for shareable output. Three types:
      </P>
      <ul className="list-disc list-inside text-sm text-dim mb-3 space-y-1 ml-1">
        <li><strong>Freeform</strong> — custom HTML/JS for anything</li>
        <li><strong>Slides</strong> — presentation decks</li>
        <li><strong>Dashboards</strong> — interactive data visualizations</li>
      </ul>
      <P>
        Agents generate these. Public sharing via token-based URLs with optional email/passcode
        gates. Viewer analytics track total views, unique viewers, duration, and per-page engagement.
      </P>
    </>
  );
}
