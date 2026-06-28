import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import CustomSelect, { CustomSelectOption } from "./CustomSelect";

const OPTIONS: CustomSelectOption[] = [
  { value: "", label: "All folders" },
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
        ariaLabel="Folder"
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
    fireEvent.click(screen.getByRole("button", { name: "Folder" }));

    fireEvent.change(screen.getByLabelText("Search Folder"), {
      target: { value: "des" },
    });

    expect(screen.getByRole("option", { name: /Design/ })).toBeTruthy();
    expect(screen.queryByRole("option", { name: /Engineering/ })).toBeNull();
  });

  it("selects a filtered match and reports its value", () => {
    render(<Harness searchable />);
    fireEvent.click(screen.getByRole("button", { name: "Folder" }));

    fireEvent.change(screen.getByLabelText("Search Folder"), {
      target: { value: "mark" },
    });
    fireEvent.click(screen.getByRole("option", { name: /Marketing/ }));

    expect(screen.getByText("ws-3")).toBeTruthy();
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("selects the first match on Enter from the search input", () => {
    render(<Harness searchable />);
    fireEvent.click(screen.getByRole("button", { name: "Folder" }));

    const input = screen.getByLabelText("Search Folder");
    fireEvent.change(input, { target: { value: "eng" } });
    fireEvent.keyDown(input, { key: "Enter" });

    // Only "Engineering" matches "eng", so Enter commits it.
    expect(screen.getByText("ws-1")).toBeTruthy();
  });

  it("shows an empty state when nothing matches", () => {
    render(<Harness searchable />);
    fireEvent.click(screen.getByRole("button", { name: "Folder" }));

    fireEvent.change(screen.getByLabelText("Search Folder"), {
      target: { value: "zzz" },
    });

    expect(screen.getByText("No matches")).toBeTruthy();
    expect(screen.queryByRole("option")).toBeNull();
  });

  it("renders no search input when not searchable", () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Folder" }));

    expect(screen.queryByLabelText("Search Folder")).toBeNull();
    expect(screen.getAllByRole("option")).toHaveLength(OPTIONS.length);
  });
});
