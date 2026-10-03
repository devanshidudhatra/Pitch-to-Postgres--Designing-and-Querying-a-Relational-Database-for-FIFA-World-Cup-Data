"""
Pitch to Postgres: Designing and Querying a Relational Database for FIFA World Cup Data
Execute a notebook top to bottom (saving its outputs) and export it to HTML and PDF.

PDF route: nbconvert HTML -> headless Chrome/Edge "print to PDF" (no LaTeX needed).
The notebook runs with the notebooks/ folder as working directory and uses the database in .env.

Usage:  python src/run_notebook.py notebooks/03_load_data.ipynb [--no-exec]
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import nbformat
from nbclient import NotebookClient
from nbconvert import HTMLExporter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from md_to_pdf import find_browser  # noqa: E402

PRINT_CSS = """<style>
@page { size: A4; margin: 12mm 10mm; }
body { font-size: 11px; }
.jp-Notebook { padding: 0 !important; }
.jp-InputPrompt, .jp-OutputPrompt { min-width: 52px !important; font-size: 9px; }
.jp-RenderedHTMLCommon table { font-size: 9.5px; }
pre { white-space: pre-wrap !important; word-break: break-word; }
.jp-Cell { break-inside: auto; }
.jp-OutputArea-output pre { font-size: 9.5px; }
</style>"""


def run(nb_path: Path, execute: bool = True) -> Path:
    nb = nbformat.read(nb_path, as_version=4)
    if execute:
        client = NotebookClient(nb, timeout=900, kernel_name="python3",
                                resources={"metadata": {"path": str(nb_path.parent)}})
        client.execute()
        nbformat.write(nb, nb_path)
        print(f"Executed and saved {nb_path.name}")
    html, _ = HTMLExporter(template_name="lab").from_notebook_node(nb)
    html = html.replace("</head>", PRINT_CSS + "</head>", 1)
    pdf = nb_path.with_suffix(".pdf")
    with tempfile.TemporaryDirectory() as tmp:
        h = Path(tmp) / (nb_path.stem + ".html")
        h.write_text(html, encoding="utf-8")
        subprocess.run([find_browser(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        "--virtual-time-budget=20000", f"--print-to-pdf={pdf}", h.as_uri()],
                       check=True, capture_output=True, timeout=300)
    print(f"Wrote {pdf} ({pdf.stat().st_size // 1024} KB)")
    return pdf


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    for a in args:
        run(Path(a).resolve(), execute="--no-exec" not in sys.argv)
