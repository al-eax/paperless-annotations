import json
import gzip
import base64
import logging
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional
from datetime import datetime
from django.template import Template, Context
from pydantic import BaseModel
from core.settings import ANNO_SERIALIZER, ANNO_STORAGE
from .models import DbAnnotation
from .paperless_api import PaperlessAPI

logger = logging.getLogger(__name__)


class Annotation(BaseModel):
    created: str
    author: str = ""
    type: int
    pageIndex: int
    db_id: Optional[int] = None
    contents: Optional[str] = None

    class Config:
        extra = "allow"


class AnnoStorage(ABC):
    """Abstract base class for annotation storage backends."""

    @abstractmethod
    def get_annotations(
        self, doc_id: int, page: Optional[int] = None
    ) -> AsyncGenerator[Annotation, None]:
        """Retrieve annotations for a document, optionally filtered by page."""

    @abstractmethod
    def create_annotation(self, doc_id: int, annotation: Annotation) -> Annotation:
        """Create a new annotation for a document."""

    @abstractmethod
    def update_annotation(
        self, doc_id: int, updated_annotation: Annotation
    ) -> Annotation:
        """Update an existing annotation for a document."""

    @abstractmethod
    def delete_annotation_by_id(self, doc_id: int, db_id: int) -> bool:
        """Delete an annotation by its database ID."""


class AnnoSerializer(ABC):
    """Abstract base class for data serialization strategies."""

    @staticmethod
    @abstractmethod
    def serialize(obj):
        """Serialize an object to a string."""

    @staticmethod
    @abstractmethod
    def deserialize(s):
        """Deserialize a string to an object."""

    @classmethod
    def get_serializer_by_name(cls, name: str) -> "AnnoSerializer":
        """Get a serializer class by its name."""
        for subclass in cls.__subclasses__():
            if subclass.NAME == name:
                return subclass
        raise ValueError(
            f"Serializer with name '{name}' not found. Known serializers: "
            + ", ".join([sc.NAME for sc in cls.__subclasses__()])
        )


class Base85GzipJSONSerializer(AnnoSerializer):
    NAME = "85gj"

    @staticmethod
    def serialize(obj):
        """Serialize an object to a base85-encoded gzip-compressed JSON string."""
        return base64.b85encode(gzip.compress(json.dumps(obj).encode())).decode()

    @staticmethod
    def deserialize(s):
        """Deserialize a base85-encoded gzip-compressed JSON string to an object."""
        return json.loads(gzip.decompress(base64.b85decode(s.encode())).decode())


class JsonSerializer(AnnoSerializer):
    NAME = "ji2"

    @staticmethod
    def serialize(obj):
        """Serialize an object to a JSON string."""
        return json.dumps(obj, indent=2)

    @staticmethod
    def deserialize(s):
        """Deserialize a JSON string to an object."""
        return json.loads(s)


