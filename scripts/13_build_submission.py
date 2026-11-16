"""Build the submission in Apart's official template: paper/report_apart.docx.

Starts FROM the template file, so its title rules, footnote ("Research conducted at the AI x Epistemics
Research Sprint"), author block, "With Apart Research" line, abstract box and embedded font are kept
exactly. The template's placeholder text and instructions box are removed. The report body
(paper/report.md, from "1. Introduction" on) is converted with pandoc and copied in with the template's
typography: Old Standard TT, 14 pt section headings, 12 pt subsection headings.

Run:  uv run --with pypandoc_binary --with python-docx python scripts/13_build_submission.py
      powershell -File scripts/14_export_pdf.ps1      (PDF + page check, needs Microsoft Word)
"""
from __future__ import annotations

import copy
import io
import re
import zipfile
from pathlib import Path

import docx
import pypandoc
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from docx.text.paragraph import Paragraph

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper"
TEMPLATE = PAPER / "template" / "apart_template.docx"
FONT = "Old Standard TT"
AUTHORS = [("Raj Gupta", "National Institute of Technology Agartala"),
           ("Prakash Kumar", "National Institute of Technology Agartala"),
           ("Abhay Pratap Singh", "National Institute of Technology Agartala")]
BODY_PT, H2_PT, H3_PT, TABLE_PT, CAPTION_PT = 11, 14, 12, 9.5, 10


def plain(md: str) -> str:
    md = re.sub(r"\*\*(.+?)\*\*", r"\1", md)
    md = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"\1", md)
    return md.replace("`", "")


def set_text(par: Paragraph, text: str, keep_footnote: bool = False) -> None:
    """Put `text` in the paragraph's first text run and drop the other text runs."""
    runs = [r for r in par.runs if not (keep_footnote and r._r.xpath(".//w:footnoteReference"))]
    runs[0].text = text
    for r in runs[1:]:
        r._r.getparent().remove(r._r)


def register_font_types(path: Path) -> None:
    """pandoc copies the template's embedded fonts without declaring their content type."""
    with zipfile.ZipFile(path) as z:
        items = {n: z.read(n) for n in z.namelist()}
    ct = items["[Content_Types].xml"].decode("utf-8")
    for ext in {n.rsplit(".", 1)[1].lower() for n in items if n.startswith("word/fonts/") and "." in n}:
        if f'Extension="{ext}"' not in ct:
            ct = ct.replace("</Types>", f'<Default Extension="{ext}" ContentType="application/x-font-{ext}"/></Types>')
    items["[Content_Types].xml"] = ct.encode("utf-8")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n, data in items.items():
            z.writestr(n, data)


