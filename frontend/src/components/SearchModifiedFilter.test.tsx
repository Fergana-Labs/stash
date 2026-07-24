/** The last-modified chip defaults to "Any time", swaps its label to the
 * active preset, and flips to a custom range as soon as either datetime input
 * is edited — the preset list and the custom inputs are one control. */
import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { DEFAULT_MODIFIED_RANGE, type ModifiedRange } from "@/app/search/modified-range";
import SearchModifiedFilter from "./SearchModifiedFilter";

function Harness({ initial = DEFAULT_MODIFIED_RANGE }: { initial?: ModifiedRange }) {
  const [range, setRange] = useState(initial);
  return <SearchModifiedFilter range={range} onChange={setRange} />;
}

function openMenu(): HTMLElement {
  // Radix triggers open on pointer/keyboard events, not jsdom's synthetic
  // click — Enter is the reliable way to open the menu in tests. The open
  // menu is modal (the trigger goes aria-hidden), so later assertions must
  // use the element captured here, not a fresh role query.
  const trigger = screen.getByRole("button", { name: "Last modified" });
  fireEvent.keyDown(trigger, { key: "Enter" });
  return trigger;
}

describe("SearchModifiedFilter", () => {
  it("labels the trigger 'Any time' by default", () => {
    render(<Harness />);
    expect(screen.getByRole("button", { name: "Last modified" })).toHaveTextContent("Any time");
  });

  it("selects a preset, relabels the trigger, and keeps the menu open", () => {
    render(<Harness />);
    const trigger = openMenu();

    const items = screen.getAllByRole("menuitemcheckbox");
    expect(items.map((i) => i.textContent)).toEqual([
      "Any time",
      "Past 24 hours",
      "Past week",
      "Past month",
      "Past year",
    ]);

    fireEvent.click(screen.getByRole("menuitemcheckbox", { name: "Past week" }));
    expect(trigger).toHaveTextContent("Past week");
    // The item is still queryable — the menu did not close on selection.
    expect(screen.getByRole("menuitemcheckbox", { name: "Past week" })).toHaveAttribute(
      "aria-checked",
      "true"
    );
  });

  it("switches to a custom range when a datetime input is edited", () => {
    render(<Harness initial={{ preset: "week", from: "", to: "" }} />);
    const trigger = openMenu();

    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-07-01T09:30" } });
    expect(trigger).toHaveTextContent("Custom range");
    expect(screen.getByLabelText("From")).toHaveValue("2026-07-01T09:30");

    fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-07-20T18:00" } });
    expect(screen.getByLabelText("From")).toHaveValue("2026-07-01T09:30");
    expect(screen.getByLabelText("To")).toHaveValue("2026-07-20T18:00");
  });
});
