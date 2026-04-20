"""
Smart Bus - Prediction Lambda
------------------------------
Triggered by: EventBridge (every 1 minute) or direct invoke
Purpose:
  1. Fetch latest bus state from SmartBus_NotificationLog (stored by ingestion lambda)
  2. Fetch all waiting students from SmartBus_Users
  3. Send data to local XGBoost model via Flask /api/predict_eta
  4. Send Predicted ETA Alert via SNS if ETA <= threshold

Environment Variables:
  - FLASK_URL     : e.g. http://<your-local-ip>:5000  (ngrok URL in production)
  - SNS_TOPIC_ARN : SNS topic ARN
"""

import json
import math
import boto3
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Attr

# --- CONFIG ---
REGION        = 'ap-south-1'
USERS_TABLE   = 'SmartBus_Users'
LOG_TABLE     = 'SmartBus_NotificationLog'
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN', '')
FLASK_URL     = os.environ.get('FLASK_URL', 'http://localhost:5000')
ETA_THRESHOLD = 10.0   # minutes — alert if ETA <= this

dynamodb = boto3.resource('dynamodb', region_name=REGION)
sns      = boto3.client('sns', region_name=REGION)


# --- HELPERS ---

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp     = math.radians(lat2 - lat1)
    dl     = math.radians(lon2 - lon1)
    a      = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return round(2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 2)


def get_latest_bus_state():
    """
    Fetch the latest ingestion record from SmartBus_NotificationLog.
    Ingestion lambda stores records with student_username = 'BUS#<bus_id>'
    """
    table = dynamodb.Table(LOG_TABLE)
    res   = table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key('student_username').eq('BUS#SJIT_BUS_10'),
        ScanIndexForward=False,   # latest first
        Limit=1
    )
    items = res.get('Items', [])
    if not items:
        return None

    # message field contains the bus state JSON
    msg = items[0].get('message', '{}')
    return json.loads(msg)


def get_waiting_students():
    """Fetch all students with is_waiting=True from SmartBus_Users."""
    table = dynamodb.Table(USERS_TABLE)
    res   = table.scan(FilterExpression=Attr('role').eq('student'))
    return [s for s in res.get('Items', []) if s.get('is_waiting') is True]


def get_stop_coords():
    """Fetch stop coordinates from SmartBus_BusStops table."""
    table = dynamodb.Table('SmartBus_BusStops')
    items = table.scan().get('Items', [])
    # Return dict: {stop_name_lower: (lat, lon)}
    return {s['name'].strip().lower(): (float(s['lat']), float(s['lon'])) for s in items}


def get_stop_etas_from_flask():
    """
    Fetch upcoming_stops ETAs directly from Flask bus_status.
    This ensures the same ETA shown on dashboard is used in the email.
    """
    req = urllib.request.Request(
        f"{FLASK_URL}/api/bus_status",
        method='GET'
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read().decode())
            stops = result.get('upcoming_stops', [])
            # Return dict: {stop_name_lower: eta_mins}
            return {s['name'].strip().lower(): float(s['eta']) for s in stops}
    except Exception as e:
        print(f"[BUS_STATUS ERROR] {e}")
        return {}


def call_predict_eta(bus_lat, bus_lon, bus_speed, traffic_index, stop_lat, stop_lon):
    """Call Flask /api/predict_eta endpoint."""
    payload = json.dumps({
        'bus_lat':       bus_lat,
        'bus_lon':       bus_lon,
        'speed':         bus_speed,
        'traffic_index': traffic_index,
        'stop_lat':      stop_lat,
        'stop_lon':      stop_lon
    }).encode('utf-8')

    req = urllib.request.Request(
        f"{FLASK_URL}/api/predict_eta",
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read().decode())
            return float(result.get('eta_mins', 999))
    except Exception as e:
        print(f"[PREDICT ERROR] {e}")
        return None


