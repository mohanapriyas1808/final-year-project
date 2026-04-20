import os
import json
import math
import pandas as pd
import xgboost as xgb
import boto3
import requests
from decimal import Decimal
from datetime import datetime, UTC
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from boto3.dynamodb.conditions import Attr

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
app.config['SECRET_KEY'] = 'sjit_final_secret'

# --- AWS CONFIG ---
AWS_REGION      = os.environ.get('AWS_REGION', 'ap-south-1')
SNS_TOPIC_ARN   = os.environ.get('SNS_TOPIC_ARN')
AWS_ACCESS_KEY  = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_KEY  = os.environ.get('AWS_SECRET_ACCESS_KEY')

dynamodb = boto3.resource('dynamodb',
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION)

sns_client = boto3.client('sns',
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION)

lambda_client = boto3.client('lambda',
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION)

users_table = dynamodb.Table('SmartBus_Users')

# --- HARDCODED STOPS ---
HARDCODED_STOPS = [
    {"name": "Thiruvanmiyur (Start)", "lat": 12.9830, "lon": 80.2594, "seq": 1},
    {"name": "Palavakkam",            "lat": 12.9564, "lon": 80.2508, "seq": 2},
    {"name": "Chinna Neelankarai",    "lat": 12.9525, "lon": 80.2505, "seq": 3},
    {"name": "Neelankarai (ECR)",     "lat": 12.9497, "lon": 80.2500, "seq": 4},
    {"name": "Vettuvankani",          "lat": 12.9360, "lon": 80.2485, "seq": 5},
    {"name": "Injambakkam",           "lat": 12.9190, "lon": 80.2460, "seq": 6},
    {"name": "Akkarai (Link Road)",   "lat": 12.8913, "lon": 80.2392, "seq": 7},
    {"name": "Sholinganallur (OMR)",  "lat": 12.8961, "lon": 80.2310, "seq": 8},
    {"name": "SJIT College Gate",     "lat": 12.8716, "lon": 80.2201, "seq": 9},
]

MODEL_PATH  = 'bus_eta_model.json'
BASE_RADIUS = 300
ALERT_TTL_MINUTES = 30

# --- GLOBAL STATE ---
latest_bus_data = {
    "bus_id": "SJIT_BUS_10", "lat": 12.9830, "lon": 80.2594,
    "speed": 0, "traffic_index": 0.4, "occupancy": 0, "max_capacity": 40,
    "last_ping": datetime.now(UTC), "driver_name": "Offline"
}
osrm_cache = {}
osrm_cache_pos = {"lat": None, "lon": None}
CACHE_MOVE_THRESHOLD = 50

# Load ML Model — use SageMaker endpoint if configured, else local model
SAGEMAKER_ENDPOINT = os.environ.get('SAGEMAKER_ENDPOINT', '')
model = None

if SAGEMAKER_ENDPOINT:
    sm_runtime = boto3.client('sagemaker-runtime',
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
        region_name=AWS_REGION)
    print(f"SageMaker Endpoint: {SAGEMAKER_ENDPOINT}")
else:
    model = xgb.XGBRegressor()
    if os.path.exists(MODEL_PATH):
        model.load_model(MODEL_PATH)
        print("XGBoost Model Loaded (local)")

def predict_with_model(features_df):
    """Predict ETA using SageMaker serverless endpoint or local model."""
    if SAGEMAKER_ENDPOINT:
        try:
            csv_input = ','.join(str(v) for v in features_df.iloc[0].values)
            response = sm_runtime.invoke_endpoint(
                EndpointName=SAGEMAKER_ENDPOINT,
                ContentType='text/csv',
                Body=csv_input
            )
            return float(response['Body'].read().decode())
        except Exception as e:
            print(f"[SAGEMAKER ERROR] {e} — falling back to local model")
            return float(model.predict(features_df)[0]) if model else 10.0
    else:
        return float(model.predict(features_df)[0])

# --- DYNAMODB HELPERS ---
def get_user(username):
    res = users_table.get_item(Key={'username': username})
    return res.get('Item')

def scan_by_role(role):
    res = users_table.scan(FilterExpression=Attr('role').eq(role))
    return res.get('Items', [])

def scan_waiting_students():
    # Filter in Python to avoid DynamoDB boolean type mismatch issues
    res = users_table.scan(FilterExpression=Attr('role').eq('student'))
    items = res.get('Items', [])
    return [s for s in items if s.get('is_waiting') is True]