class PaperlessNotesStorage(AnnoStorage):
    """Annotation storage implementation using Paperless-ngx document notes."""

    ANNOTATION_CONTENT_BEGIN = "------------ DATA BEGIN ------------"
    ANNOTATION_CONTENT_END = "------------ DATA END ------------"

    def __init__(self, paperless: PaperlessAPI):
        self.default_anno_serializer = AnnoSerializer.get_serializer_by_name(
            ANNO_SERIALIZER
        )
        self.paperless = paperless

    def get_annotations(self, doc_id: int, page: Optional[int] = None):
        """Retrieve annotations from document notes, optionally filtered by page."""
        notes = self.paperless.document_notes(doc_id)
        for note in notes:
            try:
                annotation = self._note_content_to_anno(note.note)
                annotation.db_id = note.id
                if page is None or annotation.pageIndex == page:
                    yield annotation
            except Exception:
                # Skip malformed notes that can't be parsed as annotations
                continue

    def _build_note_header(self, annotation: Annotation) -> str:
        """Build the header part of a note for an annotation."""

        created_formatted = annotation.created
        if isinstance(created_formatted, str):
            try:
                dt = datetime.fromisoformat(created_formatted.replace("Z", "+00:00"))
                created_formatted = dt.strftime("%Y.%m.%d %H:%M")
            except ValueError:
                pass  # Keep original format if parsing fails
        context = {
            "author": annotation.author,
            "page": annotation.pageIndex + 1,
            "page_index": annotation.pageIndex,
            "created": created_formatted,
            "comment": annotation.contents or "",
            "text": getattr(annotation, "custom", {}).get("text", None),
            "type": annotation.type,
            "annotation": annotation,
        }
        with open("note_annotation.template", "r", encoding="utf-8") as template_file:
            template_content = template_file.read()
            template = Template(template_content)
            rendered_header = template.render(Context(context)).replace("\n\n", "\n")
            return rendered_header

    def _anno_to_note_content(self, annotation: Annotation) -> str:
        """Serialize an annotation for storage in a Paperless note."""

        serialized = (
            self.default_anno_serializer.serialize(annotation.model_dump()) + "\n"
        )
        header = self._build_note_header(annotation)
        if (
            self.ANNOTATION_CONTENT_BEGIN in header
            or self.ANNOTATION_CONTENT_END in header
        ):
            raise ValueError(
                "Annotation header contains reserved content delimiter "
                + f"{self.ANNOTATION_CONTENT_BEGIN} or {self.ANNOTATION_CONTENT_END}"
            )
        if (
            self.ANNOTATION_CONTENT_BEGIN in serialized
            or self.ANNOTATION_CONTENT_END in serialized
        ):
            raise ValueError(
                "Serialized annotation contains reserved content delimiter "
                + f"{self.ANNOTATION_CONTENT_BEGIN} or {self.ANNOTATION_CONTENT_END}"
            )

        content = header
        content += f"\n{self.ANNOTATION_CONTENT_BEGIN}\n"
        content += self.default_anno_serializer.NAME + "\n"
        content += serialized
        content += f"{self.ANNOTATION_CONTENT_END}"
        return content

    def _note_content_to_anno(self, note_content: str) -> Annotation:
        """Deserialize a Paperless note's JSON content to an annotation."""
        begin_idx = note_content.find(self.ANNOTATION_CONTENT_BEGIN)
        end_idx = note_content.find(self.ANNOTATION_CONTENT_END)
        if begin_idx == -1 or end_idx == -1:
            return None
        data_area = note_content[
            begin_idx + len(self.ANNOTATION_CONTENT_BEGIN) : end_idx
        ].strip()

        serializer_name = data_area.splitlines()[0].strip()
        if not serializer_name:
            return None
        serializer = AnnoSerializer.get_serializer_by_name(serializer_name)
        data_area = "\n".join(data_area.splitlines()[1:])
        note_content = serializer.deserialize(data_area)
        if note_content is None:
            return None
        return Annotation(**note_content)

    def create_annotation(self, doc_id: int, annotation: Annotation) -> Annotation:
        """Create a new annotation as a document note."""
        note = self.paperless.add_note_to_document(
            doc_id=doc_id, note=self._anno_to_note_content(annotation)
        )
        annotation.db_id = note.id
        return annotation

    def update_annotation(
        self, doc_id: int, updated_annotation: Annotation
    ) -> Annotation:
        """Update an annotation by replacing its note content."""
        old_note_id = updated_annotation.db_id
        if old_note_id is None:
            raise ValueError("Cannot update annotation without db_id")

        # Delete old note
        if not self.delete_annotation_by_id(doc_id, old_note_id):
            raise ValueError(f"Annotation with db_id {old_note_id} not found")

        # Create new note with updated content
        note = self.paperless.add_note_to_document(
            doc_id=doc_id, note=self._anno_to_note_content(updated_annotation)
        )
        updated_annotation.db_id = note.id
        return updated_annotation

    def delete_annotation_by_id(self, doc_id: int, db_id: int) -> bool:
        """Delete an annotation by finding and removing its corresponding note."""
        return self.paperless.delete_note(doc_id, db_id)


class DatabaseAnnotationStorage(AnnoStorage):
    def create_annotation(self, doc_id, annotation):
        """Store a new annotation in the database."""
        page_index = annotation.pageIndex
        db_anno = DbAnnotation.objects.create(
            doc_id=doc_id,
            db_id=annotation.db_id or 0,
            page_index=page_index,
            anno_obj=annotation.model_dump(),
        )
        annotation.db_id = db_anno.id
        return annotation

    def get_annotations(self, doc_id: int, page: Optional[int] = None):
        """Retrieve annotations from the database, optionally filtered by page."""
        query = None
        if page:
            query = DbAnnotation.objects.filter(doc_id=doc_id, page_index=page)
        else:
            query = DbAnnotation.objects.filter(doc_id=doc_id)
        for db_anno in query:
            anno = Annotation(**db_anno.anno_obj)
            anno.db_id = db_anno.id
            if page is None or anno.pageIndex == page:
                yield anno

    def update_annotation(self, doc_id: int, updated_annotation: Annotation):
        """Update an existing annotation in the database."""
        db_anno = DbAnnotation.objects.get(id=updated_annotation.db_id, doc_id=doc_id)
        db_anno.page_index = updated_annotation.pageIndex
        db_anno.anno_obj = updated_annotation.model_dump()
        db_anno.save()
        return updated_annotation

    def delete_annotation_by_id(self, doc_id: int, db_id: int) -> bool:
        """Delete an annotation by its database ID."""
        try:
            db_anno = DbAnnotation.objects.get(id=db_id, doc_id=doc_id)
            db_anno.delete()
            return True
        except DbAnnotation.DoesNotExist:
            return False


def get_configured_annotation_storage(
    paperless: PaperlessAPI,
) -> AnnoStorage:
    """Get the annotation storage backend as per configuration."""
    if ANNO_STORAGE == "database":
        logger.info("Using DatabaseAnnotationStorage for annotations")
        return DatabaseAnnotationStorage()
    elif ANNO_STORAGE == "paperless_notes":
        logger.info("Using PaperlessNotesStorage for annotations")
        return PaperlessNotesStorage(paperless)
    else:
        raise ValueError(f"Unknown annotation storage type: {ANNO_STORAGE}")
