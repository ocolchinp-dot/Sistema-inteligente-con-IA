from __future__ import annotations

import io
import re
from datetime import datetime
from typing import Any

from pypdf import PdfReader
from PIL import Image

from .schemas import DocumentType


LAB_KEYWORDS = [
    "hemoglobina",
    "glucosa",
    "hematocrito",
    "referencia",
    "laboratorio",
    "resultado",
    "paciente",
]


def extract_content_tool(file_bytes: bytes, filename: str, content_type: str | None = None) -> dict[str, Any]:
    """Tool #1: Extract text and metadata from PDF/Image/plain files."""
    extension = filename.lower().split(".")[-1] if "." in filename else ""
    text = ""
    metadata: dict[str, Any] = {"filename": filename, "content_type": content_type, "extension": extension}

    if extension == "pdf":
        reader = PdfReader(io.BytesIO(file_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(pages)
        metadata["pages"] = len(reader.pages)
    elif extension in {"png", "jpg", "jpeg", "bmp", "tiff", "webp"}:
        # We keep basic metadata locally and leave deep interpretation to the LLM.
        with Image.open(io.BytesIO(file_bytes)) as img:
            metadata["image_size"] = {"width": img.width, "height": img.height}
            metadata["image_mode"] = img.mode
        text = ""
    elif extension in {"txt", "csv"}:
        text = file_bytes.decode("utf-8", errors="ignore")
    else:
        raise ValueError(f"Unsupported file extension: {extension}")

    return {"raw_text": text.strip(), "metadata": metadata}


def classify_document_tool(raw_text: str, metadata: dict[str, Any]) -> DocumentType:
    """Tool #2: Rule-based document type classifier."""
    blob = f"{raw_text}\n{metadata}".lower()
    if any(keyword in blob for keyword in LAB_KEYWORDS):
        return DocumentType.lab_result
    if "factura" in blob or "ticket" in blob:
        return DocumentType.support_document
    if "universidad" in blob or "estudiante" in blob:
        return DocumentType.academic_document
    if "receta" in blob or "diagnóstico" in blob:
        return DocumentType.medical_document
    if raw_text.strip() or metadata.get("extension") in {"pdf", "png", "jpg", "jpeg"}:
        return DocumentType.other
    return DocumentType.unknown


def normalize_date_tool(date_text: str | None) -> str | None:
    """Tool #3: Normalize date to ISO (YYYY-MM-DD) when possible."""
    if not date_text:
        return None

    candidate = date_text.strip().replace("/", "-")
    fmts = ["%Y-%m-%d", "%d-%m-%Y", "%d-%m-%y", "%Y.%m.%d", "%d.%m.%Y"]
    for fmt in fmts:
        try:
            return datetime.strptime(candidate, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    m = re.search(r"(\d{1,2})[\/-](\d{1,2})[\/-](\d{2,4})", candidate)
    if m:
        d, month, y = m.groups()
        y = f"20{y}" if len(y) == 2 else y
        try:
            return datetime(int(y), int(month), int(d)).strftime("%Y-%m-%d")
        except ValueError:
            return None
    return None


def range_validator_tool(extracted_data: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Tool #4: Detect possible out-of-range test values and data inconsistencies."""
    warnings: list[str] = []
    out_of_range_flags: list[str] = []

    for test in extracted_data.get("tests", []):
        try:
            value = float(str(test.get("value", "")).replace(",", "."))
        except Exception:
            continue

        ref = test.get("reference_range") or ""
        # Very simple parsing: "70-99"
        match = re.search(r"(-?\d+(?:\.\d+)?)\s*[-a]\s*(-?\d+(?:\.\d+)?)", ref)
        if not match:
            continue

        low, high = float(match.group(1)), float(match.group(2))
        if value < low or value > high:
            message = f"{test.get('exam_name', 'exam')}: valor {value} fuera de rango ({low}-{high})."
            out_of_range_flags.append(message)

    if not extracted_data.get("patient_name"):
        warnings.append("No se pudo identificar claramente el nombre del paciente.")
    if not extracted_data.get("collection_date"):
        warnings.append("No se pudo identificar claramente la fecha del estudio.")

    return warnings, out_of_range_flags


def clarifying_questions_tool(extracted_data: dict[str, Any], warnings: list[str]) -> list[str]:
    """Tool #5: Generate clarifying questions based on missing critical fields."""
    questions: list[str] = []

    if not extracted_data.get("patient_name"):
        questions.append("¿Cuál es el nombre completo del paciente tal como aparece en el informe?")
    if not extracted_data.get("collection_date"):
        questions.append("¿Cuál es la fecha exacta de toma de muestra?")
    if not extracted_data.get("tests"):
        questions.append("¿Podrías confirmar qué exámenes y valores aparecen en el documento?")
    if warnings and len(questions) < 2:
        questions.append("¿Deseas que marque estos resultados como pendientes de revisión manual?")

    return questions[:4]
