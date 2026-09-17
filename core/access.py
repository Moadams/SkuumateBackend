def school_access_allowed(user):
    """Fail closed for school accounts whose membership is no longer valid."""
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if not user.school_id or user.school.status == "suspended":
        return False
    profile = getattr(user, "staff_profile", None)
    return profile is None or (
        profile.school_id == user.school_id
        and profile.status not in ("inactive", "suspended", "terminated")
    )
