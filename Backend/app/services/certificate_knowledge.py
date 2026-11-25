from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any

class CertificateType(str, Enum):
    INCOME = "income_certificate"
    CASTE = "caste_certificate"
    CASTE_VALIDITY = "caste_validity_certificate"
    DOMICILE = "domicile_certificate"
    NATIONALITY = "nationality_certificate"


class KnowledgeBaseUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class OfficialSource:
    id: str
    title: str
    issuer: str
    url: str
    document_type: str
    version: str | None
    languages: str
    filename: str
    certificate_types: tuple[CertificateType, ...]
    extraction_kind: str
    expected_text: str
    summary: str
    limitations: str


@dataclass(frozen=True)
class Passage:
    source_id: str
    certificate_types: tuple[CertificateType, ...]
    text: str
    page: int | None


_SOURCE_DIRECTORY = Path(__file__).resolve().parents[1] / "data" / "certificate_sources" / "originals"
_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_CHUNK_SIZE = 1100
_CHUNK_OVERLAP = 160
_PASSAGE_LIMIT = 2

_SOURCES = (
    OfficialSource(
        id="income-form",
        title="Application for Income Certificate (1 year / 3 year)",
        issuer="Government of Maharashtra, Revenue Department",
        url="https://revenue.mahaonline.gov.in/Site/Common/Documents/Downloads/Application_form_for_Income_Certificate.pdf",
        document_type="PDF application form",
        version="PDF metadata: created 15 April 2014; modified 16 April 2014",
        languages="English and Marathi",
        filename="income_certificate_application.pdf",
        certificate_types=(CertificateType.INCOME,),
        extraction_kind="pdf",
        expected_text="income certificate",
        summary="The application form collects applicant and family details, income sources, agricultural land details, beneficiary and purpose.",
        limitations="Checklist examples are not universal requirements and do not establish scholarship income limits or certificate validity.",
    ),
    OfficialSource(
        id="income-service",
        title="Income Certificate service detail",
        issuer="Government of Maharashtra, Aaple Sarkar / Revenue Department",
        url="https://aaplesarkar.mahaonline.gov.in/en/Login/Certificate_Documents?ServiceId=1251",
        document_type="Official service-detail webpage",
        version=None,
        languages="English page; Marathi alternate link present",
        filename="aaple_income_service.html",
        certificate_types=(CertificateType.INCOME,),
        extraction_kind="service_form",
        expected_text="1251",
        summary="The official service entry identifies the Income Certificate service and its listed administrative details.",
        limitations="The service page does not establish a universal supporting-document checklist.",
    ),
    OfficialSource(
        id="caste-service",
        title="Caste Certificate service detail",
        issuer="Government of Maharashtra, Aaple Sarkar / Revenue Department",
        url="https://aaplesarkar.mahaonline.gov.in/en/Login/Certificate_Documents?ServiceId=1284",
        document_type="Official service-detail webpage",
        version=None,
        languages="English page; Marathi alternate link present",
        filename="aaple_caste_service.html",
        certificate_types=(CertificateType.CASTE,),
        extraction_kind="service_form",
        expected_text="Caste Certificate",
        summary="The official service page lists evidence categories and examples for the caste-certificate application.",
        limitations="Its broad checklist is not a universal requirement and does not resolve legal eligibility or community-schedule questions.",
    ),
    OfficialSource(
        id="caste-act",
        title="Maharashtra Act No. XXIII of 2001 — Caste Certificate Act, 2000",
        issuer="Government of Maharashtra, Law and Judiciary Department",
        url="https://cdnbbsr.s3waas.gov.in/s36a4cbdaedcbda0fa8ddc7ea32073c475/uploads/2025/02/20250210421165874.pdf",
        document_type="PDF Act",
        version="Official copy states modified through 29 October 2012",
        languages="English",
        filename="maharashtra_caste_act_modified_2012.pdf",
        certificate_types=(CertificateType.CASTE, CertificateType.CASTE_VALIDITY),
        extraction_kind="pdf",
        expected_text="Maharashtra",
        summary="Official copy of Maharashtra Act No. XXIII of 2001 concerning caste-certificate issuance and verification.",
        limitations="The available copy is not verified as a consolidation current through 2026; it is not used to determine an individual's legal status.",
    ),
    OfficialSource(
        id="caste-rules",
        title="Caste Certificate Rules, 2012",
        issuer="Government of Maharashtra, Social Justice and Special Assistance Department",
        url="https://cdnbbsr.s3waas.gov.in/s3b090409688550f3cc93f4ed88ec6cafb/uploads/2025/01/202501131491187877.pdf",
        document_type="PDF Government Gazette rules",
        version="Notification dated 31 August 2012; Gazette published 3 September 2012",
        languages="English",
        filename="maharashtra_caste_certificate_rules_2012.pdf",
        certificate_types=(CertificateType.CASTE, CertificateType.CASTE_VALIDITY),
        extraction_kind="pdf",
        expected_text="Caste Certificate Rules",
        summary="Official 2012 Rules PDF relating to caste certificate issuance.",
        limitations="The downloaded Gazette is scanned and later amendments were not verified. It is excluded from retrieval unless extractable text is available.",
    ),
    OfficialSource(
        id="caste-validity-service",
        title="Department Notified Services — Caste Certificate Verification Committee",
        issuer="Government of Maharashtra, Aaple Sarkar",
        url="https://aaplesarkar.mahaonline.gov.in/en/CommonForm/ViewAllServices",
        document_type="Official services-directory webpage",
        version=None,
        languages="English",
        filename="aaple_certificate_services.html",
        certificate_types=(CertificateType.CASTE_VALIDITY,),
        extraction_kind="directory_row",
        expected_text="Caste Certificate Verification Committee",
        summary="The official directory lists the Caste Certificate Verification Committee as a service separate from caste-certificate issuance.",
        limitations="The listing does not provide complete current application guidance or establish certificate validity.",
    ),
    OfficialSource(
        id="domicile-form",
        title="Application for Age, Nationality and Domicile Certificate",
        issuer="Government of Maharashtra, Revenue Department",
        url="https://revenue.mahaonline.gov.in/Site/Common/Documents/Downloads/Application_form_for_Age_Nationality_and%20Domicile_Certificate.pdf",
        document_type="PDF application form",
        version="PDF metadata: created 15 April 2014; modified 16 April 2014",
        languages="English and Marathi",
        filename="age_nationality_domicile_application.pdf",
        certificate_types=(CertificateType.DOMICILE, CertificateType.NATIONALITY),
        extraction_kind="pdf",
        expected_text="domicile",
        summary="The combined application form asks for current and permanent address, residence history and migration information.",
        limitations="The form does not establish a standalone nationality-only procedure or a universal minimum Maharashtra residence period.",
    ),
    OfficialSource(
        id="domicile-service",
        title="Age, Nationality and Domicile Certificate service detail",
        issuer="Government of Maharashtra, Aaple Sarkar / Revenue Department",
        url="https://aaplesarkar.mahaonline.gov.in/en/Login/Certificate_Documents?ServiceId=1253",
        document_type="Official service-detail webpage",
        version=None,
        languages="English page; Marathi alternate link present",
        filename="aaple_age_nationality_domicile_service.html",
        certificate_types=(CertificateType.DOMICILE, CertificateType.NATIONALITY),
        extraction_kind="service_form",
        expected_text="1253",
        summary="The official listing identifies a combined Age, Nationality and Domicile service.",
        limitations="The page does not establish a full nationality test or a universal domicile residence threshold.",
    ),
)


