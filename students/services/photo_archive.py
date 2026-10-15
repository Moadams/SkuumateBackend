"""Temporary extraction of an uploaded photos ZIP for bulk imports.

ZIP handling is isolated here so the import service stays about students and
the extraction directory is always removed, even when the consumer raises.
"""
import os
import shutil
import tempfile
import zipfile
from contextlib import contextmanager

from rest_framework import serializers


@contextmanager
def extracted_photo_map(photos_zip):
    """Yield a ``{lowercased filename: absolute path}`` map for the archive.

    ``photos_zip`` may be ``None`` (no photos supplied), in which case an empty
    map is yielded. A non-zip upload, a corrupt archive or an archive member
    that would escape the extraction directory raises ``ValidationError``.
    """
    if photos_zip is None:
        yield {}
        return

    if not photos_zip.name.endswith(".zip"):
        raise serializers.ValidationError("Photos file must be a .zip archive.")

    temp_dir = tempfile.mkdtemp()
    try:
        photo_map = {}
        with zipfile.ZipFile(photos_zip) as archive:
            _extract_safely(archive, temp_dir)
            for root, _dirs, files in os.walk(temp_dir):
                for filename in files:
                    photo_map[filename.lower()] = os.path.join(root, filename)
        yield photo_map
    except zipfile.BadZipFile as exc:
        raise serializers.ValidationError("Invalid ZIP file for photos.") from exc
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _extract_safely(archive, destination):
    """Extract ``archive`` into ``destination``, refusing path traversal.

    ``ZipFile.extractall`` happily writes a member named ``../../evil`` outside
    the target directory, so each member is resolved and checked first.
    """
    destination_root = os.path.realpath(destination)
    for member in archive.infolist():
        member_path = os.path.realpath(os.path.join(destination_root, member.filename))
        if not member_path.startswith(destination_root + os.sep):
            raise serializers.ValidationError("Invalid ZIP file for photos.")
        archive.extract(member, destination_root)
