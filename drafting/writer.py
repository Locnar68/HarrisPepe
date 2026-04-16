"""Write filled templates to .docx, .md, or .pdf output files."""
from __future__ import annotations

import re
from pathlib import Path


def write_markdown(text: str, output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    return output_path


def write_docx(text: str, output_path: Path, title: str = "Generated Document") -> Path:
    from docx import Document
    from docx.shared import Pt, Inches

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)
    for s in doc.sections:
        s.top_margin = s.bottom_margin = Inches(1)
        s.left_margin = s.right_margin = Inches(1)

    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            doc.add_paragraph("")
        elif stripped.startswith("# "):
            doc.add_heading(stripped[2:], level=1)
        elif stripped.startswith("## "):
            doc.add_heading(stripped[3:], level=2)
        elif stripped.startswith("### "):
            doc.add_heading(stripped[4:], level=3)
        elif stripped.startswith("---"):
            doc.add_paragraph("").paragraph_format.space_after = Pt(6)
        else:
            p = doc.add_paragraph()
            parts = re.split(r"(\*\*.*?\*\*)", stripped)
            for part in parts:
                if part.startswith("**") and part.endswith("**"):
                    p.add_run(part[2:-2]).bold = True
                else:
                    p.add_run(part)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    return output_path


def write_pdf(text: str, output_path: Path, title: str = "Generated Document") -> Path:
    """Convert filled markdown text to a clean PDF."""
    from fpdf import FPDF

    class DocPDF(FPDF):
        def header(self):
            pass  # we handle the title in the body

        def footer(self):
            self.set_y(-15)
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(150, 150, 150)
            self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    pdf = DocPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    pdf.set_margins(20, 15, 20)

    def _clean(s: str) -> str:
        """Strip markdown bold markers for plain text."""
        return re.sub(r"\*\*(.+?)\*\*", r"\1", s)

    def _write_line(line: str):
        stripped = line.strip()

        if not stripped:
            pdf.ln(4)
            return

        if stripped.startswith("---"):
            y = pdf.get_y()
            pdf.set_draw_color(200, 200, 200)
            pdf.line(20, y, pdf.w - 20, y)
            pdf.ln(6)
            return

        # Headings
        if stripped.startswith("# "):
            pdf.set_font("Helvetica", "B", 18)
            pdf.set_text_color(30, 64, 175)
            pdf.multi_cell(0, 9, _clean(stripped[2:]))
            pdf.ln(3)
            return
        if stripped.startswith("## "):
            pdf.set_font("Helvetica", "B", 14)
            pdf.set_text_color(30, 64, 175)
            pdf.multi_cell(0, 8, _clean(stripped[3:]))
            pdf.ln(2)
            return
        if stripped.startswith("### "):
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(50, 50, 50)
            pdf.multi_cell(0, 7, _clean(stripped[4:]))
            pdf.ln(1)
            return

        # Bullet / list items
        if stripped.startswith("- "):
            content = stripped[2:]
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(60, 60, 60)
            x = pdf.get_x()
            pdf.cell(6, 6, chr(8226))  # bullet
            _write_rich(content, indent=x + 6)
            pdf.ln(2)
            return

        # Checkbox items
        if stripped.startswith("- [ ] "):
            content = stripped[6:]
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(60, 60, 60)
            x = pdf.get_x()
            pdf.cell(6, 6, chr(9744))  # checkbox
            _write_rich(content, indent=x + 6)
            pdf.ln(2)
            return

        # Table rows
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            if all(set(c) <= {"-", " ", ":"} for c in cells):
                return  # skip separator rows
            col_w = (pdf.w - 40) / max(len(cells), 1)
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(60, 60, 60)
            for cell in cells:
                pdf.cell(col_w, 6, _clean(cell), border=1)
            pdf.ln()
            return

        # Regular paragraph
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(40, 40, 40)
        _write_rich(stripped)
        pdf.ln(2)

    def _write_rich(text: str, indent: float = 0):
        """Write text with **bold** support inline."""
        parts = re.split(r"(\*\*.*?\*\*)", text)
        for part in parts:
            if part.startswith("**") and part.endswith("**"):
                pdf.set_font("Helvetica", "B", 10)
                pdf.write(5, part[2:-2])
                pdf.set_font("Helvetica", "", 10)
            else:
                pdf.write(5, part)

    # Process each line.
    for line in text.split("\n"):
        _write_line(line)

    # Timestamp at bottom.
    pdf.ln(10)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(150, 150, 150)
    import datetime
    pdf.cell(0, 5, f"Generated {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}", align="R")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(output_path))
    return output_path


def fill_docx_template(template_path: Path, replacements: dict[str, str], output_path: Path) -> Path:
    from docx import Document

    doc = Document(str(template_path))

    def replace_in_paragraph(para):
        full = "".join(run.text for run in para.runs)
        if "{{" not in full:
            return
        for key, val in replacements.items():
            full = full.replace("{{" + key + "}}", val)
        full = re.sub(r"\{\{.+?\}\}", "[UNANSWERED]", full)
        if para.runs:
            para.runs[0].text = full
            for run in para.runs[1:]:
                run.text = ""

    for para in doc.paragraphs:
        replace_in_paragraph(para)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    replace_in_paragraph(para)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    return output_path
