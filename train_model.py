import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import joblib # To save the model

def train_bus_eta_model():
    # 1. Load the dataset
    df = pd.read_csv('smart_bus_data.csv')

    # 2. Select Features (As per Algorithm 2 in the paper)
    # Features: [dist_to_stop, current_speed, hour, day_of_week, traffic_index]
    # Target: actual_eta
    X = df[['dist_to_stop', 'current_speed', 'hour', 'day_of_week', 'traffic_index']]
    y = df['actual_eta']

    # 3. Split the data (80% Train, 20% Test as per paper page 5)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    print("Training XGBoost Regressor...")

    # 4. Initialize and Train XGBoost
    # Hyperparameters tuned for regression
    model = xgb.XGBRegressor(
        n_estimators=500,
        max_depth=6,
        learning_rate=0.1,
        objective='reg:squarederror',
        random_state=42
    )

    model.fit(X_train, y_train)

    # 5. Model Evaluation (Compare with Paper Metrics)
    predictions = model.predict(X_test)
    rmse = np.sqrt(mean_squared_error(y_test, predictions))
    mae = mean_absolute_error(y_test, predictions)
    r2 = r2_score(y_test, predictions)

    print("\n--- Model Performance ---")
    print(f"RMSE: {rmse:.2f} minutes")
    print(f"MAE:  {mae:.2f} minutes")
    print(f"R2 Score: {r2:.2f}")

    # 6. Save the model to a file
    model.save_model('bus_eta_model.json')
    print("\nModel saved as 'bus_eta_model.json'")

if __name__ == "__main__":
    train_bus_eta_model()