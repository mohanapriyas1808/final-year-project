import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// --- LEAFLET ICON FIX ---
import icon from 'leaflet/dist/images/marker-icon.png';
import iconShadow from 'leaflet/dist/images/marker-shadow.png';

let DefaultIcon = L.icon({
    iconUrl: icon,
    shadowUrl: iconShadow,
    iconSize: [25, 41],
    iconAnchor: [12, 41]
});
L.Marker.prototype.options.icon = DefaultIcon;

// --- CONFIG ---
const BACKEND_URL = `http://${window.location.hostname}:5000`;
const COLLEGE_COORDS = [12.8716, 80.2201];

// --- ICONS ---
const busMarkerIcon = L.divIcon({
    html: `<div style="background: #e74c3c; width: 16px; height: 16px; border-radius: 50%; border: 2px solid white; box-shadow: 0 0 10px rgba(0,0,0,0.3);"></div>`,
    className: '',
    iconSize: [16, 16]
});

const studentMarkerIcon = L.divIcon({
    html: `<div style="background: #3498db; width: 14px; height: 14px; border-radius: 50%; border: 2px solid white; box-shadow: 0 0 10px rgba(52,152,219,0.5);"></div>`,
    className: '',
    iconSize: [14, 14]
});

// Coordinate Safety Check
const isPointValid = (lat, lon) => {
    return (lat !== undefined && lon !== undefined && lat !== null && lat !== 0);
};

// --- HELPER: MAP RECENTER ---
function RecenterMap({ coords }) {
    const map = useMap();
    useEffect(() => {
        if (isPointValid(coords.lat, coords.lon)) {
            map.setView([coords.lat, coords.lon], 14);
        }
    }, [coords, map]);
    return null;
}

function DriverDashboard() {
    const [tracking, setTracking] = useState(false);
    const [coords, setCoords] = useState({ lat: null, lon: null, speed: 0 });
    const [trafficIndex, setTrafficIndex] = useState(0.4);
    const [occupancy, setOccupancy] = useState(0);
    const [routeInfo, setRouteInfo] = useState({ all_active_stops: [], next_stop: null });
    const watchId = useRef(null);
    const coordsRef = useRef({ lat: null, lon: null, speed: 0 });

    const driver = JSON.parse(localStorage.getItem('user')) || {};
    const driverName = driver.username || 'Driver';
    const busId = driver.bus_id || 'SJIT_BUS_10';

    // --- SEND LOCATION (Heartbeat) ---
    const sendLocationToBackend = useCallback((lat, lon, speed) => {
        axios.post(`${BACKEND_URL}/update_location`, {
            bus_id: busId,
            driver_name: driverName,
            latitude: lat,
            longitude: lon,
            speed: parseFloat(speed),
            traffic_index: trafficIndex
        }).catch(() => console.log("Update failed"));
    }, [trafficIndex, driverName, busId]);

    // Use ref to avoid fetchAllData depending on coords state (prevents interval stacking)
    const fetchAllData = useCallback(() => {
        axios.get(`${BACKEND_URL}/api/driver_route_info`)
            .then(res => setRouteInfo(res.data))
            .catch(() => {});
        axios.get(`${BACKEND_URL}/api/bus_status?username=${driverName}`)
            .then(res => setOccupancy(res.data.occupancy || 0))
            .catch(() => {});
        const c = coordsRef.current;
        if (tracking && c.lat && c.lon) {
            sendLocationToBackend(c.lat, c.lon, c.speed);
        }
    }, [tracking, sendLocationToBackend, driverName]);

    useEffect(() => {
        fetchAllData();
        const interval = setInterval(fetchAllData, 4000);
        return () => clearInterval(interval);
    }, [fetchAllData]);

    const startTracking = () => {
        if (!navigator.geolocation) return;
        setTracking(true);
        watchId.current = navigator.geolocation.watchPosition(
            (pos) => {
                const speedKmh = pos.coords.speed ? (pos.coords.speed * 3.6).toFixed(1) : 0;
                const newCoords = { lat: pos.coords.latitude, lon: pos.coords.longitude, speed: speedKmh };
                coordsRef.current = newCoords;
                setCoords(newCoords);
                sendLocationToBackend(pos.coords.latitude, pos.coords.longitude, speedKmh);
            },
            () => setTracking(false),
            { enableHighAccuracy: true, timeout: 15000 }
        );
    };

    const stopTracking = () => {
        if (watchId.current) navigator.geolocation.clearWatch(watchId.current);
        setTracking(false);
        coordsRef.current = { lat: null, lon: null, speed: 0 };
        setCoords({ lat: null, lon: null, speed: 0 });
    };

    return (
        <div style={styles.container}>
            <header style={{textAlign: 'center', marginBottom: '10px'}}>
                <h2 style={{margin:0}}>Driver: {driverName}</h2>
                <small style={{color: '#999'}}>Control Console | {busId}</small>
            </header>

            {/* --- MAP --- */}
            <div style={styles.mapBox}>
                <MapContainer center={COLLEGE_COORDS} zoom={13} style={{ height: '100%', width: '100%' }}>
                    <TileLayer url="https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png" />
                    
                    {/* BUS */}
                    {isPointValid(coords.lat, coords.lon) && (
                        <Marker position={[coords.lat, coords.lon]} icon={busMarkerIcon}>
                            <Popup>My Bus</Popup>
                        </Marker>
                    )}

                    {/* STUDENTS */}
                    {routeInfo.all_active_stops.map((stop, i) => (
                        isPointValid(stop.lat, stop.lon) && (
                            <Marker key={i} position={[stop.lat, stop.lon]} icon={studentMarkerIcon}>
                                <Popup><strong>{stop.name}</strong>: {stop.count} student(s)</Popup>
                            </Marker>
                        )
                    ))}

                    <RecenterMap coords={coords} />
                </MapContainer>
            </div>

            <div style={styles.content}>
                
                {/* NEXT STOP BANNER (CITY NAME) */}
                {routeInfo.next_stop ? (
                    <div style={styles.nextStopCard}>
                        <small style={{fontWeight:'bold', letterSpacing:'1px'}}>📍 NEXT PICKUP STOP</small>
                        <h2 style={{margin:'5px 0', fontSize: '26px'}}>{routeInfo.next_stop.name}</h2>
                        <div style={{fontSize:'14px', opacity: 0.8}}>
                            <strong>{routeInfo.next_stop.count}</strong> student(s) waiting
                            <span style={{marginLeft:'10px'}}>| {(routeInfo.next_stop.dist/1000).toFixed(1)} km away</span>
                        </div>
                    </div>
                ) : (
                    <div style={styles.emptyCard}>No students currently checked-in.</div>
                )}

                {/* STATS */}
                <div style={styles.statusCard}>
                    <div style={styles.statGrid}>
                        <div style={styles.statItem}>
                            <small>SPEED</small>
                            <div style={styles.bigNum}>{coords.speed} km/h</div>
                        </div>
                        <div style={styles.statItem}>
                            <small>CAPACITY</small>
                            <div style={styles.bigNum}>{occupancy}/40</div>
                        </div>
                    </div>
                </div>

                {/* TRAFFIC */}
                <div style={styles.card}>
                    <label style={{fontSize:'13px', fontWeight:'bold'}}>Traffic Intensity (T): {trafficIndex}</label>
                    <input type="range" min="0" max="1" step="0.1" value={trafficIndex} onChange={(e) => setTrafficIndex(parseFloat(e.target.value))} style={{ width: '100%', marginTop: '10px' }} />
                </div>

                {/* BOARDING BUTTONS */}
                <div style={styles.flexGap}>
                    <button onClick={() => {
                        axios.post(`${BACKEND_URL}/api/update_occupancy`, {action:'in'})
                            .then(res => {
                                if (res.data.onboarded) alert(`✅ ${res.data.onboarded} has been onboarded!`);
                            });
                    }} style={styles.btnIn}>BOARDED (+)</button>
                    <button onClick={() => axios.post(`${BACKEND_URL}/api/update_occupancy`, {action:'out'})} style={styles.btnOut}>EXITED (-)</button>
                </div>

                {!tracking ? (
                    <button onClick={startTracking} style={styles.btnStart}>START TRIP</button>
                ) : (
                    <button onClick={stopTracking} style={styles.btnStop}>STOP TRIP</button>
                )}

                {/* PICKUP QUEUE */}
                <div style={{...styles.card, marginTop: '20px'}}>
                    <h4 style={{margin:'0 0 10px 0', fontSize:'14px'}}>Waiting Pickup Queue:</h4>
                    {routeInfo.all_active_stops.length > 0 ? routeInfo.all_active_stops.map((stop, i) => (
                        <div key={i} style={styles.queueRow}>
                            <span><strong>{stop.name}</strong></span>
                            <span style={{color:'#2ecc71', fontWeight:'bold'}}>{stop.count} Waiting</span>
                        </div>
                    )) : <p style={{fontSize:'11px', color:'#999'}}>The queue is empty.</p>}
                </div>
            </div>
        </div>
    );
}

