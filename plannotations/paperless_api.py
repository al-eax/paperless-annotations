import logging
import json
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Generator
import requests
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class BasicUser(BaseModel):
    id: int
    username: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class Note(BaseModel):
    id: int
    note: str
    created: datetime
    user: BasicUser


class CustomFieldInstance(BaseModel):
    value: Optional[Any] = None
    field: int


class CustomField(BaseModel):
    id: int
    name: str
    data_type: str
    extra_data: Optional[Any] = None
    document_count: int


class Document(BaseModel):
    id: int
    correspondent: Optional[int] = None
    document_type: Optional[int] = None
    storage_path: Optional[int] = None
    title: Optional[str] = None
    content: Optional[str] = None
    tags: List[int] = Field(default_factory=list)
    created: Optional[date] = None
    modified: datetime
    added: datetime
    deleted_at: Optional[datetime] = None
    archive_serial_number: Optional[int] = None
    original_file_name: Optional[str] = None
    archived_file_name: Optional[str] = None
    owner: Optional[int] = None
    permissions: Dict[str, Any] = Field(default_factory=dict)
    user_can_change: Optional[bool] = None
    is_shared_by_requester: Optional[bool] = None
    notes: List[Note] = Field(default_factory=list)
    custom_fields: List[CustomFieldInstance] = Field(default_factory=list)
    page_count: Optional[int] = None
    mime_type: Optional[str] = None


class PaginatedDocumentList(BaseModel):
    count: int
    next: Optional[str]
    previous: Optional[str]
    results: List[Document]
    all: Optional[List[int]] = None


class PaginatedCustomFieldList(BaseModel):
    count: int
    next: Optional[str]
    previous: Optional[str]
    results: List[CustomField]
    all: Optional[List[int]] = None


class PaperlessAPIError(Exception):
    pass


