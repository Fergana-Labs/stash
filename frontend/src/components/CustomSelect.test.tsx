import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import CustomSelect, { CustomSelectOption } from "./CustomSelect";

const OPTIONS: CustomSelectOption[] = [
  { value: "", label: "All workspaces" },
  { value: "ws-1", label: "Engineering" },
  { value: "ws-2", label: "Design" },
  { value: "ws-3", label: "Marketing" },
];

// Mirrors the search filters: the parent owns the selected value, so picking an
// option must drive that state and the trigger label.
function Harness({ searchable }: { searchable?: boolean }) {
  const [value, setValue] = useState("");
  return (
    <div>
      <CustomSelect
        value={value}
        options={OPTIONS}
        onChange={setValue}
        ariaLabel="Workspace"
        searchable={searchable}
      />
      <output>{value || "none"}</output>
    </div>
  );
}

afterEach(cleanup);

describe("CustomSelect searchable", () => {
  it("filters options by the typed query", () => {
    render(<Harness searchable />);
    fireEvent.click(screen.getByRole("button", { name: "Workspace" }));

    fireEvent.change(screen.getByLabelText("Search Workspace"), {
      target: { value: "des" },
    });

    expect(screen.getByRole("option", { name: /Design/ })).toBeTruthy();
    expect(screen.queryByRole("option", { name: /Engineering/ })).toBeNull();
  });

  it("selects a filtered match and reports its value", () => {
    render(<Harness searchable />);
    fireEvent.click(screen.getByRole("button", { name: "Workspace" }));

    fireEvent.change(screen.getByLabelText("Search Workspace"), {
      target: { value: "mark" },
    });
    fireEvent.click(screen.getByRole("option", { name: /Marketing/ }));

    expect(screen.getByText("ws-3")).toBeTruthy();
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("selects the first match on Enter from the search input", () => {
    render(<Harness searchable />);
    fireEvent.click(screen.getByRole("button", { name: "Workspace" }));

    const input = screen.getByLabelText("Search Workspace");
    fireEvent.change(input, { target: { value: "eng" } });
    fireEvent.keyDown(input, { key: "Enter" });

    // Only "Engineering" matches "eng", so Enter commits it.
    expect(screen.getByText("ws-1")).toBeTruthy();
  });

  it("shows an empty state when nothing matches", () => {
    render(<Harness searchable />);
    fireEvent.click(screen.getByRole("button", { name: "Workspace" }));

    fireEvent.change(screen.getByLabelText("Search Workspace"), {
      target: { value: "zzz" },
    });

    expect(screen.getByText("No matches")).toBeTruthy();
    expect(screen.queryByRole("option")).toBeNull();
  });

  it("renders no search input when not searchable", () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Workspace" }));

    expect(screen.queryByLabelText("Search Workspace")).toBeNull();
    expect(screen.getAllByRole("option")).toHaveLength(OPTIONS.length);
  });
});
