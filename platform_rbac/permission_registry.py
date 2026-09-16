from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformPermissionSpec:
    code: str
    name: str
    description: str = ""
    module: str = ""


PERMISSION_SPECS = (
    # ─── Platform users ─────────────────────────────────────────────
    PlatformPermissionSpec("platform_users.view", "View platform users", "List and view platform superadmin users", "platform_users"),
    PlatformPermissionSpec("platform_users.create", "Create platform users", "Create new platform superadmin users", "platform_users"),
    PlatformPermissionSpec("platform_users.update", "Update platform users", "Update platform superadmin user details", "platform_users"),
    PlatformPermissionSpec("platform_users.deactivate", "Deactivate platform users", "Activate or deactivate platform superadmin users", "platform_users"),
    PlatformPermissionSpec("platform_users.assign_roles", "Assign roles to users", "Assign or remove platform roles on platform users", "platform_users"),
    # ─── Platform roles ────────────────────────────────────────────
    PlatformPermissionSpec("roles.view", "View platform roles", "List and view platform roles and their permissions", "roles"),
    PlatformPermissionSpec("roles.create", "Create platform roles", "Create new platform roles", "roles"),
    PlatformPermissionSpec("roles.update", "Update platform roles", "Update platform role details", "roles"),
    PlatformPermissionSpec("roles.deactivate", "Deactivate platform roles", "Activate or deactivate platform roles", "roles"),
    PlatformPermissionSpec("roles.assign_permissions", "Assign permissions to roles", "Assign or remove platform permissions on roles", "roles"),
    # ─── Packages ───────────────────────────────────────────────────
    PlatformPermissionSpec("packages.view", "View packages", "List and view subscription packages", "packages"),
    PlatformPermissionSpec("packages.create", "Create packages", "Create subscription packages", "packages"),
    PlatformPermissionSpec("packages.update", "Update packages", "Update subscription packages", "packages"),
    PlatformPermissionSpec("packages.deactivate", "Deactivate packages", "Activate or deactivate subscription packages", "packages"),
    PlatformPermissionSpec("packages.manage_features", "Manage package features", "Assign or remove features on packages", "packages"),
    PlatformPermissionSpec("packages.manage_limits", "Manage package limits", "Configure resource limits on packages", "packages"),
    # ─── Schools ────────────────────────────────────────────────────
    PlatformPermissionSpec("schools.view", "View schools", "List and view schools", "schools"),
    PlatformPermissionSpec("schools.create", "Create schools", "Create schools", "schools"),
    PlatformPermissionSpec("schools.update", "Update schools", "Update school details", "schools"),
    PlatformPermissionSpec("schools.activate", "Activate schools", "Activate schools", "schools"),
    PlatformPermissionSpec("schools.suspend", "Suspend schools", "Suspend schools", "schools"),
    # ─── Subscriptions ──────────────────────────────────────────────
    PlatformPermissionSpec("subscriptions.view", "View subscriptions", "List and view school subscriptions", "subscriptions"),
    PlatformPermissionSpec("subscriptions.create", "Create subscriptions", "Create new subscriptions", "subscriptions"),
    PlatformPermissionSpec("subscriptions.update", "Update subscriptions", "Update subscription details", "subscriptions"),
    PlatformPermissionSpec("subscriptions.renew", "Renew subscriptions", "Renew or extend school subscriptions", "subscriptions"),
    PlatformPermissionSpec("subscriptions.suspend", "Suspend subscriptions", "Suspend school subscriptions", "subscriptions"),
    PlatformPermissionSpec("subscriptions.cancel", "Cancel subscriptions", "Cancel school subscriptions", "subscriptions"),
    # ─── SMS ────────────────────────────────────────────────────────
    PlatformPermissionSpec("sms.view", "View SMS messages", "View SMS usage and history", "sms"),
    PlatformPermissionSpec("sms.send", "Send SMS", "Send SMS messages", "sms"),
    PlatformPermissionSpec("sms.manage", "Manage SMS settings", "Configure SMS providers and settings", "sms"),
    # ─── Billing ────────────────────────────────────────────────────
    PlatformPermissionSpec("billing.view", "View billing", "View billing invoices and payment history", "billing"),
    PlatformPermissionSpec("billing.manage", "Manage billing", "Manage invoices, payments and billing settings", "billing"),
    # ─── Audit logs ─────────────────────────────────────────────────
    PlatformPermissionSpec("audit_logs.view", "View audit logs", "View platform audit logs", "audit_logs"),
    # ─── Settings ───────────────────────────────────────────────────
    PlatformPermissionSpec("settings.view", "View settings", "View platform settings", "settings"),
    PlatformPermissionSpec("settings.manage", "Manage settings", "Update platform settings", "settings"),
)


def declared_permission_codes():
    return {spec.code for spec in PERMISSION_SPECS}