def update_user(username, updates: dict):
    expr_parts, expr_vals, expr_names = [], {}, {}
    for i, (k, v) in enumerate(updates.items()):
        safe_key = f"#f{i}"
        expr_names[safe_key] = k
        expr_vals[f":v{i}"] = v
        expr_parts.append(f"{safe_key} = :v{i}")
    users_table.update_item(
        Key={'username': username},
        UpdateExpression="SET " + ", ".join(expr_parts),
        ExpressionAttributeValues=expr_vals,
        ExpressionAttributeNames=expr_names
    )

def to_float(val):
    return float(val) if val is not None else None

# --- GENERAL HELPERS ---
def haversine_distance(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2): return 999999
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))

def get_osrm_data(s_lat, s_lon, e_lat, e_lon):
    global osrm_cache, osrm_cache_pos
    key = f"{round(s_lat,4)},{round(s_lon,4)}->{round(e_lat,4)},{round(e_lon,4)}"
    if osrm_cache_pos["lat"] is not None:
        if haversine_distance(s_lat, s_lon, osrm_cache_pos["lat"], osrm_cache_pos["lon"]) > CACHE_MOVE_THRESHOLD:
            osrm_cache.clear()
            osrm_cache_pos.update({"lat": s_lat, "lon": s_lon})
    else:
        osrm_cache_pos.update({"lat": s_lat, "lon": s_lon})
    if key in osrm_cache:
        return osrm_cache[key]
    try:
        url = f"http://router.project-osrm.org/route/v1/driving/{s_lon},{s_lat};{e_lon},{e_lat}?geometries=geojson"
        res = requests.get(url, timeout=3).json()
        if res.get('routes'):
            path = [[c[1], c[0]] for c in res['routes'][0]['geometry']['coordinates']]
            result = path, res['routes'][0]['distance'], res['routes'][0]['duration']
            osrm_cache[key] = result
            return result
    except: pass
    fallback = [], haversine_distance(s_lat, s_lon, e_lat, e_lon), 300
    osrm_cache[key] = fallback
    return fallback

def send_sns_notification(username, subject, message):
    try:
        sns_client.publish(TopicArn=SNS_TOPIC_ARN, Subject=subject, Message=message,
            MessageAttributes={'username': {'DataType': 'String', 'StringValue': username}})
    except Exception as e:
        print(f"SNS Error: {e}")

# --- AUTH ROUTES ---

@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.json
    if get_user(data['username']):
        return jsonify({"status": "error", "message": "User already exists"}), 400
    item = {
        'username':       data['username'],
        'email':          data.get('email', ''),
        'password':       generate_password_hash(data['password'], method='pbkdf2:sha256'),
        'role':           data.get('role', 'student'),
        'boarding_point': data.get('boarding_point', ''),
        'parent_name':    data.get('parent_name', ''),
        'parent_mobile':  data.get('parent_mobile', ''),
        'bus_id':         data.get('bus_id', ''),
        'starting_point': data.get('starting_point', ''),
        'is_waiting':     False,
        'predictive_alert_sent': False,
        'arrival_alert_sent':    False,
    }
    if data.get('lat'): item['lat'] = Decimal(str(data['lat']))
    if data.get('lon'): item['lon'] = Decimal(str(data['lon']))
    users_table.put_item(Item=item)
    return jsonify({"status": "success"}), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    u = get_user(data['username'])
    if u and check_password_hash(u['password'], data.get('password', '')):
        # Only reset alert flags, NOT is_waiting (student may already be at stop)
        update_user(u['username'], {
            'predictive_alert_sent': False,
            'arrival_alert_sent': False,
            'alert_sent_at': None
        })
        return jsonify({
            "status": "success",
            "user": {
                "username":       u['username'],
                "role":           u.get('role', 'student'),
                "boarding_point": u.get('boarding_point', ''),
                "lat":            to_float(u.get('lat')),
                "lon":            to_float(u.get('lon')),
                "bus_id":         u.get('bus_id', ''),
                "starting_point": u.get('starting_point', '')
            }
        }), 200
    return jsonify({"status": "error"}), 401

# --- STUDENT ROUTES ---

@app.route('/api/student_waiting', methods=['GET'])
def student_waiting():
    u = get_user(request.args.get('username'))
    if u: return jsonify({"is_waiting": u.get('is_waiting', False)})
    return jsonify({"status": "error"}), 404

