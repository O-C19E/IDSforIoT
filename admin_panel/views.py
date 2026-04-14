import ipaddress

import requests
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import AlertLog, Customer, Light, PendingRequest, RequestLog, SystemLog

IOT_URL = "http://10.165.112.138:5000/sync"
IOT_TOGGLE_URL = "http://10.165.112.138:5000/toggle"


def is_iot_alive():
    try:
        res = requests.get("http://10.165.112.138:5000", timeout=2)
        return res.status_code == 200
    except:
        return False


# 🔌 Send command to IoT (Raspberry Pi)
def send_command_to_iot(light_ids, action):
    payload = {"light_ids": light_ids, "action": action}
    print("Sending to IoT:", payload)
    # TODO: Replace with actual HTTP request to Raspberry Pi
    return True


def sync_light_add_update(light):
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
        print("Light synced:", payload)
    except Exception as e:
        print("Sync error:", e)


def sync_light_delete(light):
    payload = {
        "action": "DELETE_LIGHT",
        "data": {
            "light_id": light.light_id,
        },
    }

    try:
        requests.post(IOT_URL, json=payload)
        print("Light deleted:", payload)
    except Exception as e:
        print("Sync error:", e)


def sync_customer_add_update(light, customer_ip):
    payload = {
        "action": "ADD_OR_UPDATE_LIGHT",
        "data": {
            "light_id": light.light_id,
            "device_ip": f"http://{light.device_ip}:5001",
            "customer_ip": customer_ip,
        },
    }

    requests.post(IOT_URL, json=payload)
    print("Customer synced:", payload)


def sync_customer_delete(light):
    payload = {
        "action": "REMOVE_CUSTOMER",
        "data": {
            "light_id": light.light_id,
        },
    }

    requests.post(IOT_URL, json=payload)
    print("Customer removed:", payload)


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
            message="Missing data",
        )
        return Response({"error": "Missing data"}, status=400)

    # ✅ Create log FIRST (PENDING)
    log = RequestLog.objects.create(
        ip_address=ip, light_id=light_id, action=action, status="PENDING"
    )

    try:
        res = requests.post(
            IOT_TOGGLE_URL, json={"light_id": light_id, "action": action}
        )

        # ✅ Update SAME log
        log.status = "SUCCESS" if res.status_code == 200 else "FAILED"
        log.message = str(res.text)
        log.save()

        return Response(res.json(), status=res.status_code)

    except Exception as e:
        log.status = "FAILED"
        log.message = str(e)
        log.save()

        return Response({"error": str(e)}, status=500)


# 🔥 Toggle ALL lights (Admin control)
@api_view(["POST"])
def toggle_all_lights(request):
    action = request.data.get("action")  # "ON" or "OFF"

    if action not in ["ON", "OFF"]:
        return Response({"error": "Invalid action"}, status=400)

    all_light_ids = list(Light.objects.values_list("light_id", flat=True))

    send_command_to_iot(all_light_ids, action)

    return Response({"message": f"All lights turned {action}"})


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


@api_view(["POST"])
def request_access(request):
    light_id = request.data.get("light_id")
    customer_name = request.data.get("customer_name", "")

    ip = get_client_ip(request)

    if not light_id:
        RequestLog.objects.create(
            ip_address=ip,
            light_id="UNKNOWN",
            action="ACCESS",
            status="FAILED",
            message="Missing light_id",
        )
        return Response({"error": "light_id is required"}, status=400)

    try:
        light = Light.objects.get(light_id=light_id)
    except Light.DoesNotExist:
        RequestLog.objects.create(
            ip_address=ip,
            light_id=light_id,
            action="ACCESS",
            status="FAILED",
            message="Invalid light_id",
        )
        return Response({"error": "Invalid room ID"}, status=400)

    existing_customer = Customer.objects.filter(customer_ip=ip, light=light).first()

    if existing_customer:
        RequestLog.objects.create(
            ip_address=ip,
            light_id=light_id,
            action="ACCESS",
            status="SUCCESS",
            message="Access granted",
        )

        return Response(
            {
                "message": "Access granted",
                "approved": True,
                "light_id": light_id,
            }
        )

    # ✅ Check if room already occupied
    if Customer.objects.filter(light=light).exists():
        RequestLog.objects.create(
            ip_address=ip,
            light_id=light_id,
            action="ACCESS",
            status="FAILED",
            message="Room already occupied",
        )
        return Response({"error": "Room already occupied"}, status=400)

    # ✅ Check if request already pending
    existing_request = PendingRequest.objects.filter(
        light=light, customer_ip=ip
    ).first()

    if existing_request:
        RequestLog.objects.create(
            ip_address=ip,
            light_id=light_id,
            action="ACCESS",
            status="PENDING",
            message="Request already pending",
        )
        return Response(
            {"message": "Request already pending approval", "approved": False}
        )

    # ✅ CREATE PendingRequest (THIS WAS MISSING)
    PendingRequest.objects.create(
        light=light,
        customer_ip=ip,
        customer_name=customer_name,
    )

    # ✅ Log after creation
    RequestLog.objects.create(
        ip_address=ip,
        light_id=light_id,
        action="ACCESS",
        status="PENDING",
        message="Request sent for approval",
    )

    return Response({"message": "Request sent for approval", "approved": False})


# 🔍 Get status (optional utility)
@api_view(["GET"])
def get_light_status(request, cust_id):
    try:
        customer = Customer.objects.get(id=cust_id)
        return Response({"customer_id": cust_id, "light_id": customer.light.light_id})
    except ObjectDoesNotExist:
        return Response({"error": "Customer not found"}, status=404)


def server_dashboard(request):
    query = request.GET.get("q", "")
    status_filter = request.GET.get("status", "")
    action_filter = request.GET.get("action", "")

    requests = RequestLog.objects.all().order_by("-timestamp")

    # 🔍 Search
    if query:
        requests = requests.filter(ip_address__icontains=query) | requests.filter(
            light_id__icontains=query
        )

    # 🎯 Filters
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
