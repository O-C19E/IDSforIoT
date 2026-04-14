# admin.py
from django import forms
from django.contrib import admin

from .models import (
    AlertLog,
    Customer,
    Light,
    PendingRequest,
    RequestLog,
    SystemConfig,
    SystemLog,
    generate_valid_light_ids,
)
from .views import (
    sync_customer_add_update,
    sync_customer_delete,
    sync_light_add_update,
    sync_light_delete,
)


class LightAdminForm(forms.ModelForm):
    light_id = forms.ChoiceField(choices=[])

    class Meta:
        model = Light
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        config = SystemConfig.objects.first()
        if config:
            valid_ids = generate_valid_light_ids(config)

            # Remove already used IDs
            used_ids = Light.objects.values_list("light_id", flat=True)

            available_ids = [vid for vid in valid_ids if vid not in used_ids]

            self.fields["light_id"].choices = [(i, i) for i in available_ids]


class LightAdmin(admin.ModelAdmin):
    form = LightAdminForm

    def save_model(self, request, obj, form, change):
        # save first
        super().save_model(request, obj, form, change)

        # then sync ONLY add/update
        sync_light_add_update(obj)

    def delete_model(self, request, obj):
        # sync BEFORE delete
        sync_light_delete(obj)

        # then delete from DB
        super().delete_model(request, obj)


admin.site.register(Light, LightAdmin)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("customer_name", "light", "customer_ip")


@admin.register(SystemConfig)
class SystemConfigAdmin(admin.ModelAdmin):
    list_display = ("max_floor", "max_room_number")


@admin.register(PendingRequest)
class PendingRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "light", "customer_ip", "customer_name")

    actions = ["approve_request"]

    def approve_request(self, request, queryset):
        for req in queryset:
            # 1. Create Customer
            customer = Customer.objects.create(
                customer_name=req.customer_name or "Guest",
                light=req.light,
                customer_ip=req.customer_ip,
            )

            # 2. Sync to IoT (NEW FUNCTION)
            sync_customer_add_update(req.light, req.customer_ip)

            # 3. Delete Pending Request
            req.delete()

        self.message_user(request, "Request approved successfully")

    approve_request.short_description = "Approve selected requests"


@admin.register(RequestLog)
class RequestLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "ip_address", "light_id", "action", "status")
    search_fields = ("ip_address", "light_id")
    list_filter = ("status", "action")
    ordering = ("-timestamp",)


@admin.register(AlertLog)
class AlertLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "ip_address", "alert_type", "severity")
    list_filter = ("severity", "alert_type")
    ordering = ("-timestamp",)


@admin.register(SystemLog)
class SystemLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "event_type", "status")
    list_filter = ("status",)
    ordering = ("-timestamp",)
