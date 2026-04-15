import ipaddress
import requests
from datetime import timedelta
import hashlib, json
from django.utils import timezone
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import render

from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import AlertLog, Customer, Light, PendingRequest, RequestLog, SystemLog

IOT_URL = "http://10.165.112.138:5000/sync"
IOT_TOGGLE_URL = "http://10.165.112.138:5000/toggle"


# =========================
# IP HANDLING
# =========================
def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")

    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0]
    else:
        ip = request.META.get("REMOTE_ADDR")

    try:
        ip_obj = ipaddress.ip_address(ip)

        if ip == "::1":
            return "127.0.0.1"

        if ip_obj.version == 6 and ip_obj.ipv4_mapped:
            return str(ip_obj.ipv4_mapped)

    except:
        pass

    return ip


def is_iot_alive():
    try:
        res = requests.get("http://10.165.112.138:5000", timeout=2)
        return res.status_code == 200
    except:
        return False


# =========================
# IDS CORE ANALYSIS
# =========================
def check_request_rate(ip):
    from django.utils import timezone
    from datetime import timedelta

    one_min_ago = timezone.now() - timedelta(minutes=1)

    logs = RequestLog.objects.filter(
        ip_address=ip,
        timestamp__gte=one_min_ago
    )

    total = logs.count()

    failed_count = logs.filter(status="FAILED").count()
    pending_count = logs.filter(status="PENDING").count()

    if total == 0:
        return None

    # PRIORITY RULES (IMPORTANT)
    if failed_count >= 8:
        return {
            "category": "FAILED_ATTEMPT_SPAM",
            "count": failed_count
        }

    if pending_count >= 8:
        return {
            "category": "ACCESS_SPAM",
            "count": pending_count
        }

    return {"category": "NORMAL"}

def should_create_alert(ip, alert_type, window_seconds=60):
    time_threshold = timezone.now() - timedelta(seconds=window_seconds)

    return not AlertLog.objects.filter(
        ip_address=ip,
        alert_type=alert_type,
        timestamp__gte=time_threshold
    ).exists()

def generate_system_hash():
    lights = list(Light.objects.all().values())

    data_string = json.dumps(lights, sort_keys=True, default=str)

    return hashlib.sha256(data_string.encode()).hexdigest()

def should_run_integrity_check():
    tracker, _ = SystemIntegrityTracker.objects.get_or_create(id=1)

    if timezone.now() - tracker.last_checked >= timedelta(minutes=1):
        tracker.last_checked = timezone.now()
        tracker.save()
        return True

    return False

def check_system_integrity():
    current_hash = generate_system_hash()

    state, _ = SystemState.objects.get_or_create(id=1)

    if state.last_hash != current_hash:
        SystemLog.objects.create(
            event_type="HASH_MISMATCH",
            status="FAILED",
            message="System tampering detected"
        )

        state.last_hash = current_hash
        state.save()
    else:
        SystemLog.objects.create(
            event_type="HASH_CHECK",
            status="SUCCESS",
            message="System OK"
        )

def log_before_after(action, light=None):
    before_hash = generate_system_hash()

    SystemLog.objects.create(
        event_type=f"{action}_BEFORE",
        status="SUCCESS",
        message=before_hash
    )

    return before_hash

def log_after(action):
    after_hash = generate_system_hash()

    SystemLog.objects.create(
        event_type=f"{action}_AFTER",
        status="SUCCESS",
        message=after_hash
    )
# =========================
# IOT HELPERS
# =========================
def send_command_to_iot(light_ids, action):
    payload = {"light_ids": light_ids, "action": action}
    print("Sending to IoT:", payload)
    return True


def sync_light_add_update(light):
    log_before_after("LIGHT_SYNC")

    payload = {
        "action": "ADD_OR_UPDATE_LIGHT",
        "data": {
            "light_id": light.light_id,
            "device_ip": f"http://{light.device_ip}:5001",
            "customer_ip": "",
        },
    }

    try:
        requests.post(IOT_URL, json=payload)
        SystemLog.objects.create(
            event_type="LIGHT_SYNC",
            status="SUCCESS",
            message="Light synced to IoT"
        )
    except Exception as e:
        SystemLog.objects.create(
            event_type="LIGHT_SYNC",
            status="FAILED",
            message=str(e)
        )

    log_after("LIGHT_SYNC")

