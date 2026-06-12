import json
import os
import re
import sys
from pathlib import Path
from typing import Optional


def clean_markdown_text(text: str) -> str:
    replacements = {
        "\u00a0": " ",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2753": "(needs check)",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    text = re.sub(r"`(.*?)`", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)

    return text.strip()


def output_path_for(markdown_path: str, output_path: Optional[str] = None) -> str:
    if output_path:
        return output_path

    return str(Path(markdown_path).with_suffix(".pdf"))


def load_config(config_path: str = "pdf_config.json") -> dict:
    with open(config_path, "r", encoding="utf-8") as file:
        return json.load(file)


def output_path_from_config(config: dict) -> str:
    markdown_path = config["markdown_path"]
    output_path = config.get("output_path")

    if output_path:
        return output_path

    output_dir = config.get("output_dir")
    output_filename = config.get("output_filename")

    if not output_dir and not output_filename:
        return output_path_for(markdown_path)

    filename = output_filename or Path(markdown_path).with_suffix(".pdf").name

    return str(Path(output_dir or ".") / filename)


def is_table_separator(line: str) -> bool:
    stripped = line.strip()

    return bool(stripped) and set(stripped.replace("|", "").strip()) <= {"-", ":"}


def parse_table_row(line: str) -> list[str]:
    cells = line.strip().strip("|").split("|")

    return [clean_markdown_text(cell) for cell in cells]


def convert_markdown_to_pdf(markdown_path: str, output_path: Optional[str] = None) -> str:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            ListFlowable,
            ListItem,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise RuntimeError(
            "Missing PDF dependency. Run: pip install -r requirements.txt"
        ) from exc

    output_path = output_path_for(markdown_path, output_path)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with open(markdown_path, "r", encoding="utf-8") as file:
        lines = file.readlines()

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="BriefingTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            spaceAfter=14,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BriefingHeading",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            spaceBefore=12,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BriefingBody",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BriefingBullet",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BriefingTable",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
        )
    )

    story = []
    bullet_items = []
    table_rows = []

    def flush_bullets() -> None:
        nonlocal bullet_items

        if not bullet_items:
            return

        story.append(
            ListFlowable(
                [
                    ListItem(Paragraph(item, styles["BriefingBullet"]))
                    for item in bullet_items
                ],
                bulletType="bullet",
                leftIndent=14,
            )
        )
        story.append(Spacer(1, 0.12 * cm))
        bullet_items = []

    def flush_table() -> None:
        nonlocal table_rows

        if not table_rows:
            return

        wrapped_rows = [
            [Paragraph(cell, styles["BriefingTable"]) for cell in row]
            for row in table_rows
        ]
        column_count = max(len(row) for row in wrapped_rows)
        page_width = A4[0] - 4 * cm
        table = Table(
            wrapped_rows,
            colWidths=[page_width / column_count] * column_count,
            repeatRows=1,
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDEFF2")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1F2933")),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B8C0CC")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 0.25 * cm))
        table_rows = []

    for raw_line in lines:
        line = raw_line.rstrip("\n")
        stripped = line.strip()

        if not stripped or stripped == "---":
            flush_bullets()
            flush_table()
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            flush_bullets()

            if is_table_separator(stripped):
                continue

            table_rows.append(parse_table_row(stripped))
            continue

        flush_table()

        heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading_match:
            flush_bullets()
            level = len(heading_match.group(1))
            text = clean_markdown_text(heading_match.group(2))
            style = styles["BriefingTitle"] if level == 1 else styles["BriefingHeading"]
            story.append(Paragraph(text, style))
            continue

        bullet_match = re.match(r"^[-*]\s+(.*)$", stripped)
        if bullet_match:
            bullet_items.append(clean_markdown_text(bullet_match.group(1)))
            continue

        flush_bullets()
        story.append(Paragraph(clean_markdown_text(stripped), styles["BriefingBody"]))

    flush_bullets()
    flush_table()

    document = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        title=Path(markdown_path).stem.replace("_", " ").title(),
    )
    document.build(story)

    return output_path


def main() -> None:
    if len(sys.argv) > 2:
        print("Usage: python md_to_pdf.py [pdf_config.json]")
        raise SystemExit(1)

    config_path = sys.argv[1] if len(sys.argv) == 2 else "pdf_config.json"

    if not config_path.endswith(".json"):
        print("Usage: python md_to_pdf.py [pdf_config.json]")
        raise SystemExit(1)

    config = load_config(config_path)
    markdown_path = config["markdown_path"]
    output_path = output_path_from_config(config)

    try:
        pdf_path = convert_markdown_to_pdf(markdown_path, output_path)
    except RuntimeError as exc:
        print(exc)
        raise SystemExit(1) from exc

    print(f"Saved PDF to: {pdf_path}")


if __name__ == "__main__":
    main()
