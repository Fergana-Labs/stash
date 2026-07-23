// Per-surface error slots. The old single `lastError` string meant a clip
// failure could silently hide a broken Instagram sync (and vice versa);
// each subsystem now owns one slot, and the popup lists whichever are set.

export type ErrorSurface = 'clip' | 'chat' | 'instagram' | 'import';

export interface SurfaceError {
  surface: ErrorSurface;
  message: string;
  at: number;
}

export async function setSurfaceError(surface: ErrorSurface, message: string): Promise<void> {
  const { surfaceErrors } = await chrome.storage.local.get('surfaceErrors');
  const others = ((surfaceErrors as SurfaceError[] | undefined) ?? []).filter(
    (e) => e.surface !== surface
  );
  await chrome.storage.local.set({
    surfaceErrors: [...others, { surface, message, at: Date.now() }],
  });
}

export async function clearSurfaceError(surface: ErrorSurface): Promise<void> {
  const { surfaceErrors } = await chrome.storage.local.get('surfaceErrors');
  const others = ((surfaceErrors as SurfaceError[] | undefined) ?? []).filter(
    (e) => e.surface !== surface
  );
  await chrome.storage.local.set({ surfaceErrors: others });
}

export async function getSurfaceErrors(): Promise<SurfaceError[]> {
  const { surfaceErrors } = await chrome.storage.local.get('surfaceErrors');
  return (surfaceErrors as SurfaceError[] | undefined) ?? [];
}
