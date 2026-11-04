// Copy & paste: system clipboard access, a right-click menu, and a floating bubble on selected text.
// In the desktop window the clipboard goes through Python (window.pywebview.api); in a browser,
// through navigator.clipboard.
const Clip = (() => {
  const api = () => window.pywebview && window.pywebview.api;

  async function copy(text) {
    if (!text) return false;
    try { if (api()) return await api().copy(text); } catch {}
    try { await navigator.clipboard.writeText(text); return true; } catch {}
    const t = document.createElement("textarea");
    t.value = text; t.style.position = "fixed"; t.style.opacity = "0";
    document.body.appendChild(t); t.select();
    const ok = document.execCommand("copy");
    t.remove();
    return ok;
  }

  async function read() {
    try { if (api()) return await api().paste(); } catch {}
    try { return await navigator.clipboard.readText(); } catch { return ""; }
  }

  const isEditable = (el) => el && (el.tagName === "TEXTAREA" || (el.tagName === "INPUT" && /^(text|search|url|email)$/.test(el.type)));

  // Insert into a text box at the cursor, replacing any selection; keeps undo history where supported.
  function insert(el, text) {
    if (!text || el.readOnly || el.disabled) return;
    el.focus();
    if (!document.execCommand("insertText", false, text)) {
      const s = el.selectionStart, e = el.selectionEnd;
      el.value = el.value.slice(0, s) + text + el.value.slice(e);
      el.setSelectionRange(s + text.length, s + text.length);
    }
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function selectedText(el) {
    if (isEditable(el)) return el.value.slice(el.selectionStart, el.selectionEnd);
    return String(window.getSelection() || "");
  }

  // ---------- right-click menu ----------
  const menu = document.createElement("div");
  menu.className = "ctx glass";
  menu.hidden = true;
  document.body.appendChild(menu);
  let ctxTarget = null;

  function item(label, keys, fn, enabled = true) {
    return { label, keys, fn, enabled };
  }

  function openMenu(x, y, items) {
    menu.innerHTML = items.map((it, i) => it === "-" ? `<div class="sep"></div>` :
      `<button data-i="${i}" ${it.enabled ? "" : "disabled"}><span>${it.label}</span>${it.keys ? `<kbd>${it.keys}</kbd>` : ""}</button>`).join("");
    menu.hidden = false;
    const r = menu.getBoundingClientRect();
    menu.style.left = `${Math.min(x, innerWidth - r.width - 8)}px`;
    menu.style.top = `${Math.min(y, innerHeight - r.height - 8)}px`;
    menu.querySelectorAll("button").forEach((b) => b.onmousedown = (e) => {
      e.preventDefault(); // keep the text selection/focus while clicking
      const it = items[+b.dataset.i];
      closeMenu();
      if (it.enabled) it.fn();
    });
  }
  function closeMenu() { menu.hidden = true; }

  document.addEventListener("contextmenu", (e) => {
    const el = e.target.closest("textarea, input") || null;
    const sel = isEditable(el) ? selectedText(el) : String(window.getSelection() || "");
    const inLesson = e.target.closest(".lesson, .qcard, .you, .explain");
    e.preventDefault();
    ctxTarget = el;
    const items = [];
    if (isEditable(el)) {
      const has = el.selectionStart !== el.selectionEnd;
      items.push(
        item("Cut", "⌘X", () => { copy(selectedText(el)); insertDelete(el); }, has && !el.readOnly),
        item("Copy", "⌘C", () => copy(selectedText(el)), has),
        item("Paste", "⌘V", async () => insert(el, await read()), !el.readOnly),
        "-",
        item("Select All", "⌘A", () => { el.focus(); el.select(); }),
      );
    } else {
      items.push(item("Copy", "⌘C", () => copy(sel), !!sel));
      if (inLesson && typeof askAbout === "function") items.push(item("Ask about this", "", () => askAbout(sel || inLesson.innerText), true));
      if (inLesson) items.push("-", item("Copy this block", "", () => copy(inLesson.innerText.trim())));
      items.push("-", item("Select All", "⌘A", () => {
        const r = document.createRange(); r.selectNodeContents(document.querySelector("#col") || document.body);
        const s = getSelection(); s.removeAllRanges(); s.addRange(r);
      }));
    }
    openMenu(e.clientX, e.clientY, items);
  });
  function insertDelete(el) {
    el.focus();
    if (!document.execCommand("delete")) {
      const s = el.selectionStart;
      el.value = el.value.slice(0, s) + el.value.slice(el.selectionEnd);
      el.setSelectionRange(s, s);
    }
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }
  addEventListener("mousedown", (e) => { if (!menu.contains(e.target)) closeMenu(); });
  addEventListener("keydown", (e) => { if (e.key === "Escape") closeMenu(); });
  addEventListener("blur", closeMenu);
  document.addEventListener("scroll", closeMenu, true);

  // ---------- floating bubble on selected lesson text ----------
  const bubble = document.createElement("div");
  bubble.className = "sel-bubble glass";
  bubble.hidden = true;
  bubble.innerHTML = `<button data-b="copy">Copy</button><button data-b="ask">Ask about this</button>`;
  document.body.appendChild(bubble);
  let bubbleText = "";

  function updateBubble() {
    const s = getSelection();
    const text = String(s || "").trim();
    const anchor = s.rangeCount ? s.getRangeAt(0).commonAncestorContainer : null;
    const host = anchor && (anchor.nodeType === 1 ? anchor : anchor.parentElement);
    if (!text || !host || !host.closest || !host.closest("#col") || host.closest("textarea, input")) { bubble.hidden = true; return; }
    bubbleText = text;
    const r = s.getRangeAt(0).getBoundingClientRect();
    bubble.hidden = false;
    const b = bubble.getBoundingClientRect();
    bubble.style.left = `${Math.max(8, Math.min(r.left + r.width / 2 - b.width / 2, innerWidth - b.width - 8))}px`;
    bubble.style.top = `${r.top - b.height - 10 < 8 ? r.bottom + 10 : r.top - b.height - 10}px`;
  }
  document.addEventListener("mouseup", () => setTimeout(updateBubble, 0));
  document.addEventListener("keyup", (e) => { if (e.shiftKey || e.key === "Shift") updateBubble(); });
  document.addEventListener("selectionchange", () => { if (!String(getSelection() || "").trim()) bubble.hidden = true; });
  document.getElementById("doc")?.addEventListener("scroll", () => { bubble.hidden = true; }, { passive: true });
  bubble.addEventListener("mousedown", async (e) => {
    e.preventDefault();
    const which = e.target.closest("button")?.dataset.b;
    if (which === "copy") { await copy(bubbleText); toast("Copied"); }
    if (which === "ask" && typeof askAbout === "function") askAbout(bubbleText);
    bubble.hidden = true;
    getSelection().removeAllRanges();
  });

  return { copy, read, insert };
})();
