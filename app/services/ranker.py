# /app/services/ranker.py
import xgboost as xgb
import numpy as np
from typing import Optional

class XGBoostRanker:
    """
    A wrapper for the XGBoost ranking model.
    """
    def __init__(self, model_path: str = "app/models/ranker.xgb"):
        self.model: Optional[xgb.Booster] = self._load_model(model_path)

    def _load_model(self, model_path: str) -> Optional[xgb.Booster]:
        """Loads the XGBoost model from the specified path."""
        try:
            ranker_model = xgb.Booster()
            ranker_model.load_model(model_path)
            print(f"XGBoost ranker loaded from {model_path}")
            return ranker_model
        except FileNotFoundError:
            print(f"WARNING: Ranker model not found at {model_path}. Ranking will be disabled.")
            return None
        except Exception as e:
            print(f"ERROR: Failed to load ranker model: {e}")
            return None

    def predict(self, feature_matrix: np.ndarray) -> np.ndarray:
        """
        Applies the XGBoost ranker to predict relevance scores.
        """
        if self.model is None:
            # Fallback: return zeros if model not loaded
            return np.zeros(feature_matrix.shape[0])

        dmatrix = xgb.DMatrix(feature_matrix)
        scores = self.model.predict(dmatrix)
        return scores