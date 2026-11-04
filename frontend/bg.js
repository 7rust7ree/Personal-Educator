// Living knowledge network: drifting nodes, nearby ones link up, and light pulses travel along links.
// Motion levels: full | lite (default on 4-thread-or-less machines) | off. Pauses while dictating
// or when the window isn't focused, so speech recognition gets the CPU.
const Motion = (() => {
  const canvas = document.getElementById("net");
  const ctx = canvas.getContext("2d");
  const LINK = 170;
  const PRESETS = { full: { fps: 30, maxNodes: 64, area: 26000 }, lite: { fps: 14, maxNodes: 34, area: 42000 } };
  let w = 0, h = 0, nodes = [], pulses = [], mouse = { x: -1e4, y: -1e4 };
  let last = 0, rafId = null, mode = "lite", paused = { dictation: false, blur: false, hidden: false };

  function defaultMode() {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return "off";
    return (navigator.hardwareConcurrency || 4) <= 4 ? "lite" : "full";
  }
  function load() { try { return localStorage.getItem("motion") || defaultMode(); } catch { return defaultMode(); } }

  function resize() {
    const dpr = mode === "full" ? Math.min(window.devicePixelRatio || 1, 2) : 1;
    w = innerWidth; h = innerHeight;
    canvas.width = w * dpr; canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const p = PRESETS[mode] || PRESETS.lite;
    const n = Math.min(p.maxNodes, Math.round((w * h) / p.area));
    while (nodes.length < n) nodes.push(newNode());
    nodes.length = n;
    if (!running()) draw(performance.now()); // keep a still frame when paused/off
  }
  function newNode() {
    return { x: Math.random() * w, y: Math.random() * h, vx: (Math.random() - .5) * .18, vy: (Math.random() - .5) * .18,
             r: 1 + Math.random() * 1.6, phase: Math.random() * Math.PI * 2 };
  }
  const running = () => mode !== "off" && !paused.dictation && !paused.blur && !paused.hidden;

  function draw(t, move = false) {
    ctx.clearRect(0, 0, w, h);
    if (mode === "off") return;
    if (move) for (const p of nodes) {
      const k = mode === "lite" ? 2 : 1; // same speed at lower fps
      p.x += p.vx * k; p.y += p.vy * k;
      if (p.x < -20) p.x = w + 20; else if (p.x > w + 20) p.x = -20;
      if (p.y < -20) p.y = h + 20; else if (p.y > h + 20) p.y = -20;
    }
    ctx.lineWidth = 1;
    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i];
      for (let j = i + 1; j < nodes.length; j++) {
        const b = nodes[j], d = Math.hypot(a.x - b.x, a.y - b.y);
        if (d < LINK) {
          ctx.strokeStyle = `rgba(100, 170, 255, ${(1 - d / LINK) * 0.14})`;
          ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
          if (move && Math.random() < 0.0009 && pulses.length < 5) pulses.push({ a, b, t: 0 });
        }
      }
      const md = Math.hypot(a.x - mouse.x, a.y - mouse.y);
      if (md < 200) {
        ctx.strokeStyle = `rgba(100, 210, 255, ${(1 - md / 200) * 0.22})`;
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(mouse.x, mouse.y); ctx.stroke();
      }
    }
    for (const p of nodes) {
      ctx.fillStyle = `rgba(150, 200, 255, ${0.45 + 0.35 * Math.sin(t / 1400 + p.phase)})`;
      ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2); ctx.fill();
    }
    if (move) pulses = pulses.filter((q) => (q.t += mode === "lite" ? 0.04 : 0.02) < 1 && Math.hypot(q.a.x - q.b.x, q.a.y - q.b.y) < LINK * 1.2);
    for (const q of pulses) {
      const x = q.a.x + (q.b.x - q.a.x) * q.t, y = q.a.y + (q.b.y - q.a.y) * q.t;
      const g = ctx.createRadialGradient(x, y, 0, x, y, 10);
      g.addColorStop(0, "rgba(120, 220, 255, .9)"); g.addColorStop(1, "rgba(120, 220, 255, 0)");
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, 10, 0, Math.PI * 2); ctx.fill();
    }
  }

  function loop(t) {
    rafId = null;
    if (!running()) return;
    rafId = requestAnimationFrame(loop);
    if (t - last < 1000 / PRESETS[mode].fps) return;
    last = t;
    draw(t, true);
  }
  function kick() { if (running() && rafId === null) rafId = requestAnimationFrame(loop); }
  function applyPause() { document.body.classList.toggle("motion-paused", !running()); kick(); }

  function set(m) {
    mode = PRESETS[m] || m === "off" ? m : "lite";
    try { localStorage.setItem("motion", mode); } catch {}
    document.body.classList.remove("motion-full", "motion-lite", "motion-off");
    document.body.classList.add(`motion-${mode}`);
    resize();
    applyPause();
    document.querySelectorAll("[data-motion]").forEach((b) => b.classList.toggle("on", b.dataset.motion === mode));
  }

  addEventListener("resize", resize);
  addEventListener("mousemove", (e) => {
    mouse.x = e.clientX; mouse.y = e.clientY;
    if (!running() && mode !== "off") draw(performance.now());
  });
  addEventListener("mouseout", () => { mouse.x = mouse.y = -1e4; });
  addEventListener("blur", () => { paused.blur = true; applyPause(); });
  addEventListener("focus", () => { paused.blur = false; applyPause(); });
  document.addEventListener("visibilitychange", () => { paused.hidden = document.hidden; applyPause(); });
  document.addEventListener("dictation", (e) => { paused.dictation = e.detail; applyPause(); });

  set(load());
  return { set, get mode() { return mode; } };
})();
