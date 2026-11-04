// Personal Educator UI: sidebar, home, lesson document with inline question cards, floating composer.
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const state = {
  sid: null, session: null, busy: false, cards: [], mode: "think",
  drafts: { think: "", ask: "" }, blocks: [], renderedItems: 0, renderedSid: null, poll: null,
};
const icon = (id) => `<svg><use href="#i-${id}"/></svg>`;
const SUGGESTIONS = [
  "How does a hash table get O(1) lookups?",
  "Recursion and the call stack",
  "Pointers and memory in C++",
  "Why is merge sort O(n log n)?",
  "How do heaps make priority queues fast?",
  "Dijkstra's shortest path, from scratch",
];
const STATUS_TEXT = { waiting: "Waiting for your answer", working: "Teacher is working…", idle: "" };
const TOOL_STATUS = {
  quiz: "Writing your next question", ask_question: "Writing a question", plan_init: "Drawing your lesson plan",
  probe_done: "Summarizing what you know", plan_progress: "Updating your progress",
};

// ---------- helpers ----------
async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
  return res.json();
}
function toast(msg, isErr = false) {
  const el = document.createElement("div");
  el.className = `toast glass ${isErr ? "err" : ""}`;
  el.textContent = msg;
  $("#toasts").appendChild(el);
  setTimeout(() => { el.style.transition = "opacity .4s"; el.style.opacity = "0"; setTimeout(() => el.remove(), 400); }, isErr ? 6000 : 3200);
}
const timeAgo = (iso) => {
  const s = (Date.now() - new Date(iso)) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
};
function autosize(t) { t.style.height = "auto"; t.style.height = Math.min(t.scrollHeight, 260) + "px"; }
const inTextField = () => ["TEXTAREA", "INPUT", "SELECT"].includes(document.activeElement?.tagName);
const nearBottom = () => { const d = $("#doc"); return d.scrollHeight - d.scrollTop - d.clientHeight < 260; };
function scrollToBottom(smooth = true) { const d = $("#doc"); d.scrollTo({ top: d.scrollHeight, behavior: smooth ? "smooth" : "auto" }); }

// ---------- sidebar ----------
async function refreshSidebar() {
  const list = await api("/api/sessions");
  $("#session-list").innerHTML = list.map((s) => `
    <a class="sess ${s.id === state.sid ? "active" : ""}" href="#/s/${s.id}">
      <span class="dot ${s.status}"></span>
      <span class="sess-body"><div class="t">${escapeHTML(s.title)}</div>
      <div class="s ${s.status}">${STATUS_TEXT[s.status] || cap(s.phase)} · ${timeAgo(s.updated_at)}</div></span>
    </a>`).join("") || `<div class="sess"><span class="s">No lessons yet</span></div>`;
  const u = await api("/api/usage");
  const pct = u.budget ? Math.min(100, (u.month_cost / u.budget) * 100) : 0;
  $("#budget").innerHTML = `This month · $${u.month_cost.toFixed(2)} of $${u.budget.toFixed(0)}<div class="bar"><i style="width:${pct}%"></i></div>`;
  if (!state.sid) renderRecent(list);
}
const cap = (s) => s ? s[0].toUpperCase() + s.slice(1) : "";

function renderRecent(list) {
  const top = list.slice(0, 3);
  $("#recent").innerHTML = top.length ? `<div class="side-label" style="margin-left:2px">Continue learning</div>
    <div class="recent-grid">${top.map((s) => `<a class="recent-card glass" href="#/s/${s.id}">
      <div class="t">${escapeHTML(s.title)}</div><div class="s">${STATUS_TEXT[s.status] || cap(s.phase)} · ${timeAgo(s.updated_at)}</div></a>`).join("")}</div>` : "";
}

