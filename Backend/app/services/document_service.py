from __future__ import annotations


class DocumentService:
    """Future document preparation and OCR orchestration layer."""

    def __init__(self, db):
        self.db = db

    def save_document(self, **kwargs):
        return kwargs
