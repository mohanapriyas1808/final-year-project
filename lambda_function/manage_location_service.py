"""
Manage AWS Location Service resources for SmartBus demo.

Setup  (run before demo): python lambda_function/manage_location_service.py setup
Cleanup (run after demo): python lambda_function/manage_location_service.py cleanup
"""

import boto3
import os
import sys
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

REGION          = os.environ.get('AWS_REGION', 'ap-south-1')
TRACKER_NAME    = 'SmartBusTracker'
MAP_NAME        = 'SmartBusMap'
GEOFENCE_NAME   = 'SmartBusGeofences'

location = boto3.client('location', region_name=REGION,
    aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'])


def setup():
    print("Setting up AWS Location Service resources...\n")

    # 1. Create Tracker
    try:
        location.create_tracker(
            TrackerName=TRACKER_NAME,
            Description='Tracks SmartBus real-time position',
            PositionFiltering='TimeBased'
        )
        print(f"[TRACKER] Created: {TRACKER_NAME}")
    except location.exceptions.ConflictException:
        print(f"[TRACKER] Already exists: {TRACKER_NAME}")

    # 2. Create Geofence Collection for bus stops
    try:
        location.create_geofence_collection(
            CollectionName=GEOFENCE_NAME,
            Description='Geofences around each SmartBus stop'
        )
        print(f"[GEOFENCE] Created collection: {GEOFENCE_NAME}")

        # Add geofences for each stop (300m radius circles approximated as polygons)
        stops = [
            {"id": "Thiruvanmiyur",   "lat": 12.9830, "lon": 80.2594},
            {"id": "Palavakkam",      "lat": 12.9564, "lon": 80.2508},
            {"id": "ChinnaNeelankarai","lat": 12.9525, "lon": 80.2505},
            {"id": "NeelankaraiECR",  "lat": 12.9497, "lon": 80.2500},
            {"id": "Vettuvankani",    "lat": 12.9360, "lon": 80.2485},
            {"id": "Injambakkam",     "lat": 12.9190, "lon": 80.2460},
            {"id": "AkkaraiLinkRoad", "lat": 12.8913, "lon": 80.2392},
            {"id": "SholinganallurOMR","lat": 12.8961, "lon": 80.2310},
            {"id": "SJITCollegeGate", "lat": 12.8716, "lon": 80.2201},
        ]

        # Build geofence entries — simple square ~300m around each stop
        entries = []
        for stop in stops:
            d = 0.003  # ~300m in degrees
            lat, lon = stop['lat'], stop['lon']
            entries.append({
                'GeofenceId': stop['id'],
                'Geometry': {
                    'Polygon': [[
                        [lon - d, lat - d],
                        [lon + d, lat - d],
                        [lon + d, lat + d],
                        [lon - d, lat + d],
                        [lon - d, lat - d]   # close the polygon
                    ]]
                }
            })

        location.batch_put_geofence(
            CollectionName=GEOFENCE_NAME,
            Entries=entries
        )
        print(f"[GEOFENCE] Added {len(entries)} stop geofences")

    except location.exceptions.ConflictException:
        print(f"[GEOFENCE] Collection already exists: {GEOFENCE_NAME}")

    print("\nSetup complete. Resources ready for demo.")
    print(f"  Tracker:   {TRACKER_NAME}")
    print(f"  Geofences: {GEOFENCE_NAME}")


def cleanup():
    print("Cleaning up AWS Location Service resources...\n")

    # Delete Tracker
    try:
        location.delete_tracker(TrackerName=TRACKER_NAME)
        print(f"[TRACKER] Deleted: {TRACKER_NAME}")
    except location.exceptions.ResourceNotFoundException:
        print(f"[TRACKER] Not found (already deleted): {TRACKER_NAME}")
    except Exception as e:
        print(f"[TRACKER ERROR] {e}")

    # Delete Geofence Collection
    try:
        location.delete_geofence_collection(CollectionName=GEOFENCE_NAME)
        print(f"[GEOFENCE] Deleted: {GEOFENCE_NAME}")
    except location.exceptions.ResourceNotFoundException:
        print(f"[GEOFENCE] Not found (already deleted): {GEOFENCE_NAME}")
    except Exception as e:
        print(f"[GEOFENCE ERROR] {e}")

    print("\nCleanup complete. No more Location Service charges.")


if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] not in ('setup', 'cleanup'):
        print("Usage:")
        print("  python lambda_function/manage_location_service.py setup")
        print("  python lambda_function/manage_location_service.py cleanup")
        sys.exit(1)

    if sys.argv[1] == 'setup':
        setup()
    else:
        cleanup()
