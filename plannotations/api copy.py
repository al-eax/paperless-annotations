from typing import Any, Optional

from django.http import HttpResponse
from ninja import NinjaAPI
from ninja.security import django_auth
from pypaperless import Paperless

from core.settings import PAPERLESS_URL
from .annotations import Annotation, PaperlessAnnotator

api = NinjaAPI(auth=django_auth)


class UserNotAuthenticated(Exception):
    pass


def get_paperless_instance(request):
    """Get a Paperless object using the logged-in user's credentials."""
    if not request.user.is_authenticated:
        raise UserNotAuthenticated("User must be logged in to access Paperless.")
    token = request.user.paperless_api_token
    return Paperless(PAPERLESS_URL, token)


@api.get("/documents/{doc_id}/download")
async def download_document(request, doc_id: int):
    """Download the raw PDF for a Paperless document."""
    async with get_paperless_instance(request) as ppl:
        pdf = await PaperlessAnnotator(ppl).download_document(doc_id)

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="document_{doc_id}.pdf"'
    return response


@api.get("/documents/{doc_id}/annotations", response=list[Any])
async def get_document_annos(request, doc_id: int, page: Optional[int] = None):
    """
    List annotations for a document. If `page` is provided, only return annotations for that page.
    """
    async with get_paperless_instance(request) as ppl:
        annotator = PaperlessAnnotator(ppl)
        return [anno async for anno in annotator.get_page_annotations(doc_id, page)]


@api.post("/documents/{doc_id}/annotations", response=Any)
async def create_document_anno(request, doc_id: int, annotation: Annotation):
    """Create a new annotation (stored as a Paperless note)."""
    async with get_paperless_instance(request) as ppl:
        return await PaperlessAnnotator(ppl).create_annotation(doc_id, annotation)


@api.patch("/documents/{doc_id}/annotations/{db_id}", response=Any)
async def update_document_anno(
    request, doc_id: int, db_id: int, annotation: Annotation
):
    """Update an existing annotation."""
    annotation.db_id = db_id
    async with get_paperless_instance(request) as ppl:
        return await PaperlessAnnotator(ppl).update_annotation(doc_id, annotation)


@api.delete("/documents/{doc_id}/annotations/{db_id}")
async def delete_document_anno(
    request, doc_id: int, db_id: int, annotation: Annotation
):
    """Delete an annotation and its replies."""
    annotation.db_id = db_id
    async with get_paperless_instance(request) as ppl:
        return await PaperlessAnnotator(ppl).delete_anno(doc_id, annotation)
