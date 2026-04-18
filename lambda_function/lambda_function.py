"""
Smart Bus - Lambda Data Processing Layer
-----------------------------------------
Triggered by: Flask backend (POST /update_location)
Input event:
{
    "bus_id": "SJIT_BUS_10",
    "driver_name": "Dhinesh",
    "latitude": 12.96,
    "longitude": 80.25,
    "speed": 30,
    "traffic_index": 0.4
}

Processing steps:
1. Calculate distance from bus to each waiting student (haversine)
2. Estimate ETA using speed + traffic
3. Fire Predictive Alert if ETA <= 5 mins (student not yet waiting)
4. Fire Arrival Alert if bus inside geofence AND student is waiting
5. Log every alert to DynamoDB NotificationLog
6. Return processed bus state back to Flask
"""

import json
import math
import boto3
from datetime import datetime, timezone
from decimal import Decimal

# --- CONFIG ---
REGION          = "ap-south-1"
SNS_TOPIC_ARN   = "arn:aws:sns:ap-south-1:868295556072:SmartBusNotifications"
USERS_TABLE     = "SmartBus_Users"
LOG_TABLE       = "SmartBus_NotificationLog"
BASE_RADIUS     = 300   # metres
AVG_SPEED_KMPH  = 25    # fallback speed if bus reports 0

dynamodb = boto3.resource('dynamodb', region_name=REGION)
sns      = boto3.client('sns',        region_name=REGION)

# ── Helpers ──────────────────────────────────────────────────────────────────

def haversine(lat1, lon1, lat2, lon2):
    """Straight-line distance in metres between two GPS points."""
    R = 6371000
    p1, p2   = math.radians(lat1), math.radians(lat2)
    dp       = math.radians(lat2 - lat1)
    dl       = math.radians(lon2 - lon1)
    a        = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def estimate_eta(distance_m, speed_kmph, traffic_index):
    """
    ETA in minutes.
    Formula: (distance / effective_speed) * traffic_penalty
    """
    speed = max(speed_kmph, AVG_SPEED_KMPH)          # never divide by 0
    speed_mps = (speed * 1000) / 60                  # km/h → m/min
    raw_eta   = distance_m / speed_mps               # minutes
    penalty   = 1 + (traffic_index * 0.5)            # e.g. T=0.8 → 1.4x longer
    return round(raw_eta * penalty, 1)

def send_alert(username, subject, message):
    """Publish SNS alert filtered to a specific student."""
    try:
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject,
            Message=message,
            MessageAttributes={
                'username': {
                    'DataType': 'String',
                    'StringValue': username
                }
            }
        )
        print(f"[SNS] Alert sent → {username}: {subject}")
    except Exception as e:
        print(f"[SNS ERROR] {username}: {e}")

def log_alert(username, alert_type, message):
    """Write alert record to DynamoDB NotificationLog."""
    try:
        table = dynamodb.Table(LOG_TABLE)
        table.put_item(Item={
            'student_username': username,
            'timestamp':        datetime.now(timezone.utc).isoformat(),
            'alert_type':       alert_type,
            'message':          message
        })
    except Exception as e:
        print(f"[DYNAMO LOG ERROR] {username}: {e}")

def update_student_flag(username, field, value):
    """Update a boolean flag on the student's DynamoDB record."""
    try:
        table = dynamodb.Table(USERS_TABLE)
        table.update_item(
            Key={'username': username},
            UpdateExpression=f"SET {field} = :v",
            ExpressionAttributeValues={':v': value}
        )
    except Exception as e:
        print(f"[DYNAMO UPDATE ERROR] {username}.{field}: {e}")

def get_all_students():
    """Scan SmartBus_Users for all students."""
    table = dynamodb.Table(USERS_TABLE)
    res   = table.scan(
        FilterExpression=boto3.dynamodb.conditions.Attr('role').eq('student')
    )
    return res.get('Items', [])

# ── Main Handler ─────────────────────────────────────────────────────────────

