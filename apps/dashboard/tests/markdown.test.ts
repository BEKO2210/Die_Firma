import { describe, expect, it } from "vitest";
import { escapeHtml, renderMarkdown } from "../src/lib/markdown.ts";

describe("renderMarkdown", () => {
  it("escapes HTML to prevent XSS", () => {
    const html = renderMarkdown('<img src=x onerror=alert(1)> & "quote"');
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img");
    expect(html).toContain("&amp;");
  });

  it("renders fenced code blocks verbatim with a language tag", () => {
    const html = renderMarkdown("```py\nprint('<hi>')\n```");
    expect(html).toContain('<pre data-lang="py">');
    expect(html).toContain("<code>print('&lt;hi&gt;')</code>");
  });

  it("renders inline code, bold, italic and headings", () => {
    expect(renderMarkdown("# Title")).toBe("<h1>Title</h1>");
    expect(renderMarkdown("use `x` here")).toContain("<code>x</code>");
    expect(renderMarkdown("**b**")).toContain("<strong>b</strong>");
    expect(renderMarkdown("a *i* b")).toContain("<em>i</em>");
  });

  it("renders unordered lists", () => {
    const html = renderMarkdown("- one\n- two");
    expect(html).toBe("<ul><li>one</li><li>two</li></ul>");
  });

  it("renders paragraphs and only allows http(s) links", () => {
    expect(renderMarkdown("hello")).toBe("<p>hello</p>");
    const ok = renderMarkdown("[site](https://example.com)");
    expect(ok).toContain('href="https://example.com"');
    expect(ok).toContain('rel="noopener noreferrer"');
    // javascript: scheme is not matched -> rendered as plain text, no anchor
    const bad = renderMarkdown("[x](javascript:alert(1))");
    expect(bad).not.toContain("<a ");
  });

  it("handles text before and after a code block", () => {
    const html = renderMarkdown("intro\n```js\nx\n```\nouter");
    expect(html).toContain("<p>intro</p>");
    expect(html).toContain('<pre data-lang="js">');
    expect(html).toContain("<p>outer</p>");
  });

  it("separates paragraphs on blank lines", () => {
    expect(renderMarkdown("a\n\nb")).toBe("<p>a</p><p>b</p>");
  });

  it("renders italic at the start of a line", () => {
    expect(renderMarkdown("*i* tail")).toContain("<em>i</em>");
  });

  it("flushes a list before following text", () => {
    const html = renderMarkdown("- a\ntext");
    expect(html).toBe("<ul><li>a</li></ul><p>text</p>");
  });

  it("escapeHtml handles the core entities", () => {
    expect(escapeHtml('<&>"')).toBe("&lt;&amp;&gt;&quot;");
  });
});
