import React, { useState } from 'react';
import axios from 'axios';
import { useNavigate, Link } from 'react-router-dom';

// This allows mobile phones on the same Wi-Fi to find your backend automatically
const BACKEND_URL = `http://${window.location.hostname}:5000`;

function Login() {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [loading, setLoading] = useState(false);
    const navigate = useNavigate();

    const handleLogin = async (e) => {
        e.preventDefault();
        setLoading(true);
        try {
            const res = await axios.post(`${BACKEND_URL}/api/login`, { username, password });
            
            if (res.data.status === "success") {
                const user = res.data.user;
                
                // Store user info (including role) in browser memory
                localStorage.setItem('user', JSON.stringify(user));
                
                // ROLE-BASED REDIRECTION
                if (user.role === 'admin') {
                    navigate('/admin');
                } else if (user.role === 'driver') {
                    navigate('/driver-dashboard');
                } else {
                    navigate('/dashboard');
                }
            }
        } catch (err) {
            console.error(err);
            alert(err.response?.data?.message || "Invalid credentials!");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div style={styles.container}>
            <form onSubmit={handleLogin} style={styles.card}>
                <h2 style={{ color: '#2c3e50', marginBottom: '10px' }}>Smart Bus Login</h2>
                <p style={{ color: '#7f8c8d', fontSize: '14px', marginBottom: '25px' }}>
                    Enter your credentials to continue
                </p>

                <input 
                    type="text" 
                    placeholder="Username" 
                    onChange={e => setUsername(e.target.value)} 
                    style={styles.input} 
                    required 
                />
                
                <input 
                    type="password" 
                    placeholder="Password" 
                    onChange={e => setPassword(e.target.value)} 
                    style={styles.input} 
                    required 
                />

                <button type="submit" style={styles.button} disabled={loading}>
                    {loading ? "Authenticating..." : "Login"}
                </button>

                <div style={{ marginTop: '20px', fontSize: '14px' }}>
                    New user? <Link to="/signup" style={{ color: '#3498db', textDecoration: 'none' }}>Create an account</Link>
                </div>
            </form>
        </div>
    );
}

const styles = {
    container: { 
        display: 'flex', 
        justifyContent: 'center', 
        alignItems: 'center', 
        height: '100vh', 
        background: '#f4f7f6' 
    },
    card: { 
        background: 'white', 
        padding: '40px', 
        borderRadius: '12px', 
        boxShadow: '0 10px 25px rgba(0,0,0,0.1)', 
        textAlign: 'center',
        width: '100%',
        maxWidth: '350px'
    },
    input: { 
        width: '100%', 
        padding: '12px', 
        margin: '10px 0', 
        borderRadius: '8px', 
        border: '1px solid #ddd', 
        boxSizing: 'border-box',
        fontSize: '14px'
    },
    button: { 
        width: '100%', 
        padding: '12px', 
        background: '#3498db', 
        color: 'white', 
        border: 'none', 
        borderRadius: '8px', 
        cursor: 'pointer',
        fontSize: '16px',
        fontWeight: 'bold',
        marginTop: '10px',
        transition: '0.3s'
    }
};

export default Login;