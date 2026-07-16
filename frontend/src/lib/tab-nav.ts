// Product-wide "open in a new tab vs navigate here" signal.
//
// Clicking something in the explorer/file tree navigates the CURRENT tab by
// default; holding cmd/ctrl opens a NEW tab (the browser convention). Rather
// than thread the mouse event through every navigation handler, a
// capture-phase pointerdown listener records the modifier of the most recent
// click, and the navigation callbacks read it right after.

let newTabIntent = false;

if (typeof window !== "undefined" && !(window as unknown as { __tabNavInstalled?: boolean }).__tabNavInstalled) {
  (window as unknown as { __tabNavInstalled?: boolean }).__tabNavInstalled = true;
  window.addEventListener(
    "pointerdown",
    (e) => {
      newTabIntent = e.metaKey || e.ctrlKey;
    },
    true,
  );
}

/** True when the most recent click asked for a new tab (cmd/ctrl held). */
export function opensNewTab(): boolean {
  return newTabIntent;
}
