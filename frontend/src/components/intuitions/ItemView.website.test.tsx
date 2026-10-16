import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import ItemView from "./ItemView";

it("shows the website brief and actual pixels without dumping the image payload", () => {
  render(<ItemView item={{ kind: "website", brief: "A compact dashboard", render: {
    kind: "image", name: "Recorded interface", data_url: "data:image/png;base64,aGVsbG8=",
    content: "A navigation sidebar and thin table rows", extraction: "Visual description",
  } }} />);
  expect(screen.getByText("A compact dashboard")).toBeVisible();
  expect(screen.getByRole("img", { name: "Recorded interface" })).toHaveAttribute("src", "data:image/png;base64,aGVsbG8=");
  expect(screen.queryByText(/aGVsbG8=/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Enlarge Recorded interface" }));
  expect(within(screen.getByRole("dialog")).getByRole("img", { name: "Recorded interface" })).toBeVisible();
});