@app.route('/api/student_status', methods=['POST'])
def student_status():
    data = request.json
    print(f"\n[student_status] received: {data}")
    u = get_user(data.get('username'))
    if not u:
        return jsonify({"status": "error", "message": "User not found"}), 404
    is_waiting_val = data.get('is_waiting', False)
    is_waiting_bool = is_waiting_val is True or is_waiting_val == 'true' or is_waiting_val == 1
    print(f"[student_status] is_waiting raw={is_waiting_val} -> bool={is_waiting_bool}")
    updates = {'is_waiting': is_waiting_bool}
    if data.get('stop_name'):  updates['boarding_point'] = data['stop_name']
    if data.get('lat'):        updates['lat'] = Decimal(str(data['lat']))
    if data.get('lon'):        updates['lon'] = Decimal(str(data['lon']))
    update_user(data['username'], updates)
    print(f"[student_status] updated DB for {data['username']} -> is_waiting={is_waiting_bool}")
    return jsonify({"status": "success", "is_waiting": is_waiting_bool})

# --- BUS ROUTES ---

@app.route('/update_location', methods=['POST'])
def update_location():
    global latest_bus_data
    data = request.json
    latest_bus_data.update({
        "lat": data['latitude'], "lon": data['longitude'],
        "speed": data['speed'], "traffic_index": data['traffic_index'],
        "last_ping": datetime.now(UTC),
        "driver_name": data.get('driver_name', latest_bus_data['driver_name']),
        "bus_id": data.get('bus_id', latest_bus_data['bus_id'])
    })

    # --- Invoke Data Ingestion Lambda (async, non-blocking) ---
    try:
        lambda_client.invoke(
            FunctionName='SmartBus_DataIngestion',
            InvocationType='Event',   # async — don't wait for response
            Payload=json.dumps({
                'bus_id':        data.get('bus_id', 'SJIT_BUS_10'),
                'driver_name':   data.get('driver_name', 'Unknown'),
                'latitude':      data['latitude'],
                'longitude':     data['longitude'],
                'speed':         data['speed'],
                'traffic_index': data['traffic_index']
            })
        )
    except Exception as e:
        print(f"[LAMBDA INVOKE ERROR] {e}")

    students = scan_by_role('student')
    dyn_radius = BASE_RADIUS * (1 + 1.5 * data['traffic_index'])
    now = datetime.now()

    for s in students:
        s_lat, s_lon = to_float(s.get('lat')), to_float(s.get('lon'))
        if s_lat is None or s_lon is None: continue

        _, road_dist, _ = get_osrm_data(data['latitude'], data['longitude'], s_lat, s_lon)
        feat = pd.DataFrame([{
            'dist_to_stop': road_dist,
            'current_speed': data['speed'] or 25,
            'hour': now.hour, 'day_of_week': now.weekday(),
            'traffic_index': data['traffic_index']
        }])
        eta = predict_with_model(feat)
        updates = {}

        # Predictive Alert
        if eta <= 10.0 and not s.get('predictive_alert_sent'):
            send_sns_notification(s['username'], "Bus Arriving Soon",
                f"Hi {s['username']}, bus reaching {s.get('boarding_point')} in {round(eta,1)} mins.")
            updates['predictive_alert_sent'] = True
            updates['alert_sent_at'] = now.isoformat()

        # Arrival Alert
        if s.get('is_waiting') and road_dist <= dyn_radius and not s.get('arrival_alert_sent'):
            traffic_status = (
                "🔴 Heavy traffic" if data['traffic_index'] > 0.7
                else "🟡 Moderate traffic" if data['traffic_index'] > 0.4
                else "🟢 Clear roads"
            )
            send_sns_notification(s['username'], "SmartBus: Bus Has Arrived!",
                f"Hi {s['username']},\n\n"
                f"📍 ARRIVAL ALERT: Bus is NOW at {s.get('boarding_point', 'your stop')}!\n"
                f"Traffic: {traffic_status} (index: {data['traffic_index']})\n"
                f"Geofence radius: {int(dyn_radius)}m\n"
                f"Board the bus now!\n\n"
                f"- Smart Bus System")
            updates['arrival_alert_sent'] = True
            updates['alert_sent_at'] = now.isoformat()

        # TTL Reset
        alert_sent_at = s.get('alert_sent_at')
        if alert_sent_at and s.get('predictive_alert_sent'):
            sent_time = datetime.fromisoformat(alert_sent_at)
            if (now - sent_time).total_seconds() > ALERT_TTL_MINUTES * 60:
                updates.update({'predictive_alert_sent': False, 'arrival_alert_sent': False, 'alert_sent_at': None})
        if road_dist > 2000:
            updates.update({'predictive_alert_sent': False, 'arrival_alert_sent': False, 'alert_sent_at': None})

        if updates:
            update_user(s['username'], updates)

    return jsonify({"status": "success"})

