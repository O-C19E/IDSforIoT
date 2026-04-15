# utils.py (or inside models.py)
import string
import uuid

from django.core.exceptions import ValidationError
from django.db import models


def generate_valid_light_ids(config):
    floors = string.ascii_uppercase[
        : string.ascii_uppercase.index(config.max_floor) + 1
    ]

    room_numbers = [f"{i:02}" for i in range(1, config.max_room_number + 1)]

    return [f"{f}{r}" for f in floors for r in room_numbers]


class Light(models.Model):
    light_id = models.CharField(max_length=10, primary_key=True)
    device_ip = models.GenericIPAddressField()
    device_id = models.CharField(max_length=50)

    def clean(self):
        config = SystemConfig.objects.first()

        if not config:
            raise ValidationError("SystemConfig not set")

        valid_ids = generate_valid_light_ids(config)

        if self.light_id not in valid_ids:
            raise ValidationError(f"{self.light_id} is not in allowed range")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.light_id


class Customer(models.Model):
    customer_name = models.CharField(max_length=100)

    # One light can be assigned to only one customer
    light = models.OneToOneField(Light, on_delete=models.CASCADE)

    customer_ip = models.GenericIPAddressField()

    def __str__(self):
        return f"{self.customer_name} - {self.light.light_id}"


class SystemConfig(models.Model):
    max_floor = models.CharField(max_length=1, default="B")
    max_room_number = models.IntegerField(default=3)

    def clean(self):
        # Rule 1: floor must be A–Z
        if self.max_floor not in string.ascii_uppercase:
            raise ValidationError("Floor must be a capital letter (A-Z)")

        # Rule 2: room number must be >= 1
        if self.max_room_number < 1:
            raise ValidationError("Room number must be at least 1")

        # Rule 3: prevent decreasing values
        if self.pk:
            old = SystemConfig.objects.get(pk=self.pk)

            if self.max_floor < old.max_floor:
                raise ValidationError("Cannot decrease max_floor")

            if self.max_room_number < old.max_room_number:
                raise ValidationError("Cannot decrease max_room_number")

    def save(self, *args, **kwargs):
        if not self.pk and SystemConfig.objects.exists():
            raise ValidationError("Only one SystemConfig allowed")

        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"A-{self.max_floor}, Rooms: 01-{self.max_room_number}"


class PendingRequest(models.Model):
    light = models.ForeignKey(Light, on_delete=models.CASCADE)

    customer_name = models.CharField(max_length=100, blank=True, null=True)

    customer_ip = models.GenericIPAddressField()
    requested_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.light.device_id} - {self.customer_ip} - {self.customer_name}"


# ================= REQUEST LOG =================
class RequestLog(models.Model):
    ACTION_CHOICES = [
        ("ON", "ON"),
        ("OFF", "OFF"),
        ("ACCESS", "ACCESS"),
    ]

    STATUS_CHOICES = [
        ("SUCCESS", "SUCCESS"),
        ("FAILED", "FAILED"),
        ("PENDING", "PENDING"),
    ]

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    ip_address = models.GenericIPAddressField(db_index=True)
    light_id = models.CharField(max_length=10, db_index=True)

    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)

    message = models.TextField(blank=True, null=True)

    source = models.CharField(max_length=10, default="django")  # django / iot

    def __str__(self):
        return f"{self.timestamp} | {self.ip_address} | {self.light_id} | {self.status}"


# ================= ALERT LOG =================
class AlertLog(models.Model):
    SEVERITY_CHOICES = [
        ("LOW", "LOW"),
        ("MEDIUM", "MEDIUM"),
        ("HIGH", "HIGH"),
    ]

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    ip_address = models.GenericIPAddressField(db_index=True)

    light_id = models.CharField(
        max_length=10, blank=True, null=True
    )  # optional but useful

    alert_type = models.CharField(max_length=50)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES)

    message = models.TextField()

    def __str__(self):
        return f"{self.timestamp} | {self.alert_type} | {self.severity}"


# ================= SYSTEM LOG =================
class SystemLog(models.Model):
    STATUS_CHOICES = [
        ("SUCCESS", "SUCCESS"),
        ("FAILED", "FAILED"),
    ]

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    event_type = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)

    message = models.TextField()

    def __str__(self):
        return f"{self.timestamp} | {self.event_type} | {self.status}"

class SystemState(models.Model):
    last_hash = models.CharField(max_length=256)
    updated_at = models.DateTimeField(auto_now=True)