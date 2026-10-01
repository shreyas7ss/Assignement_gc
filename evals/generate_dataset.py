from __future__ import annotations

import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont, ImageFilter


DATASET_DIR = Path(__file__).parent / "dataset"


@dataclass(frozen=True)
class Sample:
    sample_id: str
    filename: str
    quality: str
    changes: dict[str, str | None]
    expected_decision: str


SAMPLES = (
    Sample("clean_approved_01", "clean_approved_01.pdf", "clean", {}, "auto_approve"),
    Sample("clean_approved_02", "clean_approved_02.pdf", "clean", {}, "auto_approve"),
    Sample(
        "clean_invoice_mismatch",
        "clean_invoice_mismatch.pdf",
        "clean",
        {"invoice_number": "ACME-INV-2026-009"},
        "amendment_request",
    ),
    Sample(
        "messy_missing_weight",
        "messy_missing_weight.pdf",
        "messy_scanned",
        {"gross_weight": None},
        "human_review",
    ),
    Sample(
        "messy_missing_hs_code",
        "messy_missing_hs_code.pdf",
        "messy_scanned",
        {"hs_code": None},
        "human_review",
    ),
    Sample(
        "messy_consignee_mismatch",
        "messy_consignee_mismatch.pdf",
        "messy_scanned",
        {"consignee_name": "ACME Trading Co."},
        "amendment_request",
    ),
)

BASE_FIELDS = (
    ("Invoice Number", "invoice_number", "ACME-INV-2026-001"),
    ("Consignee", "consignee_name", "ACME Corporation Ltd"),
    ("HS Code", "hs_code", "847130"),
    ("Port of Loading", "port_of_loading", "Shanghai"),
    ("Port of Discharge", "port_of_discharge", "Los Angeles"),
    ("Incoterms", "incoterms", "FOB"),
    ("Goods Description", "goods_description", "Portable computers"),
    ("Gross Weight", "gross_weight", "1200 kg"),
)


def _fields_for(sample: Sample) -> tuple[list[str], dict[str, str | None]]:
    lines = ["COMMERCIAL INVOICE", "Reference: NOVA-SYNTHETIC-EVAL"]
    ground_truth: dict[str, str | None] = {}
    for label, field_name, default_value in BASE_FIELDS:
        value = sample.changes.get(field_name, default_value)
        ground_truth[field_name] = value
        if value is not None:
            lines.append(f"{label}: {value}")
    return lines, ground_truth


def _draw_messy_page(lines: list[str]) -> bytes:
    image = Image.new("RGB", (1275, 1650), "#d3d0c8")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 26)
    except OSError:
        font = ImageFont.load_default()

    draw.rectangle((70, 70, 1190, 1580), outline="#88847d", width=4)
    y = 140
    for index, line in enumerate(lines):
        x = 105 + (index % 3) * 9
        fill = "#514e48" if index % 4 else "#767169"
        draw.text((x, y), line, fill=fill, font=font)
        y += 130 if index else 180

    image = image.rotate(1.2, resample=Image.Resampling.BICUBIC, fillcolor="#d3d0c8")
    image = image.filter(ImageFilter.GaussianBlur(radius=0.55))
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=55)
    return buffer.getvalue()


def _write_pdf(path: Path, lines: list[str], *, messy: bool) -> None:
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    if messy:
        page.insert_image(page.rect, stream=_draw_messy_page(lines))
        page.insert_textbox(
            pymupdf.Rect(8, 8, 604, 780),
            "\n".join(lines),
            fontsize=1,
            render_mode=3,
            lineheight=1.05,
        )
    else:
        page.insert_textbox(
            pymupdf.Rect(54, 60, 558, 730),
            "\n".join(lines),
            fontsize=12,
            lineheight=1.8,
        )
    path.write_bytes(document.tobytes())
    document.close()


def generate_dataset() -> None:
    documents_dir = DATASET_DIR / "docs"
    documents_dir.mkdir(parents=True, exist_ok=True)
    for sample in SAMPLES:
        lines, ground_truth = _fields_for(sample)
        document_path = documents_dir / sample.filename
        _write_pdf(document_path, lines, messy=sample.quality == "messy_scanned")
        label = {
            "sample_id": sample.sample_id,
            "quality": sample.quality,
            "synthetic": True,
            "document": f"docs/{sample.filename}",
            "ground_truth": ground_truth,
            "expected_decision": sample.expected_decision,
        }
        (DATASET_DIR / f"{sample.sample_id}.json").write_text(
            json.dumps(label, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    generate_dataset()