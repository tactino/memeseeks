// The Pop Cat (docs/design.md, "The cat"). Its shapes come from popcat.js: every shape has the same
// command list in the open (logo) and the closed state, so any state in between is the numbers
// interpolated. Cat.set() draws any state; pop() and loop() animate it (docs/design.md, "The cat").
"use strict";

(function () {
  const P = window.POPCAT;
  const K = "#161411";
  const NUM = /-?\d+(\.\d+)?/g;

  function lerp(a, b, t) {
    const nb = b.match(NUM);
    let i = 0;
    return a.replace(NUM, (x) => (+x + (nb[i++] - x) * t).toFixed(1));
  }

  // closed: 0 = the logo's open O, 1 = mouth shut; bubble: the chat bubble's scale (0 = gone)
  function set(svg, closed, bubble) {
    const [mx, my] = P.mc;
    const q = (sel) => svg.querySelector(sel);
    [[".e0", P.final.eyes[0], P.closed.eyes[0]], [".e1", P.final.eyes[1], P.closed.eyes[1]],
      [".nose", P.final.nose, P.closed.nose], [".mouth", P.final.mouth, P.closed.mouth]]
      .forEach(([sel, a, b]) => q(sel).setAttribute("d", lerp(a, b, closed)));
    q(".nose").setAttribute("opacity", closed >= 0.375 ? 1 : 0);  // gone below half its size: no dot left
    q(".bub").setAttribute("transform", `translate(${mx} ${my}) scale(${bubble.toFixed(3)}) translate(${-mx} ${-my})`);
  }

  function draw(svg, state = {}) {
    const [mx, my] = P.mc;
    svg.setAttribute("viewBox", P.vb);
    svg.innerHTML = `<path d="${P.body}" fill="#FFD21F" stroke="${K}" stroke-width="15" stroke-linejoin="round"/>
      <path class="e0" fill="${K}"/><path class="e1" fill="${K}"/><path class="nose" fill="${K}"/>
      <path class="mouth" fill="${K}"/><g class="bub">${P.bubble}</g>`;
    set(svg, state.closed || 0, state.bubble === undefined ? 1 : state.bubble);
    return svg;
  }

  function make(state, className = "cat") {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", className);
    svg.setAttribute("aria-hidden", "true");
    return draw(svg, state);
  }

  // ---- motion: nothing moves when the system or the 动效 setting asks for less ----
  const still = () => matchMedia("(prefers-reduced-motion: reduce)").matches || document.documentElement.dataset.motion === "reduced";
  const ease = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
  const part = (u, a, b) => ease(Math.min(1, Math.max(0, (u - a) / (b - a))));
  const spit = (u) => (u < 0.6 ? 1.15 * ease(u / 0.6) : 1.15 - 0.15 * ease((u - 0.6) / 0.4));  // the bubble pops out

  // a click: swallow the bubble and shut, hold, open and spit it out; a click while it plays starts over, faster
  function pop(svg, fast = false) {
    if (still()) return;
    const d = fast ? { close: 110, hold: 0, open: 110, spit: 120 } : { close: 280, hold: 100, open: 280, spit: 200 };
    const o = d.close + d.hold, e = o + d.open, end = e + d.spit, t0 = performance.now(), token = {};
    svg._pop = token;
    const step = (now) => {
      if (svg._pop !== token) return;  // a newer click took over
      const t = Math.min(end, now - t0);
      const closed = t < d.close ? ease(t / d.close) : t < o ? 1 : t < e ? 1 - ease((t - o) / d.open) : 0;
      const bubble = t < d.close / 2 ? 1 - ease(t / (d.close / 2)) : t >= e ? spit((t - e) / d.spit) : 0;
      set(svg, closed, bubble);
      if (t < end) requestAnimationFrame(step); else svg._pop = null;
    };
    requestAnimationFrame(step);
  }

  // loading: shut, open into the logo, the bubble pops, hold, shut again; 3.2 s, until the cat leaves the page
  function loop(svg) {
    if (still()) return;
    const t0 = performance.now();
    let shown = false;
    const step = (now) => {
      if (svg.isConnected) shown = true;
      else if (shown || now - t0 > 2000) return;
      const u = ((now - t0) / 3200) % 1;
      const closed = u < 0.14 ? 1 : u < 0.44 ? 1 - part(u, 0.14, 0.44) : u < 0.70 ? 0 : part(u, 0.70, 1);
      const bubble = u < 0.44 || u >= 0.70 ? 0 : u < 0.52 ? spit((u - 0.44) / 0.08) : u < 0.64 ? 1 : 1 - part(u, 0.64, 0.70);
      set(svg, closed, bubble);
      requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  window.Cat = { draw, set, make, lerp, pop, loop, still, ease, spit };
})();
