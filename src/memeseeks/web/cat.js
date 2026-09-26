// The Pop Cat (docs/design.md, "The cat"). Its shapes come from popcat.js: every shape has the same
// command list in the open (logo) and the closed state, so any state in between is the numbers
// interpolated. This file draws still cats; the animations build on Cat.set().
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

  window.Cat = { draw, set, make, lerp };
})();
