// Mic buttons with live text: words appear in the box as you speak (Vosk), then get replaced with a
// cleaner, punctuated version (Whisper) a few seconds after you stop, unless you've edited them.
// Click the mic or press Ctrl+M to start/stop. Esc cancels and restores the box.
const Dictation = (() => {
  let active = null;   // { btn, target, prefix, suffix, pad, original, timer }

  async function post(path) {
    const res = await fetch(path, { method: "POST" });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || res.statusText);
    return body;
  }

  function show(a, text) {
    const t = a.target;
    t.value = a.prefix + (text ? a.pad + text : "") + a.suffix;
    const pos = (a.prefix + (text ? a.pad + text : "")).length;
    t.setSelectionRange(pos, pos);
    t.scrollTop = t.scrollHeight;
    t.dispatchEvent(new Event("input", { bubbles: true }));
  }

  async function start(btn, target) {
    if (active) await stop();
    const start = target.selectionStart ?? target.value.length;
    const end = target.selectionEnd ?? target.value.length;
    const prefix = target.value.slice(0, start);
    const a = { btn, target, prefix, suffix: target.value.slice(end), original: target.value,
                pad: prefix && !/\s$/.test(prefix) ? " " : "" };
    btn.classList.add("busy");
    try {
      await post("/api/dictation/start");
    } catch (e) { btn.classList.remove("busy"); toast(e.message, true); return; }
    btn.classList.remove("busy");
    active = a;
    btn.classList.add("rec");
    btn.title = "Stop (Ctrl+M) · Esc cancels";
    target.readOnly = true;
    target.classList.add("dictating");
    target.focus();
    document.dispatchEvent(new CustomEvent("dictation", { detail: true }));
    let last = "";
    a.timer = setInterval(async () => {
      if (active !== a) return;
      try {
        const r = await (await fetch("/api/dictation/live")).json();
        if (active !== a) return;
        btn.style.setProperty("--lvl", r.level.toFixed(2));
        if (r.text !== last) { last = r.text; show(a, r.text); }
      } catch {}
    }, 120);
  }

  function finish(a) {
    clearInterval(a.timer);
    a.btn.classList.remove("rec");
    a.btn.style.removeProperty("--lvl");
    a.btn.title = "Speak (Ctrl+M)";
    a.target.readOnly = false;
    a.target.classList.remove("dictating");
    document.dispatchEvent(new CustomEvent("dictation", { detail: false }));
  }

  async function stop() {
    if (!active) return;
    const a = active;
    active = null;
    finish(a);
    let res;
    try { res = await post("/api/dictation/stop"); }
    catch (e) { toast(e.message, true); return; }
    const live = res.text || "";
    show(a, live);
    if (!res.take) { if (!live) toast("Didn't catch anything. Try again a little closer to the mic."); return; }
    // Polish in the background; swap in only if the dictated words are still untouched.
    const t = a.target;
    t.classList.add("polishing");
    try {
      const { text } = await post(`/api/dictation/polish/${res.take}`);
      const expected = a.prefix + (live ? a.pad + live : "") + a.suffix;
      if (text && t.value === expected && !t.readOnly) show(a, text);
    } catch {}
    t.classList.remove("polishing");
  }

  async function cancel() {
    if (!active) return;
    const a = active;
    active = null;
    finish(a);
    await post("/api/dictation/cancel").catch(() => {});
    a.target.value = a.original;
    a.target.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function toggle(btn, target) {
    if (btn.classList.contains("busy")) return;
    if (active && active.btn === btn) stop(); else start(btn, target);
  }

  // Wire every [data-mic-for] button under `root` to its textarea.
  function wire(root = document) {
    root.querySelectorAll("[data-mic-for]").forEach((btn) => {
      if (btn._wired) return;
      btn._wired = true;
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        const target = document.getElementById(btn.dataset.micFor);
        if (target) toggle(btn, target);
      });
    });
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && active) { e.preventDefault(); e.stopPropagation(); cancel(); return; }
    if (active && e.key === "Enter" && document.activeElement === active.target) {
      e.preventDefault(); e.stopPropagation(); stop(); return;  // Enter stops dictation, doesn't submit
    }
    if (e.ctrlKey && (e.key === "m" || e.key === "M")) {
      e.preventDefault();
      if (active) return void stop();
      const el = document.activeElement;
      if (el && el.tagName === "TEXTAREA" && el.id) {
        const btn = document.querySelector(`[data-mic-for="${el.id}"]`);
        if (btn) toggle(btn, el);
      }
    }
  }, true);

  return { wire, isActive: () => !!active };
})();
