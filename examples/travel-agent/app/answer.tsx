/**
 * Atlas answers in the markdown a chat model naturally writes — paragraphs,
 * bullet lists, and **bold** for the thing you should notice. Rendered as
 * plain text the asterisks stayed on screen, which is the one thing that stops
 * a chat from looking like a chat.
 *
 * Paragraphs keep their line breaks rather than being reflowed, so a numbered
 * itinerary still reads as a list of lines without needing its own case here.
 */
export function Answer({ text }: { text: string }) {
  return (
    <>
      {paragraphs(text).map((lines, i) =>
        lines.every(isBullet) ? (
          <ul key={i}>
            {lines.map((line, j) => (
              <li key={j}>{inline(line.replace(/^[-*]\s+/, ""))}</li>
            ))}
          </ul>
        ) : (
          <p key={i}>{inline(lines.join("\n"))}</p>
        ),
      )}
    </>
  );
}

function paragraphs(text: string): string[][] {
  return text
    .trim()
    .split(/\n{2,}/)
    .map((block) => block.split("\n").map((line) => line.trim()).filter(Boolean))
    .filter((lines) => lines.length);
}

function isBullet(line: string): boolean {
  return /^[-*]\s+/.test(line);
}

// Odd positions are what sat between the marker pairs — backticks first, so a
// `**` inside a code span stays literal.
function inline(text: string) {
  return text
    .split(/`([^`]+)`/g)
    .flatMap((part, i) => (i % 2 ? <code key={`c${i}`}>{part}</code> : bold(part, i)));
}

function bold(text: string, seed: number) {
  return text
    .split(/\*\*(.+?)\*\*/g)
    .map((part, i) => (i % 2 ? <strong key={`b${seed}-${i}`}>{part}</strong> : part));
}