@app.route('/api/predict_eta', methods=['POST'])
def predict_eta():
    """Called by Prediction Lambda — uses same ETA formula as dashboard."""
    data      = request.json
    bus_lat   = data['bus_lat']
    bus_lon   = data['bus_lon']
    stop_lat  = data['stop_lat']
    stop_lon  = data['stop_lon']
    speed     = data.get('speed', 25) or 25
    traffic   = data.get('traffic_index', 0.4)

    _, dist, dur = get_osrm_data(bus_lat, bus_lon, stop_lat, stop_lon)
    now  = datetime.now()
    feat = pd.DataFrame([{
        'dist_to_stop':   dist,
        'current_speed':  speed,
        'hour':           now.hour,
        'day_of_week':    now.weekday(),
        'traffic_index':  traffic
    }])
    ml_eta = predict_with_model(feat)
    # Same formula as dashboard
    eta = max(ml_eta, dur/60) * (1 + traffic * 0.2)
    return jsonify({'eta_mins': round(eta, 1), 'dist_m': int(dist)})

@app.route('/api/bus_status', methods=['GET'])
def get_bus_status():
    username = request.args.get('username')
    drivers = scan_by_role('driver')
    if drivers:
        d = drivers[0]
        latest_bus_data['driver_name'] = d.get('username', 'N/A')
        if d.get('bus_id'): latest_bus_data['bus_id'] = d['bus_id']

    upcoming = []
    last_eta = 0
    for stop in HARDCODED_STOPS:
        _, dist, dur = get_osrm_data(latest_bus_data['lat'], latest_bus_data['lon'], stop['lat'], stop['lon'])
        if dist > 150:
            feat = pd.DataFrame([{
                'dist_to_stop': dist,
                'current_speed': latest_bus_data['speed'] or 25,
                'hour': datetime.now().hour, 'day_of_week': datetime.now().weekday(),
                'traffic_index': latest_bus_data['traffic_index']
            }])
            ml_eta = predict_with_model(feat)
            cur_eta = max(ml_eta, dur/60) * (1 + latest_bus_data['traffic_index'] * 0.2)
            if cur_eta <= last_eta: cur_eta = last_eta + 2.1
            last_eta = cur_eta
            upcoming.append({"name": stop['name'], "eta": round(cur_eta, 1), "dist": int(dist)})

    is_active = (datetime.now(UTC) - latest_bus_data['last_ping']).seconds < 40
    res = {**latest_bus_data, "upcoming_stops": upcoming, "driver_status": "Active" if is_active else "Offline",
           "last_ping": latest_bus_data['last_ping'].isoformat()}

    if username:
        u = get_user(username)
        if u and u.get('lat'):
            u_lat = to_float(u['lat'])
            u_lon = to_float(u['lon'])
            res.update({"user_lat": u_lat, "user_lon": u_lon})

            # Use Lambda-predicted ETA if available (matches email exactly)
            last_predicted_eta = u.get('last_predicted_eta')
            if last_predicted_eta:
                personal_eta = float(last_predicted_eta)
            else:
                # Fallback: calculate locally
                _, u_dist, u_dur = get_osrm_data(
                    latest_bus_data['lat'], latest_bus_data['lon'], u_lat, u_lon)
                now = datetime.now()
                feat = pd.DataFrame([{
                    'dist_to_stop':  u_dist,
                    'current_speed': latest_bus_data['speed'] or 25,
                    'hour':          now.hour,
                    'day_of_week':   now.weekday(),
                    'traffic_index': latest_bus_data['traffic_index']
                }])
                ml_eta = predict_with_model(feat)
                personal_eta = max(ml_eta, u_dur/60) * (1 + latest_bus_data['traffic_index'] * 0.2)

            res['personal_eta'] = round(personal_eta, 1)

            # Update the student's stop in upcoming_stops with the same ETA
            boarding = u.get('boarding_point', '').strip().lower()
            for stop in res['upcoming_stops']:
                if stop['name'].strip().lower() == boarding:
                    stop['eta'] = res['personal_eta']
                    break

    return jsonify(res)

