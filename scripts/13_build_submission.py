"""Build the submission in Apart's official template: paper/report_apart.docx.

  - the title / author / abstract box is the template's own first table, filled in
  - the template's "How to use this template" box and guidance text are dropped
  - the report body (from paper/report.md) is converted with pandoc using the template as the
    reference document, so it inherits the template's page size, margins, fonts and heading styles

Run:  uv run --with pypandoc_binary --with python-docx python scripts/13_build_submission.py
      (then export to PDF with Word; see scripts/14_export_pdf.ps1)
"""
from __future__ import annotations

import copy
import re
from pathlib import Path

import docx
import pypandoc

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper"
TEMPLATE = PAPER / "template" / "apart_template.docx"
AUTHOR_LINE = "Raj Gupta · Independent researcher"
EVENT_LINE = "AI x Epistemics Research Sprint (Apart Research), 13–16 November 2026"
CODE_LINE = "Code and data: https://github.com/rajkumar0932/Evidence-Audit-of-AI-Written-Community-Notes"


def plain(md: str) -> str:
    md = re.sub(r"\*\*(.+?)\*\*", r"\1", md)
    md = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"\1", md)
    return md.replace("`", "")


def register_font_types(path: Path) -> None:
    """pandoc copies the template's embedded fonts (word/fonts/*.ttf) without declaring their content
    type; add the declaration so Word and python-docx accept the file."""
    import zipfile
    with zipfile.ZipFile(path) as z:
        items = {n: z.read(n) for n in z.namelist()}
    ct = items["[Content_Types].xml"].decode("utf-8")
    exts = {n.rsplit(".", 1)[1].lower() for n in items if n.startswith("word/fonts/") and "." in n}
    for ext in exts:
        if f'Extension="{ext}"' not in ct:
            ct = ct.replace("<Types ", "<Types ", 1).replace(
                "</Types>", f'<Default Extension="{ext}" ContentType="application/x-font-{ext}"/></Types>')
    items["[Content_Types].xml"] = ct.encode("utf-8")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n, data in items.items():
            z.writestr(n, data)


def main() -> None:
    text = (PAPER / "report.md").read_text(encoding="utf-8")
    title = text.splitlines()[0].lstrip("# ").strip()
    abstract_md = text.split("## Abstract", 1)[1].split("## 1. Introduction", 1)[0].strip()
    body_md = "## 1. Introduction" + text.split("## 1. Introduction", 1)[1]
    abstract = []
    for block in abstract_md.split("\n\n"):
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if all(l.startswith("- ") for l in lines):
            abstract += ["• " + plain(l[2:]) for l in lines]
        else:
            abstract.append(plain(" ".join(lines)))

    body_md_path = PAPER / "_body.md"
    body_md_path.write_text(body_md, encoding="utf-8")
    out = PAPER / "report_apart.docx"
    pypandoc.convert_file(str(body_md_path), "docx", format="markdown-implicit_figures", outputfile=str(out),
                          extra_args=[f"--reference-doc={TEMPLATE}", f"--resource-path={PAPER}"])
    body_md_path.unlink()
    register_font_types(out)

    tpl = docx.Document(str(TEMPLATE))
    box = copy.deepcopy(tpl.tables[0]._tbl)
    doc = docx.Document(str(out))
    doc.element.body.insert(0, box)
    table = doc.tables[0]
    title_cell, abstract_cell = table.rows[0].cells[0], table.rows[1].cells[0]
    for nested in table._tbl.xpath(".//w:tc//w:tbl"):  # template's placeholder author grid and guidance box
        nested.getparent().remove(nested)
    for t in doc.tables[1:]:  # compact the report's own tables
        for row in t.rows:
            for cell in row.cells:
                for par in cell.paragraphs:
                    par.paragraph_format.space_before = docx.shared.Pt(1)
                    par.paragraph_format.space_after = docx.shared.Pt(1)
                    for run in par.runs:
                        run.font.size = docx.shared.Pt(9)

    title_par = next(p for p in title_cell.paragraphs if p.text.strip())
    for r in title_par.runs[1:]:
        r._r.getparent().remove(r._r)
    title_par.runs[0].text = title
    anchor = title_par
    for line in (AUTHOR_LINE, EVENT_LINE, CODE_LINE):
        new = copy.deepcopy(title_par._p)
        anchor._p.addnext(new)
        par = docx.text.paragraph.Paragraph(new, title_cell)
        for r in par.runs[1:]:
            r._r.getparent().remove(r._r)
        par.runs[0].text = line
        par.style = doc.styles["Normal"] if "Normal" in [s.name for s in doc.styles] else par.style
        par.runs[0].font.size = docx.shared.Pt(10)
        par.runs[0].bold = False
        anchor = par

    label = next(p for p in abstract_cell.paragraphs if p.text.strip())
    for r in label.runs[1:]:
        r._r.getparent().remove(r._r)
    label.runs[0].text = "Abstract"
    label.runs[0].bold = True
    anchor = label
    for para in abstract:
        new = copy.deepcopy(label._p)
        anchor._p.addnext(new)
        par = docx.text.paragraph.Paragraph(new, abstract_cell)
        for r in par.runs[1:]:
            r._r.getparent().remove(r._r)
        par.runs[0].text = para
        par.runs[0].bold = False
        anchor = par

    doc.save(str(out))
    print(f"wrote {out}: {len(doc.tables)} tables, {len(doc.inline_shapes)} figures, abstract {sum(len(a.split()) for a in abstract)} words")


if __name__ == "__main__":
    main()