def sync_light_delete(light):
    log_before_after("LIGHT_DELETE")

    payload = {
        "action": "DELETE_LIGHT",
        "data": {"light_id": light.light_id},
    }

    try:
        requests.post(IOT_URL, json=payload)
        SystemLog.objects.create(
            event_type="LIGHT_DELETE",
            status="SUCCESS",
            message="Light deleted"
        )
    except Exception as e:
        SystemLog.objects.create(
            event_type="LIGHT_DELETE",
            status="FAILED",
            message=str(e)
        )

    log_after("LIGHT_DELETE")

def sync_customer_add_update(light, customer_ip):
    from .models import SystemLog

    before_hash = generate_system_hash()

    SystemLog.objects.create(
        event_type="CUSTOMER_SYNC_BEFORE",
        status="SUCCESS",
        message=f"Before hash: {before_hash}"
    )

    payload = {
        "action": "ADD_OR_UPDATE_LIGHT",
        "data": {
            "light_id": light.light_id,
            "device_ip": f"http://{light.device_ip}:5001",
            "customer_ip": customer_ip,
        },
    }

    try:
        requests.post(IOT_URL, json=payload)

        after_hash = generate_system_hash()

        SystemLog.objects.create(
            event_type="CUSTOMER_SYNC_AFTER",
            status="SUCCESS",
            message=f"After hash: {after_hash}"
        )

        SystemLog.objects.create(
            event_type="CUSTOMER_SYNC",
            status="SUCCESS",
            message=f"Customer synced for {customer_ip}"
        )

    except Exception as e:
        SystemLog.objects.create(
            event_type="CUSTOMER_SYNC",
            status="FAILED",
            message=str(e)
        )


def sync_customer_delete(light):
    from .models import SystemLog

    before_hash = generate_system_hash()

    SystemLog.objects.create(
        event_type="CUSTOMER_DELETE_BEFORE",
        status="SUCCESS",
        message=f"Before hash: {before_hash}"
    )

    payload = {
        "action": "REMOVE_CUSTOMER",
        "data": {
            "light_id": light.light_id
        },
    }

    try:
        requests.post(IOT_URL, json=payload)

        after_hash = generate_system_hash()

        SystemLog.objects.create(
            event_type="CUSTOMER_DELETE_AFTER",
            status="SUCCESS",
            message=f"After hash: {after_hash}"
        )

        SystemLog.objects.create(
            event_type="CUSTOMER_DELETE",
            status="SUCCESS",
            message=f"Customer removed from light {light.light_id}"
        )

    except Exception as e:
        SystemLog.objects.create(
            event_type="CUSTOMER_DELETE",
            status="FAILED",
            message=str(e)
        )


# =========================
# TOGGLE LIGHT
# =========================
@api_view(["POST"])
def toggle_light(request):
    light_id = request.data.get("light_id")
    action = request.data.get("action")

    ip = get_client_ip(request)

    if not light_id or not action:
        RequestLog.objects.create(
            ip_address=ip,
            light_id=light_id or "UNKNOWN",
            action=action or "UNKNOWN",
            status="FAILED",
            message="FAILED_ATTEMPT",
        )
        return Response({"error": "Missing data"}, status=400)

    log = RequestLog.objects.create(
        ip_address=ip,
        light_id=light_id,
        action=action,
        status="PENDING"
    )

    try:
        res = requests.post(
            IOT_TOGGLE_URL,
            json={"light_id": light_id, "action": action}
        )

        log.status = "SUCCESS" if res.status_code == 200 else "FAILED"
        log.message = "TOGGLE_COMPLETE"
        log.save()

        return Response(res.json(), status=res.status_code)

    except Exception as e:
        log.status = "FAILED"
        log.message = "FAILED_ATTEMPT"
        log.save()

        return Response({"error": str(e)}, status=500)


