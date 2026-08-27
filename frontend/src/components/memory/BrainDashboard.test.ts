import { describe, expect, it } from "vitest";

import type { OnboardingStatus, UploadSource } from "@/lib/api";
import { getInitialUploadProgress } from "./BrainDashboard";

const status: OnboardingStatus = {
  curatable_trace_count: 0,
  curatable_session_ids: [],
  skill_count: 0,
  trace_target: 5,
  skill_target: 3,
};

const uploadingSource: UploadSource = {
  client: "codex_cli",
  key_id: "key-1",
  key_name: "CLI (Henry's MacBook Pro)",
  session_count: 0,
  last_uploaded_at: null,
  uploads_enabled: true,
  can_manage: true,
};

describe("first-session upload progress", () => {
  it("starts at zero as soon as a connected installation is uploading", () => {
    expect(getInitialUploadProgress(status, [uploadingSource])).toEqual({ done: 0, total: 5 });
  });

  it("does not replace setup instructions for a disabled installation", () => {
    expect(
      getInitialUploadProgress(status, [{ ...uploadingSource, uploads_enabled: false }]),
    ).toBeNull();
  });

  it("ends once the five-session onboarding target is reached", () => {
    expect(
      getInitialUploadProgress({ ...status, curatable_trace_count: 5 }, [uploadingSource]),
    ).toBeNull();
  });
});