def font(run_el, size=None, bold=None, italic=None, name=FONT, color=None, underline=None) -> None:
    from docx.text.run import Run
    r = Run(run_el, None)
    r.font.name = name
    rpr = run_el.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    for attr in ("w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), name)
    if size is not None:
        r.font.size = Pt(size)
    if bold is not None:
        r.font.bold = bold
    if italic is not None:
        r.font.italic = italic
    if color is not None:
        r.font.color.rgb = RGBColor.from_string(color)
    if underline is not None:
        r.font.underline = underline


def merge_numbering(base, src, elements) -> None:
    """Copy list definitions from the pandoc document and renumber list references in `elements`."""
    if not elements:
        return
    try:
        sn = src.part.numbering_part.element
    except KeyError:
        return
    bn = base.part.numbering_part.element
    a_ids = [int(a.get(qn("w:abstractNumId"))) for a in bn.findall(qn("w:abstractNum"))]
    n_ids = [int(n.get(qn("w:numId"))) for n in bn.findall(qn("w:num"))]
    a_off, n_off = max(a_ids, default=-1) + 1, max(n_ids, default=0) + 1
    first_num = bn.find(qn("w:num"))
    for a in sn.findall(qn("w:abstractNum")):
        c = copy.deepcopy(a)
        c.set(qn("w:abstractNumId"), str(int(a.get(qn("w:abstractNumId"))) + a_off))
        for nsid in c.findall(qn("w:nsid")):
            c.remove(nsid)
        if first_num is not None:
            first_num.addprevious(c)
        else:
            bn.append(c)
    mapping = {}
    for n in sn.findall(qn("w:num")):
        c = copy.deepcopy(n)
        new = int(n.get(qn("w:numId"))) + n_off
        mapping[n.get(qn("w:numId"))] = str(new)
        c.set(qn("w:numId"), str(new))
        ref = c.find(qn("w:abstractNumId"))
        ref.set(qn("w:val"), str(int(ref.get(qn("w:val"))) + a_off))
        bn.append(c)
    for el in elements:
        for nid in el.iter(qn("w:numId")):
            if nid.get(qn("w:val")) in mapping:
                nid.set(qn("w:val"), mapping[nid.get(qn("w:val"))])


def main() -> None:
    text = (PAPER / "report.md").read_text(encoding="utf-8")
    title = text.splitlines()[0].lstrip("# ").strip()
    abstract_md = text.split("## Abstract", 1)[1].split("## 1. Introduction", 1)[0].strip()
    abstract = []
    for block in abstract_md.split("\n\n"):
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if lines and all(l.startswith("- ") for l in lines):
            abstract += ["• " + plain(l[2:]) for l in lines]
        elif lines:
            abstract.append(plain(" ".join(lines)))

    # 1. report body -> docx with pandoc (template as reference for style ids)
    body_md = PAPER / "_body.md"
    body_md.write_text("## 1. Introduction" + text.split("## 1. Introduction", 1)[1], encoding="utf-8")
    body_docx = PAPER / "_body.docx"
    pypandoc.convert_file(str(body_md), "docx", format="markdown-implicit_figures", outputfile=str(body_docx),
                          extra_args=[f"--reference-doc={TEMPLATE}", f"--resource-path={PAPER}"])
    body_md.unlink()
    register_font_types(body_docx)
    src = docx.Document(str(body_docx))

    # 2. the template is the base document: keep its title box, drop its info box and guidance sections
    base = docx.Document(str(TEMPLATE))
    body = base.element.body
    box = base.tables[0]._tbl
    sect = body.find(qn("w:sectPr"))
    kids = list(body.iterchildren())
    for el in kids[kids.index(box) + 1:]:
        if el is not sect:
            body.remove(el)

    # 3. title (keeps the footnote reference), authors, abstract
    title_cell, lower_cell = [tr.xpath("./w:tc")[0] for tr in box.xpath("./w:tr")]
    title_p = next(Paragraph(p, None) for p in title_cell.xpath("./w:p") if p.xpath(".//w:footnoteReference"))
    set_text(title_p, title, keep_footnote=True)

    author_box, abstract_box = lower_cell.xpath("./w:tbl")[:2]
    grid = author_box.xpath(".//w:tbl")[0]
    rows = grid.xpath("./w:tr")
    for extra in rows[1:]:
        grid.remove(extra)
    cells = rows[0].xpath("./w:tc")
    for extra in cells[len(AUTHORS):]:
        rows[0].remove(extra)
    # The template's author grid is fixed at ~1.4 in wide (fine for "Author name 1"); widen it so a
    # full affiliation fits: two columns of 3,500 twips (~2.4 in) each.
    col_w = min(3500, 7100 // len(AUTHORS))  # the author box is ~7,185 twips wide
    cols = grid.find(qn("w:tblGrid")).findall(qn("w:gridCol"))
    for extra in cols[len(AUTHORS):]:
        extra.getparent().remove(extra)
    for c in grid.find(qn("w:tblGrid")).findall(qn("w:gridCol")):
        c.set(qn("w:w"), str(col_w))
    tblw = grid.find(qn("w:tblPr")).find(qn("w:tblW"))
    tblw.set(qn("w:w"), str(col_w * len(AUTHORS)))
    tblw.set(qn("w:type"), "dxa")
    for tc, (name, aff) in zip(rows[0].xpath("./w:tc"), AUTHORS):
        tcpr = tc.find(qn("w:tcPr"))
        if tcpr is None:
            tcpr = tc.makeelement(qn("w:tcPr"), {})
            tc.insert(0, tcpr)
        tcw = tcpr.find(qn("w:tcW"))
        if tcw is None:
            tcw = tcpr.makeelement(qn("w:tcW"), {})
            tcpr.insert(0, tcw)
        tcw.set(qn("w:w"), str(col_w))
        tcw.set(qn("w:type"), "dxa")
        ts = list(tc.iter(qn("w:t")))  # one run: "Author name N" <w:br/> "Affiliation"
        ts[0].text, ts[1].text = name, aff
        for t in ts[2:]:
            t.getparent().remove(t)

    abs_cell = abstract_box.xpath(".//w:tc")[0]
    abs_ps = abs_cell.xpath("./w:p")
    proto = next(p for p in abs_ps if "".join(p.itertext()).strip())
    for p in abs_ps:
        if p is not proto:
            abs_cell.remove(p)
    anchor = proto
    for i, para in enumerate(abstract):
        p_el = proto if i == 0 else copy.deepcopy(proto)
        if i:
            anchor.addnext(p_el)
        par = Paragraph(p_el, None)
        set_text(par, para)
        for r in par.runs:
            font(r._r, italic=False, underline=False)
        anchor = p_el

    # 4. copy the body in, re-linking images and hyperlinks, merging list definitions
    new_elements = []
    for el in src.element.body.iterchildren():
        if el.tag == qn("w:sectPr"):
            continue
        c = copy.deepcopy(el)
        for blip in c.iter(qn("a:blip")):
            rid = blip.get(qn("r:embed"))
            blob = src.part.related_parts[rid].blob
            new_rid, _ = base.part.get_or_add_image(io.BytesIO(blob))
            blip.set(qn("r:embed"), new_rid)
        for link in c.iter(qn("w:hyperlink")):
            rid = link.get(qn("r:id"))
            if rid:
                url = src.part.rels[rid].target_ref
                link.set(qn("r:id"), base.part.relate_to(url, RT.HYPERLINK, is_external=True))
        sect.addprevious(c)
        new_elements.append(c)
    merge_numbering(base, src, new_elements)

    # 5. template typography for everything copied in
    for el in new_elements:
        if el.tag == qn("w:tbl"):
            tbl = el
            tblpr = tbl.find(qn("w:tblPr"))
            borders = tblpr.find(qn("w:tblBorders"))
            if borders is None:
                borders = tblpr.makeelement(qn("w:tblBorders"), {})
                tblpr.append(borders)
            for side in ("top", "bottom", "insideH"):
                b = borders.makeelement(qn(f"w:{side}"), {qn("w:val"): "single", qn("w:sz"): "4", qn("w:color"): "808080"})
                borders.append(b)
            for ri, tr in enumerate(tbl.xpath("./w:tr")):
                for p in tr.iter(qn("w:p")):
                    par = Paragraph(p, None)
                    par.paragraph_format.space_before = Pt(1)
                    par.paragraph_format.space_after = Pt(1)
                    par.paragraph_format.keep_with_next = True  # keep each table (and its caption) on one page
                    for r in p.iter(qn("w:r")):
                        font(r, size=TABLE_PT, bold=True if ri == 0 else None)
            continue
        if el.tag != qn("w:p"):
            continue
        par = Paragraph(el, None)
        style = el.find(qn("w:pPr")).find(qn("w:pStyle")).get(qn("w:val")) if el.find(qn("w:pPr")) is not None \
            and el.find(qn("w:pPr")).find(qn("w:pStyle")) is not None else ""
        is_h2, is_h3 = style.lower().startswith("heading2"), style.lower().startswith("heading3")
        has_image = bool(el.xpath(".//w:drawing"))
        texts = [t.text or "" for t in el.iter(qn("w:t"))]
        is_caption = bool(texts) and "".join(texts).lstrip().startswith(("Figure ", "Table "))
        if has_image:
            par.alignment = 1
        is_list = bool(el.xpath('./w:pPr/w:numPr'))
        par.paragraph_format.space_after = Pt(2 if is_list else 4 if is_caption else 6)
        for r in el.iter(qn("w:r")):
            rstyle = r.find(qn("w:rPr")).find(qn("w:rStyle")).get(qn("w:val")) \
                if r.find(qn("w:rPr")) is not None and r.find(qn("w:rPr")).find(qn("w:rStyle")) is not None else ""
            in_link = r.getparent().tag == qn("w:hyperlink")
            if "Verbatim" in rstyle:
                font(r, size=BODY_PT - 1.5, name="Consolas")
            elif is_h2:
                font(r, size=H2_PT, bold=True)
            elif is_h3:
                font(r, size=H3_PT, bold=True)
            elif is_caption:
                font(r, size=CAPTION_PT)
            else:
                font(r, size=BODY_PT, color="1155CC" if in_link else None, underline=True if in_link else None)

    out = PAPER / "Evidence_Audit_Community_Notes.docx"
    base.save(str(out))
    body_docx.unlink()
    print(f"wrote {out}: {len(base.tables) - 1} body tables, {len(base.inline_shapes)} figures, "
          f"abstract {sum(len(a.split()) for a in abstract)} words, authors {[a for a, _ in AUTHORS]}")


if __name__ == "__main__":
    main()
