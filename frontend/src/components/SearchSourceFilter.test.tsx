/** The sources chip defaults to everything selected ("All sources"), shows a
 * count once narrowed, and stays open while toggling — deselecting three
 * providers must not take three open-the-menu round trips. */
import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import SearchSourceFilter from "./SearchSourceFilter";

const TOKENS = ["files", "sessions", "skills", "tables", "gmail"];

function Harness({ initialDeselected = [] }: { initialDeselected?: string[] }) {
  const [deselected, setDeselected] = useState(new Set(initialDeselected));
  return (
    <SearchSourceFilter
      tokens={TOKENS}
      deselected={deselected}
      onToggle={(token) =>
        setDeselected((prev) => {
          const next = new Set(prev);
          if (next.has(token)) next.delete(token);
          else next.add(token);
          return next;
        })
      }
    />
  );
}

describe("SearchSourceFilter", () => {
  it("labels the trigger 'All sources' when everything is selected", () => {
    render(<Harness />);
    expect(screen.getByRole("button", { name: "Sources" })).toHaveTextContent("All sources");
  });

  it("shows the selected count when narrowed", () => {
    render(<Harness initialDeselected={["gmail"]} />);
    expect(screen.getByRole("button", { name: "Sources" })).toHaveTextContent("Sources · 4/5");
  });

  it("renders every token checked by default and keeps the menu open on toggle", () => {
    render(<Harness />);
    // Radix triggers open on pointer/keyboard events, not jsdom's synthetic
    // click — Enter is the reliable way to open the menu in tests.
    fireEvent.keyDown(screen.getByRole("button", { name: "Sources" }), { key: "Enter" });

    const items = screen.getAllByRole("menuitemcheckbox");
    expect(items.map((i) => i.textContent)).toEqual([
      "Files",
      "Sessions",
      "Skills",
      "Tables",
      "Gmail",
    ]);
    expect(items.every((i) => i.getAttribute("aria-checked") === "true")).toBe(true);

    fireEvent.click(screen.getByRole("menuitemcheckbox", { name: /Gmail/ }));
    // The item is still queryable — the menu did not close on toggle.
    expect(screen.getByRole("menuitemcheckbox", { name: /Gmail/ })).toHaveAttribute(
      "aria-checked",
      "false"
    );
  });
});
