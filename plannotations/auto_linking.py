import logging
import time
from django.urls import reverse
from core.settings import (
    BASE_URL,
    CUSTOM_FIELD_NAME,
    PAPERLESS_URL,
    UPDATE_INTERVAL_MINS,
)
from .paperless_api import PaperlessAPI
from .models import User

logger = logging.getLogger(__name__)

_custom_field_cache = {}


def delete_all_document_links(ppl: PaperlessAPI):
    """Delete all custom field links from all documents."""
    cf_query = [CUSTOM_FIELD_NAME, "exists", True]
    removed_links = 0
    cf_id = _get_or_create_custom_link_field(ppl)
    for doc in ppl.documents_custom_field_query_iter(cf_query):
        ppl.delete_custom_field_from_document(doc, cf_id.id)
        removed_links += 1
    return removed_links


def _get_or_create_custom_link_field(ppl: PaperlessAPI):
    """Ensure the custom field exists and return it (cached)."""
    # Implementation as in previous snippets
    if CUSTOM_FIELD_NAME in _custom_field_cache:
        return _custom_field_cache[CUSTOM_FIELD_NAME]

    cf = ppl.get_custom_field_by_name(CUSTOM_FIELD_NAME)
    if cf:
        logger.debug("Found existing custom field '%s'", CUSTOM_FIELD_NAME)
        _custom_field_cache[CUSTOM_FIELD_NAME] = cf
        return cf

    logger.info("Creating custom field '%s'", CUSTOM_FIELD_NAME)
    cf = ppl.create_custom_field(CUSTOM_FIELD_NAME, data_type="url")
    _custom_field_cache[CUSTOM_FIELD_NAME] = cf
    logger.info("Created custom field '%s'", CUSTOM_FIELD_NAME)
    return cf


def update_document_links(ppl: PaperlessAPI, docs_to_skip: list[int] | None = None):
    if not docs_to_skip:
        docs_to_skip = []

    link_is_outdated_query = [
        "NOT",
        [
            CUSTOM_FIELD_NAME,
            "istartswith",
            f"{BASE_URL}/view/",
        ],
    ]  # placeholder
    link_not_exists_query = [
        CUSTOM_FIELD_NAME,
        "exists",
        False,
    ]
    custom_field = _get_or_create_custom_link_field(ppl)
    updated_docs = []
    for doc in ppl.documents_custom_field_query_iter(link_not_exists_query):
        if doc.id in docs_to_skip:
            continue
        logger.info("Adding missing link for doc %d", doc.id)
        ppl.add_custom_field_to_document(
            doc,
            custom_field.id,
            BASE_URL + reverse("view_document", kwargs={"doc_id": doc.id}),
        )
        updated_docs.append(doc.id)

    for doc in ppl.documents_custom_field_query_iter(link_is_outdated_query):
        if doc.id in docs_to_skip:
            continue
        logger.info("Updating outdated link for doc %d", doc.id)
        ppl.add_custom_field_to_document(
            doc,
            custom_field.id,
            BASE_URL + "/" + reverse("view_document", kwargs={"doc_id": doc.id}),
        )
        updated_docs.append(doc.id)
    return updated_docs


def auto_update_links_loop():
    """Periodically scan all documents and ensure links are present and up to date."""

    scan_interval_seconds = UPDATE_INTERVAL_MINS * 60
    while True:
        try:
            updated_docs = []
            logger.info("Auto-linking: Starting link update scan")
            for user in User.objects.exclude(paperless_api_token=""):
                ppl = PaperlessAPI(PAPERLESS_URL, user.paperless_api_token)
                updated_docs += update_document_links(ppl, docs_to_skip=updated_docs)
            logger.info("Auto-linking: Link update scan completed")
        except Exception as e:
            logger.exception("Auto-linking: Link update scan failed: %s", e)
        logger.info("Sleeping for %d minutes", UPDATE_INTERVAL_MINS)
        time.sleep(scan_interval_seconds)
