from typing import Any, Iterable, Optional
import logging
from .paperless_api import PaperlessAPI
from .annostorage import Annotation, get_configured_annotation_storage

logger = logging.getLogger(__name__)


class PaperlessAnnotator:

    def __init__(self, paperless: PaperlessAPI):
        self.paperless = paperless
        self.annotation_storage = get_configured_annotation_storage(paperless)

    def download_document(self, doc_id: int) -> bytes:
        """Return the raw PDF for a Paperless document."""
        logger.debug("Downloading document %d", doc_id)
        return self.paperless.download_document(doc_id)

    def get_page_annotations(self, doc_id: int, page: Optional[int]) -> Iterable[Any]:
        """List annotations for a document.
        If `page` is provided, only return annotations for that page.
        """
        logger.debug("Getting annotations for doc %d, page %s", doc_id, page)
        for anno in self.annotation_storage.get_annotations(doc_id, page):
            yield anno

    def delete_anno(self, doc_id: int, annotation: Annotation) -> bool:
        """Delete an annotation and all its replies."""
        logger.info("Deleting annotation %s from doc %d", annotation.db_id, doc_id)
        # Delete all reply annotations first
        for other_anno in self.annotation_storage.get_annotations(
            doc_id, annotation.pageIndex
        ):
            is_reply = (
                other_anno.db_id != annotation.db_id
                and getattr(other_anno, "inReplyToId", None) == annotation.id
            )
            if is_reply:
                logger.debug("Deleting reply annotation %s", other_anno.db_id)
                self.annotation_storage.delete_annotation_by_id(
                    doc_id, other_anno.db_id
                )

        # Delete the main annotation
        return self.annotation_storage.delete_annotation_by_id(doc_id, annotation.db_id)

    def create_annotation(self, doc_id: int, annotation: Annotation) -> Annotation:
        """Create a new annotation for a document."""
        logger.info(
            "Creating annotation on doc %d, page %d", doc_id, annotation.pageIndex
        )
        return self.annotation_storage.create_annotation(doc_id, annotation)

    def update_annotation(
        self, doc_id: int, new_annotation: Annotation
    ) -> Optional[Any]:
        """Update an existing annotation."""
        logger.info("Updating annotation %s on doc %d", new_annotation.db_id, doc_id)
        return self.annotation_storage.update_annotation(doc_id, new_annotation)

    def get_all_documents_with_annotations(self, docs_to_skip) -> Iterable[Any]:
        """Get all document IDs that have annotations."""
        logger.info("Getting all documents with annotations")
        documents = list(self.paperless.documents_iter())
        for doc in documents:

            if docs_to_skip and doc.id in docs_to_skip:
                logger.debug("Skipping doc %d", doc.id)
                continue
            for _ in self.annotation_storage.get_annotations(doc.id):
                yield doc
                break

    def delete_all_annotations(self, docs_to_skip: None):
        """Delete all annotations for all documents, except those in docs_to_skip."""
        if docs_to_skip is None:
            docs_to_skip = []
        logger.info("Starting deletion of all annotations")
        processed_docs = set()
        documents = list(self.paperless.documents_iter())
        logger.info("Found %d documents", len(documents))
        for doc in self.get_all_documents_with_annotations(docs_to_skip=docs_to_skip):
            if doc.id in docs_to_skip:
                logger.debug("Skipping doc %d", doc.id)
                continue
            for anno in self.annotation_storage.get_annotations(doc.id):
                self.annotation_storage.delete_annotation_by_id(doc.id, anno.db_id)
                processed_docs.add(doc.id)
        logger.info("Deleted annotations from %d documents", len(processed_docs))
        return processed_docs
