import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import AnchoredText from "./AnchoredText";
import { domSourceOffset } from "./source-anchors";

const source = "I'll **check the policy** first, then call `lookup_order`.\n\n- refund within 30 days\n- item: blender\n\n```json\n{\"status\": \"delivered\"}\n```\n";

function renderMarkdown(highlights: { id: string; start: number; end: number; className: string }[] = []) {
  return render(
    <AnchoredText stepId="s1" content={source} markdown highlights={highlights} onSelectAnnotation={() => {}} />,
  ).container;
}

describe("AnchoredText (markdown)", () => {
  // If a rendered run's offset drifted from the source, a comment on
  // "the policy" would be stored against different text than the annotator saw.
  it("tags every rendered run with the offset of that exact text in the source", () => {
    const runs = [...renderMarkdown().querySelectorAll<HTMLElement>("[data-o]")];
    expect(runs.length).toBeGreaterThan(5);
    for (const run of runs) {
      const offset = Number(run.dataset.o);
      expect(source.slice(offset, offset + run.textContent!.length)).toBe(run.textContent);
    }
  });

  it("maps text inside bold, inline code, lists, and fenced code", () => {
    const text = [...renderMarkdown().querySelectorAll("[data-o]")].map((el) => el.textContent).join("|");
    for (const piece of ["check the policy", "lookup_order", "refund within 30 days", "\"status\""]) {
      expect(text).toContain(piece);
    }
  });

  it("highlights a source range even when it spans rendered formatting", () => {
    const start = source.indexOf("check the policy");
    const end = source.indexOf(" first");
    const container = renderMarkdown([{ id: "a1", start, end, className: "hl" }]);
    const marks = [...container.querySelectorAll<HTMLElement>("mark[data-ids='a1']")];
    expect(marks.map((m) => m.textContent).join("")).toBe("check the policy");
  });

  it("turns a DOM selection boundary back into a source offset", () => {
    const container = renderMarkdown();
    const run = [...container.querySelectorAll<HTMLElement>("[data-o]")].find((el) => el.textContent === "check the policy")!;
    const offset = domSourceOffset(run.firstChild!, "check the ".length);
    expect(source.slice(offset!, offset! + "policy".length)).toBe("policy");
  });
});

describe("AnchoredText (plain)", () => {
  it("anchors each formatted tool output token to the original source", () => {
    const content = "{\"status\": \"delivered\", \"days\": 41}";
    const start = content.indexOf("41");
    const { container } = render(
      <AnchoredText
        stepId="s2"
        content={content}
        markdown={false}
        highlights={[{ id: "a2", start, end: start + 2, className: "hl" }]}
        onSelectAnnotation={() => {}}
      />,
    );
    expect(JSON.parse(container.textContent!)).toEqual(JSON.parse(content));
    for (const run of container.querySelectorAll<HTMLElement>("[data-o]")) {
      const offset = Number(run.dataset.o);
      expect(content.slice(offset, offset + run.textContent!.length)).toBe(run.textContent);
    }
    expect(container.querySelector("mark[data-ids='a2']")!.textContent).toBe("41");
  });
});
