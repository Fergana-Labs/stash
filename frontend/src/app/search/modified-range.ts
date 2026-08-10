// The last-modified chip stores user intent (a preset id, or custom
// datetime-local bounds); concrete ISO bounds are computed at query time so
// relative presets like "Past 24 hours" re-anchor to now on every fetch.
export type ModifiedPreset = "any" | "24h" | "week" | "month" | "year" | "custom";

export interface ModifiedRange {
  preset: ModifiedPreset;
  // datetime-local input values ("2026-07-01T09:30"); "" means unset.
  from: string;
  to: string;
}

export interface ModifiedBounds {
  modifiedAfter?: string;
  modifiedBefore?: string;
}

export const DEFAULT_MODIFIED_RANGE: ModifiedRange = { preset: "any", from: "", to: "" };

const PRESET_LABELS: Record<ModifiedPreset, string> = {
  any: "Any time",
  "24h": "Past 24 hours",
  week: "Past week",
  month: "Past month",
  year: "Past year",
  custom: "Custom range",
};

const PRESET_MS: Partial<Record<ModifiedPreset, number>> = {
  "24h": 24 * 60 * 60 * 1000,
  week: 7 * 24 * 60 * 60 * 1000,
  month: 30 * 24 * 60 * 60 * 1000,
  year: 365 * 24 * 60 * 60 * 1000,
};

export function modifiedRangeLabel(range: ModifiedRange): string {
  return PRESET_LABELS[range.preset];
}

// The ISO bounds the search request should carry. Custom values come from
// datetime-local inputs, which parse as local time — new Date().toISOString()
// is the local→UTC conversion the server expects.
export function modifiedRangeParams(range: ModifiedRange, now: Date): ModifiedBounds {
  const ms = PRESET_MS[range.preset];
  if (ms) return { modifiedAfter: new Date(now.getTime() - ms).toISOString() };
  if (range.preset !== "custom") return {};
  const bounds: ModifiedBounds = {};
  if (range.from) bounds.modifiedAfter = new Date(range.from).toISOString();
  if (range.to) bounds.modifiedBefore = new Date(range.to).toISOString();
  return bounds;
}

// Client-side counterpart of the server filter, for the kinds searched in the
// browser (skills, tables): strict bounds, and a result with no timestamp is
// excluded whenever any bound is set.
export function withinModifiedRange(
  updatedAt: string | null | undefined,
  bounds: ModifiedBounds
): boolean {
  if (!bounds.modifiedAfter && !bounds.modifiedBefore) return true;
  if (!updatedAt) return false;
  const ts = new Date(updatedAt).getTime();
  if (bounds.modifiedAfter && ts <= new Date(bounds.modifiedAfter).getTime()) return false;
  if (bounds.modifiedBefore && ts >= new Date(bounds.modifiedBefore).getTime()) return false;
  return true;
}