# =========================
# REQUEST ACCESS (CLEAN IDS VERSION)
# =========================
@api_view(["POST"])
def request_access(request):
    if should_run_integrity_check():
        check_system_integrity()
    light_id = request.data.get("light_id")
    customer_name = request.data.get("customer_name", "")

    ip = get_client_ip(request)

    # =========================
    # 1. Missing light_id
    # =========================
    if not light_id:
        RequestLog.objects.create(
            ip_address=ip,
            light_id="UNKNOWN",
            action="ACCESS",
            status="FAILED",
            message="FAILED_ATTEMPT",
        )

        if should_create_alert(ip, "FAILED_ATTEMPT_SPAM"):
            AlertLog.objects.create(
                ip_address=ip,
                alert_type="FAILED_ATTEMPT_SPAM",
                severity="HIGH",
                message="Failed attempt spike detected"
            )

        return Response({"error": "light_id is required"}, status=400)

    # =========================
    # 2. Invalid light
    # =========================
    try:
        light = Light.objects.get(light_id=light_id)

    except Light.DoesNotExist:
        RequestLog.objects.create(
            ip_address=ip,
            light_id=light_id,
            action="ACCESS",
            status="FAILED",
            message="FAILED_ATTEMPT",
        )

        if should_create_alert(ip, "FAILED_ATTEMPT_SPAM"):
            AlertLog.objects.create(
                ip_address=ip,
                alert_type="FAILED_ATTEMPT_SPAM",
                severity="HIGH",
                message="Failed attempt spike detected"
            )

        return Response({"error": "Invalid room ID"}, status=400)

    # =========================
    # 3. Existing customer
    # =========================
    existing_customer = Customer.objects.filter(
        customer_ip=ip,
        light=light
    ).first()

    if existing_customer:
        RequestLog.objects.create(
            ip_address=ip,
            light_id=light_id,
            action="ACCESS",
            status="SUCCESS",
            message="ACCESS_GRANTED",
        )

        return Response({
            "message": "Access granted",
            "approved": True,
            "light_id": light_id,
        })

    # =========================
    # 4. Room occupied
    # =========================
    if Customer.objects.filter(light=light).exists():
        RequestLog.objects.create(
            ip_address=ip,
            light_id=light_id,
            action="ACCESS",
            status="FAILED",
            message="FAILED_ATTEMPT",
        )

        if should_create_alert(ip, "FAILED_ATTEMPT_SPAM"):
            AlertLog.objects.create(
                ip_address=ip,
                alert_type="FAILED_ATTEMPT_SPAM",
                severity="HIGH",
                message="Failed attempt spike detected"
            )

        return Response({"error": "Room already occupied"}, status=400)

    # =========================
    # 5. Pending exists
    # =========================
    existing_request = PendingRequest.objects.filter(
        light=light,
        customer_ip=ip
    ).first()

    if existing_request:
        RequestLog.objects.create(
            ip_address=ip,
            light_id=light_id,
            action="ACCESS",
            status="PENDING",
            message="PENDING",
        )

        if should_create_alert(ip, "ACCESS_SPAM"):
            AlertLog.objects.create(
                ip_address=ip,
                alert_type="ACCESS_SPAM",
                severity="MEDIUM",
                message="Repeated access requests detected"
            )

        return Response({
            "message": "Request already pending approval",
            "approved": False
        })

    # =========================
    # 6. Create request
    # =========================
    PendingRequest.objects.create(
        light=light,
        customer_ip=ip,
        customer_name=customer_name,
    )

    RequestLog.objects.create(
        ip_address=ip,
        light_id=light_id,
        action="ACCESS",
        status="PENDING",
        message="PENDING",
    )

    return Response({
        "message": "Request sent for approval",
        "approved": False
    })


# =========================
# ADMIN CONTROL
# =========================
@api_view(["POST"])
def toggle_all_lights(request):
    action = request.data.get("action")

    if action not in ["ON", "OFF"]:
        return Response({"error": "Invalid action"}, status=400)

    all_light_ids = list(Light.objects.values_list("light_id", flat=True))
    send_command_to_iot(all_light_ids, action)

    return Response({"message": f"All lights turned {action}"})


@api_view(["GET"])
def get_light_status(request, cust_id):
    try:
        customer = Customer.objects.get(id=cust_id)
        return Response({
            "customer_id": cust_id,
            "light_id": customer.light.light_id
        })
    except ObjectDoesNotExist:
        return Response({"error": "Customer not found"}, status=404)


# =========================
# DASHBOARD
# =========================
def server_dashboard(request):
    query = request.GET.get("q", "")
    status_filter = request.GET.get("status", "")
    action_filter = request.GET.get("action", "")

    requests = RequestLog.objects.all().order_by("-timestamp")

    if query:
        requests = requests.filter(ip_address__icontains=query) | requests.filter(
            light_id__icontains=query
        )

    if status_filter:
        requests = requests.filter(status=status_filter)

    if action_filter:
        requests = requests.filter(action=action_filter)

    alerts = AlertLog.objects.order_by("-timestamp")[:50]
    system_logs = SystemLog.objects.order_by("-timestamp")[:50]

    return render(
        request,
        "server.html",
        {
            "requests": requests[:50],
            "alerts": alerts,
            "system_logs": system_logs,
        },
    )

