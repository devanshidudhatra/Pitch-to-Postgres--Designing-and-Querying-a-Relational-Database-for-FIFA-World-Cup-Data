"""
Pitch to Postgres: Designing and Querying a Relational Database for FIFA World Cup Data
Convert a Markdown document in docs/ to PDF.

Markdown -> HTML (python-markdown, with tables) -> PDF (headless Chrome or Edge).
```mermaid blocks are drawn as diagrams by mermaid.js (loaded from cdn.jsdelivr.net,
so an internet connection is needed for documents that contain diagrams).

Usage:  python src/md_to_pdf.py docs/milestone1.md [more.md ...]
"""

from __future__ import annotations

import html
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]

CSS = """
@page { size: A4; margin: 16mm 14mm 16mm 14mm; }
body { font-family: "Segoe UI", Arial, sans-serif; font-size: 10pt; line-height: 1.45; color: #1a1a1a; }
h1 { font-size: 20pt; color: #0b3d2e; margin: 0 0 6pt; }
h2 { font-size: 14pt; color: #0b3d2e; border-bottom: 1.5pt solid #0b3d2e; padding-bottom: 2pt; margin-top: 18pt; page-break-after: avoid; }
h3 { font-size: 11.5pt; color: #14532d; margin-top: 12pt; page-break-after: avoid; }
h4 { font-size: 10.5pt; margin-top: 10pt; page-break-after: avoid; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-size: 8.6pt; page-break-inside: auto; }
tr { page-break-inside: avoid; }
th { background: #e6efe9; text-align: left; }
th, td { border: 0.6pt solid #b9c7be; padding: 3pt 4pt; vertical-align: top; }
code { font-family: Consolas, "Courier New", monospace; font-size: 8.8pt; background: #f3f5f4; padding: 0 2pt; }
pre { background: #f3f5f4; border: 0.6pt solid #d5ddd8; padding: 6pt; font-size: 8.2pt; white-space: pre-wrap; word-break: break-word; }
pre code { background: none; padding: 0; }
img { max-width: 100%; max-height: 245mm; display: block; margin: 6pt auto; }
.figure { page-break-inside: avoid; text-align: center; }
pre.sql { font-size: 7.4pt; }
pre.mermaid { background: none; border: none; text-align: center; page-break-inside: avoid; }
blockquote { border-left: 3pt solid #0b3d2e; margin: 6pt 0; padding: 2pt 10pt; background: #f6faf7; }
.titlepage { text-align: center; padding-top: 70mm; page-break-after: always; }
.titlepage h1 { font-size: 24pt; }
.titlepage .sub { font-size: 14pt; margin: 14pt 0 30pt; color: #14532d; }
.titlepage table { width: 70%; margin: 0 auto; font-size: 10.5pt; }
.titlepage .meta { margin-top: 26pt; font-size: 10pt; color: #444; }
.pagebreak { page-break-before: always; }
a { color: #14532d; }
"""

MERMAID = """
<script type="module">
import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs";
mermaid.initialize({ startOnLoad: false, theme: "neutral", er: { useMaxWidth: true }, flowchart: { useMaxWidth: true } });
await mermaid.run({ querySelector: "pre.mermaid" });
document.body.setAttribute("data-rendered", "1");
</script>
"""


def find_browser() -> str:
    for b in BROWSERS:
        if Path(b).exists():
            return b
    raise SystemExit("Chrome or Edge not found; install one or add its path to BROWSERS.")


def expand_includes(md_text: str, base: Path) -> str:
    """Replace lines '<!-- include: path -->' with the file content in a code block (path relative to the .md file)."""
    def repl(m):
        f = (base / m.group(1).strip()).resolve()
        lang = "sql" if f.suffix == ".sql" else ""
        return "```" + lang + "\n" + f.read_text(encoding="utf-8").rstrip() + "\n```"
    return re.sub(r"^<!--\s*include:\s*(.+?)\s*-->\s*$", repl, md_text, flags=re.M)


def to_html(md_text: str, title: str, base: Path | None = None) -> str:
    body = markdown.markdown(md_text, extensions=["tables", "fenced_code", "sane_lists", "attr_list", "md_in_html"])
    # turn ```mermaid code blocks into <pre class="mermaid"> for mermaid.js
    body = re.sub(r'<pre><code class="language-mermaid">(.*?)</code></pre>',
                  lambda m: f'<pre class="mermaid">{m.group(1)}</pre>', body, flags=re.S)
    has_mermaid = 'class="mermaid"' in body
    body = body.replace('<pre><code class="language-sql">', '<pre class="sql"><code class="language-sql">')
    base_tag = f"<base href='{base.as_uri()}/'>" if base else ""
    return (f"<!doctype html><html><head><meta charset='utf-8'>{base_tag}<title>{html.escape(title)}</title>"
            f"<style>{CSS}</style></head><body>{body}{MERMAID if has_mermaid else ''}</body></html>")


def convert(md_path: Path) -> Path:
    md_text = expand_includes(md_path.read_text(encoding="utf-8"), md_path.parent)
    m = re.search(r"^#\s+(.+)$", md_text, flags=re.M)
    title = m.group(1).strip() if m else md_path.stem
    pdf_path = md_path.with_suffix(".pdf")
    with tempfile.TemporaryDirectory() as tmp:
        html_path = Path(tmp) / (md_path.stem + ".html")
        html_path.write_text(to_html(md_text, title, md_path.parent), encoding="utf-8")
        cmd = [find_browser(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
               "--run-all-compositor-stages-before-draw", "--virtual-time-budget=20000",
               f"--print-to-pdf={pdf_path}", html_path.as_uri()]
        subprocess.run(cmd, check=True, capture_output=True, timeout=180)
    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        raise SystemExit(f"PDF was not produced for {md_path}")
    return pdf_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    for arg in sys.argv[1:]:
        out = convert(Path(arg).resolve())
        print(f"Wrote {out} ({out.stat().st_size // 1024} KB)")
