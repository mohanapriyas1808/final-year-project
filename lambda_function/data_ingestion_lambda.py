"""
Smart Bus - Data Ingestion & Processing Lambda
-----------------------------------------------
Triggered by: API Gateway (POST /ingest)
Purpose:
  1. Validate & preprocess incoming GPS data from driver app
  2. Enrich with distances to all stops (from SmartBus_BusStops table)
  3. Store real-time state in DynamoDB (SmartBus_Users - driver record)
  4. Store historical record in S3 (for SageMaker model training)
  5. Log ingestion event to SmartBus_NotificationLog

Existing DynamoDB Tables used:
  - SmartBus_BusStops       : partition key = sequence (N) — stop coords
  - SmartBus_NotificationLog: partition key = student_username, sort = timestamp
  - SmartBus_Users          : updates driver's lat/lon/speed

S3 Bucket: smartbus-historical-data
  - Path: raw/YYYY/MM/DD/bus_id_timestamp.json
  - Used by SageMaker for ETA model retraining
"""

import json
import math
import boto3
import os
from datetime import datetime, timezone
from decimal import Decimal

# --- CONFIG ---
REGION          = os.environ.get('AWS_REGION', 'ap-south-1')
USERS_TABLE     = 'SmartBus_Users'
STOPS_TABLE     = 'SmartBus_BusStops'
LOG_TABLE       = 'SmartBus_NotificationLog'
S3_BUCKET       = os.environ.get('S3_BUCKET', 'smartbus-historical-data')

dynamodb = boto3.resource('dynamodb', region_name=REGION)
s3       = boto3.client('s3', region_name=REGION)


# --- HELPERS ---

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp     = math.radians(lat2 - lat1)
    dl     = math.radians(lon2 - lon1)
    a      = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return round(2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 2)


def get_all_stops():
    """Fetch all stops from SmartBus_BusStops, sorted by sequence."""
    table = dynamodb.Table(STOPS_TABLE)
    items = table.scan().get('Items', [])
    return sorted(items, key=lambda x: int(x['sequence']))


def validate_and_enrich(event, stops):
    """Validate, fill defaults, compute distances to all stops."""
    required = ['bus_id', 'latitude', 'longitude']
    for field in required:
        if field not in event:
            raise ValueError(f"Missing required field: {field}")

    lat = float(event['latitude'])
    lon = float(event['longitude'])

    if not (8.0 <= lat <= 14.0 and 76.0 <= lon <= 82.0):
        raise ValueError(f"Coordinates out of expected range: {lat}, {lon}")

    now = datetime.now(timezone.utc)

    # Distance to each stop
    stop_distances = []
    nearest_stop = None
    min_dist = float('inf')

    for stop in stops:
        dist = haversine(lat, lon, float(stop['lat']), float(stop['lon']))
        stop_distances.append({
            'sequence': int(stop['sequence']),
            'name':     stop['name'],
            'dist_m':   dist
        })
        if dist < min_dist:
            min_dist = dist
            nearest_stop = stop['name']

    # College gate is always sequence 9
    college = next((s for s in stops if int(s['sequence']) == 9), None)
    dist_to_college = haversine(lat, lon, float(college['lat']), float(college['lon'])) if college else 0

    return {
        'bus_id':            event['bus_id'],
        'driver_name':       event.get('driver_name', 'Unknown'),
        'latitude':          lat,
        'longitude':         lon,
        'speed':             float(event.get('speed', 0)),
        'traffic_index':     float(event.get('traffic_index', 0.4)),
        'timestamp':         event.get('timestamp', now.isoformat()),
        'date':              now.strftime('%Y-%m-%d'),
        'hour':              now.hour,
        'day_of_week':       now.weekday(),
        'dist_to_college_m': dist_to_college,
        'nearest_stop':      nearest_stop,
        'nearest_stop_dist_m': min_dist,
        'stop_distances':    stop_distances,
        'ingested_at':       now.isoformat()
    }


def update_driver_in_users(payload):
    """Update driver's position in SmartBus_Users table."""
    table = dynamodb.Table(USERS_TABLE)
    table.update_item(
        Key={'username': payload['driver_name']},
        UpdateExpression='SET lat = :lat, lon = :lon, speed = :spd, last_ping = :ts',
        ExpressionAttributeValues={
            ':lat': Decimal(str(payload['latitude'])),
            ':lon': Decimal(str(payload['longitude'])),
            ':spd': Decimal(str(payload['speed'])),
            ':ts':  payload['ingested_at']
        }
    )
    print(f"[DYNAMO] Updated driver {payload['driver_name']} in SmartBus_Users")


def log_ingestion(payload):
    """Log ingestion event to SmartBus_NotificationLog."""
    table = dynamodb.Table(LOG_TABLE)
    table.put_item(Item={
        'student_username': f"BUS#{payload['bus_id']}",
        'timestamp':        payload['ingested_at'],
        'alert_type':       'INGESTION',
        'message':          json.dumps({
            'lat':              payload['latitude'],
            'lon':              payload['longitude'],
            'speed':            payload['speed'],
            'nearest_stop':     payload['nearest_stop'],
            'dist_to_college_m': payload['dist_to_college_m']
        })
    })
    print(f"[DYNAMO] Logged ingestion for {payload['bus_id']}")


def save_to_s3(payload):
    """Save historical record to S3 for SageMaker training."""
    now = datetime.now(timezone.utc)
    key = (
        f"raw/{now.strftime('%Y/%m/%d')}/"
        f"{payload['bus_id']}_{now.strftime('%H%M%S%f')}.json"
    )
    # Remove stop_distances list for cleaner ML training record
    training_record = {k: v for k, v in payload.items() if k != 'stop_distances'}

    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=json.dumps(training_record),
        ContentType='application/json'
    )
    print(f"[S3] Saved: s3://{S3_BUCKET}/{key}")
    return key


# --- MAIN HANDLER ---

def lambda_handler(event, context):
    print("[INPUT]", json.dumps(event))

    if isinstance(event.get('body'), str):
        event = json.loads(event['body'])

    try:
        stops   = get_all_stops()
        payload = validate_and_enrich(event, stops)

        update_driver_in_users(payload)
        log_ingestion(payload)
        s3_key = save_to_s3(payload)

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'status':            'success',
                'bus_id':            payload['bus_id'],
                'nearest_stop':      payload['nearest_stop'],
                'dist_to_college_m': payload['dist_to_college_m'],
                'ingested_at':       payload['ingested_at'],
                's3_key':            s3_key
            })
        }

    except ValueError as e:
        print(f"[VALIDATION ERROR] {e}")
        return {'statusCode': 400, 'body': json.dumps({'status': 'error', 'message': str(e)})}
    except Exception as e:
        print(f"[ERROR] {e}")
        return {'statusCode': 500, 'body': json.dumps({'status': 'error', 'message': str(e)})}