def _chunks(text: str, source: OfficialSource, page: int | None) -> list[Passage]:
    normalized = re.sub(r"[ \t]+", " ", text).strip()
    if not normalized:
        return []

    passages = []
    start = 0
    while start < len(normalized):
        end = min(start + _CHUNK_SIZE, len(normalized))
        if end < len(normalized):
            boundary = max(
                normalized.rfind(". ", start + _CHUNK_SIZE // 2, end),
                normalized.rfind("; ", start + _CHUNK_SIZE // 2, end),
            )
            if boundary > start:
                end = boundary + 1
        excerpt = normalized[start:end].strip()
        if excerpt:
            passages.append(
                Passage(
                    source_id=source.id,
                    certificate_types=source.certificate_types,
                    text=excerpt,
                    page=page,
                )
            )
        if end == len(normalized):
            break
        start = max(start + 1, end - _CHUNK_OVERLAP)
    return passages


def _extract_html(source: OfficialSource, raw: bytes) -> str:
    try:
        from bs4 import BeautifulSoup
    except ImportError as error:
        raise KnowledgeBaseUnavailableError(
            "HTML parser library (beautifulsoup4) is unavailable on the server."
        ) from error
    soup = BeautifulSoup(raw, "html.parser")
    if source.extraction_kind == "directory_row":
        matching_rows = [
            row
            for row in soup.find_all("tr")
            if source.expected_text.casefold() in row.get_text(" ", strip=True).casefold()
        ]
        if len(matching_rows) != 1:
            raise KnowledgeBaseUnavailableError(
                f"Expected exactly one approved service row in {source.filename}."
            )
        return matching_rows[0].get_text(" ", strip=True)

    if source.extraction_kind != "service_form":
        raise KnowledgeBaseUnavailableError(
            f"Unsupported HTML extraction rule for source {source.id}."
        )
    form = soup.find("form", id="TheForm")
    if form is None:
        raise KnowledgeBaseUnavailableError(
            f"The approved service form was not found in {source.filename}."
        )
    text = form.get_text(" ", strip=True)
    if source.expected_text.casefold() not in text.casefold() and source.expected_text not in raw.decode(
        "utf-8", errors="replace"
    ):
        raise KnowledgeBaseUnavailableError(
            f"The service identity check failed for {source.filename}."
        )
    return text


def _extract_source(source: OfficialSource, raw: bytes) -> list[Passage]:
    if source.extraction_kind == "pdf":
        if not raw.startswith(b"%PDF-"):
            raise KnowledgeBaseUnavailableError(
                f"The approved PDF signature is missing from {source.filename}."
            )
        try:
            from pypdf import PdfReader
            from pypdf.errors import PdfReadError
        except ImportError as error:
            raise KnowledgeBaseUnavailableError(
                "PDF parsing library (pypdf) is unavailable on the server."
            ) from error
        try:
            reader = PdfReader(BytesIO(raw), strict=False)
            passages = []
            for page_number, page in enumerate(reader.pages, start=1):
                page_text = page.extract_text() or ""
                if len(page_text.strip()) >= 20:
                    passages.extend(_chunks(page_text, source, page_number))
            return passages
        except (PdfReadError, OSError, ValueError) as error:
            raise KnowledgeBaseUnavailableError(
                f"The approved PDF could not be parsed: {source.filename}."
            ) from error

    text = _extract_html(source, raw)
    return _chunks(text, source, None)


@lru_cache(maxsize=1)
def _load_corpus() -> tuple[tuple[Passage, ...], tuple[dict[str, Any], ...]]:
    passages: list[Passage] = []
    manifest: list[dict[str, Any]] = []
    for source in _SOURCES:
        path = _SOURCE_DIRECTORY / source.filename
        try:
            raw = path.read_bytes()
        except OSError as error:
            raise KnowledgeBaseUnavailableError(
                f"Approved knowledge source is unavailable: {source.filename}."
            ) from error

        source_passages = _extract_source(source, raw)
        digest = hashlib.sha256(raw).hexdigest()
        status = "indexed" if source_passages else "excluded_no_extractable_text"
        manifest.append(
            {
                "id": source.id,
                "title": source.title,
                "issuer": source.issuer,
                "url": source.url,
                "document_type": source.document_type,
                "version": source.version,
                "languages": source.languages,
                "filename": source.filename,
                "sha256": digest,
                "certificate_types": [item.value for item in source.certificate_types],
                "chunk_count": len(source_passages),
                "ingestion_status": status,
                "limitations": source.limitations,
            }
        )
        passages.extend(source_passages)

    if not passages:
        raise KnowledgeBaseUnavailableError(
            "The approved certificate knowledge base contains no extractable text."
        )
    return tuple(passages), tuple(manifest)


@lru_cache(maxsize=1)
def _load_embedding_model() -> Any:
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(
            _MODEL_NAME,
            local_files_only=True,
            device="cpu",
        )
    except (OSError, ValueError, RuntimeError, ImportError) as error:
        raise KnowledgeBaseUnavailableError(
            "The local embedding model is unavailable; no external model download was attempted."
        ) from error


@lru_cache(maxsize=1)
def _load_embeddings() -> tuple[tuple[Passage, ...], tuple[dict[str, Any], ...], Any]:
    passages, manifest = _load_corpus()
    try:
        import numpy as np
        model = _load_embedding_model()
        vectors = model.encode(
            [passage.text for passage in passages],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
    except (OSError, ValueError, RuntimeError, ImportError) as error:
        raise KnowledgeBaseUnavailableError(
            "The approved source passages could not be embedded locally."
        ) from error
    return passages, manifest, vectors


def source_manifest() -> list[dict[str, Any]]:
    _, manifest = _load_corpus()
    return [dict(source) for source in manifest]


def retrieve_sources(
    certificate_type: CertificateType,
    query: str,
    limit: int = 4,
) -> list[dict[str, Any]]:
    passages, manifest, vectors = _load_embeddings()
    source_by_id = {source.id: source for source in _SOURCES}
    manifest_by_id = {source["id"]: source for source in manifest}
    eligible_indexes = [
        index
        for index, passage in enumerate(passages)
        if certificate_type in passage.certificate_types
    ]
    if not eligible_indexes:
        return []

    model = _load_embedding_model()
    query_vector = model.encode(
        [f"{certificate_type.value} {query}"],
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )[0]
    scores = vectors[eligible_indexes] @ query_vector
    ranked_indexes = sorted(
        zip(eligible_indexes, scores.tolist()),
        key=lambda item: (-item[1], passages[item[0]].source_id, passages[item[0]].page or 0),
    )

    grouped: dict[str, list[tuple[Passage, float]]] = {}
    for passage_index, score in ranked_indexes:
        passage = passages[passage_index]
        grouped.setdefault(passage.source_id, []).append((passage, float(score)))

    ranked_source_ids = sorted(
        grouped,
        key=lambda source_id: (-grouped[source_id][0][1], source_id),
    )[: max(0, limit)]
    retrieved_at = datetime.now(timezone.utc).isoformat()
    references = []
    for source_id in ranked_source_ids:
        source = source_by_id[source_id]
        source_manifest_entry = manifest_by_id[source_id]
        selected_passages = grouped[source_id][:_PASSAGE_LIMIT]
        references.append(
            {
                "id": source.id,
                "title": source.title,
                "issuer": source.issuer,
                "url": source.url,
                "document_type": source.document_type,
                "version": source.version,
                "languages": source.languages,
                "verification_status": "Official source; downloaded file fingerprinted at retrieval.",
                "summary": source.summary,
                "limitations": source.limitations,
                "source_sha256": source_manifest_entry["sha256"],
                "retrieval_score": round(selected_passages[0][1], 6),
                "retrieval_method": "local_sentence_transformer_cosine",
                "retrieved_at": retrieved_at,
                "retrieved_passages": [
                    {
                        "page": passage.page,
                        "text": passage.text,
                        "score": round(score, 6),
                    }
                    for passage, score in selected_passages
                ],
            }
        )
    return references
