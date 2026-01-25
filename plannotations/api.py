from typing import Any, Optional

from django.http import HttpResponse
from django.dispatch import Signal
from ninja import NinjaAPI
from ninja.security import django_auth

from core.settings import PAPERLESS_URL
from plannotations.tasks import task_auto_update_links
from .annotations import PaperlessAnnotator
from .annostorage import Annotation
from .paperless_api import PaperlessAPI

sig_user_added_annotation = Signal()

api = NinjaAPI(auth=django_auth)


class UserNotAuthenticated(Exception):
    pass


def get_paperless_instance(request) -> PaperlessAPI:
    """Get a PaperlessAPI object using the logged-in user's credentials."""
    if not request.user.is_authenticated:
        raise UserNotAuthenticated("User must be logged in to access Paperless.")
    token = request.user.paperless_api_token
    return PaperlessAPI(PAPERLESS_URL, token)


@api.get("/documents/{doc_id}/download")
def download_document(request, doc_id: int):
    """Download the raw PDF for a Paperless document."""
    ppl = get_paperless_instance(request)
    pdf = PaperlessAnnotator(ppl).download_document(doc_id)

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="document_{doc_id}.pdf"'
    return response


@api.get("/documents/{doc_id}/annotations", response=list[Any])
def get_document_annos(request, doc_id: int, page: Optional[int] = None):
    """
    List annotations for a document. If `page` is provided, only return annotations for that page.
    """
    ppl = get_paperless_instance(request)
    annotator = PaperlessAnnotator(ppl)
    return list(annotator.get_page_annotations(doc_id, page))


@api.post("/documents/{doc_id}/annotations", response=Any)
def create_document_anno(request, doc_id: int, annotation: Annotation):
    """Create a new annotation (stored as a Paperless note)."""
    ppl = get_paperless_instance(request)
    sig_user_added_annotation.send(
        sender=None,
        user=request.user,
        doc_id=doc_id,
        annotation=annotation,
    )
    return PaperlessAnnotator(ppl).create_annotation(doc_id, annotation)


@api.patch("/documents/{doc_id}/annotations/{db_id}", response=Any)
def update_document_anno(request, doc_id: int, db_id: int, annotation: Annotation):
    """Update an existing annotation."""
    annotation.db_id = db_id
    ppl = get_paperless_instance(request)
    return PaperlessAnnotator(ppl).update_annotation(doc_id, annotation)


@api.delete("/documents/{doc_id}/annotations/{db_id}")
def delete_document_anno(request, doc_id: int, db_id: int, annotation: Annotation):
    """Delete an annotation and its replies."""
    annotation.db_id = db_id
    ppl = get_paperless_instance(request)
    return PaperlessAnnotator(ppl).delete_anno(doc_id, annotation)


@api.post("/webhooks/document_added", auth=None)
def document_added_webhook(_):
    """Webhook endpoint to trigger link update when a new document is added."""
    task_auto_update_links.enqueue()
    return {"status": "ok"}
