/* Renders the shared icon rail + sidebar + topbar. Each page sets
   window.STASH = { rail, side, crumb:[...], search } before loading this. */
(function () {
  const cfg = window.STASH || {};
  const railOn = cfg.rail || "home";
  const sideOn = cfg.side || "home";

  const ICON = {
    home: '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/>',
    index: '<path d="M4 6h16M4 12h16M4 18h10"/>',
    agents: '<path d="M21 11.5a8.5 8.5 0 0 1-12.3 7.6L3 21l1.9-5.7A8.5 8.5 0 1 1 21 11.5z"/>',
    discover: '<circle cx="12" cy="12" r="9"/><path d="M2 12h20M12 3c2.5 3 2.5 15 0 18M12 3c-2.5 3-2.5 15 0 18"/>',
    sessions: '<path d="M21 11.5a8.5 8.5 0 0 1-12.3 7.6L3 21l1.9-5.7A8.5 8.5 0 1 1 21 11.5z"/>',
    files: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
    skills: '<path d="M12 3l9 5-9 5-9-5 9-5z"/><path d="M3 13l9 5 9-5"/>',
    docs: '<path d="M4 4h9a3 3 0 0 1 3 3v13a2 2 0 0 0-2-2H4z"/><path d="M20 4h-2a3 3 0 0 0-3 3v11a2 2 0 0 1 2-2h3z"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8 2 2 0 1 1-2.7 2.7 1.6 1.6 0 0 0-2.7 1.1 2 2 0 1 1-4 0 1.6 1.6 0 0 0-2.7-1.1 2 2 0 1 1-2.7-2.7 1.6 1.6 0 0 0-1.1-2.7 2 2 0 1 1 0-4 1.6 1.6 0 0 0 1.1-2.7 2 2 0 1 1 2.7-2.7 1.6 1.6 0 0 0 2.7-1.1 2 2 0 1 1 4 0 1.6 1.6 0 0 0 2.7 1.1 2 2 0 1 1 2.7 2.7 1.6 1.6 0 0 0 1.1 2.7 2 2 0 1 1 0 4 1.6 1.6 0 0 0-1.4 1z"/>',
    trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/>',
  };
  const sv = (k, w) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${w || 1.7}" stroke-linecap="round" stroke-linejoin="round">${ICON[k]}</svg>`;

  const railBtn = (k, label) =>
    `<button class="${railOn === k ? "active" : ""}" title="${label}">${sv(k)}</button>`;

  const rail = `<nav class="rail">
    <div class="logo"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 8v13H3V8"/><path d="M1 3h22v5H1z"/><path d="M10 12h4"/></svg></div>
    ${railBtn("home", "Home")}${railBtn("index", "Index")}${railBtn("agents", "Agents")}${railBtn("discover", "Discover")}
    <div class="spacer"></div>
    ${railBtn("docs", "Docs")}${railBtn("settings", "Settings")}
    <div class="me">SL</div>
  </nav>`;

  const nav = (k, label, extra) =>
    `<div class="nav ${sideOn === k ? "on" : ""}"><span class="i">${sv(k, 1.8)}</span> ${label}${extra || ""}</div>`;

  const SOURCES = [
    ["GitHub", "#111", "GH", "#34D399"], ["Slack", "#4A154B", "Sl", "#34D399"],
    ["Linear", "#5B57D1", "Li", "#34D399"], ["Gong", "#6F2CFF", "Gg", "#60A5FA"],
    ["Notion", "#000", "No", "#34D399"], ["Snowflake", "#29B5E8", "Sn", "#34D399"],
  ];
  const srcRows = SOURCES.map(
    ([n, c, a, d]) => `<div class="src"><span class="av" style="background:${c}">${a}</span> ${n} <span class="dot" style="background:${d}"></span></div>`
  ).join("");

  const side = `<aside class="side">
    <div class="ws"><span class="ico">A</span><span class="nm">Acme</span><span class="ch"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 9l4-4 4 4M8 15l4 4 4-4"/></svg></span></div>
    <div class="scroll">
      <div class="grp">${nav("home", "Home")}${nav("index", "Index")}${nav("discover", "Discover")}</div>
      <div class="grp"><div class="hd">Your brain</div>
        ${nav("sessions", "Agent Sessions", '<span class="ct">312</span>')}
        ${nav("files", "Files", '<span class="ct">196</span>')}
        ${nav("skills", "Skills", '<span class="ct">24</span>')}
      </div>
      <div class="grp"><div class="hd">External sources <span class="ch"><svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg></span></div>
        ${srcRows}
        <div class="addsrc"><svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg> Add a new source</div>
      </div>
    </div>
    <div class="foot">${nav("trash", "Trash")}</div>
  </aside>`;

  const crumb = (cfg.crumb || ["Acme", "Home"])
    .map((c, i, arr) => (i === 0 ? `<b>${c}</b>` : `<span>/</span><span class="${i === arr.length - 1 ? "cur" : ""}">${c}</span>`))
    .join("");

  const topbar = `<div class="topbar">
    <div class="crumb">${crumb}</div>
    <div class="search"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/></svg> ${cfg.search || "Search your brain"} <span class="kbd">⌘K</span></div>
    <button class="share"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="M8.6 13.5l6.8 4M15.4 6.5l-6.8 4"/></svg> Share</button>
  </div>`;

  document.querySelector('[data-shell="rail"]').outerHTML = rail;
  document.querySelector('[data-shell="side"]').outerHTML = side;
  const tb = document.querySelector('[data-shell="topbar"]');
  if (tb) tb.outerHTML = topbar;
})();
