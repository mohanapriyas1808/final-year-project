import os
import math
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
import pandas as pd
import xgboost as xgb
import boto3
from boto3.dynamodb.conditions import Attr
from decimal import Decimal
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = 'sjit_project_secret_key'

# --- DYNAMODB CONFIG ---
dynamodb = boto3.resource(
    'dynamodb',
    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
    region_name=os.environ.get('AWS_REGION', 'ap-south-1')
)
users_table = dynamodb.Table('SmartBus_Users')

# --- ML & GEOFENCING CONFIG ---
STOP_LAT, STOP_LON = 12.8716, 80.2201
BASE_RADIUS = 300
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'bus_eta_model.json')

# Global in-memory bus state
latest_bus_data = {
    "lat": STOP_LAT, "lon": STOP_LON,
    "eta": 0, "dist": 0, "radius": BASE_RADIUS,
    "traffic_index": 0, "status_msg": "System Ready",
    "smart_alert": "", "alert_level": "normal",
    "driver_name": "Not Started", "bus_id": "SJIT_BUS_10",
    "driver_status": "Offline", "speed": 0, "occupancy": 0,
    "upcoming_stops": [], "route_path": [], "weather": "Sunny", "delay_mins": 0
}
bus_occupancy = 0

# Load XGBoost Model
model = xgb.XGBRegressor()
if os.path.exists(MODEL_PATH):
    model.load_model(MODEL_PATH)
else:
    print(f"ERROR: {MODEL_PATH} not found.")

# --- HELPERS ---
def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))

def get_user(username):
    res = users_table.get_item(Key={'username': username})
    return res.get('Item')

def scan_by_role(role):
    res = users_table.scan(FilterExpression=Attr('role').eq(role))
    return res.get('Items', [])

def scan_waiting_students():
    # Scan all students first, then filter in Python to avoid DynamoDB bool type issues
    res = users_table.scan(
        FilterExpression=Attr('role').eq('student')
    )
    items = res.get('Items', [])
    return [s for s in items if s.get('is_waiting') is True]

def to_float(val):
    return float(val) if val is not None else None

# --- AUTH ROUTES ---

@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.json
    if get_user(data['username']):
        return jsonify({"status": "error", "message": "User already exists"}), 400

    item = {
        'username':      data['username'],
        'email':         data.get('email', ''),
        'password':      generate_password_hash(data['password'], method='pbkdf2:sha256'),
        'role':          data.get('role', 'student'),
        'boarding_point': data.get('boarding_point', ''),
        'parent_name':   data.get('parent_name', ''),
        'parent_mobile': data.get('parent_mobile', ''),
        'bus_id':        data.get('bus_id', ''),
        'starting_point': data.get('starting_point', ''),
        'is_waiting':    False,
    }
    if data.get('lat'): item['lat'] = Decimal(str(data['lat']))
    if data.get('lon'): item['lon'] = Decimal(str(data['lon']))

    users_table.put_item(Item=item)
    return jsonify({"status": "success", "message": "User created successfully"}), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user = get_user(data['username'])
    if user and check_password_hash(user['password'], data['password']):
        return jsonify({
            "status": "success",
            "user": {
                "username":      user['username'],
                "boarding_point": user.get('boarding_point', ''),
                "role":          user.get('role', 'student'),
                "lat":           to_float(user.get('lat')),
                "lon":           to_float(user.get('lon')),
                "bus_id":        user.get('bus_id', ''),
                "starting_point": user.get('starting_point', '')
            }
        }), 200
    return jsonify({"status": "error", "message": "Invalid credentials"}), 401

# --- STUDENT ROUTES ---

@app.route('/api/student_status', methods=['POST'])
def student_status():
    data = request.json
    user = get_user(data['username'])
    if not user:
        return jsonify({"status": "error", "message": "User not found"}), 404

    update_expr = "SET is_waiting = :w"
    expr_vals = {':w': data.get('is_waiting', False)}

    if data.get('lat') and data.get('lon'):
        update_expr += ", lat = :lat, lon = :lon"
        expr_vals[':lat'] = Decimal(str(data['lat']))
        expr_vals[':lon'] = Decimal(str(data['lon']))

    users_table.update_item(
        Key={'username': data['username']},
        UpdateExpression=update_expr,
        ExpressionAttributeValues=expr_vals
    )
    return jsonify({"status": "success"})

@app.route('/api/sos_alert', methods=['POST'])
def sos_alert():
    data = request.json
    print(f"SOS ALERT from {data.get('username')} at {data.get('boarding_point')}")
    return jsonify({"status": "success", "message": "SOS alert sent"})

# --- BUS ROUTES ---

