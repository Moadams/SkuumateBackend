import io
import zipfile
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework import serializers

from students.services import photo_archive


def _zip_bytes(names):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in names:
            archive.writestr(name, b"x")
    return buffer.getvalue()


class PhotoArchiveLimitTests(TestCase):
    """A photos ZIP must not be usable to exhaust the hosting disk quota."""

    def test_rejects_archive_with_too_many_members(self):
        upload = SimpleUploadedFile("photos.zip", _zip_bytes(["a.jpg", "b.jpg", "c.jpg"]))

        with patch.object(photo_archive, "MAX_ARCHIVE_MEMBERS", 2):
            with self.assertRaises(serializers.ValidationError):
                with photo_archive.extracted_photo_map(upload):
                    pass

    def test_accepts_archive_within_the_member_limit(self):
        upload = SimpleUploadedFile("photos.zip", _zip_bytes(["a.jpg"]))

        with patch.object(photo_archive, "MAX_ARCHIVE_MEMBERS", 2):
            with photo_archive.extracted_photo_map(upload) as mapping:
                self.assertIn("a.jpg", mapping)
