# app/scripts/create_dummy_ranker.py
import xgboost as xgb
import numpy as np
import os

def create_dummy_ranker():
    """
    Creates and saves a dummy XGBoost model.
    This model is used as a placeholder for the actual ranking model.
    """
    # Create dummy training data matching the feature schema
    # 9 features, 100 samples
    n_samples = 100
    n_features = 9

    X_train = np.random.rand(n_samples, n_features)
    y_train = np.random.rand(n_samples)  # Random relevance scores

    # Create and train a simple model
    dtrain = xgb.DMatrix(X_train, label=y_train)
    params = {
        'objective': 'reg:squarederror',
        'max_depth': 3,
        'eta': 0.1
    }

    model = xgb.train(params, dtrain, num_boost_round=10)

    # Ensure the 'app/models' directory exists
    model_dir = 'app/models'
    if not os.path.exists(model_dir):
        os.makedirs(model_dir)

    # Save the model
    model_path = os.path.join(model_dir, 'ranker.xgb')
    model.save_model(model_path)
    print(f"Dummy ranker model created at {model_path}")

if __name__ == "__main__":
    create_dummy_ranker()