async function fillSelects() {
  const st = await api("/api/settings");
  const opts = (list, val) => list.map((m) => `<option ${m === val ? "selected" : ""} value="${m}">${m.replace("claude-", "").replace(/-(\d)-(\d)$/, " $1.$2")}</option>`).join("");
  $("#home-model").innerHTML = $("#model").innerHTML = opts(st.models, st.teacher_model);
  $("#home-effort").innerHTML = $("#effort").innerHTML = opts(st.efforts, st.teacher_effort);
  $("#chips").innerHTML = SUGGESTIONS.map((s) => `<button class="chip">${escapeHTML(s)}</button>`).join("");
  $$("#chips .chip").forEach((c) => c.onclick = () => { $("#topic").value = c.textContent; autosize($("#topic")); $("#topic").focus(); });
}

// ---------- routing ----------
async function route() {
  const m = location.hash.match(/^#\/s\/(\w+)/);
  state.sid = m ? m[1] : null;
  clearTimeout(state.poll);
  const inSession = !!state.sid;
  $("#home").hidden = inSession;
  $("#doc").hidden = $("#composer-wrap").hidden = $("#topbar").hidden = !inSession;
  if (!inSession) {
    $("#planpanel").hidden = true;
    await refreshSidebar();
    $("#topic").focus();
    return;
  }
  if (state.renderedSid !== state.sid) {
    state.renderedItems = 0; state.drafts = { think: "", ask: "" };
    $("#composer").value = ""; state.mode = "think";
  }
  setMode(state.mode);
  await loadSession();
  await refreshSidebar();
}

async function loadSession() {
  const s = await api(`/api/sessions/${state.sid}`);
  state.session = s;
  $("#title").textContent = s.title;
  const order = ["probe", "plan", "teach"];
  $$("#stepper span").forEach((el) => {
    const i = order.indexOf(el.dataset.p), cur = order.indexOf(s.phase);
    el.className = i === cur ? "on" : i < cur ? "done" : "";
  });
  $("#model").value = s.model;
  $("#effort").value = s.effort;
  $("#session-meter").textContent = `Session $${s.usage.cost.toFixed(3)}`;
  await renderDoc(s);
  await renderPlan(s.plan);
  if (s.status === "working" && !state.busy) {
    $("#col").insertAdjacentHTML("beforeend", liveHTML("Teacher is working"));
    state.poll = setTimeout(loadSession, 2000);
  }
}

// ---------- lesson document ----------
function lessonHTML(md) {
  state.blocks.push(md);
  const b = state.blocks.length - 1;
  return `<div class="lesson"><div class="hover-tools glass">
      <button class="icon-btn" data-act="copy" data-b="${b}" title="Copy">${icon("copy")}</button>
      <button class="icon-btn" data-act="ask" data-b="${b}" title="Ask about this">${icon("ask")}</button>
    </div>${renderMD(md)}</div>`;
}

const KIND_LABEL = { probe: "Probe", predict: "Predict", check: "Check" };

function answeredQuizHTML(item) {
  const q = item.quiz, a = item.answer || {};
  const opts = q.options || [];
  let body = "";
  if (opts.length) {
    body = `<div class="opts">${opts.map((o, i) => {
      let cls = i === q.correct_index ? "right" : i === a.choice_index ? "wrong" : "";
      return `<div class="opt ${cls}"><span class="key">${i + 1}</span><span class="ot">${renderMD(o)}</span></div>`;
    }).join("")}${a.answer === "I don't know" ? `<div class="opt idk wrong"><span class="key">0</span><span class="ot">I don't know</span></div>` : ""}</div>`;
  } else if (a.answer) {
    body = `<div class="given"><b>Your answer</b>${escapeHTML(a.answer)}</div>`;
  }
  const verdict = a.correct === true ? `<div class="verdict right">${icon("check").replace("<svg>", '<svg width="15" height="15">')} Correct</div>`
    : a.correct === false ? `<div class="verdict wrong">Not quite</div>` : "";
  const meta = [a.confidence && `<div class="given"><b>Confidence</b>${escapeHTML(a.confidence)}</div>`,
                a.thinking && `<div class="given"><b>Thinking</b>${escapeHTML(a.thinking)}</div>`,
                a.learner_interjected_instead_of_answering && `<div class="given"><b>Skipped</b>you asked a question instead</div>`].filter(Boolean).join("");
  return `${q.lesson ? lessonHTML(q.lesson) : ""}
    <div class="qcard glass"><div class="kind ${q.kind}"><i></i>${KIND_LABEL[q.kind] || q.kind}</div>
    <div class="qtext">${renderMD(q.question)}</div>${body}${verdict}${meta}
    ${q.explanation && a.answer && opts.length ? `<div class="explain">${renderMD(q.explanation)}</div>` : ""}</div>`;
}

function answeredAskHTML(item) {
  const q = item.question, a = item.answer || {};
  return `${q.lesson ? lessonHTML(q.lesson) : ""}
    <div class="qcard glass"><div class="kind question"><i></i>Question</div><div class="qtext">${renderMD(q.question)}</div>
    <div class="given"><b>You</b>${escapeHTML(a.answer || a.learner_interjected_instead_of_answering || "")}</div></div>`;
}

function itemHTML(it) {
  switch (it.kind) {
    case "teacher_text": return lessonHTML(it.text);
    case "learner_text": return `<div class="you"><div class="bubble">${escapeHTML(it.text)}</div></div>`;
    case "reading_thinking": return `<div class="you"><div class="bubble"><span class="lbl">Thinking while reading</span>${escapeHTML(it.text)}</div></div>`;
    case "agent_thinking": return `<details class="reasoning"><summary>${icon("chev")}Teacher's reasoning</summary><div class="body">${renderMD(it.text)}</div></details>`;
    case "quiz": return it.answer ? answeredQuizHTML(it) : "";
    case "ask": return it.answer ? answeredAskHTML(it) : "";
    case "probe_done": {
      const s = it.summary;
      const list = (title, xs) => xs?.length ? `\n\n**${title}**\n${xs.map((g) => "- " + g).join("\n")}` : "";
      return `<div class="divider">Probe complete</div><details class="summary-card glass"><summary>What the teacher found</summary>
        <div class="lesson">${renderMD(`**Where you are:** ${s.current_understanding}\n\n**Goal:** ${s.goal}` + list("Gaps", s.gaps) + list("Misconceptions", s.misconceptions))}</div></details>`;
    }
    case "plan": return `<div class="divider">Lesson plan</div><div class="plan-inline" data-plan="${escapeHTML(JSON.stringify(it.plan))}"></div>`;
    default: return "";
  }
}

// Interactive cards for questions waiting on the learner.
function liveCardHTML(c, i) {
  const inp = c.input;
  const lesson = inp.lesson ? lessonHTML(inp.lesson) : "";
  if (c.name === "ask_question") {
    const opts = inp.options || [];
    return `${lesson}<div class="qcard glass live" data-card="${i}"><div class="kind question"><i></i>Question</div>
      <div class="qtext">${renderMD(inp.question)}</div>
      ${opts.length ? `<div class="ask-opts">${opts.map((o, j) => `<button class="opt" data-ask="${j}"><span class="ot">${escapeHTML(o)}</span></button>`).join("")}</div>` : ""}
      <div class="tfield"><textarea id="free-${i}" class="free" rows="1" placeholder="${opts.length ? "Or say it in your own words…" : "Your answer…"}"></textarea>
        <button class="mic" data-mic-for="free-${i}" title="Speak (Ctrl+M)">${icon("mic")}</button></div>
      <div class="card-actions"><span class="kbd-hint"><kbd>↵</kbd> submit · <kbd>⇧↵</kbd> new line</span>
        <button class="btn btn-primary submit">Submit</button></div></div>`;
  }
  const opts = inp.options || [];
  const optsHTML = opts.length
    ? `<div class="opts">${opts.map((o, j) => `<button class="opt" data-choice="${j}"><span class="key">${j + 1}</span><span class="ot">${renderMD(o)}</span></button>`).join("")}
       <button class="opt idk" data-choice="idk"><span class="key">0</span><span class="ot">I don't know</span></button></div>`
    : `<div class="tfield"><textarea id="free-${i}" class="free" rows="2" placeholder="Your answer…"></textarea>
       <button class="mic" data-mic-for="free-${i}" title="Speak (Ctrl+M)">${icon("mic")}</button></div>`;
  return `${lesson}<div class="qcard glass live" data-card="${i}"><div class="kind ${inp.kind}"><i></i>${KIND_LABEL[inp.kind] || inp.kind}</div>
    <div class="qtext">${renderMD(inp.question)}</div>${optsHTML}
    <div class="field-label"><span>Confidence</span></div>
    <div class="conf"><input type="range" min="0" max="100" step="5" value="50" class="untouched"><span class="v">—</span></div>
    <div class="conf-scale"><span>Guessing</span><span>Unsure</span><span>Fairly sure</span><span>Certain</span></div>
    <div class="field-label"><span>Your thinking</span></div>
    <div class="tfield"><textarea id="think-${i}" class="thinking" rows="2" placeholder="Why this answer? Talk it through, messy is fine."></textarea>
      <button class="mic" data-mic-for="think-${i}" title="Speak (Ctrl+M)">${icon("mic")}</button></div>
    <div class="card-actions"><span class="kbd-hint">${opts.length ? `<kbd>1</kbd>–<kbd>${opts.length}</kbd> pick · <kbd>0</kbd> don't know · ` : ""}<kbd>↵</kbd> submit</span>
      <button class="btn btn-primary submit">Submit answer</button></div></div>`;
}

async function renderDoc(s) {
  const col = $("#col");
  const keepScroll = !nearBottom() && state.renderedSid === s.id;
  const prevTop = $("#doc").scrollTop;
  state.blocks = [];
  const isNewSession = state.renderedSid !== s.id;
  const html = s.items.map((it, idx) => {
    const inner = itemHTML(it);
    if (!inner) return "";
    const fresh = !isNewSession && idx >= state.renderedItems;
    return `<div class="item ${fresh ? "new" : ""}">${inner}</div>`;
  });
  state.cards = s.pending.map((p) => ({ ...p, a: { choice: null, idk: false, text: "", confidence: 50, touched: false, thinking: "" } }));
  const cards = state.cards.map((c, i) => `<div class="item new">${liveCardHTML(c, i)}</div>`);
  col.innerHTML = html.join("") + cards.join("");
  state.renderedItems = s.items.length;
  state.renderedSid = s.id;

  for (const el of $$(".plan-inline", col)) {
    const p = JSON.parse(el.dataset.plan);
    await renderPlanInto(el, { ...p, nodes: p.nodes.map((n) => ({ ...n, status: "todo" })) });
  }
  await renderDiagrams(col);
  wireCards();
  Dictation.wire(col);
  if (keepScroll) $("#doc").scrollTop = prevTop;
  else if (state.cards.length) {
    const first = $(".qcard.live", col);
    const lessonAbove = first?.previousElementSibling;
    (lessonAbove || first)?.scrollIntoView({ behavior: isNewSession ? "auto" : "smooth", block: "start" });
  } else scrollToBottom(!isNewSession);
  updateToBottom();
}

async function renderPlan(plan) {
  $("#plan-toggle").hidden = !plan;
  if (!plan) { $("#planpanel").hidden = true; return; }
  let hidden = false;
  try { hidden = localStorage.getItem("planHidden") === "1"; } catch {}
  $("#planpanel").hidden = hidden;
  $("#plan-goal").textContent = plan.goal;
  const done = plan.nodes.filter((n) => n.status === "done").length;
  $("#plan-bar").style.width = `${(done / plan.nodes.length) * 100}%`;
  $("#plan-count").textContent = `${done} of ${plan.nodes.length} steps done`;
  await renderPlanInto($("#plan-map"), plan);
}

// ---------- interactive cards ----------
function cardEl(i) { return $(`.qcard.live[data-card="${i}"]`); }

function selectChoice(i, choice) {
  const c = state.cards[i], el = cardEl(i);
  if (!c || !el || state.busy) return;
  c.a.idk = choice === "idk";
  c.a.choice = c.a.idk ? null : +choice;
  $$(".opt[data-choice]", el).forEach((o) => o.classList.toggle("sel", o.dataset.choice === String(choice)));
  $(".card-error", el)?.remove();
}

function wireCards() {
  state.cards.forEach((c, i) => {
    const el = cardEl(i);
    if (!el) return;
    $$(".opt[data-choice]", el).forEach((b) => b.onclick = () => selectChoice(i, b.dataset.choice));
    $$(".opt[data-ask]", el).forEach((b) => b.onclick = () => {
      if (state.busy) return;
      c.a.choice = c.a.choice === +b.dataset.ask ? null : +b.dataset.ask;
      $$(".opt[data-ask]", el).forEach((o) => o.classList.toggle("sel", +o.dataset.ask === c.a.choice));
      // picking a suggested answer with nothing typed submits right away
      if (c.a.choice !== null && !c.a.text.trim() && state.cards.length === 1) submitCards();
    });
    const range = $('input[type="range"]', el);
    if (range) range.oninput = () => {
      c.a.confidence = +range.value; c.a.touched = true;
      range.classList.remove("untouched");
      range.style.setProperty("--p", `${range.value}%`);
      const v = range.nextElementSibling; v.textContent = `${range.value}%`; v.classList.add("set");
    };
    $$("textarea", el).forEach((t) => {
      t.addEventListener("input", () => {
        autosize(t);
        if (t.classList.contains("thinking")) c.a.thinking = t.value; else c.a.text = t.value;
      });
      t.onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); submitCards(); } };
    });
    $(".submit", el).onclick = submitCards;
  });
}

function cardError(i, msg) {
  const el = cardEl(i);
  $(".card-error", el)?.remove();
  $(".card-actions", el).insertAdjacentHTML("beforebegin", `<div class="card-error">${escapeHTML(msg)}</div>`);
}

function submitCards() {
  if (state.busy || !state.cards.length) return;
  const answers = {};
  for (const [i, c] of state.cards.entries()) {
    if (c.name === "quiz") {
      const hasOpts = (c.input.options || []).length;
      if (hasOpts && c.a.choice === null && !c.a.idk) return cardError(i, "Pick an option, or “I don't know”.");
      if (!hasOpts && !c.a.text.trim()) return cardError(i, "Type or say an answer first.");
      answers[c.id] = { choice: c.a.choice, idk: c.a.idk, text: c.a.text, thinking: c.a.thinking,
                        confidence: c.a.touched ? c.a.confidence : null };
    } else {
      const picked = c.a.choice !== null ? c.input.options[c.a.choice] : "";
      const text = [picked, c.a.text.trim()].filter(Boolean).join(" — ");
      if (!text) return cardError(i, "Choose an option or type an answer.");
      answers[c.id] = { text };
    }
  }
  // instant feedback: lock the cards and show the button working
  state.cards.forEach((_, i) => {
    const el = cardEl(i);
    $$("button, textarea, input", el).forEach((x) => x.disabled = true);
    $(".submit", el).innerHTML = `<span class="spinner"></span>Checking`;
  });
  sendTurn({ answers });
}

function revealGrades(feedback) {
  state.cards.forEach((c, i) => {
    const fb = feedback[c.id], el = cardEl(i);
    if (!el) return;
    $(".card-actions", el)?.remove();
    if (!fb) return;
    $$(".opt[data-choice]", el).forEach((o) => {
      const j = o.dataset.choice === "idk" ? -1 : +o.dataset.choice;
      if (j === fb.correct_index) o.classList.add("right", "reveal");
      else if (o.classList.contains("sel")) o.classList.add("wrong", "shake");
    });
    el.insertAdjacentHTML("beforeend",
      (fb.correct ? `<div class="verdict right">${icon("check").replace("<svg>", '<svg width="15" height="15">')} Correct</div>`
                  : `<div class="verdict wrong">Not quite</div>`) +
      (fb.explanation ? `<div class="explain">${renderMD(fb.explanation)}</div>` : ""));
    renderDiagrams(el);
  });
}

// ---------- sending a turn + live streaming ----------
function liveHTML(label) {
  return `<div class="item new" id="live"><div class="thinking-live"><span class="orb"></span>
    <div class="status"><div class="shimmer" id="live-label">${escapeHTML(label)}</div><div class="line" id="live-line"></div></div></div>
    <div id="live-text"></div></div>`;
}

async function sendTurn({ answers = {}, message = "" }) {
  if (state.busy) return;
  const reading = (state.mode === "think" ? $("#composer").value : state.drafts.think).trim();
  setBusy(true);
  const col = $("#col");
  if (message) col.insertAdjacentHTML("beforeend", `<div class="item new"><div class="you"><div class="bubble">${escapeHTML(message)}</div></div></div>`);
  if (reading) col.insertAdjacentHTML("beforeend", `<div class="item new"><div class="you"><div class="bubble"><span class="lbl">Thinking while reading</span>${escapeHTML(reading)}</div></div></div>`);
  $("#live")?.remove();
  col.insertAdjacentHTML("beforeend", liveHTML("Thinking"));
  scrollToBottom();

  let thinking = "", text = "", errorMsg = "";
  try {
    const res = await fetch(`/api/sessions/${state.sid}/turn`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers, message, reading_thinking: reading }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    if (reading) {
      state.drafts.think = "";
      if (state.mode === "think") { $("#composer").value = ""; autosize($("#composer")); }
    }
    if (message) { state.drafts.ask = ""; if (state.mode === "ask") { $("#composer").value = ""; autosize($("#composer")); } }
    updateNoteChip();

    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const line = buf.slice(0, idx); buf = buf.slice(idx + 2);
        if (!line.startsWith("data: ")) continue;
        const evt = JSON.parse(line.slice(6));
        const stick = nearBottom();
        if (evt.type === "graded") revealGrades(evt.feedback);
        else if (evt.type === "thinking_delta") {
          thinking += evt.text;
          const sentences = thinking.trim().split(/[.!?]\s+/);
          const lineEl = $("#live-line"); if (lineEl) lineEl.textContent = sentences[sentences.length - 1] || "";
        } else if (evt.type === "text_delta") {
          text += evt.text;
          const t = $("#live-text"); if (t) t.innerHTML = `<div class="lesson">${renderMD(text)}</div>`;
        } else if (evt.type === "block_start") {
          const lbl = $("#live-label");
          if (lbl) lbl.textContent = evt.block_type === "tool_use" ? (TOOL_STATUS[evt.name] || "Working") : evt.block_type === "thinking" ? "Thinking" : "Writing";
          if (evt.block_type === "text" && text) text += "\n\n";
        } else if (evt.type === "usage") $("#session-meter").textContent = `Session $${evt.session_cost.toFixed(3)}`;
        else if (evt.type === "error") errorMsg = evt.message;
        if (stick) scrollToBottom(false);
      }
    }
  } catch (e) { errorMsg = e.message; }
  setBusy(false);
  if (errorMsg) toast(errorMsg, true);
  await loadSession();
  refreshSidebar();
}

function setBusy(b) {
  state.busy = b;
  updateSendBtn();
}

// ---------- composer (Thinking note / Ask) ----------
function setMode(mode) {
  const ta = $("#composer");
  state.drafts[state.mode] = ta.value;
  state.mode = mode;
  ta.value = state.drafts[mode] || "";
  autosize(ta);
  $$("#seg button").forEach((b) => b.classList.toggle("on", b.dataset.mode === mode));
  const on = $(`#seg button[data-mode="${mode}"]`), bg = $("#seg .pill-bg");
  if (on && on.offsetWidth) { bg.style.left = `${on.offsetLeft}px`; bg.style.width = `${on.offsetWidth}px`; }
  ta.placeholder = mode === "think" ? "Thinking while reading… (sent with your next answer)" : "Ask a question or steer the lesson…";
  updateSendBtn();
  updateNoteChip();
}
function updateSendBtn() {
  const btn = $("#send-btn");
  btn.hidden = state.mode === "think";
  btn.disabled = state.busy || !$("#composer").value.trim();
}
function updateNoteChip() {
  const chip = $("#note-chip");
  const note = state.mode === "think" ? $("#composer").value.trim() : state.drafts.think.trim();
  chip.hidden = !note;
  chip.textContent = "Your note will be sent with your next answer";
}
function sendAsk() {
  const m = $("#composer").value.trim();
  if (!m || state.busy) return;
  sendTurn({ message: m });
}

// ---------- hover tools ----------
$("#col").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-act]");
  if (!b) return;
  const md = state.blocks[+b.dataset.b] || "";
  if (b.dataset.act === "copy") {
    if (await Clip.copy(md)) toast("Copied");
  } else if (b.dataset.act === "ask") {
    askAbout(md.replace(/```[\s\S]*?```/g, "[code]"));
  }
});

