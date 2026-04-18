import React, { useEffect, useState, useRef } from 'react';
import axios from 'axios';
import { MapContainer, TileLayer, Marker, Polyline, Circle, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// --- LEAFLET ASSET FIX ---
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
const HARDCODED_STOPS = {
    "thiruvanmiyur (start)": [12.9830, 80.2594],
    "palavakkam":            [12.9564, 80.2508],
    "chinna neelankarai":    [12.9525, 80.2505],
    "neelankarai (ecr)":     [12.9497, 80.2500],
    "vettuvankani":          [12.9360, 80.2485],
    "injambakkam":           [12.9190, 80.2460],
    "akkarai (link road)":   [12.8913, 80.2392],
    "sholinganallur (omr)":  [12.8961, 80.2310],
    "sjit college gate":     [12.8716, 80.2201],
};
const BACKEND_URL = `http://${window.location.hostname}:5000`;
const COLLEGE_GATE = [12.8716, 80.2201];
const busIcon = L.divIcon({ 
    className: 'bus-ping', 
    html: `🚍<div class="ping"></div>`, 
    iconSize: [30, 30] 
});

const isPointValid = (lat, lon) => {
    return (lat !== undefined && lon !== undefined && lat !== null && lat !== null && lat !== 0 && lon !== 0);
};

// Helper to center map on bus
function RecenterMap({ lat, lon }) {
    const map = useMap();
    useEffect(() => { 
        if (isPointValid(lat, lon)) map.setView([lat, lon], 14); 
    }, [lat, lon, map]);
    return null;
}

function Dashboard() {
    // Current Student: Priya
    const user = JSON.parse(localStorage.getItem('user')) || { username: "Priya", boarding_point: "Palavakkam" };
    
    const [bus, setBus] = useState({ 
        lat: COLLEGE_GATE[0], lon: COLLEGE_GATE[1], speed: 0, 
        upcoming_stops: [], route_path: [], driver_status: "Offline", 
        occupancy: 0, weather: "Sunny", delay_mins: 0,
        user_lat: COLLEGE_GATE[0], user_lon: COLLEGE_GATE[1], eta: 0
    });

    const [dataReady, setDataReady] = useState(false);
    const [isWaiting, setIsWaiting] = useState(false); 
    const [walkTime, setWalkTime] = useState(5); 
    const watchId = useRef(null);
    const isWaitingRef = useRef(false);

    // 1. POLLING: Get Live Bus Data every 2 seconds
    useEffect(() => {
        const fetchData = () => {
            axios.get(`${BACKEND_URL}/api/bus_status?username=${user.username}`)
                .then(res => {
                    const d = res.data;
                    setBus({
                        ...d,
                        lat: Number(d.lat) || COLLEGE_GATE[0],
                        lon: Number(d.lon) || COLLEGE_GATE[1],
                        user_lat: Number(d.user_lat) || COLLEGE_GATE[0],
                        user_lon: Number(d.user_lon) || COLLEGE_GATE[1],
                        route_path: Array.isArray(d.route_path) ? d.route_path : []
                    });
                    setDataReady(true);
                })
                .catch(e => console.error("Syncing..."));
        };
        fetchData();
        const interval = setInterval(fetchData, 2000);
        return () => clearInterval(interval);
    }, [user.username]);

    // Cleanup: reset waiting status if user closes/refreshes the tab
    useEffect(() => {
        const handleUnload = () => {
            navigator.sendBeacon(`${BACKEND_URL}/api/student_status`,
                new Blob([JSON.stringify({ username: user.username, is_waiting: false })], { type: 'application/json' })
            );
        };
        window.addEventListener('beforeunload', handleUnload);
        return () => window.removeEventListener('beforeunload', handleUnload);
    }, [user.username]);

    // 2. LIVE LOCATION SHARING LOGIC — only manages GPS, DB writes handled by button
    useEffect(() => {
        if (!isWaiting) {
            if (watchId.current) {
                navigator.geolocation.clearWatch(watchId.current);
                watchId.current = null;
            }
            return;
        }

        // Start GPS and keep sending location updates while waiting
        watchId.current = navigator.geolocation.watchPosition(
            (pos) => {
                if (!isWaitingRef.current) return; // stopped — don't overwrite false
                axios.post(`${BACKEND_URL}/api/student_status`, {
                    username: user.username,
                    is_waiting: true,
                    lat: pos.coords.latitude,
                    lon: pos.coords.longitude
                });
            },
            (err) => console.error(err),
            { enableHighAccuracy: true }
        );

        return () => {
            if (watchId.current) {
                navigator.geolocation.clearWatch(watchId.current);
                watchId.current = null;
            }
        };
    }, [isWaiting, user.username]);

    // 3. Find specific Stop in the sequence — exact match only
    const myStop = user.boarding_point?.trim().toLowerCase();
    const isMyStop = (name) => name.trim().toLowerCase() === myStop;
    const myStopData = bus.upcoming_stops.find(s => isMyStop(s.name));

    const handleWaitingToggle = () => {
        const newVal = !isWaitingRef.current;
        isWaitingRef.current = newVal;
        setIsWaiting(newVal);
        console.log('Button clicked, sending is_waiting:', newVal, 'for user:', user.username);
        fetch(`${BACKEND_URL}/api/student_status`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: user.username, is_waiting: newVal })
        })
        .then(r => r.json())
        .then(d => console.log('DB response:', d))
        .catch(e => console.error('FAILED:', e));
    };

    const handleSOS = () => {
        if (window.confirm("🚨 Trigger Emergency SOS? This will alert your parents.")) {
            axios.post(`${BACKEND_URL}/api/sos_alert`, { username: user.username, boarding_point: user.boarding_point })
            .then(() => alert("SOS Sent Successfully!"));
        }
    };

    return (
        <div style={styles.container}>
            {/* --- TOP BAR CONTROL PANEL --- */}
            <header style={styles.topBar}>
                <div>
                    <h2 style={{margin:0, color: '#2c3e50'}}>Student Control Panel</h2>
                    <p style={{margin:0, color: '#2980b9', fontWeight: 'bold'}}>
                        Welcome, {user.username} 👋 
                        <span style={{color: '#95a5a6', fontWeight: 'normal', marginLeft: '10px'}}>
                            | Assigned Stop: {user.boarding_point}
                        </span>
                    </p>
                </div>
                
                <div style={styles.headerStats}>
                    <div style={{textAlign: 'right', marginRight: '20px'}}>
                        <small style={{display: 'block', color: '#95a5a6', fontSize: '10px'}}>BUS TRACKER STATUS</small>
                        <span style={{color: bus.driver_status === 'Active' ? '#2ecc71' : '#e74c3c', fontWeight:'bold'}}>
                            ● {bus.driver_name || 'Driver'} ({bus.driver_status || 'Offline'})
                        </span>
                        <div style={{fontSize: '11px', color: '#7f8c8d', marginTop: '2px'}}>
                            {bus.driver_status === 'Active' ? '🟢 In Transit' : '🔴 Not Started'} | Bus: {bus.bus_id || '—'}
                        </div>
                    </div>
                    <button onClick={handleSOS} style={styles.sosBtn}>🚨 SOS</button>
                </div>
            </header>

            <div style={styles.grid}>
                {/* --- COLUMN 1: LIVE TELEMETRY --- */}
                <aside style={styles.leftCol}>
                    <div style={{...styles.card, background: bus.delay_mins > 0 ? '#ff4757' : '#2ecc71', color: '#fff'}}>
                        <small>SCHEDULE STATUS</small>
                        <h3 style={{margin: '5px 0'}}>{bus.delay_mins > 0 ? `Delayed ${bus.delay_mins}m` : "On Time"}</h3>
                    </div>

                    <div style={styles.card}>
                        <small>REAL-TIME SPEED</small>
                        <h2 style={{margin: '5px 0'}}>{bus.speed} <small style={{fontSize:'14px'}}>km/h</small></h2>
                    </div>

                    <div style={styles.card}>
                        <small>BUS OCCUPANCY</small>
                        <div style={styles.progressBase}><div style={{...styles.progressFill, width: `${(bus.occupancy/40)*100}%`, background: bus.occupancy > 35 ? '#ff4757' : '#2ecc71'}}></div></div>
                        <p style={{fontSize:'12px', marginTop:'5px'}}>{bus.occupancy}/40 Seats filled</p>
                    </div>

                    <div style={styles.card}>
                        <small>WALKING ASSISTANT</small>
                        <div style={{margin: '10px 0'}}>
                            <input type="number" value={walkTime} onChange={e => setWalkTime(e.target.value)} style={styles.input} /> <small>min walk to stop</small>
                        </div>
        <button onClick={handleWaitingToggle} style={{...styles.waitBtn, background: isWaiting ? '#ff4757' : '#3498db'}}>
                            {isWaiting ? "🔴 STOP SHARING" : "🟢 I'M AT THE STOP"}
                        </button>
                    </div>
                </aside>

                {/* --- COLUMN 2: STOP SCHEDULE --- */}
                <main style={styles.middleCol}>
                    <h4 style={styles.sectionTitle}>🎯 YOUR PERSONALIZED ETA</h4>
                    {myStopData ? (
                        <div style={styles.highlightCard}>
                            <small>TIME TO ARRIVAL AT {myStopData.name.toUpperCase()}</small>
                            <h1 style={styles.bigEta}>{myStopData.eta} <span style={{fontSize: '20px'}}>mins</span></h1>
                            <div style={styles.distTag}>{ (myStopData.dist/1000).toFixed(1) } km away</div>
                        </div>
                    ) : (
                        <div style={styles.passedCard}>
                            {bus.driver_status === 'Active' ? "Bus has passed your stop." : "Waiting for trip to start..."}
                        </div>
                    )}

                    <h4 style={{...styles.sectionTitle, marginTop: '30px'}}>🗺️ FULL ROUTE PROGRESS</h4>
                    <div style={styles.stopList}>
                        {bus.upcoming_stops.map((stop, i) => (
                            <div key={i} style={{
                                ...styles.stopRow, 
                                backgroundColor: isMyStop(stop.name) ? '#e3f2fd' : 'transparent',
                                borderLeft: isMyStop(stop.name) ? '4px solid #3498db' : 'none'
                            }}>
                                <div style={{...styles.stopIndicator, background: isMyStop(stop.name) ? '#3498db' : '#bdc3c7'}}></div>
                                <div style={{...styles.stopName, fontWeight: isMyStop(stop.name) ? 'bold' : 'normal'}}>
                                    {stop.name}
                                </div>
                                {isMyStop(stop.name) && <div style={styles.liveTag}>YOU</div>}
                            </div>
                        ))}
                    </div>
                </main>

                {/* --- COLUMN 3: MAP VIEW --- */}
                <section style={styles.rightCol}>
                    <h4 style={styles.sectionTitle}>🗺️ LIVE POSITION</h4>
                    <div style={styles.mapFrame}>
                        {!dataReady ? (
                            <div style={styles.loader}>Initializing System...</div>
                        ) : (
                            <MapContainer center={COLLEGE_GATE} zoom={13} style={{height: '100%', width: '100%'}}>
                                <TileLayer url="https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png" />
                                {bus.route_path.length > 1 && <Polyline positions={bus.route_path} color="#3498db" weight={4} dashArray="5, 10" />}
                                
                                {isPointValid(bus.lat, bus.lon) && <Marker position={[bus.lat, bus.lon]} icon={busIcon} />}
                                
                                {isPointValid(bus.user_lat, bus.user_lon) && (
                                    <Marker position={[bus.user_lat, bus.user_lon]}>
                                        <Circle center={[bus.user_lat, bus.user_lon]} radius={300} pathOptions={{color: 'green', fillOpacity: 0.1}} />
                                    </Marker>
                                )}
                                <RecenterMap lat={bus.lat} lon={bus.lon} />
                            </MapContainer>
                        )}
                    </div>
                </section>
            </div>
            <style>{`.bus-ping{font-size:24px;position:relative}.ping{position:absolute;top:5px;left:5px;width:20px;height:20px;border:2px solid red;border-radius:50%;animation:pinger 1.5s infinite}@keyframes pinger{0%{transform:scale(1); opacity:1}100%{transform:scale(2.5); opacity:0}}`}</style>
        </div>
    );
}

