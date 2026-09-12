from __future__ import annotations

import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Preformatted, SimpleDocTemplate, Spacer, PageBreak, ListFlowable, ListItem, Table, TableStyle

ROOT = Path(__file__).resolve().parents[2]
MD_PATH = ROOT / "docs" / "AI-Assisted_CTI_Detection_Platform_Technical_Documentation.md"
OUT_PATH = ROOT / "docs" / "AI-Assisted_CTI_Detection_Platform_Technical_Documentation.pdf"

styles = getSampleStyleSheet()

TITLE_STYLE = ParagraphStyle(
    "TitleStyle",
    parent=styles["Title"],
    fontName="Helvetica-Bold",
    fontSize=20,
    leading=24,
    alignment=1,
    spaceAfter=8,
    textColor=colors.HexColor("#1f2937"),
)
SUBTITLE_STYLE = ParagraphStyle(
    "SubtitleStyle",
    parent=styles["Heading2"],
    fontName="Helvetica-Bold",
    fontSize=11,
    leading=16,
    alignment=1,
    textColor=colors.HexColor("#374151"),
)
SECTION_STYLE = ParagraphStyle(
    "SectionStyle",
    parent=styles["Heading1"],
    fontName="Helvetica-Bold",
    fontSize=14,
    leading=18,
    textColor=colors.HexColor("#111827"),
    spaceBefore=16,
    spaceAfter=10,
)
SUBSECTION_STYLE = ParagraphStyle(
    "SubsectionStyle",
    parent=styles["Heading2"],
    fontName="Helvetica-Bold",
    fontSize=11,
    leading=14,
    textColor=colors.HexColor("#1f2937"),
    spaceBefore=12,
    spaceAfter=8,
)
BODY_STYLE = ParagraphStyle(
    "BodyStyle",
    parent=styles["BodyText"],
    fontName="Helvetica",
    fontSize=9.2,
    leading=13,
    spaceAfter=6,
    textColor=colors.HexColor("#111827"),
)
CODE_STYLE = ParagraphStyle(
    "CodeStyle",
    parent=styles["Code"],
    fontName="Courier",
    fontSize=8,
    leading=10,
    backColor=colors.HexColor("#f3f4f6"),
    borderPadding=8,
    borderWidth=1,
    borderColor=colors.HexColor("#d1d5db"),
    spaceAfter=8,
    leftIndent=10,
)
BULLET_STYLE = ParagraphStyle(
    "BulletStyle",
    parent=BODY_STYLE,
    leftIndent=18,
    bulletIndent=12,
    spaceAfter=3,
)
SMALL_STYLE = ParagraphStyle(
    "SmallStyle",
    parent=BODY_STYLE,
    fontSize=8,
    leading=10,
    textColor=colors.HexColor("#4b5563"),
)


def parse_markdown(md_text: str):
    story = []
    lines = md_text.splitlines()
    i = 0
    in_code = False
    code_lines = []

    def flush_code():
        if code_lines:
            story.append(Preformatted("\n".join(code_lines), CODE_STYLE))
            story.append(Spacer(1, 8))
            code_lines.clear()

    while i < len(lines):
        line = lines[i]

        if line.startswith("```"):
            flush_code()
            in_code = not in_code
            if in_code:
                code_lines = []
            i += 1
            continue

        if in_code:
            code_lines.append(line)
            i += 1
            continue

        if line.startswith("# "):
            flush_code()
            story.append(Paragraph(line[2:], TITLE_STYLE))
            story.append(Spacer(1, 4))
        elif line.startswith("## "):
            flush_code()
            story.append(Paragraph(line[3:], SECTION_STYLE))
        elif line.startswith("### "):
            flush_code()
            story.append(Paragraph(line[4:], SUBSECTION_STYLE))
        elif line.startswith("---"):
            flush_code()
            story.append(Spacer(1, 10))
        elif line.strip().startswith("- "):
            flush_code()
            item = line.strip()[2:].strip()
            story.append(Paragraph(f"• {item}", BULLET_STYLE))
        elif line.strip().startswith("*"):
            flush_code()
            item = line.strip()[2:].strip()
            story.append(Paragraph(f"• {item}", BULLET_STYLE))
        elif line.startswith("|") and "|" in line:
            flush_code()
            table_rows = []
            row = [cell.strip() for cell in line.split("|")[1:-1]]
            if row:
                table_rows.append(row)
            j = i + 1
            while j < len(lines) and lines[j].startswith("|") and "|" in lines[j]:
                table_rows.append([cell.strip() for cell in lines[j].split("|")[1:-1]])
                j += 1
            if len(table_rows) > 1:
                table = Table(table_rows, colWidths=[55 * mm, 75 * mm, 35 * mm])
                table.setStyle(TableStyle([
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                ]))
                story.append(table)
                story.append(Spacer(1, 8))
                i = j
                continue
        elif line.strip():
            flush_code()
            story.append(Paragraph(line.strip(), BODY_STYLE))
        i += 1

    flush_code()
    return story


if __name__ == "__main__":
    md_text = MD_PATH.read_text(encoding="utf-8")
    story = []

    title_lines = [
        "AI-Assisted CTI Detection Engineering Platform",
        "Technical Documentation & Deployment Guide",
        "",
        "Internship Project",
        "Forvis Mazars Group",
        "Student: ILYES HAMDI",
        "Academic year: 2026 / 2027",
        "Version: 1.0",
        "Date: 2026-09-12",
        "Technology stack: Python 3.11, FastAPI, SQLAlchemy, Alembic, PostgreSQL, Redis, Celery, LangGraph, MISP, DeepSeek, Next.js 14, TypeScript, Docker Compose, nginx",
    ]
    story.append(Paragraph("<b>" + title_lines[0] + "</b>", TITLE_STYLE))
    story.append(Paragraph(title_lines[1], SUBTITLE_STYLE))
    story.append(Spacer(1, 8))
    for line in title_lines[2:]:
        story.append(Paragraph(line, BODY_STYLE))
    story.append(PageBreak())

    story.append(Paragraph("Table of Contents", SECTION_STYLE))
    contents = [
        "1. Project Overview",
        "2. System Architecture",
        "3. CTI to Detection Engineering Pipeline",
        "4. AI and LangGraph",
        "5. Detection Engineering",
        "6. Repository / Source Code Guide",
        "7. Installation and Configuration",
        "8. Running the Platform",
        "9. API Documentation",
        "10. Testing",
        "11. DevSecOps / CI-CD",
        "12. Troubleshooting",
        "13. Security Considerations",
        "14. Current Project Status",
        "15. Documentation Index",
    ]
    for item in contents:
        story.append(Paragraph(item, BODY_STYLE))
    story.append(PageBreak())

    normalized_md = md_text.replace("# AI-Assisted CTI Detection Engineering Platform\n\n## Technical Documentation & Deployment Guide\n\n- Internship Project\n- Forvis Mazars Group\n- Student: ILYES HAMDI\n- Academic year: 2026 / 2027\n- Version: 1.0\n- Date: 2026-09-12\n- Technology stack: Python 3.11, FastAPI, SQLAlchemy, Alembic, PostgreSQL, Redis, Celery, LangGraph, MISP, DeepSeek, Next.js 14, TypeScript, TailwindCSS, Docker Compose, nginx\n\n---\n\n# 1. Project Overview\n", "# 1. Project Overview\n")
    story.extend(parse_markdown(normalized_md))

    doc = SimpleDocTemplate(
        str(OUT_PATH),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
    )
    doc.build(story)
    print(f"PDF written to: {OUT_PATH}")