const styles = {
    container: { maxWidth: '480px', margin: '0 auto', background: '#f4f7f6', minHeight: '100vh', fontFamily: 'Segoe UI, sans-serif' },
    mapBox: { height: '30vh', width: '100%', borderBottom: '1px solid #ddd' },
    content: { padding: '15px' },
    nextStopCard: { background: '#fab005', padding: '15px', borderRadius: '12px', color: '#2c3e50', marginBottom: '15px', boxShadow: '0 4px 8px rgba(0,0,0,0.1)' },
    emptyCard: { textAlign: 'center', padding: '15px', background: '#fff', borderRadius: '12px', marginBottom: '15px', border: '1px dashed #ccc', color: '#7f8c8d', fontSize: '13px' },
    statusCard: { background: 'white', padding: '15px', borderRadius: '12px', marginBottom: '15px', boxShadow: '0 2px 5px rgba(0,0,0,0.05)' },
    statGrid: { display: 'flex', justifyContent: 'space-around' },
    statItem: { textAlign: 'center' },
    bigNum: { fontSize: '24px', fontWeight: 'bold', color: '#2980b9' },
    card: { background: '#fff', padding: '15px', borderRadius: '12px', marginBottom: '15px', boxShadow: '0 2px 5px rgba(0,0,0,0.05)' },
    flexGap: { display: 'flex', gap: '10px', marginBottom: '15px' },
    btnIn: { flex: 1, padding: '12px', background: '#2ecc71', color: '#fff', border: 'none', borderRadius: '8px', fontWeight: 'bold', cursor: 'pointer' },
    btnOut: { flex: 1, padding: '12px', background: '#e67e22', color: '#fff', border: 'none', borderRadius: '8px', fontWeight: 'bold', cursor: 'pointer' },
    btnStart: { width: '100%', padding: '15px', background: '#3498db', color: '#fff', border: 'none', borderRadius: '10px', fontSize: '18px', fontWeight: 'bold', cursor: 'pointer' },
    btnStop: { width: '100%', padding: '15px', background: '#e74c3c', color: '#fff', border: 'none', borderRadius: '10px', fontSize: '18px', fontWeight: 'bold', cursor: 'pointer' },
    queueRow: { display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #eee', fontSize: '13px' }
};

export default DriverDashboard;