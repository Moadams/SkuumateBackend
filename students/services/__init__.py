"""
Application layer for the students module.

Services own business rules and orchestration; views and serializers only
handle transport and presentation.
"""
from .class_bulk_import import ClassBulkImportService

__all__ = ["ClassBulkImportService"]
