from datetime import timedelta

import joblib
from django.utils import timezone

from .models import AlertLog, RequestLog

# =========================
# 1. Load Model (once)
# =========================
model = joblib.load("admin_panel/xgboost_model.pkl")


# =========================
# 2. Feature Extraction
# =========================
def extract_features(ip):
    one_min_ago = timezone.now() - timedelta(minutes=1)

    logs = RequestLog.objects.filter(ip_address=ip, timestamp__gte=one_min_ago)

    if not logs.exists():
        return None, None

    total_requests = logs.count()
    failed_count = logs.filter(status="FAILED").count()
    pending_count = logs.filter(status="PENDING").count()

    # -------------------------
    # Simulated Feature Mapping
    # -------------------------

    src_bytes = total_requests * 50
    dst_bytes = total_requests * 100
    duration = 60
    src_pkts = total_requests
    dst_pkts = total_requests // 2
    proto = 0  # TCP

    features = [[src_bytes, dst_bytes, duration, src_pkts, dst_pkts, proto]]

    # return logs also (for alert message)
    stats = {"total": total_requests, "failed": failed_count, "pending": pending_count}

    return features, stats


# =========================
# 3. Prediction
# =========================
def detect_attack(ip):
    features, stats = extract_features(ip)

    if not features:
        return None, None

    prediction = model.predict(features)[0]

    return prediction, stats


# =========================
# 4. Alert Creator
# =========================
def run_ml_detection(ip):
    result, stats = detect_attack(ip)

    if result is None:
        return

    if result == 1:  # DDoS detected
        one_min_ago = timezone.now() - timedelta(minutes=1)

        # 🚫 Prevent duplicate alerts in same window
        exists = AlertLog.objects.filter(
            ip_address=ip, alert_type="ML_DDOS_DETECTED", timestamp__gte=one_min_ago
        ).exists()

        if exists:
            return

        # ✅ Smart message (VERY IMPORTANT)
        AlertLog.objects.create(
            ip_address=ip,
            alert_type="ML_DDOS_DETECTED",
            severity="HIGH",
            message=(
                f"ML DDoS detected | "
                f"total={stats['total']}, "
                f"failed={stats['failed']}, "
                f"pending={stats['pending']}"
            ),
        )
