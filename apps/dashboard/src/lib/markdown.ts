// Minimal, safe Markdown -> HTML for chat answers (review §UX). Dependency-free
// and XSS-safe: all text is HTML-escaped first, then a small, fixed set of
// constructs is rendered into known-safe tags. Fenced code blocks are extracted
// before escaping so their contents are shown verbatim. Supports: fenced + inline
// code, bold, italic, headings, unordered lists, links (http/https only),
// paragraphs and line breaks.

export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Inline formatting applied to already-escaped text. */
function inline(escaped: string): string {
  let out = escaped;
  // inline code first so its contents aren't further formatted
  out = out.replace(/`([^`]+)`/g, (_m, c) => `<code>${c}</code>`);
  // links [text](http(s)://url) — scheme allow-listed
  out = out.replace(
    /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    (_m, text, url) => `<a href="${url}" target="_blank" rel="noopener noreferrer">${text}</a>`,
  );
  // bold then italic
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>");
  return out;
}

interface Block {
  code?: { lang: string; body: string };
  text?: string;
}

/** Split into fenced-code blocks and everything else (pre-escape). */
function splitFences(src: string): Block[] {
  const blocks: Block[] = [];
  const fence = /```([\w+-]*)\n?([\s\S]*?)```/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = fence.exec(src)) !== null) {
    if (m.index > last) blocks.push({ text: src.slice(last, m.index) });
    // The regex groups always match (lang is `[\w+-]*`, body is `[\s\S]*?`).
    blocks.push({ code: { lang: m[1]!.trim(), body: m[2]! } });
    last = fence.lastIndex;
  }
  if (last < src.length) blocks.push({ text: src.slice(last) });
  return blocks;
}

/** Render a non-code text block (headings, lists, paragraphs). */
function renderText(text: string): string {
  const lines = text.split("\n");
  const html: string[] = [];
  let list: string[] = [];
  const flushList = () => {
    if (list.length) {
      html.push(`<ul>${list.map((li) => `<li>${inline(li)}</li>`).join("")}</ul>`);
      list = [];
    }
  };
  for (const raw of lines) {
    const line = raw.trimEnd();
    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    const bullet = /^[-*]\s+(.*)$/.exec(line);
    if (heading) {
      flushList();
      const level = heading[1]!.length;
      html.push(`<h${level}>${inline(heading[2]!)}</h${level}>`);
    } else if (bullet) {
      list.push(bullet[1]!);
    } else if (line.trim() === "") {
      flushList();
    } else {
      flushList();
      html.push(`<p>${inline(line)}</p>`);
    }
  }
  flushList();
  return html.join("");
}

/** Render Markdown to safe HTML. */
export function renderMarkdown(src: string): string {
  return splitFences(src)
    .map((b) =>
      b.code
        ? `<pre data-lang="${escapeHtml(b.code.lang)}"><code>${escapeHtml(b.code.body.replace(/\n$/, ""))}</code></pre>`
        : renderText(escapeHtml(b.text!)),
    )
    .join("");
}
