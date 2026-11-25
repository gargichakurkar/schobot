from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from io import BytesIO
from math import sqrt
from time import monotonic
from typing import Any

try:
    import pytesseract
except ImportError:  # pragma: no cover
    pytesseract = None


def resolve_tesseract_binary() -> str | None:
    """Resolve the Tesseract binary path from TESSERACT_CMD or system PATH.

    Validates that the target path exists and has executable permissions.
    """
    custom_cmd = os.environ.get("TESSERACT_CMD")
    if custom_cmd:
        if os.path.isfile(custom_cmd) and os.access(custom_cmd, os.X_OK):
            return custom_cmd
        resolved = shutil.which(custom_cmd)
        if resolved and (os.name == "nt" or os.access(resolved, os.X_OK)):
            return resolved

    found = shutil.which("tesseract")
    if found:
        return found
    return None


# Initialize pytesseract command at module load if binary is available
if pytesseract is not None:
    _initial_bin = resolve_tesseract_binary()
    if _initial_bin and hasattr(pytesseract, "pytesseract") and hasattr(pytesseract.pytesseract, "tesseract_cmd"):
        pytesseract.pytesseract.tesseract_cmd = _initial_bin


MAX_PDF_PAGES = 15
MAX_IMAGE_PIXELS = 25_000_000
MAX_TEXT_CHARS = 100_000
OCR_TIMEOUT_SECONDS = 20
MAX_TOTAL_PDF_OCR_SECONDS = 90


class InvalidDocumentError(ValueError):
    pass


class OCRUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class OCRResult:
    text: str
    method: str
    pages_processed: int
    warnings: tuple[str, ...] = ()


class OCRService:
    def __init__(self) -> None:
        self.languages = os.environ.get("SCHOBOT_OCR_LANGUAGES", "eng+mar")

    def extract_text(self, file_bytes: bytes, file_type: str) -> OCRResult:
        if file_type == "application/pdf":
            result = self._extract_pdf(file_bytes)
        else:
            result = self._extract_image(file_bytes)

        text = result.text[:MAX_TEXT_CHARS]
        warnings = list(result.warnings)
        if len(result.text) > MAX_TEXT_CHARS:
            warnings.append("Extracted text was limited to the supported character maximum.")
        return OCRResult(
            text=text,
            method=result.method,
            pages_processed=result.pages_processed,
            warnings=tuple(warnings),
        )

    def _image_to_text(
        self,
        image: Any,
        timeout_seconds: float = OCR_TIMEOUT_SECONDS,
    ) -> str:
        if pytesseract is None:
            raise OCRUnavailableError(
                "Tesseract OCR library is not installed on the server."
            )
        binary = resolve_tesseract_binary()
        if binary and hasattr(pytesseract, "pytesseract") and hasattr(pytesseract.pytesseract, "tesseract_cmd"):
            pytesseract.pytesseract.tesseract_cmd = binary

        try:
            return pytesseract.image_to_string(
                image,
                lang=self.languages,
                timeout=timeout_seconds,
            )
        except getattr(pytesseract, "TesseractNotFoundError", Exception) as error:
            raise OCRUnavailableError(
                "Tesseract OCR is not installed on the server."
            ) from error
        except getattr(pytesseract, "TesseractError", Exception) as error:
            raise OCRUnavailableError(
                "Tesseract OCR or its configured language data is unavailable."
            ) from error

    def _extract_image(self, file_bytes: bytes) -> OCRResult:
        try:
            from PIL import Image, UnidentifiedImageError
        except ImportError as error:
            raise OCRUnavailableError(
                "Image processing library (Pillow) is not installed on the server."
            ) from error
        try:
            with Image.open(BytesIO(file_bytes)) as source_image:
                if source_image.width * source_image.height > MAX_IMAGE_PIXELS:
                    raise InvalidDocumentError(
                        "Image dimensions exceed the supported 25-megapixel limit."
                    )
                image = source_image.convert("RGB")
        except InvalidDocumentError:
            raise
        except (UnidentifiedImageError, OSError, getattr(Image, "DecompressionBombError", Exception)) as error:
            raise InvalidDocumentError("The uploaded image could not be decoded.") from error

        try:
            text = self._image_to_text(image)
        finally:
            image.close()
        warning = () if text.strip() else ("No readable text was detected.",)
        return OCRResult(text=text, method="ocr", pages_processed=1, warnings=warning)

    def _extract_pdf(self, file_bytes: bytes) -> OCRResult:
        try:
            from pypdf import PdfReader
            from pypdf.errors import PdfReadError
        except ImportError as error:
            raise OCRUnavailableError(
                "PDF processing library (pypdf) is not installed on the server."
            ) from error
        try:
            reader = PdfReader(BytesIO(file_bytes), strict=False)
        except PdfReadError as error:
            raise InvalidDocumentError("The uploaded PDF could not be read.") from error

        if reader.is_encrypted:
            raise InvalidDocumentError("Password-protected PDFs are not supported.")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise InvalidDocumentError(
                f"PDFs are limited to {MAX_PDF_PAGES} pages."
            )

        pages: list[str] = []
        methods: set[str] = set()
        warnings: list[str] = []
        pdfium_document = None
        ocr_deadline = monotonic() + MAX_TOTAL_PDF_OCR_SECONDS
        try:
            for page_index, source_page in enumerate(reader.pages):
                page_text = source_page.extract_text() or ""
                if len(page_text.strip()) < 20:
                    remaining_ocr_seconds = ocr_deadline - monotonic()
                    if remaining_ocr_seconds <= 0:
                        raise OCRUnavailableError(
                            "PDF OCR exceeded the 90-second processing limit."
                        )
                    if pdfium_document is None:
                        try:
                            import pypdfium2 as pdfium
                        except ImportError as error:
                            raise OCRUnavailableError(
                                "PDF page rendering is unavailable on the server."
                            ) from error
                        pdfium_document = pdfium.PdfDocument(file_bytes)

                    rendered_page = pdfium_document[page_index]
                    try:
                        page_width, page_height = rendered_page.get_size()
                        if page_width <= 0 or page_height <= 0:
                            raise InvalidDocumentError(
                                f"PDF page {page_index + 1} has invalid dimensions."
                            )
                        scale = min(
                            1.5,
                            sqrt(MAX_IMAGE_PIXELS / (page_width * page_height)),
                        )
                        bitmap = rendered_page.render(scale=scale)
                        try:
                            rendered_image = bitmap.to_pil()
                            try:
                                page_text = self._image_to_text(
                                    rendered_image,
                                    timeout_seconds=min(
                                        OCR_TIMEOUT_SECONDS,
                                        remaining_ocr_seconds,
                                    ),
                                )
                            finally:
                                rendered_image.close()
                        finally:
                            bitmap.close()
                    finally:
                        rendered_page.close()

                    if ocr_deadline - monotonic() <= 0:
                        raise OCRUnavailableError(
                            "PDF OCR exceeded the 90-second processing limit."
                        )
                    methods.add("ocr")
                else:
                    methods.add("pdf_text")

                if page_text.strip():
                    pages.append(page_text)
                else:
                    warnings.append(f"No readable text was detected on page {page_index + 1}.")
        finally:
            if pdfium_document is not None:
                pdfium_document.close()

        text = "\n\n".join(pages)
        method = "+".join(sorted(methods)) if methods else "pdf_text"
        return OCRResult(
            text=text,
            method=method,
            pages_processed=len(reader.pages),
            warnings=tuple(warnings),
        )
