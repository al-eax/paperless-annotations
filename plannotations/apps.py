import sys
from logging import getLogger
from django.apps import AppConfig
from core.settings import (
    ENABLE_AUTO_UPDATE_LINKS,
)

logging = getLogger(__name__)


def is_not_testing_and_not_migrating():
    """Check if the current process is not running tests or migrations."""
    return not (
        "test" in sys.argv
        or "makemigrations" in sys.argv
        or "migrate" in sys.argv
    )


class PaperlessAnnotationsConfig(AppConfig):
    name = "plannotations"

    def ready(self):
        if is_not_testing_and_not_migrating():
            logging.info("AppConfig: PaperlessAnnotationsConfig initialized.")
            if ENABLE_AUTO_UPDATE_LINKS:
                logging.info("Auto-update links is enabled, scheduling background task...")
                # pylint: disable=import-outside-toplevel
                from .tasks import task_auto_update_links

                task_auto_update_links.enqueue()