def send_eta_alert(username, stop_name, eta_mins, bus_id):
    """Send predicted ETA alert via SNS."""
    try:
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject='SmartBus: Bus Arriving Soon',
            Message=(
                f"Hi {username},\n\n"
                f"🚌 Bus {bus_id} is arriving at {stop_name} in {eta_mins} mins.\n"
                f"Please be ready at your stop!\n\n"
                f"- Smart Bus System"
            ),
            MessageAttributes={
                'username': {'DataType': 'String', 'StringValue': username}
            }
        )
        print(f"[SNS] ETA alert sent to {username}: {eta_mins} mins")
    except Exception as e:
        print(f"[SNS ERROR] {e}")


# --- MAIN HANDLER ---

def lambda_handler(event, context):
    print("[Prediction Lambda] Triggered at", datetime.now(timezone.utc).isoformat())

    # Step 1: Get latest bus state from DynamoDB
    bus_state = get_latest_bus_state()
    if not bus_state:
        print("[WARN] No bus state found in NotificationLog")
        return {'statusCode': 200, 'body': 'No bus data available'}

    bus_lat       = float(bus_state.get('lat', 0))
    bus_lon       = float(bus_state.get('lon', 0))
    bus_speed     = float(bus_state.get('speed', 25))
    traffic_index = float(bus_state.get('traffic_index', 0.4))
    bus_id        = bus_state.get('bus_id', 'SJIT_BUS_10')

    print(f"[BUS STATE] lat={bus_lat}, lon={bus_lon}, speed={bus_speed}, traffic={traffic_index}")

    # Step 2: Get waiting students + stop coordinates
    students   = get_waiting_students()
    stop_coords = get_stop_coords()
    print(f"[STUDENTS] {len(students)} waiting")

    results = []
    for s in students:
        username  = s['username']
        stop_name = s.get('boarding_point', '').strip()
        s_lat     = float(s.get('lat') or 0)
        s_lon     = float(s.get('lon') or 0)

        if not s_lat or not s_lon:
            print(f"[SKIP] {username} has no GPS coords")
            continue

        # Use student's actual GPS — matches dashboard personal ETA
        eta = call_predict_eta(bus_lat, bus_lon, bus_speed, traffic_index, s_lat, s_lon)
        if eta is None:
            continue

        print(f"[ETA] {username} @ {stop_name}: {eta} mins")

        # Store ETA in DynamoDB so dashboard can read the same value
        try:
            dynamodb.Table(USERS_TABLE).update_item(
                Key={'username': username},
                UpdateExpression='SET last_predicted_eta = :e',
                ExpressionAttributeValues={':e': str(round(eta, 1))}
            )
        except Exception as e:
            print(f"[DYNAMO ETA STORE ERROR] {e}")

        if eta <= ETA_THRESHOLD and not s.get('predictive_alert_sent'):
            send_eta_alert(username, stop_name, round(eta, 1), bus_id)

        results.append({
            'username': username,
            'stop':     stop_name,
            'eta_mins': eta,
            'stop_lat': s_lat,
            'stop_lon': s_lon
        })

    # Step 5: Publish event to EventBridge → triggers GeoFencing Lambda
    if results:
        try:
            events_client = boto3.client('events', region_name=REGION)
            events_client.put_events(
                Entries=[{
                    'Source':       'smartbus.prediction',
                    'DetailType':   'ETACalculated',
                    'Detail':       json.dumps({
                        'bus_id':        bus_id,
                        'bus_lat':       bus_lat,
                        'bus_lon':       bus_lon,
                        'speed':         bus_speed,
                        'traffic_index': traffic_index,
                        'predictions':   results
                    }),
                    'EventBusName': 'default'
                }]
            )
            print(f"[EVENTBRIDGE] Published ETACalculated event for {len(results)} students")
        except Exception as e:
            print(f"[EVENTBRIDGE ERROR] {e}")

    return {
        'statusCode': 200,
        'body': json.dumps({
            'bus_state':   bus_state,
            'predictions': results,
            'processed_at': datetime.now(timezone.utc).isoformat()
        })
    }
