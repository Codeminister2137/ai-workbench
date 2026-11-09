"use strict";
/* Minimal Markdown renderer for document previews.
 * Escape-first: raw HTML in the source is shown as text, never passed through.
 * Covers headings, fenced code, lists, quotes, rules, tables, paragraphs,
 * and inline code/bold/italic/links. Nested lists render flattened. */

function mdEscape(text) {
  return String(text).replace(/[&<>"']/g, (ch) => (
    {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[ch]
  ));
}

function mdSafeHref(raw) {
  const url = String(raw).trim();
  if (url.startsWith("#")) return url;
  const lower = url.toLowerCase();
  if (lower.startsWith("http://") || lower.startsWith("https://") || lower.startsWith("mailto:")) {
    return url;
  }
  if (/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(url)) return null;
  if (url.includes("\\")) return null;
  return url;
}

function mdInline(src) {
  const codeSpans = [];
  const withoutCode = mdEscape(src).replace(/(`+)([\s\S]*?)\1/g, (match, _ticks, code) => {
    codeSpans.push(code);
    return "\0" + (codeSpans.length - 1) + "\0";
  });
  const linked = withoutCode.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (match, text, href) => {
    const safe = mdSafeHref(href);
    if (safe === null) return text;
    return `<a href="${mdEscape(safe)}" rel="noopener">${text}</a>`;
  });
  const bolded = linked
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
  return bolded.replace(/\0(\d+)\0/g, (_match, id) => `<code>${codeSpans[Number(id)]}</code>`);
}

function mdToHtml(src) {
  const lines = String(src).replace(/\r\n?/g, "\n").split("\n");
  const blocks = [];
  let paragraph = [];
  let list = null;
  let fence = null;

  function flushParagraph() {
    if (paragraph.length) {
      blocks.push(`<p>${mdInline(paragraph.join(" "))}</p>`);
      paragraph = [];
    }
  }
  function flushList() {
    if (list) {
      const tag = list.ordered ? "ol" : "ul";
      blocks.push(`<${tag}>` + list.items.map((item) => `<li>${mdInline(item)}</li>`).join("") + `</${tag}>`);
      list = null;
    }
  }

  function tableCells(row) {
    let cells = row.trim();
    if (cells.startsWith("|")) cells = cells.slice(1);
    if (cells.endsWith("|")) cells = cells.slice(0, -1);
    return cells.split("|").map((cell) => cell.trim());
  }
  function isDelimiterRow(row) {
    const cells = tableCells(row);
    return cells.length > 0 && cells.every((cell) => /^:?-+:?$/.test(cell));
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (fence !== null) {
      if (/^\s*```/.test(line)) {
        blocks.push(`<pre><code>${mdEscape(fence.join("\n"))}</code></pre>`);
        fence = null;
      } else {
        fence.push(line);
      }
      continue;
    }
    const fenceOpen = line.match(/^\s*```/);
    if (fenceOpen) {
      flushParagraph();
      flushList();
      fence = [];
      continue;
    }
    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      flushParagraph();
      flushList();
      const level = heading[1].length;
      blocks.push(`<h${level}>${mdInline(heading[2].trim())}</h${level}>`);
      continue;
    }
    if (/^\s*(---|\*\*\*|___)\s*$/.test(line)) {
      flushParagraph();
      flushList();
      blocks.push("<hr>");
      continue;
    }
    const quote = line.match(/^\s*>\s?(.*)$/);
    if (quote) {
      flushParagraph();
      flushList();
      blocks.push(`<blockquote>${mdInline(quote[1])}</blockquote>`);
      continue;
    }
    const bullet = line.match(/^\s*[-*+]\s+(.*)$/);
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (bullet || numbered) {
      flushParagraph();
      const ordered = Boolean(numbered);
      const item = (bullet || numbered)[1];
      if (!list || list.ordered !== ordered) {
        flushList();
        list = { ordered, items: [] };
      }
      list.items.push(item);
      continue;
    }
    if (/^\s*\|/.test(line) && isDelimiterRow(lines[i + 1] || "")) {
      flushParagraph();
      flushList();
      const head = tableCells(line);
      const rows = [];
      let j = i + 2;
      while (j < lines.length && /^\s*\|/.test(lines[j]) && !/^\s*$/.test(lines[j])) {
        rows.push(tableCells(lines[j]));
        j++;
      }
      const headHtml = head.map((cell) => `<th>${mdInline(cell)}</th>`).join("");
      const rowsHtml = rows.map((row) =>
        "<tr>" + row.map((cell) => `<td>${mdInline(cell)}</td>`).join("") + "</tr>").join("");
      blocks.push(`<table><thead><tr>${headHtml}</tr></thead><tbody>${rowsHtml}</tbody></table>`);
      i = j - 1;
      continue;
    }
    if (/^\s*$/.test(line)) {
      flushParagraph();
      flushList();
      continue;
    }
    if (list) {
      // Lazy continuation line: no blank line since the last item,
      // so this text belongs to the open item, not a stray paragraph.
      list.items[list.items.length - 1] += " " + line.trim();
      continue;
    }
    paragraph.push(line.trim());
  }
  if (fence !== null) {
    blocks.push(`<pre><code>${mdEscape(fence.join("\n"))}</code></pre>`);
  }
  flushParagraph();
  flushList();
  return blocks.join("");
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { mdToHtml, mdInline, mdEscape, mdSafeHref };
}
