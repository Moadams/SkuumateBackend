from django.contrib import admin

from .models import Feature, Package, PackageFeature, PackageLimit, Subscription, SubscriptionPayment


@admin.register(Feature)
class FeatureAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "category", "is_active"]
    list_filter = ["is_active", "category"]
    search_fields = ["name", "code"]
    ordering = ["category", "name"]


class PackageFeatureInline(admin.TabularInline):
    model = PackageFeature
    extra = 0
    autocomplete_fields = ["feature"]


class PackageLimitInline(admin.TabularInline):
    model = PackageLimit
    extra = 0


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "price", "currency", "billing_period", "is_active", "is_public"]
    list_filter = ["is_active", "is_public", "billing_period", "currency"]
    search_fields = ["name", "code"]
    ordering = ["display_order", "price"]
    inlines = [PackageFeatureInline, PackageLimitInline]


@admin.register(PackageFeature)
class PackageFeatureAdmin(admin.ModelAdmin):
    list_display = ["package", "feature", "is_enabled"]
    list_filter = ["is_enabled"]
    autocomplete_fields = ["package", "feature"]


@admin.register(PackageLimit)
class PackageLimitAdmin(admin.ModelAdmin):
    list_display = ["package", "key", "name", "value"]
    list_filter = ["package"]
    autocomplete_fields = ["package"]


class SubscriptionPaymentInline(admin.TabularInline):
    model = SubscriptionPayment
    extra = 0
    readonly_fields = ["id", "created_at"]
    fk_name = "subscription"


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ["school", "plan", "status", "is_paid", "is_current", "term", "start_date", "end_date"]
    list_filter = ["status", "is_paid", "is_current"]
    search_fields = ["school__name", "school__school_code", "plan__name"]
    readonly_fields = ["created_at", "updated_at"]
    autocomplete_fields = ["school", "plan", "term", "activated_by"]
    inlines = [SubscriptionPaymentInline]


@admin.register(SubscriptionPayment)
class SubscriptionPaymentAdmin(admin.ModelAdmin):
    list_display = ["id", "school", "plan", "amount", "currency", "provider", "payment_mode", "status", "created_at"]
    list_filter = ["status", "payment_mode", "provider"]
    search_fields = ["payment_reference", "school__name", "plan__name"]
    readonly_fields = ["created_at", "updated_at"]
    autocomplete_fields = ["school", "plan", "subscription", "term", "recorded_by"]
