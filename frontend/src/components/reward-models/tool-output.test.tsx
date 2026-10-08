import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import AnchoredText from "./AnchoredText";
import { domSourceOffset } from "./source-anchors";
import { toolOutputRuns } from "./tool-output";

it("indents nested tool output without losing numbers or duplicate keys, decoding escaped strings", () => {
  const source = '{"id":9007199254740993,"id":2,"items":[{"text":"a\\\"b"}],"empty":{}}';
  const runs = toolOutputRuns(source);
  expect(runs.map((run) => run.text).join("")).toContain('text: a"b');
  expect(runs.map((run) => run.text).join("")).toContain('id: 9007199254740993');
  expect(runs.map((run) => run.text).join("")).toContain('id: 2');
  for (const run of runs) {
    if (run.offset !== null && (!run.sourceLength || run.sourceLength === run.text.length)) expect(source.slice(run.offset, run.offset + run.text.length)).toBe(run.text);
  }
});

it("keeps ordinary tool output and spaces in bracketed text readable", () => {
  expect(toolOutputRuns("Search complete.\nFound 3 results.")).toEqual([{ text: "Search complete.\nFound 3 results.", offset: 0 }]);
  expect(toolOutputRuns("[No results found]").map((run) => run.text).join("")).toContain("No results found");
  const wrapped = 'Script completed\nOutput:\n{"output":"first\\nsecond"}';
  expect(toolOutputRuns(wrapped).map((run) => run.text).join("")).toContain("first\nsecond");
  const first = toolOutputRuns(wrapped).find((run) => run.text === "first")!;
  expect(first.offset).toBe(wrapped.indexOf("first"));
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


it("maps decoded escapes and Unicode back to exact recorded selection boundaries", () => {
  const source = String.raw`{"output":"a\nb \uD83D\uDC19"}`;
  const { container } = render(<AnchoredText stepId="s" content={source} markdown={false} highlights={[]} onSelectAnnotation={() => {}} />);
  expect(container.textContent).toContain("a\nb 🐙");
  const escapes = container.querySelectorAll<HTMLElement>("[data-source-end]");
  expect(escapes).toHaveLength(2);
  for (const escape of escapes) {
    expect(domSourceOffset(escape.firstChild!, 0)).toBe(Number(escape.dataset.o));
    expect(domSourceOffset(escape.firstChild!, escape.textContent!.length)).toBe(Number(escape.dataset.sourceEnd));
  }
});
