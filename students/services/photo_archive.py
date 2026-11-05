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

# A photos archive is a convenience for bulk import, not a general file dump.
# Cap both the number of entries and the total uncompressed size so a zip bomb
# cannot exhaust the shared-hosting disk quota.
MAX_ARCHIVE_MEMBERS = 5000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 500 * 1024 * 1024


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
    members = archive.infolist()
    if len(members) > MAX_ARCHIVE_MEMBERS:
        raise serializers.ValidationError(
            f"Photos archive has too many files (limit {MAX_ARCHIVE_MEMBERS})."
        )

    total_size = 0
    for member in members:
        if member.is_dir():
            continue
        total_size += member.file_size
        if total_size > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
            raise serializers.ValidationError("Photos archive is too large.")

        # Normalise Windows separators so a member cannot escape on either OS.
        name = member.filename.replace("\\", "/")
        member_path = os.path.realpath(os.path.join(destination_root, name))
        if not member_path.startswith(destination_root + os.sep):
            raise serializers.ValidationError("Invalid ZIP file for photos.")
        archive.extract(member, destination_root)
