"""
Smart Bus - Dynamic Geo-Fencing Lambda
----------------------------------------
Triggered by: SmartBus_PredictionLambda (direct invoke after ETA calculated)
Purpose:
  1. Dynamically calculate geofence radius based on traffic index
  2. Check if bus is inside geofence of any waiting student's stop
  3. Send Arrival Notification via SNS when bus enters geofence
  4. Update AWS Location Service with current bus position + geofence

Input event:
{
    "bus_id":        "SJIT_BUS_10",
    "bus_lat":       12.96,
    "bus_lon":       80.25,
    "speed":         30,
    "traffic_index": 0.4,
    "predictions": [
        {"username": "Priya", "stop": "Palavakkam", "eta_mins": 4.5,
         "stop_lat": 12.9564, "stop_lon": 80.2508}
    ]
}
"""

import json
import math
import boto3
import os
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Attr

# --- CONFIG ---
REGION          = 'ap-south-1'
SNS_TOPIC_ARN   = os.environ.get('SNS_TOPIC_ARN', '')
USERS_TABLE     = 'SmartBus_Users'
LOG_TABLE       = 'SmartBus_NotificationLog'
LOCATION_TRACKER = os.environ.get('LOCATION_TRACKER', 'SmartBusTracker')

BASE_RADIUS     = 300    # metres — base geofence radius
MAX_RADIUS      = 800    # metres — cap at heavy traffic
MIN_RADIUS      = 150    # metres — minimum radius

dynamodb = boto3.resource('dynamodb', region_name=REGION)
sns      = boto3.client('sns', region_name=REGION)

try:
    location = boto3.client('location', region_name=REGION)
    LOCATION_ENABLED = True
except Exception:
    LOCATION_ENABLED = False


# --- HELPERS ---

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp     = math.radians(lat2 - lat1)
    dl     = math.radians(lon2 - lon1)
    a      = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return round(2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 2)


def calculate_dynamic_radius(traffic_index, speed):
    """
    Dynamically expand geofence based on traffic and speed.
    - High traffic → larger radius (bus may stop/slow unpredictably)
    - High speed   → larger radius (bus covers distance faster)
    Formula: base * (1 + 1.5 * traffic) * speed_factor
    """
    speed_factor  = 1 + (max(speed, 0) / 100)        # e.g. 60km/h → 1.6x
    traffic_factor = 1 + (1.5 * traffic_index)        # e.g. T=0.8 → 2.2x
    radius = BASE_RADIUS * traffic_factor * speed_factor
    return round(min(max(radius, MIN_RADIUS), MAX_RADIUS), 1)


def get_waiting_students():
    table = dynamodb.Table(USERS_TABLE)
    res   = table.scan(FilterExpression=Attr('role').eq('student'))
    return [s for s in res.get('Items', []) if s.get('is_waiting') is True]


def send_arrival_notification(username, stop_name, bus_id, distance_m, radius_m):
    """Send SNS arrival alert to student."""
    try:
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject='SmartBus: Bus Has Arrived!',
            Message=(
                f"Hi {username},\n\n"
                f"📍 ARRIVAL ALERT: Bus {bus_id} is NOW at {stop_name}!\n"
                f"Distance: {int(distance_m)}m (Geofence: {int(radius_m)}m)\n"
                f"Board the bus now!\n\n"
                f"- Smart Bus System"
            ),
            MessageAttributes={
                'username': {'DataType': 'String', 'StringValue': username}
            }
        )
        print(f"[SNS] Arrival alert → {username} at {stop_name}")
    except Exception as e:
        print(f"[SNS ERROR] {e}")


def log_geofence_event(username, event_type, message):
    """Log geofence event to SmartBus_NotificationLog."""
    try:
        dynamodb.Table(LOG_TABLE).put_item(Item={
            'student_username': username,
            'timestamp':        datetime.now(timezone.utc).isoformat(),
            'alert_type':       event_type,
            'message':          message
        })
    except Exception as e:
        print(f"[LOG ERROR] {e}")


def update_location_service(bus_id, bus_lat, bus_lon):
    """Update AWS Location Service tracker with current bus position."""
    if not LOCATION_ENABLED:
        return
    try:
        location.batch_update_device_position(
            TrackerName=LOCATION_TRACKER,
            Updates=[{
                'DeviceId':   bus_id,
                'Position':   [bus_lon, bus_lat],   # Location uses [lon, lat]
                'SampleTime': datetime.now(timezone.utc).isoformat()
            }]
        )
        print(f"[LOCATION] Updated tracker: {bus_id} → {bus_lat}, {bus_lon}")
    except Exception as e:
        print(f"[LOCATION ERROR] {e}")


def mark_arrival_sent(username):
    """Set arrival_alert_sent=True in SmartBus_Users."""
    try:
        dynamodb.Table(USERS_TABLE).update_item(
            Key={'username': username},
            UpdateExpression='SET arrival_alert_sent = :t',
            ExpressionAttributeValues={':t': True}
        )
    except Exception as e:
        print(f"[DYNAMO ERROR] {e}")


# --- MAIN HANDLER ---

def lambda_handler(event, context):
    print("[Geo-Fencing Lambda] Input:", json.dumps(event))

    # EventBridge wraps payload inside 'detail'
    detail = event.get('detail', event)

    bus_id        = detail.get('bus_id', 'SJIT_BUS_10')
    bus_lat       = float(detail.get('bus_lat', 0))
    bus_lon       = float(detail.get('bus_lon', 0))
    speed         = float(detail.get('speed', 0))
    traffic_index = float(detail.get('traffic_index', 0.4))
    predictions   = detail.get('predictions', [])

    if not bus_lat or not bus_lon:
        return {'statusCode': 400, 'body': 'Missing bus coordinates'}

    # Step 1: Calculate dynamic geofence radius
    radius = calculate_dynamic_radius(traffic_index, speed)
    print(f"[GEOFENCE] Dynamic radius: {radius}m (traffic={traffic_index}, speed={speed})")

    # Step 2: Update AWS Location Service
    update_location_service(bus_id, bus_lat, bus_lon)

    # Step 3: Get waiting students
    students = get_waiting_students()
    student_map = {s['username']: s for s in students}

    geofence_results = []

    for pred in predictions:
        username  = pred.get('username')
        stop_name = pred.get('stop', 'your stop')
        stop_lat  = float(pred.get('stop_lat', 0))
        stop_lon  = float(pred.get('stop_lon', 0))

        if not stop_lat or not stop_lon:
            continue

        # Distance from bus to student's stop
        distance = haversine(bus_lat, bus_lon, stop_lat, stop_lon)
        inside   = distance <= radius

        print(f"[CHECK] {username} @ {stop_name}: dist={distance}m, radius={radius}m, inside={inside}")

        student = student_map.get(username, {})
        already_sent = student.get('arrival_alert_sent', False)

        if inside and not already_sent:
            send_arrival_notification(username, stop_name, bus_id, distance, radius)
            mark_arrival_sent(username)
            log_geofence_event(username, 'ARRIVAL',
                json.dumps({'stop': stop_name, 'distance_m': distance, 'radius_m': radius}))

        geofence_results.append({
            'username':   username,
            'stop':       stop_name,
            'distance_m': distance,
            'radius_m':   radius,
            'inside':     inside,
            'alert_sent': inside and not already_sent
        })

    return {
        'statusCode': 200,
        'body': json.dumps({
            'bus_id':           bus_id,
            'dynamic_radius_m': radius,
            'geofence_results': geofence_results,
            'processed_at':     datetime.now(timezone.utc).isoformat()
        })
    }
