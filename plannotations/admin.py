from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(BaseUserAdmin):
    list_display = (
        "username",
        "is_staff",
    )

    fieldsets = (
        (None, {"fields": ("username", "password", "display_name")}),
        ("Paperless Instance", {"fields": ("paperless_api_token",)}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "password1",
                    "password2",
                    "display_name",
                    "paperless_api_token",
                ),
                "description": "Enter a username and password.",
            },
        ),
    )
