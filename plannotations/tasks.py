"""Background task definitions for document link sync and annotation management."""

import logging
from django.tasks import task

from plannotations.auto_linking import (
    auto_update_links_loop,
    update_document_links,
    delete_all_document_links,
)

from core.settings import (
    PAPERLESS_URL,
)
from .paperless_api import PaperlessAPI
from .annotations import PaperlessAnnotator
from .models import User

logger = logging.getLogger(__name__)


@task()
def task_auto_update_links():
    """Start periodic scan loop (not implemented)."""
    auto_update_links_loop()


@task()
def task_trigger_update_links_manually(user_id: int):
    """Background task to trigger a manual scan."""
    logger.info("Syncer: Triggering manual scan")
    user = User.objects.get(id=user_id)
    token = user.paperless_api_token
    update_document_links(PaperlessAPI(PAPERLESS_URL, token), docs_to_skip=None)


@task()
def task_delete_document_links_for_user(user_id: int) -> dict:
    """Background task to remove document links."""
    user = User.objects.get(id=user_id)
    token = user.paperless_api_token

    ppl = PaperlessAPI(PAPERLESS_URL, token)
    delete_all_document_links(ppl)


@task()
def task_delete_annos_for_user(user_id: int) -> dict:
    """Background task to delete all annotations."""
    user = User.objects.get(id=user_id)
    token = user.paperless_api_token

    ppl = PaperlessAPI(PAPERLESS_URL, token)
    annotator = PaperlessAnnotator(ppl)
    docs = annotator.delete_all_annotations(docs_to_skip=None)
    return {"docs_processed": len(docs)}
