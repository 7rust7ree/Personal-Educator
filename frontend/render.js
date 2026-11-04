// Markdown + KaTeX math + Mermaid diagrams, sanitized.
mermaid.initialize({
  startOnLoad: false, securityLevel: "strict", theme: "base",
  themeVariables: {
    darkMode: true, background: "transparent", fontFamily: "-apple-system, Inter, sans-serif", fontSize: "14px",
    primaryColor: "#121827", primaryTextColor: "#f5f5f7", primaryBorderColor: "#2997ff",
    secondaryColor: "#161b2b", tertiaryColor: "#0e1220", lineColor: "#5b7fb0", textColor: "#d6d6dd",
    mainBkg: "#121827", nodeBorder: "#2997ff", clusterBkg: "#0e1220", clusterBorder: "#2a3550",
    edgeLabelBackground: "#0b0e16", noteBkgColor: "#161b2b", noteTextColor: "#f5f5f7",
  },
  flowchart: { curve: "basis", padding: 14, htmlLabels: false, wrappingWidth: 160 },
});
marked.setOptions({ gfm: true, breaks: false });

// Pull math out before Markdown parsing (so _ and * inside math survive), skipping code.
function protectMath(src) {
  const math = [];
  const parts = src.split(/(```[\s\S]*?```|`[^`\n]*`)/g);
  const out = parts.map((part, i) => {
    if (i % 2 === 1) return part; // code: leave alone
    return part
      .replace(/\$\$([\s\S]+?)\$\$/g, (_, tex) => { math.push([tex, true]); return `MATHPH${math.length - 1}X`; })
      .replace(/\\\[([\s\S]+?)\\\]/g, (_, tex) => { math.push([tex, true]); return `MATHPH${math.length - 1}X`; })
      .replace(/\\\((.+?)\\\)/g, (_, tex) => { math.push([tex, false]); return `MATHPH${math.length - 1}X`; })
      .replace(/(^|[^\\$])\$([^\s$](?:[^$\n]*?[^\s$])?)\$(?!\d)/g,
        (_, pre, tex) => { math.push([tex, false]); return `${pre}MATHPH${math.length - 1}X`; });
  }).join("");
  return { text: out, math };
}

function renderMD(src) {
  const { text, math } = protectMath(src || "");
  let html = DOMPurify.sanitize(marked.parse(text));
  html = html.replace(/MATHPH(\d+)X/g, (_, i) => {
    const [tex, display] = math[+i];
    try {
      return katex.renderToString(tex, { displayMode: display, throwOnError: false, trust: false });
    } catch { return tex; }
  });
  return html;
}

let mermaidSeq = 0;
// Turn ```mermaid code blocks inside `el` into rendered diagrams.
const fontsReady = () => (document.fonts && document.fonts.ready) || Promise.resolve();

async function renderDiagrams(el) {
  const blocks = el.querySelectorAll("code.language-mermaid");
  if (blocks.length) await fontsReady();
  for (const code of blocks) {
    const src = code.textContent;
    const div = document.createElement("div");
    div.className = "mermaid";
    try {
      const { svg } = await mermaid.render(`mmd${mermaidSeq++}`, src);
      div.innerHTML = svg;
    } catch {
      div.innerHTML = `<pre>${escapeHTML(src)}</pre>`;
    }
    code.closest("pre").replaceWith(div);
  }
}

function escapeHTML(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Plan nodes -> Mermaid flowchart source, coloured by status.
function planToMermaid(plan) {
  const id = (s) => "n_" + String(s).replace(/[^A-Za-z0-9_]/g, "_");
  const label = (s) => String(s).replace(/["<>]/g, "'");
  const lines = ["flowchart TD"];
  for (const n of plan.nodes) lines.push(`  ${id(n.id)}["${label(n.title)}"]`);
  for (const n of plan.nodes) for (const d of n.depends_on || []) lines.push(`  ${id(d)} --> ${id(n.id)}`);
  lines.push("  classDef done fill:#0d2a19,stroke:#30d158,color:#f5f5f7");
  lines.push("  classDef active fill:#0b2747,stroke:#64d2ff,color:#ffffff,stroke-width:2.5px");
  lines.push("  classDef todo fill:#121622,stroke:#39425a,color:#c9c9d1");
  for (const n of plan.nodes) lines.push(`  class ${id(n.id)} ${n.status || "todo"}`);
  return lines.join("\n");
}

async function renderPlanInto(el, plan) {
  await fontsReady();
  try {
    const { svg } = await mermaid.render(`plan${mermaidSeq++}`, planToMermaid(plan));
    el.innerHTML = `<div class="mermaid">${svg}</div>`;
  } catch {
    el.innerHTML = "<ol>" + plan.nodes.map((n) => `<li>${escapeHTML(n.title)} <small>(${n.status || "todo"})</small></li>`).join("") + "</ol>";
  }
}
