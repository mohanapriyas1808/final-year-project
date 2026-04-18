import React, { useState } from 'react';
import axios from 'axios';
import { useNavigate, Link } from 'react-router-dom';

// Use window.location.hostname to find your backend IP automatically
const BACKEND_URL = `http://${window.location.hostname}:5000`;

function Signup() {
    const [formData, setFormData] = useState({ 
        username: '', 
        email: '',
        password: '', 
        role: 'student',    
        boarding_point: '', 
        parent_name: '',    
        parent_mobile: '',
        lat: null, 
        lon: null,
        bus_id: '',
        starting_point: ''
    });
    const [gpsStatus, setGpsStatus] = useState("");
    const navigate = useNavigate();

    // TRIGGER: Captures the student's exact GPS location for personalized ETA
    const captureLocation = () => {
        setGpsStatus("Capturing...");
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    setFormData({
                        ...formData,
                        lat: position.coords.latitude,
                        lon: position.coords.longitude
                    });
                    setGpsStatus("✅ Location Captured!");
                },
                (error) => {
                    alert("Error: Please enable GPS/Location permissions in your browser.");
                    setGpsStatus("❌ Failed");
                },
                { enableHighAccuracy: true }
            );
        } else {
            alert("Geolocation is not supported by your browser.");
        }
    };

    const handleSignup = async (e) => {
        e.preventDefault();
        
        // Validation for Students
        if (formData.role === 'student') {
            if (!formData.lat) {
                alert("Please click 'Capture My Location' so the bus knows where to find you!");
                return;
            }
            if (!formData.email.includes("@")) {
                alert("Please enter a valid email address for notifications.");
                return;
            }
        }

        // Validation for Drivers
        if (formData.role === 'driver') {
            if (!formData.bus_id.trim()) {
                alert("Please enter your Bus ID.");
                return;
            }
            if (!formData.starting_point.trim()) {
                alert("Please enter your starting boarding point.");
                return;
            }
        }

        try {
            const res = await axios.post(`${BACKEND_URL}/api/signup`, formData);
            if (res.status === 201) {
                alert("Registration Successful!");
                navigate('/login');
            }
        } catch (err) {
            alert("Error: " + (err.response?.data?.message || "Registration failed. Try again."));
        }
    };

    return (
        <div style={styles.container}>
            <form onSubmit={handleSignup} style={styles.card}>
                <h2 style={{ textAlign: 'center', color: '#2c3e50', marginBottom: '5px' }}>Smart Bus System</h2>
                <p style={{ textAlign: 'center', color: '#7f8c8d', fontSize: '14px', marginBottom: '20px' }}>Join the tracking network</p>
                
                <label style={styles.label}>I am registering as a:</label>
                <select 
                    value={formData.role} 
                    onChange={e => setFormData({...formData, role: e.target.value})} 
                    style={styles.input}
                >
                    <option value="student">Student</option>
                    <option value="driver">Bus Driver</option>
                    <option value="admin">Admin</option>
                </select>

                <input 
                    placeholder="User's Full Name" 
                    onChange={e => setFormData({...formData, username: e.target.value})} 
                    style={styles.input} 
                    required 
                />

                <input 
                    type="email"
                    placeholder="Personal Email Address" 
                    onChange={e => setFormData({...formData, email: e.target.value})} 
                    style={styles.input} 
                    required 
                />
                
                <input 
                    type="password" 
                    placeholder="Create Password" 
                    onChange={e => setFormData({...formData, password: e.target.value})} 
                    style={styles.input} 
                    required 
                />
                
                {/* CONDITIONAL FIELDS for Students Only */}
                {formData.role === 'student' && (
                    <div style={{ borderTop: '1px solid #eee', marginTop: '10px', paddingTop: '15px' }}>
                        
                        <label style={styles.label}>Location-Based Setup:</label>
                        <button 
                            type="button" 
                            onClick={captureLocation} 
                            style={styles.gpsButton}
                        >
                            📍 {formData.lat ? "Update Boarding Location" : "Capture My Location"}
                        </button>
                        <center><small style={{color: '#27ae60', fontWeight: 'bold'}}>{gpsStatus}</small></center>

                        <input 
                            type="text"
                            placeholder="Boarding Point Name (e.g. Tiruvanmiyur)" 
                            onChange={e => setFormData({...formData, boarding_point: e.target.value})} 
                            style={styles.input} 
                            required 
                        />

                        <input 
                            placeholder="Parent/Guardian Name" 
                            onChange={e => setFormData({...formData, parent_name: e.target.value})} 
                            style={styles.input} 
                            required 
                        />
                        
                        <input 
                            placeholder="Guardian Mobile Number" 
                            onChange={e => setFormData({...formData, parent_mobile: e.target.value})} 
                            style={styles.input} 
                            required 
                        />
                    </div>
                )}

                {/* CONDITIONAL FIELDS for Drivers Only */}
                {formData.role === 'driver' && (
                    <div style={{ borderTop: '1px solid #eee', marginTop: '10px', paddingTop: '15px' }}>
                        <input 
                            type="text"
                            placeholder="Bus ID (e.g. SJIT_BUS_10)" 
                            onChange={e => setFormData({...formData, bus_id: e.target.value})} 
                            style={styles.input} 
                            required 
                        />
                        <input 
                            type="text"
                            placeholder="Starting Boarding Point (e.g. Tambaram)" 
                            onChange={e => setFormData({...formData, starting_point: e.target.value})} 
                            style={styles.input} 
                            required 
                        />
                    </div>
                )}

                <button type="submit" style={styles.button}>
                    Register as {formData.role.charAt(0).toUpperCase() + formData.role.slice(1)}
                </button>
                
                <p style={{ textAlign: 'center', marginTop: '15px', fontSize: '14px' }}>
                    Already have an account? <Link to="/login" style={{ color: '#3498db', textDecoration: 'none' }}>Login</Link>
                </p>
            </form>
        </div>
    );
}

const styles = {
    container: { display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: '#f4f7f6', padding: '20px' },
    card: { background: 'white', padding: '30px', borderRadius: '15px', boxShadow: '0 8px 20px rgba(0,0,0,0.1)', width: '100%', maxWidth: '400px' },
    input: { width: '100%', padding: '12px', margin: '8px 0', borderRadius: '8px', border: '1px solid #ddd', boxSizing: 'border-box', fontSize: '14px' },
    gpsButton: { width: '100%', padding: '10px', background: '#9b59b6', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', marginBottom: '5px', fontWeight: 'bold' },
    button: { width: '100%', padding: '14px', background: '#3498db', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontWeight: 'bold', fontSize: '16px', marginTop: '15px' },
    label: { fontSize: '12px', color: '#7f8c8d', fontWeight: 'bold', display: 'block', marginBottom: '4px' }
};

export default Signup;