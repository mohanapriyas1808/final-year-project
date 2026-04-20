import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import icon from 'leaflet/dist/images/marker-icon.png';
import iconShadow from 'leaflet/dist/images/marker-shadow.png';

L.Marker.prototype.options.icon = L.icon({ iconUrl: icon, shadowUrl: iconShadow, iconSize: [25, 41], iconAnchor: [12, 41] });

const BACKEND_URL = `http://${window.location.hostname}:5000`;
const DEFAULT_CENTER = [12.8716, 80.2201];

const busIcon = L.divIcon({
    className: '',
    html: `<div style="background:#e74c3c;width:40px;height:40px;border-radius:50%;border:3px solid #fff;box-shadow:0 0 0 3px #e74c3c,0 4px 10px rgba(0,0,0,0.3);display:flex;align-items:center;justify-content:center;font-size:22px;">🚌</div>`,
    iconSize: [40, 40],
    iconAnchor: [20, 20]
});

const NAV = [
    { label: 'Dashboard', icon: '📊', key: 'dashboard' },
    { label: 'Bus Drivers', icon: '🧑‍✈️', key: 'drivers' },
    { label: 'Track Buses', icon: '🚌', key: 'track' },
    { label: 'Students', icon: '🎓', key: 'students' },
];

export default function AdminDashboard() {
    const navigate = useNavigate();
    const [active, setActive] = useState('track');
    const [drivers, setDrivers] = useState([]);
    const [students, setStudents] = useState([]);
    const [selected, setSelected] = useState('');
    const [busFilter, setBusFilter] = useState('');
    const [stats, setStats] = useState({ drivers: 0, students: 0, active: 0 });

    useEffect(() => {
        const user = JSON.parse(localStorage.getItem('user'));
        if (!user || user.role !== 'admin') navigate('/login');
    }, [navigate]);

    useEffect(() => {
        const fetch = () => {
            axios.get(`${BACKEND_URL}/api/admin/drivers`).then(r => {
                setDrivers(r.data.drivers || []);
                setStats(s => ({ ...s, drivers: r.data.drivers.length, active: r.data.drivers.filter(d => d.status === 'Active').length }));
            }).catch(() => {});
            axios.get(`${BACKEND_URL}/api/admin/students`).then(r => {
                setStudents(r.data.students || []);
                setStats(s => ({ ...s, students: r.data.students.length }));
            }).catch(() => {});
        };
        fetch();
        const id = setInterval(fetch, 3000);
        return () => clearInterval(id);
    }, []);

    const logout = () => { localStorage.removeItem('user'); navigate('/login'); };

    const visibleDrivers = selected ? drivers.filter(d => d.username === selected) : drivers;
    const mapCenter = visibleDrivers.length && visibleDrivers[0].lat ? [visibleDrivers[0].lat, visibleDrivers[0].lon] : DEFAULT_CENTER;

    return (
        <div style={s.shell}>
            {/* SIDEBAR */}
            <aside style={s.sidebar}>
                <div style={s.logo}>🚍<br /><span style={s.adminLabel}>Admin</span></div>
                <div style={s.navGroup}>
                    <div style={s.navTitle}>Main</div>
                    {NAV.map(n => (
                        <div key={n.key} onClick={() => setActive(n.key)}
                            style={{ ...s.navItem, ...(active === n.key ? s.navActive : {}) }}>
                            <span style={s.navIcon}>{n.icon}</span>{n.label}
                        </div>
                    ))}
                </div>
                <div style={s.navGroup}>
                    <div style={s.navTitle}>Settings</div>
                    <div onClick={logout} style={s.navItem}><span style={s.navIcon}>⏻</span>Logout</div>
                </div>
            </aside>

            {/* MAIN */}
            <main style={s.main}>
                {active === 'dashboard' && (
                    <div>
                        <h2 style={s.pageTitle}>Dashboard</h2>
                        <div style={s.statsRow}>
                            <div style={s.statCard}><div style={s.statNum}>{stats.drivers}</div><div style={s.statLbl}>Total Drivers</div></div>
                            <div style={s.statCard}><div style={s.statNum}>{stats.active}</div><div style={s.statLbl}>Active Buses</div></div>
                            <div style={s.statCard}><div style={s.statNum}>{stats.students}</div><div style={s.statLbl}>Students</div></div>
                        </div>
                    </div>
                )}

                {active === 'track' && (
                    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                        <div style={s.trackHeader}>
                            <h2 style={s.pageTitle}>Track Buses</h2>
                            <select style={s.select} value={selected} onChange={e => setSelected(e.target.value)}>
                                <option value="">Select Driver</option>
                                {drivers.map(d => <option key={d.username} value={d.username}>{d.username}</option>)}
                            </select>
                        </div>
                        <div style={s.mapWrap}>
                            <MapContainer center={mapCenter} zoom={12} style={{ height: '100%', width: '100%' }}>
                                <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
                                {visibleDrivers.filter(d => d.lat && d.lon).map(d => (
                                    <Marker key={d.username} position={[d.lat, d.lon]} icon={busIcon}>
                                        <Popup>
                                            <b>{d.username}</b><br />
                                            Bus: {d.bus_id || 'N/A'}<br />
                                            Status: {d.status || 'Offline'}<br />
                                            Speed: {d.speed || 0} km/h
                                        </Popup>
                                    </Marker>
                                ))}
                            </MapContainer>
                        </div>
                    </div>
                )}

                {active === 'drivers' && (
                    <div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
                            <h2 style={s.pageTitle}>Bus Drivers</h2>
                            <select style={s.select} value={busFilter} onChange={e => setBusFilter(e.target.value)}>
                                <option value="">All Bus IDs</option>
                                {[...new Set(drivers.map(d => d.bus_id).filter(b => b && b !== '—'))].map(bid => (
                                    <option key={bid} value={bid}>{bid}</option>
                                ))}
                            </select>
                        </div>
                        <table style={s.table}>
                            <thead><tr>{['Name', 'Bus ID', 'Starting Point', 'Status', 'Reached College'].map(h => <th key={h} style={s.th}>{h}</th>)}</tr></thead>
                            <tbody>
                                {drivers
                                    .filter(d => !busFilter || d.bus_id === busFilter)
                                    .map(d => (
                                    <tr key={d.username}>
                                        <td style={s.td}>{d.username}</td>
                                        <td style={s.td}>{d.bus_id || '—'}</td>
                                        <td style={s.td}>{d.starting_point || '—'}</td>
                                        <td style={s.td}><span style={{ ...s.badge, background: d.status === 'Active' ? '#2ecc71' : '#e74c3c' }}>{d.status || 'Offline'}</span></td>
                                        <td style={s.td}><span style={{ ...s.badge, background: d.reached_college ? '#2ecc71' : '#e67e22' }}>{d.reached_college ? 'Yes' : 'No'}</span></td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}

                {active === 'students' && (
                    <div>
                        <h2 style={s.pageTitle}>Students</h2>
                        <table style={s.table}>
                            <thead><tr>{['Name', 'Email', 'Boarding Point', 'Waiting'].map(h => <th key={h} style={s.th}>{h}</th>)}</tr></thead>
                            <tbody>
                                {students.map(st => (
                                    <tr key={st.username}>
                                        <td style={s.td}>{st.username}</td>
                                        <td style={s.td}>{st.email || '—'}</td>
                                        <td style={s.td}>{st.boarding_point || '—'}</td>
                                        <td style={s.td}><span style={{ ...s.badge, background: st.is_waiting ? '#2ecc71' : '#bdc3c7' }}>{st.is_waiting ? 'Yes' : 'No'}</span></td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </main>
        </div>
    );
}

const s = {
    shell: { display: 'flex', height: '100vh', fontFamily: 'Segoe UI, sans-serif', background: '#f4f7f9' },
    sidebar: { width: '220px', background: '#fff', boxShadow: '2px 0 8px rgba(0,0,0,0.06)', display: 'flex', flexDirection: 'column', padding: '20px 0' },
    logo: { textAlign: 'center', fontSize: '40px', padding: '10px 0 20px', borderBottom: '1px solid #f0f0f0' },
    adminLabel: { fontSize: '14px', fontWeight: 'bold', color: '#2c3e50' },
    navGroup: { padding: '15px 0 5px' },
    navTitle: { fontSize: '11px', color: '#3498db', fontWeight: 'bold', padding: '0 20px 8px', textTransform: 'uppercase', letterSpacing: '1px' },
    navItem: { display: 'flex', alignItems: 'center', padding: '10px 20px', cursor: 'pointer', color: '#555', fontSize: '14px', borderRadius: '0 8px 8px 0', marginRight: '10px' },
    navActive: { background: '#eaf4fd', color: '#3498db', fontWeight: 'bold' },
    navIcon: { marginRight: '10px', fontSize: '16px' },
    main: { flex: 1, padding: '25px', overflowY: 'auto' },
    pageTitle: { margin: '0 0 20px', color: '#2c3e50', fontSize: '22px' },
    statsRow: { display: 'flex', gap: '20px' },
    statCard: { background: '#fff', borderRadius: '12px', padding: '25px 35px', boxShadow: '0 2px 8px rgba(0,0,0,0.06)', textAlign: 'center' },
    statNum: { fontSize: '36px', fontWeight: 'bold', color: '#3498db' },
    statLbl: { fontSize: '13px', color: '#7f8c8d', marginTop: '5px' },
    trackHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' },
    select: { padding: '8px 14px', borderRadius: '8px', border: '1px solid #ddd', fontSize: '14px', minWidth: '180px' },
    mapWrap: { flex: 1, borderRadius: '12px', overflow: 'hidden', minHeight: '500px' },
    table: { width: '100%', borderCollapse: 'collapse', background: '#fff', borderRadius: '12px', overflow: 'hidden', boxShadow: '0 2px 8px rgba(0,0,0,0.06)' },
    th: { background: '#f8f9fa', padding: '12px 16px', textAlign: 'left', fontSize: '13px', color: '#7f8c8d', fontWeight: '600', borderBottom: '1px solid #eee' },
    td: { padding: '12px 16px', fontSize: '14px', color: '#2c3e50', borderBottom: '1px solid #f8f9fa' },
    badge: { color: '#fff', padding: '3px 10px', borderRadius: '12px', fontSize: '12px', fontWeight: 'bold' },
};
