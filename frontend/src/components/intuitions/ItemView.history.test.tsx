import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import ItemView from "./ItemView";

it("shows a past session as readable turns with its real source and excerpt limits", () => {
  const { container } = render(
    <ItemView
      clamp={false}
      item={{
        kind: "history",
        source: {
          kind: "local",
          title: "Website feedback",
          id: "private-session-id",
        },
        offset: 8,
        end_offset: 10,
        content_truncated: true,
        events: [
          { index: 8, role: "user", content: "The corners are too rounded" },
          { index: 9, role: "assistant", content: "<script>unsafe()</script>" },
        ],
      }}
    />,
  );
  expect(screen.getByText("Website feedback")).toBeInTheDocument();
  expect(
    screen.getByText(/Local Codex session.*turns 9–10/),
  ).toBeInTheDocument();
  expect(screen.getByText("The corners are too rounded")).toBeInTheDocument();
  expect(
    screen.getByText("Some long messages are shortened."),
  ).toBeInTheDocument();
  expect(screen.queryByText("private-session-id")).not.toBeInTheDocument();
  expect(container.querySelector("script")).toBeNull();
});

it("does not render an untrusted history source URL as a link", () => {
  render(
    <ItemView
      item={{
        kind: "history",
        source: { kind: "local", url: "javascript:alert(1)" },
        events: [],
      }}
    />,
  );
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
});
