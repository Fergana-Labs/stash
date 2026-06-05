import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import Header from "./Header";

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: ReactNode;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

const user = {
  id: "user-1",
  name: "henry",
  display_name: "Henry Dowling",
  email: "henry@example.com",
  description: "",
  created_at: "2026-05-11T00:00:00Z",
  last_seen: "2026-05-11T00:00:00Z",
};

afterEach(() => {
  cleanup();
});

describe("Header account menu", () => {
  it("shows the signed-in email and signs out", () => {
    const onLogout = vi.fn();

    render(<Header user={user} onLogout={onLogout} />);

    fireEvent.click(screen.getByTitle("henry@example.com"));

    expect(screen.getByText("henry@example.com")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("menuitem", { name: "Sign out" }));

    expect(onLogout).toHaveBeenCalledTimes(1);
  });
});
