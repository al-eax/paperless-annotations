import logging
from collections import defaultdict
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from core.settings import (
    ANNO_STORAGE,
    ENABLE_AUTO_UPDATE_LINKS,
    PAPERLESS_URL,
    BASE_URL,
    UPDATE_INTERVAL_MINS,
    VERSION,
)
from plannotations.api import get_paperless_instance
from .models import User
from .tasks import (
    task_trigger_update_links_manually,
    task_delete_annos_for_user,
    task_delete_document_links_for_user,
)

logging = logging.getLogger(__name__)

_last_viewed_docs: defaultdict[int, list[tuple[int, str]]] = defaultdict(
    list
)  # user id -> doc ids and titles
_keep_last_n_docs = 10  # Keep last N documents per user


def _create_user_from_request(request, is_admin):
    """Helper to create a user from a request POST data."""
    username = request.POST.get("username")
    password1 = request.POST.get("password1")
    password2 = request.POST.get("password2")
    token = request.POST.get("paperless_api_token")

    if not username or not password1:
        messages.error(request, "Username and password are required.")
        return None
    if password1 != password2:
        messages.error(request, "Passwords do not match.")
        return None
    if User.objects.filter(username=username).exists():
        messages.error(request, f"User '{username}' already exists.")
        return None
    # Create user
    user = None
    if is_admin:
        user = User.objects.create_superuser(
            username=username,
            password=password1,
            paperless_api_token=token or None,
        )
        messages.success(request, f"Admin account '{username}' created successfully.")
    else:
        user = User.objects.create_user(
            username=username,
            password=password1,
            paperless_api_token=token,
        )
        messages.success(request, f"User '{username}' created successfully.")
    logging.info("Created user: %s, is_admin: %s", username, is_admin)
    return user


def initialize(request):
    """Create initial admin account if none exists."""
    # Redirect to index if admin already exists
    if User.objects.filter(is_superuser=True).exists():
        return redirect("index")

    if request.method == "POST":
        user = _create_user_from_request(request, is_admin=True)
        if user:
            return redirect("index")
    return render(
        request,
        "create_user.html",
        {
            "request": request,
            "version": VERSION,
            "title": "Create a new Admin User",
        },
    )


@login_required(login_url="/login")
def create_user(request):
    """Allow admin to create new users."""
    if not request.user.is_staff:
        messages.error(request, "You don't have permission to create users.")
        return redirect("index")

    if request.method == "POST":
        user = _create_user_from_request(request, is_admin=False)
        if user:
            return redirect("index")
    return render(
        request,
        "create_user.html",
        {
            "request": request,
            "version": VERSION,
            "title": "Create New User",
        },
    )


@login_required(login_url="/login")
def view_document(request, doc_id: int):
    """Render the annotation frontend for a document."""
    username = request.user.display_name or request.user.username
    ppl = get_paperless_instance(request)
    document = ppl.document(doc_id)
    doc_name = document.title
    doc_id = document.id
    uid = request.user.id

    cache_obj = (doc_id, doc_name)
    if cache_obj in _last_viewed_docs[uid]:
        _last_viewed_docs[uid].remove(cache_obj)
    _last_viewed_docs[uid].insert(0, cache_obj)
    _last_viewed_docs[uid] = _last_viewed_docs[uid][:_keep_last_n_docs]

    return render(
        request,
        "view.html",
        {
            "request": request,
            "doc_id": doc_id,
            "username": username,
            "paperless_url": PAPERLESS_URL,
            "doc_name": doc_name,
            "version": VERSION,
        },
    )


def index(request):
    """Render the index page with admin and login links."""
    # Redirect to initialize if no admin exists
    if not User.objects.filter(is_superuser=True).exists():
        return redirect("initialize")

    is_authenticated = request.user.is_authenticated
    if not is_authenticated:
        return redirect("login")

    infos = {
        "Paperless-ngx URL": PAPERLESS_URL,
        "Paperless Annotations URL": BASE_URL,
        "Storage Backend": (
            "in Database" if ANNO_STORAGE == "database" else "in Paperless Notes"
        ),
        "Author display name": request.user.display_name or request.user.username,
        "Auto-update links": (
            f"Enabled (every {UPDATE_INTERVAL_MINS} minute(s))"
            if ENABLE_AUTO_UPDATE_LINKS
            else "Disabled"
        ),
    }

    return render(
        request,
        "index.html",
        {
            "request": request,
            "version": VERSION,
            "infos": infos,
            "last_viewed_docs": _last_viewed_docs.get(request.user.id, []),
        },
    )


@login_required(login_url="/login")
def trigger_sync_manually(request):
    """Add annotation view links to all documents."""
    if request.method == "POST":
        user_id = request.user.id
        task_trigger_update_links_manually.enqueue(user_id)
    return redirect("index")


@login_required(login_url="/login")
def delete_document_links(request):
    """Remove annotation view links from all documents."""
    if request.method == "POST":
        user_id = request.user.id
        task_delete_document_links_for_user.enqueue(user_id)
    return redirect("index")


@login_required(login_url="/login")
def delete_all_annotations(request):
    """Delete all annotations from all documents."""
    if request.method == "POST":
        user_id = request.user.id
        task_delete_annos_for_user.enqueue(user_id)
    return redirect("index")