class PaperlessAPI:
    def __init__(self, base_url: str, api_token: str, timeout: int = 10) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        if not api_token:
            raise PaperlessAPIError("paperless api_token is required")
        # Paperless-ngx uses `Token <token>` authorization header
        self.session.headers.update({"Authorization": f"Token {api_token}"})

    def _url(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

    def _get_json(self, path: str, params: dict | None = None) -> dict:
        return self._request("get", path, params=params or {}).json()

    def _get_content(self, path: str) -> bytes:
        return self._request("get", path).content

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Send an HTTP request and raise a PaperlessAPIError on failure.

        Returns the raw requests.Response on success.
        """
        url = self._url(path)
        logger.debug(
            "%s %s kwargs=%s",
            method.upper(),
            url,
            {k: v for k, v in kwargs.items() if k != "json"},
        )
        try:
            resp = self.session.request(method, url, timeout=self.timeout, **kwargs)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.exception("Paperless API request failed: %s %s", method.upper(), url)
            raise PaperlessAPIError(str(exc)) from exc
        return resp

    def _documents(self, page: int = 1) -> dict:
        """Return a single page dict from /api/documents/ (paginated)."""
        return self._get_json("/api/documents/", params={"page": page})

    def documents_custom_field_query_iter(
        self, custom_field_query: object
    ) -> Generator[Document, None, None]:
        """Yield documents matching a `custom_field_query`.
        see https://docs.paperless-ngx.com/api/#filtering-by-custom-fields

        custom_field_query samples:
            ["<field_name>", "exists", true]
            ["<field_name>", "equals", "<value>"]
            ["<field_name>", "contains", "<substring>"]
        parsed `Document` models.
        """
        page = 1
        while True:
            params = {
                "page": page,
                "custom_field_query": json.dumps(custom_field_query),
            }
            payload = self._get_json("/api/documents/", params=params)
            for doc in payload.get("results", []):
                yield Document.model_validate(doc)
            if not payload.get("next"):
                break
            page += 1

    def documents_iter(self) -> Generator[Document, None, None]:
        """Yield documents across all pages as `Document` models."""
        page = 1
        while True:
            payload = self._documents(page=page)
            for doc in payload.get("results", []):
                yield Document.model_validate(doc)
            if not payload.get("next"):
                break
            page += 1

    def document(self, doc_id: int) -> Document:
        """Return document metadata from /api/documents/{id}/ as a Document."""
        return Document.model_validate(self._get_json(f"/api/documents/{doc_id}/"))

    def document_notes(self, doc_id: int) -> List[Note]:
        """Return list of notes for a document as `Note` models."""
        return [
            Note.model_validate(n)
            for n in self._get_json(f"/api/documents/{doc_id}/notes/")
        ]

    def download_document(self, doc_id: int) -> bytes:
        """Return bytes for a document from /api/documents/{id}/download"""
        res = self._get_content(f"/api/documents/{doc_id}/download/")
        return res

    # --- Notes and custom fields helpers ---
    def add_note_to_document(self, doc_id: int, note: str) -> Note:
        """Add a note to a document (POST /api/documents/{id}/notes/).

        Returns the created note dict.
        """
        notes = self._request(
            "post", f"/api/documents/{doc_id}/notes/", json={"note": note}
        ).json()
        if not notes:
            return None
        return Note.model_validate(notes[-1])

    def delete_note(self, doc_id: int, note_id: int) -> bool:
        """Delete a note from a document"""
        self._request(
            "delete", f"/api/documents/{doc_id}/notes/", params={"id": note_id}
        )
        return True

    def custom_fields(self, page: int = 1) -> dict:
        """Return a single page of custom fields from /api/custom-fields/"""
        return self._get_json("/api/custom_fields/", params={"page": page})

    def custom_fields_iter(self) -> Generator[dict, None, None]:
        """Yield all custom field objects across pages."""
        page = 1
        while True:
            payload = self.custom_fields(page=page)
            for cf in payload.get(
                "results", payload if isinstance(payload, list) else []
            ):
                yield CustomField.model_validate(cf)
            if not payload.get("next"):
                break
            page += 1

    def get_custom_field_by_name(self, name: str) -> Optional[CustomField]:
        """Find a custom field by name (returns first match) or None."""
        for cf in self.custom_fields_iter():
            if cf.name == name:
                return cf
        return None

    def create_custom_field(self, name: str, data_type: str = "url") -> CustomField:
        """Create a new global custom field (/api/custom_fields/)."""
        return CustomField.model_validate(
            self._request(
                "post",
                "/api/custom_fields/",
                json={"name": name, "data_type": data_type},
            ).json()
        )

    def delete_custom_field(self, custom_field_id: int) -> bool:
        """Delete a custom field by id (/api/custom_fields/{id}/).

        Returns True on success (200/204). Raises PaperlessAPIError on failure.
        """
        self._request("delete", f"/api/custom_fields/{custom_field_id}/")
        return True

    def add_custom_field_to_document(
        self, doc: Document, custom_field_id: int, value: str
    ) -> Document:
        """Add or update a custom field instance on a document."""

        doc_cf_instances = doc.custom_fields or []

        updated = False
        for inst in doc_cf_instances:
            if inst.field == custom_field_id:
                inst.value = value
                updated = True
                break

        if not updated:
            doc_cf_instances.append(
                CustomFieldInstance(field=custom_field_id, value=value)
            )

        updated_doc = self._request(
            "patch",
            f"/api/documents/{doc.id}/",
            json={"custom_fields": [cf.model_dump() for cf in doc_cf_instances]},
        ).json()
        return Document.model_validate(updated_doc)

    def delete_custom_field_from_document(
        self, doc: Document, custom_field_id: int
    ) -> Document:
        """Delete a custom field instance from a document."""
 
        doc_cf_instances = doc.custom_fields

        filtered = [
            inst.model_dump()
            for inst in doc_cf_instances
            if not (inst.field == custom_field_id)
        ]

        if len(filtered) == len(doc_cf_instances):
            # No change needed
            return doc

        updated_doc = self._request(
            "patch",
            f"/api/documents/{doc.id}/",
            json={"custom_fields": filtered},
        ).json()
        return Document.model_validate(updated_doc)
