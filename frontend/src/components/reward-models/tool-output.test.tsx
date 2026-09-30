import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import AnchoredText from "./AnchoredText";
import { domSourceOffset } from "./source-anchors";
import { toolOutputRuns } from "./tool-output";

it("indents nested tool output without rewriting numbers, escapes, or duplicate keys", () => {
  const source = '{"id":9007199254740993,"id":2,"items":[{"text":"a\\\"b"}],"empty":{}}';
  const runs = toolOutputRuns(source);
  expect(runs.map((run) => run.text).join("")).toBe(`{
  "id": 9007199254740993,
  "id": 2,
  "items": [
    {
      "text": "a\\\"b"
    }
  ],
  "empty": {}
}`);
  for (const run of runs) {
    if (run.offset !== null) expect(source.slice(run.offset, run.offset + run.text.length)).toBe(run.text);
  }
});

it("keeps ordinary tool output and spaces in bracketed text readable", () => {
  expect(toolOutputRuns("Search complete.\nFound 3 results.")).toEqual([{ text: "Search complete.\nFound 3 results.", offset: 0 }]);
  expect(toolOutputRuns("[No results found]").map((run) => run.text).join("")).toContain("No results found");
});

it("keeps comments and text selections anchored to the raw output after formatting", () => {
  const source = '{"action":{"query":"engine parts"},"sources":[]}';
  const start = source.indexOf("engine parts");
  const onSelect = vi.fn();
  render(<AnchoredText stepId="result" content={source} markdown={false}
    highlights={[{ id: "comment", start, end: start + 12, className: "highlight" }]}
    onSelectAnnotation={onSelect} />);
  const marked = screen.getByText("engine parts");
  expect(marked.tagName).toBe("MARK");
  expect(domSourceOffset(marked.firstChild!, 0)).toBe(start);
  expect(domSourceOffset(marked.firstChild!, 12)).toBe(start + 12);
  fireEvent.click(marked);
  expect(onSelect).toHaveBeenCalledWith(["comment"]);
});
