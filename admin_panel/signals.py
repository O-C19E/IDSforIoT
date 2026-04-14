from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Customer, Light
from .views import (
    sync_customer_add_update,
    sync_customer_delete,
    sync_light_add_update,
    sync_light_delete,
)

# ---------------- LIGHT ----------------


@receiver(post_save, sender=Light)
def light_saved(sender, instance, **kwargs):
    sync_light_add_update(instance)


@receiver(post_delete, sender=Light)
def light_deleted(sender, instance, **kwargs):
    sync_light_delete(instance)


# ---------------- CUSTOMER ----------------


@receiver(post_save, sender=Customer)
def customer_saved(sender, instance, **kwargs):
    sync_customer_add_update(instance.light, instance.customer_ip)


@receiver(post_delete, sender=Customer)
def customer_deleted(sender, instance, **kwargs):
    sync_customer_delete(instance.light)
