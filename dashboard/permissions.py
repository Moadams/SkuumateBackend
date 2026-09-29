from core.permissions import IsAdmin, IsFinanceManager, OrPermission


class IsAdminOrFinanceManager(OrPermission):
    permissions = (IsAdmin, IsFinanceManager)