const styles = {
    container: { height: '100vh', background: '#f4f7f9', padding: '15px', boxSizing: 'border-box', fontFamily: 'Segoe UI, sans-serif' },
    topBar: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#fff', padding: '15px 25px', borderRadius: '12px', marginBottom: '15px', boxShadow: '0 4px 6px rgba(0,0,0,0.02)' },
    headerStats: { display: 'flex', gap: '15px', alignItems: 'center' },
    sosBtn: { background: '#ff4757', color: 'white', border: 'none', padding: '8px 15px', borderRadius: '8px', cursor: 'pointer', fontWeight: 'bold' },
    grid: { display: 'grid', gridTemplateColumns: '240px 1.2fr 1fr', gap: '15px', height: 'calc(100vh - 120px)' },
    leftCol: { display: 'flex', flexDirection: 'column', gap: '15px' },
    card: { background: '#fff', padding: '15px', borderRadius: '12px', textAlign: 'center', boxShadow: '0 2px 4px rgba(0,0,0,0.04)' },
    progressBase: { background: '#eee', height: '6px', borderRadius: '3px', marginTop: '10px', overflow: 'hidden' },
    progressFill: { height: '100%', transition: '0.5s' },
    input: { width: '45px', padding: '5px', border: '1px solid #ddd', borderRadius: '5px' },
    waitBtn: { width: '100%', marginTop: '10px', padding: '10px', border: 'none', borderRadius: '8px', color: '#fff', fontWeight: 'bold', cursor: 'pointer', fontSize: '11px' },
    middleCol: { background: '#fff', padding: '20px', borderRadius: '12px', boxShadow: '0 2px 4px rgba(0,0,0,0.04)', overflowY: 'auto' },
    highlightCard: { background: 'linear-gradient(135deg, #3498db, #2980b9)', padding: '25px', borderRadius: '15px', color: '#fff', textAlign: 'center' },
    bigEta: { fontSize: '56px', margin: '10px 0' },
    distTag: { background: 'rgba(255,255,255,0.2)', display: 'inline-block', padding: '4px 12px', borderRadius: '20px', fontSize: '12px' },
    passedCard: { background: '#f8f9fa', padding: '30px', borderRadius: '15px', textAlign: 'center', color: '#95a5a6', border: '1px dashed #ddd' },
    sectionTitle: { margin: '0 0 10px 0', fontSize: '11px', color: '#95a5a6', textTransform: 'uppercase', letterSpacing: '1px' },
    stopRow: { display: 'flex', alignItems: 'center', padding: '12px 15px', borderBottom: '1px solid #f8f9fa' },
    stopIndicator: { width: '8px', height: '8px', borderRadius: '50%', marginRight: '15px' },
    stopName: { flex: 1, fontSize: '15px', color: '#2c3e50' },
    liveTag: { background: '#2ecc71', color: '#fff', padding: '2px 8px', borderRadius: '4px', fontSize: '10px', fontWeight: 'bold' },
    rightCol: { background: '#fff', padding: '15px', borderRadius: '12px', boxShadow: '0 2px 4px rgba(0,0,0,0.04)' },
    mapFrame: { height: 'calc(100% - 40px)', borderRadius: '10px', overflow: 'hidden', background: '#f8f9fa', display: 'flex', alignItems: 'center', justifyContent: 'center' },
    loader: { color: '#95a5a6', fontStyle: 'italic', fontSize: '14px' }
};

export default Dashboard;