def lambda_handler(event, context):
    print("[INPUT EVENT]", json.dumps(event))

    # --- Parse input ---
    bus_lat       = float(event['latitude'])
    bus_lon       = float(event['longitude'])
    speed         = float(event.get('speed', 0))
    traffic_index = float(event.get('traffic_index', 0.4))
    bus_id        = event.get('bus_id', 'SJIT_BUS_10')
    driver_name   = event.get('driver_name', 'Driver')

    dyn_radius    = BASE_RADIUS * (1 + 1.5 * traffic_index)

    students      = get_all_students()
    alerts_fired  = []
    student_stats = []

    for s in students:
        username   = s['username']
        s_lat      = float(s.get('lat') or 0)
        s_lon      = float(s.get('lon') or 0)
        is_waiting = bool(s.get('is_waiting', False))
        pred_sent  = bool(s.get('predictive_alert_sent', False))
        arr_sent   = bool(s.get('arrival_alert_sent', False))
        stop_name  = s.get('boarding_point', 'your stop')

        if not s_lat or not s_lon:
            continue

        distance = haversine(bus_lat, bus_lon, s_lat, s_lon)
        eta      = estimate_eta(distance, speed, traffic_index)

        student_stats.append({
            'username':  username,
            'stop':      stop_name,
            'distance_m': round(distance),
            'eta_mins':  eta,
            'is_waiting': is_waiting
        })

        # ── Phase 1: Predictive Alert ──────────────────────────────────────
        # Fires when bus is ≤ 5 mins away, regardless of waiting status
        if eta <= 5.0 and not pred_sent:
            msg = (
                f"Hi {username},\n\n"
                f"🚨 PREDICTIVE ALERT: Bus {bus_id} is {eta} mins away "
                f"from {stop_name}.\n"
                f"Time to start walking!\n\n"
                f"Driver: {driver_name}\n"
                f"- Smart Bus System"
            )
            send_alert(username, "SmartBus: Time to Leave!", msg)
            log_alert(username, "PREDICTIVE", msg)
            update_student_flag(username, 'predictive_alert_sent', True)
            alerts_fired.append({'username': username, 'type': 'PREDICTIVE', 'eta': eta})

        # ── Phase 2: Arrival Alert ─────────────────────────────────────────
        # Fires only when student pressed "I'm at the stop" AND bus is inside geofence
        if is_waiting and distance <= dyn_radius and not arr_sent:
            msg = (
                f"Hi {username},\n\n"
                f"📍 ARRIVAL ALERT: Bus {bus_id} has arrived at {stop_name}.\n"
                f"Board now!\n\n"
                f"Driver: {driver_name}\n"
                f"- Smart Bus System"
            )
            send_alert(username, "SmartBus: Bus Has Arrived!", msg)
            log_alert(username, "ARRIVAL", msg)
            update_student_flag(username, 'arrival_alert_sent', True)
            alerts_fired.append({'username': username, 'type': 'ARRIVAL', 'distance_m': round(distance)})

        # ── Reset flags when bus moves away (next trip) ────────────────────
        if distance > 2000 and (pred_sent or arr_sent):
            update_student_flag(username, 'predictive_alert_sent', False)
            update_student_flag(username, 'arrival_alert_sent', False)
            print(f"[RESET] Flags reset for {username} (bus moved away)")

    # --- Build response ---
    response = {
        'statusCode': 200,
        'bus_id':        bus_id,
        'driver_name':   driver_name,
        'bus_lat':       bus_lat,
        'bus_lon':       bus_lon,
        'speed':         speed,
        'traffic_index': traffic_index,
        'dyn_radius_m':  round(dyn_radius),
        'students_processed': len(student_stats),
        'student_stats': student_stats,
        'alerts_fired':  alerts_fired,
        'processed_at':  datetime.now(timezone.utc).isoformat()
    }

    print("[OUTPUT]", json.dumps(response))
    return response