@app.route('/update_location', methods=['POST'])
def update_location():
    global latest_bus_data
    try:
        data = request.json
        curr_lat, curr_lon = data['latitude'], data['longitude']
        speed, traffic_t = data['speed'], data['traffic_index']

        drivers = scan_by_role('driver')
        driver_user = drivers[0] if drivers else None
        bus_id = data.get('bus_id') or (driver_user.get('bus_id') if driver_user else 'SJIT_BUS_10')
        driver_name = data.get('driver_name') or (driver_user.get('username') if driver_user else 'Unknown')

        dist = haversine_distance(curr_lat, curr_lon, STOP_LAT, STOP_LON)
        features = pd.DataFrame([{
            'dist_to_stop': dist, 'current_speed': speed,
            'hour': datetime.now().hour, 'day_of_week': datetime.now().weekday(),
            'traffic_index': traffic_t
        }])
        predicted_eta = float(model.predict(features)[0])

        status_msg, alert_level = "Traffic is smooth.", "normal"
        if traffic_t > 0.7:   status_msg, alert_level = "Heavy traffic at main junction.", "urgent"
        elif traffic_t > 0.4: status_msg, alert_level = "Moderate traffic detected.", "warning"

        smart_alert = "EARLY BIRD: Roads are clear! Bus is ahead of schedule." if traffic_t < 0.2 and speed > 40 else ""
        dyn_radius = BASE_RADIUS * (1 + 1.5 * traffic_t)

        waiting = scan_waiting_students()
        stop_map = {}
        for s in waiting:
            bp = s.get('boarding_point') or 'Unknown'
            if bp not in stop_map:
                stop_map[bp] = {"name": bp, "count": 0, "eta": round(predicted_eta, 1),
                                "dist": int(haversine_distance(curr_lat, curr_lon,
                                    to_float(s.get('lat')) or STOP_LAT,
                                    to_float(s.get('lon')) or STOP_LON))}
            stop_map[bp]["count"] += 1

        latest_bus_data.update({
            "lat": curr_lat, "lon": curr_lon,
            "eta": round(predicted_eta, 1), "dist": int(dist),
            "radius": int(dyn_radius), "traffic_index": traffic_t,
            "status_msg": status_msg, "smart_alert": smart_alert,
            "alert_level": alert_level, "driver_name": driver_name,
            "bus_id": bus_id, "driver_status": "Active",
            "speed": speed, "occupancy": bus_occupancy,
            "upcoming_stops": list(stop_map.values())
        })

        return jsonify({"status": "success", "distance_meters": int(dist),
                        "predicted_eta_mins": round(predicted_eta, 1), "notification": status_msg})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/bus_status', methods=['GET'])
def get_bus_status():
    data = dict(latest_bus_data)
    drivers = scan_by_role('driver')
    if drivers:
        d = drivers[0]
        data['driver_name'] = d.get('username', 'N/A')
        data['bus_id'] = d.get('bus_id', 'N/A')
        data['starting_point'] = d.get('starting_point', 'N/A')
    return jsonify(data)

@app.route('/api/driver_route_info', methods=['GET'])
def driver_route_info():
    waiting = scan_waiting_students()
    bus_lat, bus_lon = latest_bus_data["lat"], latest_bus_data["lon"]
    city_map = {}
    for s in waiting:
        city = s.get('boarding_point') or 'Unknown'
        if city not in city_map:
            city_map[city] = {
                "name": city, "count": 0,
                "lat": to_float(s.get('lat')) or STOP_LAT,
                "lon": to_float(s.get('lon')) or STOP_LON,
                "dist": 0
            }
        city_map[city]["count"] += 1

    all_stops = []
    for c in city_map.values():
        c["dist"] = int(haversine_distance(bus_lat, bus_lon, c["lat"], c["lon"]))
        all_stops.append(c)
    all_stops.sort(key=lambda x: x["dist"])

    return jsonify({"all_active_stops": all_stops, "next_stop": all_stops[0] if all_stops else None})

@app.route('/api/update_occupancy', methods=['POST'])
def update_occupancy():
    global bus_occupancy
    action = request.json.get('action')
    if action == 'in':   bus_occupancy = min(bus_occupancy + 1, 40)
    elif action == 'out': bus_occupancy = max(bus_occupancy - 1, 0)
    latest_bus_data["occupancy"] = bus_occupancy
    return jsonify({"status": "success", "count": bus_occupancy})

# --- ADMIN ROUTES ---

@app.route('/api/admin/drivers', methods=['GET'])
def admin_drivers():
    drivers = scan_by_role('driver')
    result = []
    for d in drivers:
        is_active = latest_bus_data.get('driver_name') == d['username']
        result.append({
            'username':      d['username'],
            'bus_id':        d.get('bus_id', ''),
            'starting_point': d.get('starting_point', ''),
            'status':        latest_bus_data.get('driver_status', 'Offline') if is_active else 'Offline',
            'lat':           latest_bus_data.get('lat') if is_active and latest_bus_data.get('driver_status') == 'Active' else None,
            'lon':           latest_bus_data.get('lon') if is_active and latest_bus_data.get('driver_status') == 'Active' else None,
            'speed':         latest_bus_data.get('speed', 0) if is_active else 0
        })
    return jsonify({'drivers': result})

@app.route('/api/admin/students', methods=['GET'])
def admin_students():
    students = scan_by_role('student')
    return jsonify({'students': [{
        'username':      s['username'],
        'email':         s.get('email', ''),
        'boarding_point': s.get('boarding_point', ''),
        'is_waiting':    s.get('is_waiting', False)
    } for s in students]})

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
    app.run(debug=True, host='0.0.0.0', port=5000)