@app.route('/api/driver_route_info', methods=['GET'])
def driver_info():
    waiting = scan_waiting_students()
    print("\n--- WAITING STUDENTS ---")
    for s in waiting:
        print(f"  {s['username']} | {s.get('boarding_point')} | {s.get('lat')}, {s.get('lon')}")

    # Build a lookup from stop name -> coords using HARDCODED_STOPS as fallback
    stop_coords = {st['name'].strip().lower(): (st['lat'], st['lon']) for st in HARDCODED_STOPS}

    stop_map = {}
    for s in waiting:
        city = s.get('boarding_point', '').strip()
        if not city: continue

        # Use live GPS if available, else fall back to hardcoded stop coords
        s_lat, s_lon = to_float(s.get('lat')), to_float(s.get('lon'))
        if s_lat is None or s_lon is None:
            fallback = stop_coords.get(city.lower())
            if fallback:
                s_lat, s_lon = fallback
            else:
                continue  # truly unknown stop, skip

        if city not in stop_map:
            dist = haversine_distance(latest_bus_data['lat'], latest_bus_data['lon'], s_lat, s_lon)
            stop_map[city] = {"name": city, "location": city, "count": 0, "dist": dist, "lat": s_lat, "lon": s_lon}
        stop_map[city]["count"] += 1

    sorted_stops = sorted(stop_map.values(), key=lambda x: x['dist'])
    return jsonify({"all_active_stops": sorted_stops, "next_stop": sorted_stops[0] if sorted_stops else None})

@app.route('/api/update_occupancy', methods=['POST'])
def update_occ():
    act = request.json.get('action')
    onboarded = None
    if act == 'in':
        latest_bus_data['occupancy'] = min(40, latest_bus_data['occupancy'] + 1)
        waiting = scan_waiting_students()
        if waiting:
            closest = min(waiting, key=lambda s: haversine_distance(
                latest_bus_data['lat'], latest_bus_data['lon'],
                to_float(s.get('lat')) or 0, to_float(s.get('lon')) or 0))
            update_user(closest['username'], {'is_waiting': False})
            onboarded = closest['username']
    elif act == 'out':
        latest_bus_data['occupancy'] = max(0, latest_bus_data['occupancy'] - 1)
    return jsonify({"status": "success", "count": latest_bus_data['occupancy'], "onboarded": onboarded})

@app.route('/api/sos_alert', methods=['POST'])
def sos_alert():
    data = request.json
    msg = f"SOS: Student {data['username']} at stop {data['boarding_point']} triggered an alert!"
    sns_client.publish(TopicArn=SNS_TOPIC_ARN, Message=msg, Subject="Emergency SOS")
    return jsonify({"status": "sent"})

# --- ADMIN ROUTES ---

@app.route('/api/admin/drivers', methods=['GET'])
def admin_drivers():
    drivers = scan_by_role('driver')
    result = []
    for d in drivers:
        is_active = (latest_bus_data.get('driver_name') == d['username'] and
                     (datetime.now(UTC) - latest_bus_data['last_ping']).seconds < 40)
        result.append({
            'username':      d['username'],
            'email':         d.get('email', '—'),
            'bus_id':        d.get('bus_id', '—'),
            'starting_point': d.get('starting_point', '—'),
            'status':        'Active' if is_active else 'Offline',
            'lat':           latest_bus_data.get('lat') if is_active else None,
            'lon':           latest_bus_data.get('lon') if is_active else None,
            'speed':         latest_bus_data.get('speed', 0) if is_active else 0
        })
    return jsonify({'drivers': result})

@app.route('/api/admin/students', methods=['GET'])
def admin_students():
    students = scan_by_role('student')
    return jsonify({'students': [{
        'username':      s['username'],
        'email':         s.get('email', '—'),
        'boarding_point': s.get('boarding_point', '—'),
        'is_waiting':    s.get('is_waiting', False)
    } for s in students]})

@app.route('/api/debug/force_waiting/<username>', methods=['GET'])
def force_waiting(username):
    update_user(username, {'is_waiting': True})
    u = get_user(username)
    return jsonify({"after_update": u.get('is_waiting'), "type": type(u.get('is_waiting')).__name__})

@app.route('/api/debug/reset_waiting/<username>', methods=['GET'])
def reset_waiting(username):
    update_user(username, {
        'is_waiting': False,
        'predictive_alert_sent': False,
        'arrival_alert_sent': False,
        'alert_sent_at': None
    })
    u = get_user(username)
    return jsonify({
        "is_waiting": u.get('is_waiting'),
        "predictive_alert_sent": u.get('predictive_alert_sent'),
        "arrival_alert_sent": u.get('arrival_alert_sent')
    })

@app.route('/api/debug/waiting', methods=['GET'])
def debug_waiting():
    all_students = users_table.scan(FilterExpression=Attr('role').eq('student')).get('Items', [])
    return jsonify([{
        'username': s['username'],
        'is_waiting': s.get('is_waiting'),
        'is_waiting_type': type(s.get('is_waiting')).__name__,
        'boarding_point': s.get('boarding_point'),
        'lat': str(s.get('lat')),
        'lon': str(s.get('lon'))
    } for s in all_students])

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False, host='0.0.0.0', port=5000)