// Quote some lesson text into the Ask box (used by hover tools, right-click menu, selection bubble).
function askAbout(text) {
  if (!state.sid) return;
  setMode("ask");
  const plain = String(text).replace(/\s+/g, " ").trim().slice(0, 180);
  $("#composer").value = `About “${plain}${plain.length >= 180 ? "…" : ""}”: `;
  autosize($("#composer")); updateSendBtn();
  const ta = $("#composer");
  ta.focus();
  ta.setSelectionRange(ta.value.length, ta.value.length);
}

// ---------- start / wiring ----------
async function startLesson() {
  const topic = $("#topic").value.trim();
  if (!topic) return $("#topic").focus();
  $("#start-btn").disabled = true;
  try {
    const s = await api("/api/sessions", { method: "POST",
      body: JSON.stringify({ topic, model: $("#home-model").value, effort: $("#home-effort").value }) });
    $("#topic").value = ""; autosize($("#topic"));
    location.hash = `#/s/${s.id}`;
    await route();
    await sendTurn({ message: topic });
  } catch (e) { toast(e.message, true); }
  finally { $("#start-btn").disabled = false; }
}

function updateToBottom() { $("#to-bottom").classList.toggle("show", !!state.sid && !nearBottom()); }

$("#start-btn").onclick = startLesson;
$("#topic").addEventListener("input", () => autosize($("#topic")));
$("#topic").onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); startLesson(); } };
$("#new-btn").onclick = () => { location.hash = ""; };
$("#send-btn").onclick = sendAsk;
$("#composer").addEventListener("input", () => { autosize($("#composer")); updateSendBtn(); updateNoteChip(); });
$("#composer").onkeydown = (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing && state.mode === "ask") { e.preventDefault(); sendAsk(); }
};
$$("#seg button").forEach((b) => b.onclick = () => { setMode(b.dataset.mode); $("#composer").focus(); });
$("#doc").addEventListener("scroll", updateToBottom, { passive: true });
$("#to-bottom").onclick = () => scrollToBottom();
const setPlanHidden = (hide) => { $("#planpanel").hidden = hide; try { localStorage.setItem("planHidden", hide ? "1" : "0"); } catch {} };
$("#plan-toggle").onclick = () => setPlanHidden(!$("#planpanel").hidden);
$("#plan-close").onclick = () => setPlanHidden(true);
for (const sel of ["#model", "#effort"]) $(sel).onchange = () => state.sid && api(`/api/sessions/${state.sid}`, {
  method: "PATCH", body: JSON.stringify({ model: $("#model").value, effort: $("#effort").value }) });

// keyboard: 1-5 pick, 0 = don't know, Enter submits (when not typing)
document.addEventListener("keydown", (e) => {
  if (!state.sid || inTextField() || e.metaKey || e.ctrlKey || e.altKey) return;
  const live = state.cards.findIndex((c) => c.name === "quiz" && (c.input.options || []).length);
  if (/^[0-9]$/.test(e.key) && live >= 0) {
    const n = +e.key, opts = state.cards[live].input.options;
    if (n === 0) selectChoice(live, "idk");
    else if (n <= opts.length) selectChoice(live, n - 1);
    e.preventDefault();
  } else if (e.key === "Enter" && state.cards.length) { e.preventDefault(); submitCards(); }
});

$$("[data-motion]").forEach((b) => b.onclick = () => Motion.set(b.dataset.motion));
window.addEventListener("hashchange", route);
Dictation.wire(document);
fillSelects().then(route).then(() => setMode("think"));
