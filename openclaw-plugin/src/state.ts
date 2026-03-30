/**
 * State persistence — local JSON files for session state, context cache, and injection state.
 * Port of claude-plugin/scripts/config.py.
 */

import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";

const DATA_DIR = join(
  homedir(),
  ".openclaw",
  "plugins",
  "data",
  "boozle",
);
const STATE_FILE = join(DATA_DIR, "state.json");
const CACHE_FILE = join(DATA_DIR, "context_cache.json");
const INJECTION_STATE_FILE = join(DATA_DIR, "injection_state.json");
const CACHE_TTL = 300; // 5 minutes

function ensureDir(): void {
  if (!existsSync(DATA_DIR)) {
    mkdirSync(DATA_DIR, { recursive: true });
  }
}

function readJson(path: string): Record<string, unknown> | null {
  try {
    return JSON.parse(readFileSync(path, "utf-8")) as Record<string, unknown>;
  } catch {
    return null;
  }
}

function writeJson(path: string, data: unknown): void {
  ensureDir();
  writeFileSync(path, JSON.stringify(data, null, 2));
}

// --- Plugin State ---

export interface PluginState {
  session_id: string;
  streaming_enabled: boolean;
  persona: string;
  last_sync: number | null;
}

const DEFAULT_STATE: PluginState = {
  session_id: "",
  streaming_enabled: true,
  persona: "",
  last_sync: null,
};

export function loadState(): PluginState {
  const data = readJson(STATE_FILE);
  return { ...DEFAULT_STATE, ...data } as PluginState;
}

export function saveState(state: PluginState): void {
  writeJson(STATE_FILE, state);
}

// --- Context Cache ---

export interface ContextCache {
  _timestamp: number;
  profile: Record<string, unknown>;
  recent_events: Record<string, unknown>[];
}

export function loadCache(): ContextCache | null {
  const data = readJson(CACHE_FILE) as ContextCache | null;
  if (!data) return null;
  if (Date.now() / 1000 - (data._timestamp ?? 0) > CACHE_TTL) return null;
  return data;
}

export function saveCache(
  profile: Record<string, unknown>,
  recentEvents: Record<string, unknown>[],
): void {
  writeJson(CACHE_FILE, {
    _timestamp: Date.now() / 1000,
    profile,
    recent_events: recentEvents,
  });
}

// --- Injection State ---

export interface InjectionState {
  prompt_num: number;
  session_start: string;
  items: Record<string, unknown>;
}

const DEFAULT_INJECTION_STATE: InjectionState = {
  prompt_num: 0,
  session_start: "",
  items: {},
};

export function loadInjectionState(): InjectionState {
  const data = readJson(INJECTION_STATE_FILE);
  return { ...DEFAULT_INJECTION_STATE, ...data } as InjectionState;
}

export function saveInjectionState(state: InjectionState): void {
  writeJson(INJECTION_STATE_FILE, state);
}
