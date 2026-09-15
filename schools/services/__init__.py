"""
Application layer for the schools module.

Services and projectors live here; views and serializers only
orchestrate transport and presentation. Business rules never live
in views.
"""
from .school_details import SchoolDetailsService

__all__ = ["SchoolDetailsService"]