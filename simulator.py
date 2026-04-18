import requests
import time
import random

# --- SETTINGS ---
SERVER_URL = "http://127.0.0.1:5000/update_location"
BUS_ID = "SJIT_BUS_10"

# --- SCENARIO SELECTOR ---
# Change these values to test different features in your React UI:
# Scenario 1 (Normal): TRAFFIC = 0.3, SPEED = 35
# Scenario 2 (Heavy Traffic): TRAFFIC = 0.9, SPEED = 10 -> (Red UI)
# Scenario 3 (Early Bird): TRAFFIC = 0.1, SPEED = 55 -> (Blue/Green UI + Alert)
TRAFFIC_INDEX = 0.4  # T value between 0.0 and 1.0
CURRENT_SPEED = 30   # km/h

# Coordinates (Moving from outside toward St. Joseph's Gate)
start_lat, start_lon = 12.8850, 80.2201 
target_lat, target_lon = 12.8716, 80.2201

print(f"--- Smart Bus Simulator: {BUS_ID} ---")
print(f"Targeting: {target_lat}, {target_lon}")
print(f"Traffic Level: {TRAFFIC_INDEX} | Speed: {CURRENT_SPEED} km/h")
print("---------------------------------------")

curr_lat = start_lat
curr_lon = start_lon

try:
    # Simulation loop
    while curr_lat >= target_lat:
        payload = {
            "bus_id": BUS_ID,
            "latitude": curr_lat,
            "longitude": curr_lon,
            "speed": CURRENT_SPEED,
            "traffic_index": TRAFFIC_INDEX
        }
        
        try:
            response = requests.post(SERVER_URL, json=payload, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                dist = data.get('distance_meters')
                eta = data.get('predicted_eta_mins')
                note = data.get('notification')
                
                print(f"[SENT] Dist: {dist}m | ETA: {eta}m | Status: {note}")
            else:
                print(f"[ERROR] Server returned {response.status_code}")

        except requests.exceptions.ConnectionError:
            print("[X] Backend (app.py) is not running! Please start it.")
            break

        # Move the bus closer (step logic)
        curr_lat -= 0.0004 
        # Add tiny random jitter to GPS to make it look real on the React map
        curr_lon += random.uniform(-0.0001, 0.0001) 
        
        time.sleep(2) # Send update every 2 seconds

    print("\n[FINISH] Bus has reached the destination.")

except KeyboardInterrupt:
    print("\n[STOP] Simulator stopped by user.")