from __future__ import annotations

import json
import os
import re
from typing import Any

from openai import OpenAI

from .schemas import AnalyzeResponse, DocumentType, LLMLabExtraction, Status, ToolTraceItem
from .tools import (
    clarifying_questions_tool,
    classify_document_tool,
    extract_content_tool,
    normalize_date_tool,
    range_validator_tool,
)


SYSTEM_PROMPT = """Eres un analista clínico documental. Extrae datos de forma prudente y estructurada.
Si hay duda, usa null o listas vacías en vez de inventar.
"""


def _heuristic_extract(raw_text: str) -> LLMLabExtraction:
    patient = None
    date = None

    m_patient = re.search(r"(?:paciente|nombre)\s*[:\-]\s*(.+)", raw_text, re.IGNORECASE)
    if m_patient:
        patient = m_patient.group(1).strip().split("\n")[0][:120]

    m_date = re.search(r"(?:fecha|toma)\s*[:\-]\s*(\d{1,2}[\/-]\d{1,2}[\/-]\d{2,4})", raw_text, re.IGNORECASE)
    if m_date:
        date = m_date.group(1)

    tests = []
    for line in raw_text.splitlines():
        m = re.search(r"([A-Za-zÁÉÍÓÚáéíóúñÑ ]{3,})\s+(\d+(?:[\.,]\d+)?)\s*([A-Za-z/%µ]+)?\s*(\d+(?:[\.,]\d+)?\s*[-a]\s*\d+(?:[\.,]\d+)?)?", line)
        if m:
            tests.append(
                {
                    "exam_name": m.group(1).strip(),
                    "value": m.group(2),
                    "unit": m.group(3),
                    "reference_range": m.group(4),
                    "interpretation": None,
                }
            )

    return LLMLabExtraction(
        patient_name=patient,
        collection_date=date,
        observations=[],
        tests=tests[:20],
        confidence_notes=["Extracción heurística por ausencia de OPENAI_API_KEY o fallo del modelo."],
    )


def _extract_with_llm(raw_text: str, metadata: dict[str, Any], document_type: DocumentType) -> LLMLabExtraction:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _heuristic_extract(raw_text)

    client = OpenAI(api_key=api_key)
    user_payload = {
        "document_type_hint": document_type.value,
        "metadata": metadata,
        "raw_text": raw_text[:14000],
    }

    response = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Extrae la información clínica de laboratorio en JSON con campos: "
                    "patient_name, collection_date, laboratory_name, observations, tests, confidence_notes. "
                    "No inventes datos. Fuente:\n" + json.dumps(user_payload, ensure_ascii=False)
                ),
            },
        ],
        text={"format": {"type": "json_schema", "name": "llm_lab_extraction", "schema": LLMLabExtraction.model_json_schema()}},
    )

    raw = response.output_text
    return LLMLabExtraction.model_validate_json(raw)


def run_agent(file_bytes: bytes, filename: str, content_type: str | None) -> AnalyzeResponse:
    trace: list[ToolTraceItem] = []

    try:
        extracted = extract_content_tool(file_bytes, filename, content_type)
        trace.append(ToolTraceItem(tool="extract_content_tool", reason="Extraer texto y metadatos del archivo", success=True))
    except Exception as exc:
        trace.append(ToolTraceItem(tool="extract_content_tool", reason=f"Error al extraer contenido: {exc}", success=False))
        return AnalyzeResponse(
            status=Status.error,
            document_type=DocumentType.unknown,
            summary="No se pudo procesar el archivo cargado.",
            extracted_data={},
            warnings=[f"Archivo inválido o no soportado: {exc}"],
            needs_clarification=False,
            clarifying_questions=[],
            tool_trace=trace,
        )

    raw_text = extracted["raw_text"]
    metadata = extracted["metadata"]

    document_type = classify_document_tool(raw_text, metadata)
    trace.append(ToolTraceItem(tool="classify_document_tool", reason="Clasificar tipo de documento", success=True))

    llm_ok = True
    try:
        llm_data = _extract_with_llm(raw_text, metadata, document_type)
    except Exception as exc:
        llm_ok = False
        llm_data = _heuristic_extract(raw_text)
        llm_data.confidence_notes.append(f"Fallback heurístico tras error del LLM: {exc}")
    trace.append(ToolTraceItem(tool="llm_extraction", reason="Extraer estructura clínica con LLM", success=llm_ok))

    normalized_date = normalize_date_tool(llm_data.collection_date)
    trace.append(ToolTraceItem(tool="normalize_date_tool", reason="Normalizar fecha del estudio", success=True))

    extracted_data: dict[str, Any] = {
        "patient_name": llm_data.patient_name,
        "collection_date": normalized_date,
        "laboratory_name": llm_data.laboratory_name,
        "tests": [t.model_dump() for t in llm_data.tests],
        "observations": llm_data.observations,
        "confidence_notes": llm_data.confidence_notes,
    }

    warnings, out_flags = range_validator_tool(extracted_data)
    trace.append(ToolTraceItem(tool="range_validator_tool", reason="Validar consistencia y posibles valores fuera de rango", success=True))

    if out_flags:
        warnings.extend(out_flags)

    clarifying_questions = clarifying_questions_tool(extracted_data, warnings)
    trace.append(ToolTraceItem(tool="clarifying_questions_tool", reason="Generar preguntas de aclaración cuando faltan datos", success=True))

    needs_clarification = len(clarifying_questions) >= 2
    status = Status.needs_review if needs_clarification else Status.success

    if document_type not in {DocumentType.lab_result, DocumentType.other, DocumentType.unknown}:
        warnings.append("El documento no parece un resultado de laboratorio clínico.")
        status = Status.needs_review
        needs_clarification = True
        if len(clarifying_questions) < 2:
            clarifying_questions += [
                "¿Confirmas que el archivo corresponde a un resultado de laboratorio?",
                "¿Deseas continuar con extracción parcial del documento?",
            ]

    summary = (
        "Se procesó el archivo y se extrajeron resultados de laboratorio."
        if status == Status.success
        else "Se procesó parcialmente el archivo, pero requiere revisión o aclaraciones."
    )

    return AnalyzeResponse(
        status=status,
        document_type=document_type if document_type != DocumentType.other else DocumentType.lab_result,
        summary=summary,
        extracted_data=extracted_data,
        warnings=warnings,
        needs_clarification=needs_clarification,
        clarifying_questions=clarifying_questions if needs_clarification else [],
        tool_trace=trace,
    )
