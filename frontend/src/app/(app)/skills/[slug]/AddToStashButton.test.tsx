import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AddToStashButton from "./AddToStashButton";
import { forkSkill } from "@/lib/api";

const router = vi.hoisted(() => ({
  push: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => router,
}));

vi.mock("@/lib/api", () => ({
  ApiError: class ApiError extends Error {
    status = 500;
  },
  forkSkill: vi.fn(),
}));

describe("AddToStashButton", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => cleanup());

  // Forking gives back a folder id. /skills/<x> is the published-slug route,
  // so sending the folder id there renders "Skill not found" — the user
  // installs a skill and Open takes them to a 404.
  it("opens the forked skill on the folder route", async () => {
    vi.mocked(forkSkill).mockResolvedValue({
      folder_id: "folder-9",
      name: "Brake Shoes",
    });

    render(<AddToStashButton slug="brake-shoes" />);
    fireEvent.click(screen.getByText("Add to my files"));

    const open = await screen.findByText(/Open Brake Shoes/);
    fireEvent.click(open);

    expect(router.push).toHaveBeenCalledWith("/skills/folder/folder-9");
  });
});
