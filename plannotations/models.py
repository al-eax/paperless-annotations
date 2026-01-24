from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    first_name = None
    last_name = None
    paperless_api_token = models.CharField(max_length=255)
    display_name = models.CharField(max_length=100, default="")
    REQUIRED_FIELDS = ["paperless_api_token"]


class DbAnnotation(models.Model):
    """Model to store annotations in the database."""

    doc_id = models.IntegerField()
    db_id = models.IntegerField()
    page_index = models.IntegerField(null=True)
    anno_obj = models.JSONField()
