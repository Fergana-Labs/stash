import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import ToolInput from "./ToolInput";
import AnchoredText from "./AnchoredText";

afterEach(() => vi.unstubAllGlobals());

it("has one independently expandable row and exact copy target per input", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal("navigator", { clipboard: { writeText } });
  const code = 'const value = "<script>alert(1)</script>";\nawait tools.exec(value);';
  const { container } = render(<ToolInput input={{ code, title: "Read a page", options: { retry: false } }} tool="exec" />);
  expect(container.querySelector("pre")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Expand input code" }));
  expect(container.querySelector("pre")?.textContent).toBe(code);
  expect(container.querySelector(".hljs-keyword")).toHaveTextContent("const");
  expect(container.querySelector("script")).toBeNull();
  expect(screen.getByRole("button", { name: "Expand input title" })).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(screen.getByRole("button", { name: "Copy input code" }));
  await waitFor(() => expect(writeText).toHaveBeenLastCalledWith(code));
  fireEvent.click(screen.getByRole("button", { name: "Copy input options" }));
  await waitFor(() => expect(writeText).toHaveBeenLastCalledWith('{\n  "retry": false\n}'));
  fireEvent.click(screen.getByRole("button", { name: "Collapse input code" }));
  expect(container.querySelector("pre")).toBeNull();
});

it("highlights fenced code without moving comment offsets on repeated tokens", () => {
  const source = '```javascript\nconst value = "value";\nconsole.log(value, value);\n```\n';
  const start = source.lastIndexOf("value");
  const { container } = render(<AnchoredText stepId="s1" content={source} markdown highlights={[{ id: "comment", start, end: start + 5, className: "hl" }]} onSelectAnnotation={() => {}} />);
  expect(container.querySelector(".hljs-keyword")).toHaveTextContent("const");
  expect(container.querySelector("mark[data-ids='comment']")).toHaveTextContent("value");
  for (const run of container.querySelectorAll<HTMLElement>("[data-o]")) {
    expect(source.slice(Number(run.dataset.o), Number(run.dataset.o) + run.textContent!.length)).toBe(run.textContent);
  }
  const mark = container.querySelector("mark[data-ids='comment'] [data-o]") ?? container.querySelector("mark[data-ids='comment']");
  expect(Number((mark as HTMLElement).dataset.o)).toBe(start);
});
