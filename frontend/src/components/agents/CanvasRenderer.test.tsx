import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CanvasRenderer from "./CanvasRenderer";

describe("CanvasRenderer", () => {
  afterEach(cleanup);

  it("renders the pre-built block catalog", () => {
    render(
      <CanvasRenderer
        blocks={[
          { type: "heading", text: "Pipeline" },
          { type: "stat", label: "Deals", value: "12", delta: "+3" },
          { type: "table", columns: ["Name", "Stage"], rows: [["Acme", "Won"]] },
          { type: "list", items: ["first", "second"] },
        ]}
        onAction={vi.fn()}
      />,
    );

    expect(screen.getByText("Pipeline")).toBeInTheDocument();
    expect(screen.getByText("Deals")).toBeInTheDocument();
    expect(screen.getByText("Acme")).toBeInTheDocument();
    expect(screen.getByText("second")).toBeInTheDocument();
  });

  it("sends a button's message back through onAction — the canvas→chat loop", () => {
    const onAction = vi.fn();
    render(
      <CanvasRenderer
        blocks={[{ type: "button", label: "Create CRM", message: "Create a CRM table" }]}
        onAction={onAction}
      />,
    );

    fireEvent.click(screen.getByText("Create CRM"));
    expect(onAction).toHaveBeenCalledWith("Create a CRM table");
  });

  it("submits a form's values back through onAction", () => {
    const onAction = vi.fn();
    render(
      <CanvasRenderer
        blocks={[
          {
            type: "form",
            title: "Add lead",
            fields: [{ name: "company", label: "Company" }],
            submitLabel: "Save",
          },
        ]}
        onAction={onAction}
      />,
    );

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Acme" } });
    fireEvent.click(screen.getByText("Save"));
    expect(onAction).toHaveBeenCalledWith("Add lead submitted — Company: Acme");
  });

  it("degrades unknown block types instead of throwing", () => {
    render(<CanvasRenderer blocks={[{ type: "hologram" }]} onAction={vi.fn()} />);
    expect(screen.getByText(/Unsupported block: hologram/)).toBeInTheDocument();
  });
});
