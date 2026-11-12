"""Turn a tailored resume's text into a clean Word (.docx) file.

The tailored text uses light markup (see ai_tools.render_resume_text):
    first lines   name, then contact line(s)
    ## Heading    a section heading
    @ Role line   a job/school line (bold)
    - bullet      a bullet point
    anything else a normal paragraph

The file is built fresh each time you download it, so edits you make to the
text on the Documents page are always included.
"""
import io

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt


def build_docx(text):
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)
    for section in doc.sections:                       # narrow margins: resumes need the room
        section.top_margin = section.bottom_margin = Pt(40)
        section.left_margin = section.right_margin = Pt(50)

    lines = text.splitlines()
    # Header: everything before the first heading.
    first_heading = next((i for i, line in enumerate(lines) if line.startswith("## ")), len(lines))
    header = [line for line in lines[:first_heading] if line.strip()]
    for i, line in enumerate(header):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(line)
        if i == 0:
            run.bold = True
            run.font.size = Pt(16)
        p.paragraph_format.space_after = Pt(2)

    for line in lines[first_heading:]:
        line = line.rstrip()
        if not line:
            continue
        if line.startswith("## "):
            p = doc.add_paragraph()
            run = p.add_run(line[3:].upper())
            run.bold = True
            run.font.size = Pt(11.5)
            p.paragraph_format.space_before = Pt(10)
            p.paragraph_format.space_after = Pt(2)
        elif line.startswith("@ "):
            p = doc.add_paragraph()
            p.add_run(line[2:]).bold = True
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(0)
        elif line.startswith(("- ", "• ")):
            p = doc.add_paragraph(line[2:], style="List Bullet")
            p.paragraph_format.space_after = Pt(0)
        else:
            doc.add_paragraph(line).paragraph_format.space_after = Pt(2)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf
