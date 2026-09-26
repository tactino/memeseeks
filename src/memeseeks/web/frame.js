// The Mondrian frame around the window (docs/design.md, "Lines, blocks and the frame"): one SVG computed
// for the window size. Planes are drawn first and lines on top, so no seam can show; every line runs
// until it meets another line or the edge; colour fills whole cells; rhythm comes from line weight.
"use strict";

(function () {
  const F = {
    T: { top: 24, bottom: 28, left: 22, right: 22 },   // strip thickness
    outer: 3,
    inner: { top: 5, bottom: 6, left: 4, right: 5 },    // the long inner lines, each edge to edge
    // each strip: dividers [position along the strip, weight] and fills by segment (or a cell split by a thin line)
    top:    { div: [[.21, 4], [.36, 6], [.52, 3], [.60, 5], [.79, 4]], fill: { 1: "y", 3: "r", 4: { at: .5, w: 3, fills: ["p", "b"] } } },
    bottom: { div: [[.09, 5], [.31, 3], [.47, 6], [.66, 4], [.90, 5]], fill: { 1: { at: .45, w: 3, fills: ["p", "y"] }, 3: "b", 5: "y" } },
    left:   { div: [[.17, 4], [.29, 3], [.54, 6], [.62, 3], [.83, 4]], fill: { 1: "y", 3: "r", 4: { at: .5, w: 3, fills: ["b", "p"] } } },
    right:  { div: [[.11, 3], [.34, 5], [.46, 3], [.71, 4], [.84, 5]], fill: { 2: "r", 5: "b" } },
    corner: { tl: "k", tr: "p", bl: "p", br: "r" },
  };
  const COLOUR = { p: "var(--paper)", y: "var(--accent)", r: "var(--red)", b: "var(--blue)", k: "var(--ink)" };

  function draw() {
    let svg = document.getElementById("mframe");
    if (document.documentElement.dataset.frame === "off") { if (svg) svg.remove(); return; }
    const W = document.documentElement.clientWidth, H = window.innerHeight;
    const k = W < 700 ? 0.55 : 1;                                             // thinner on phones
    const T = Object.fromEntries(Object.entries(F.T).map(([s, v]) => [s, Math.round(v * k)]));
    const lw = (v) => Math.max(2, Math.round(v * (k < 1 ? 0.7 : 1)));
    const I = Object.fromEntries(Object.entries(F.inner).map(([s, v]) => [s, lw(v)]));
    const O = lw(F.outer);
    const paper = [], planes = [], lines = [];
    const rect = (arr, x, y, w, h, c) => arr.push(`<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${c}"/>`);
    const strip = (side) => {
      const horiz = side === "top" || side === "bottom";
      const a0 = horiz ? T.left : T.top, a1 = horiz ? W - T.right : H - T.bottom;
      const b0 = side === "top" ? 0 : side === "bottom" ? H - T.bottom : side === "left" ? 0 : W - T.right;
      const th = T[side];
      const cut = F[side].div.map(([f, w]) => [Math.round(a0 + f * (a1 - a0)), lw(w)]);
      const edges = [a0, ...cut.flatMap(([x, w]) => [x, x + w]), a1];
      const put = (arr, u0, u1, v0, v1, c) => (horiz ? rect(arr, u0, v0, u1 - u0, v1 - v0, c) : rect(arr, v0, u0, v1 - v0, u1 - u0, c));
      for (const [i, f] of Object.entries(F[side].fill)) {
        const u0 = edges[2 * i], u1 = edges[2 * i + 1];
        if (typeof f === "string") put(planes, u0, u1, b0, b0 + th, COLOUR[f]);
        else {
          const m = Math.round(b0 + f.at * th), w = lw(f.w);
          put(planes, u0, u1, b0, m, COLOUR[f.fills[0]]);
          put(planes, u0, u1, m, b0 + th, COLOUR[f.fills[1]]);
          put(lines, u0 - 1, u1 + 1, m - Math.floor(w / 2), m + Math.ceil(w / 2), COLOUR.k);   // ends inside the dividers
        }
      }
      for (const [x, w] of cut) put(lines, x, x + w, b0, b0 + th, COLOUR.k);   // dividers cross the whole strip
    };
    rect(paper, 0, 0, W, T.top, COLOUR.p); rect(paper, 0, H - T.bottom, W, T.bottom, COLOUR.p);
    rect(paper, 0, 0, T.left, H, COLOUR.p); rect(paper, W - T.right, 0, T.right, H, COLOUR.p);
    rect(planes, 0, 0, T.left, T.top, COLOUR[F.corner.tl]);
    rect(planes, W - T.right, 0, T.right, T.top, COLOUR[F.corner.tr]);
    rect(planes, 0, H - T.bottom, T.left, T.bottom, COLOUR[F.corner.bl]);
    rect(planes, W - T.right, H - T.bottom, T.right, T.bottom, COLOUR[F.corner.br]);
    ["top", "bottom", "left", "right"].forEach(strip);
    rect(lines, 0, 0, W, O, COLOUR.k); rect(lines, 0, H - O, W, O, COLOUR.k);
    rect(lines, 0, 0, O, H, COLOUR.k); rect(lines, W - O, 0, O, H, COLOUR.k);
    rect(lines, 0, T.top - I.top, W, I.top, COLOUR.k); rect(lines, 0, H - T.bottom, W, I.bottom, COLOUR.k);
    rect(lines, T.left - I.left, 0, I.left, H, COLOUR.k); rect(lines, W - T.right, 0, I.right, H, COLOUR.k);
    if (!svg) {
      svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.id = "mframe";
      svg.setAttribute("aria-hidden", "true");
      document.body.prepend(svg);
    }
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("width", W);
    svg.setAttribute("height", H);
    svg.setAttribute("shape-rendering", "crispEdges");
    svg.innerHTML = paper.join("") + planes.join("") + lines.join("");
    const root = document.documentElement.style;
    root.setProperty("--frame-top", `${T.top}px`);
    root.setProperty("--frame-bottom", `${T.bottom}px`);
    root.setProperty("--frame-side", `${T.left}px`);
  }

  window.Frame = { draw };
  addEventListener("resize", draw);
})();
