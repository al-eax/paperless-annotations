from django.urls import path
from django.contrib.auth import views as auth_views
from .api import api
from core.settings import VERSION
from .views import (
    index,
    initialize,
    create_user,
    view_document,
    delete_document_links,
    delete_all_annotations,
)

urlpatterns = [
    path("initialize/", initialize, name="initialize"),
    path("create_user/", create_user, name="create_user"),
    path("api/", api.urls),
    path(
        "login/",
        auth_views.LoginView.as_view(
            next_page="/",
            template_name="login.html",
            extra_context={"version": VERSION},
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(next_page="/"), name="logout"),
    path("view/<doc_id>", view_document, name="view_document"),
    path("remove_links/", delete_document_links, name="remove_document_links"),
    path(
        "delete-annotations/",
        delete_all_annotations,
        name="delete_all_annotations",
    ),
    path("", index, name="index"),
]
