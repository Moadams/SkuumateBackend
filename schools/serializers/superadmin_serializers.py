from rest_framework import serializers

from schools.models import School

class SchoolStatsSerializer(serializers.ModelSerializer):
    total_users = serializers.IntegerField()
    total_active_users = serializers.IntegerField()
    total_students = serializers.IntegerField()
    total_staff = serializers.IntegerField()
    

    class Meta:
        model = School
        fields = ['total_users', 'total_active_users', 'total_students', 'total_staff']

class SchoolDetailSerializer(serializers.ModelSerializer):
    stats = serializers.SerializerMethodField()
    admin = serializers.SerializerMethodField()
    plan = serializers.SerializerMethodField()

    class Meta:
        model = School
        fields = [
            "id",
            "name",
            "email",
            "phone",
            "address",
            "status",
            "joined",
            "plan",
            "admin",
            "stats",
        ]

    def get_stats(self, obj):
        return {
            "total_users": obj.total_users,
            "total_active_users": obj.total_active_users,
            "total_students": obj.total_students,
            "total_staff": obj.total_staff,
        }
    
    def get_admin(self, obj):
        from accounts.models import User
        admin_user = User.objects.filter(school=obj, role = User.Role.ADMIN).first()
        if admin_user:
            return {
                "name": admin_user.full_name,
                "email": admin_user.email,
            }
        return None

    def get_plan(self, obj):
        current_sub = obj.subscriptions.filter(is_current=True).first()
        return current_sub.plan.name if current_sub else None