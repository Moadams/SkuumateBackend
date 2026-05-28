from rest_framework import generics
from core.models import AuditLog
from core.responses import ApiResponse
from core.mixins import AuditLogMixin
from core.permissions import IsSuperAdmin
from subscriptions.models import Plan, Subscription
from subscriptions.serializers import ManualActivationSerializer, PlanSerializer, SubscriptionSerializer

class PlanRetrieveUpdateView(AuditLogMixin, generics.RetrieveUpdateAPIView):
    """
    API view to retrieve and update a subscription plan.
    """
    queryset = Plan.objects.all()
    serializer_class = PlanSerializer
    permission_classes = [IsSuperAdmin]

    audit_action = AuditLog.Action.UPDATE
    audit_resource = "Plan"

    def get_audit_description(self, instance):
        
        return f"Plan '{instance.name}' (ID: {instance.id}) was updated by {self.request.user.first_name} {self.request.user.last_name}."
    
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return ApiResponse.success(data=serializer.data)
    

class SchoolSubscriptionView(AuditLogMixin, generics.ListCreateAPIView):
    permission_classes = [IsSuperAdmin]
    serializer_class = ManualActivationSerializer
    queryset = Subscription.objects.all()

    audit_action = AuditLog.Action.CREATE
    audit_resource = "Subscription"

    def get_audit_description(self, instance):
        return f"Subscription for school '{instance.school.name}' was manually activated by {self.request.user.first_name} {self.request.user.last_name}."
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        subscription = self.perform_create(serializer)
        return ApiResponse.success(data=SubscriptionSerializer(subscription).data)
    
