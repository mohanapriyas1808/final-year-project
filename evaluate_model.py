"""
Evaluates the existing trained XGBoost model and shows metrics.
Run on EC2: python3 evaluate_model.py
"""

import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import os

MODEL_FILE = 'bus_eta_model.json'
DATA_FILE  = 'smart_bus_data.csv'

print("=" * 50)
print("  SmartBus XGBoost Model Evaluation")
print("=" * 50)

# Load model
model = xgb.XGBRegressor()
model.load_model(MODEL_FILE)
print(f"\n[MODEL] Loaded: {MODEL_FILE}")

# Load data
if os.path.exists(DATA_FILE):
    df = pd.read_csv(DATA_FILE)
else:
    # Reproduce same synthetic data with same seed
    np.random.seed(42)
    n = 10000
    dist    = np.random.uniform(100, 15000, n)
    speed   = np.random.uniform(5, 60, n)
    hour    = np.random.randint(6, 22, n)
    dow     = np.random.randint(0, 7, n)
    traffic = np.random.uniform(0, 1, n)
    speed_mpm = np.maximum(speed, 5) * 1000 / 60
    eta = (dist / speed_mpm) * (1 + traffic * 0.5)
    noise = np.random.normal(0, 0.6, n)
    eta = np.clip(eta + noise, 0.5, 60)
    df = pd.DataFrame({
        'dist_to_stop': dist, 'current_speed': speed,
        'hour': hour, 'day_of_week': dow,
        'traffic_index': traffic, 'actual_eta': eta
    })

print(f"[DATA] {len(df)} records loaded")

X = df[['dist_to_stop', 'current_speed', 'hour', 'day_of_week', 'traffic_index']]
y = df['actual_eta']
_, X_test, _, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

predictions = model.predict(X_test)
rmse = np.sqrt(mean_squared_error(y_test, predictions))
mae  = mean_absolute_error(y_test, predictions)
r2   = r2_score(y_test, predictions)

print("\n" + "=" * 50)
print("  Model Performance Metrics")
print("=" * 50)
print(f"  RMSE     : {rmse:.2f} minutes")
print(f"  MAE      : {mae:.2f} minutes")
print(f"  R² Score : {r2:.4f}")
print("=" * 50)

# Sample prediction
sample = pd.DataFrame([{
    'dist_to_stop': 1200, 'current_speed': 25,
    'hour': 17, 'day_of_week': 1, 'traffic_index': 0.8
}])
eta = model.predict(sample)[0]
print(f"\n[SAMPLE] dist=1200m, speed=25km/h, traffic=0.8")
print(f"         Predicted ETA = {eta:.2f} minutes")
