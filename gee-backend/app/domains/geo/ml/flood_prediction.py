"""
Flood prediction model for canal zones.

Uses DEM-derived features (HAND, TWI, slope, flow_acc) plus historical
water detection data to predict flood probability per zona operativa.

Level 1 (current): Feature-based scoring with learned weights
Level 2 (future):  Trained classifier (Random Forest / XGBoost)

The model learns feature weights from historical flood events and
produces a probability score (0-1) for each zona.
"""

from __future__ import annotations

import logging
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

MODEL_PATH = Path("/data/geo/models/flood_model.json")


@dataclass
class ZoneFeatures:
    """DEM-derived features for a zona operativa."""

    zona_id: str
    zona_name: str
    hand_mean: float = 0.0
    hand_min: float = 0.0
    twi_mean: float = 0.0
    twi_max: float = 0.0
    slope_mean: float = 0.0
    flow_acc_max: float = 0.0
    flow_acc_mean: float = 0.0
    water_pct_current: float = 0.0   # From latest water detection
    water_pct_historical: float = 0.0  # Average from historical detections
    elevation_range: float = 0.0
    rainfall_48h: float = 0.0   # Accumulated rainfall last 48 hours (mm)
    rainfall_7d: float = 0.0    # Accumulated rainfall last 7 days (mm)
    rainfall_30d: float = 0.0   # Accumulated rainfall last 30 days (mm)


@dataclass
class FloodModel:
    """Feature-based flood prediction model.

    Weights are calibrated for flat Pampas terrain (Argentine lowlands).
    Can be retrained from historical data via `train_from_events()`.
    """

    weights: dict[str, float] = field(default_factory=lambda: {
        "hand_mean": -0.35,        # Lower HAND = higher flood risk (negative)
        "hand_min": -0.10,         # Very low minimum HAND = flood prone
        "twi_mean": 0.20,          # Higher TWI = more water accumulation
        "twi_max": 0.05,           # Extreme TWI spots
        "slope_mean": -0.10,       # Flatter terrain = worse drainage
        "flow_acc_log_max": 0.15,  # More upstream flow = more water
        "flow_acc_log_mean": 0.05, # Average upstream contribution
        "water_pct_current": 0.25, # Current water presence is strong signal
        "water_pct_historical": 0.15, # Historical pattern
    })
    bias: float = 0.3  # Base flood probability for Pampas terrain
    version: str = "1.0.0"

    def predict(self, features: ZoneFeatures) -> dict[str, Any]:
        """Predict flood probability for a zone.

        Returns:
            Dict with probability (0-1), risk level, and feature contributions.
        """
        contributions = {}

        # Normalize features to 0-1 range using domain knowledge
        normalized = {
            "hand_mean": max(0, min(1, 1 - features.hand_mean / 5.0)),
            "hand_min": max(0, min(1, 1 - features.hand_min / 3.0)),
            "twi_mean": max(0, min(1, (features.twi_mean - 5) / 15.0)),
            "twi_max": max(0, min(1, (features.twi_max - 10) / 15.0)),
            "slope_mean": max(0, min(1, 1 - features.slope_mean / 5.0)),
            "flow_acc_log_max": max(0, min(1, np.log1p(features.flow_acc_max) / 15.0)),
            "flow_acc_log_mean": max(0, min(1, np.log1p(features.flow_acc_mean) / 10.0)),
            "water_pct_current": max(0, min(1, features.water_pct_current / 20.0)),
            "water_pct_historical": max(0, min(1, features.water_pct_historical / 15.0)),
            "rainfall_48h": max(0, min(1, features.rainfall_48h / 100.0)),
            "rainfall_7d": max(0, min(1, features.rainfall_7d / 200.0)),
            "rainfall_30d": max(0, min(1, features.rainfall_30d / 400.0)),
        }

        # Weighted sum
        score = self.bias
        for feat_name, weight in self.weights.items():
            val = normalized.get(feat_name, 0)
            contribution = weight * val
            score += contribution
            contributions[feat_name] = {
                "raw_value": getattr(features, feat_name.replace("_log", ""), val),
                "normalized": round(val, 4),
                "weight": weight,
                "contribution": round(contribution, 4),
            }

        # Clamp to 0-1
        probability = max(0.0, min(1.0, score))

        # Risk level
        risk_level = (
            "critico" if probability >= 0.75 else
            "alto" if probability >= 0.55 else
            "moderado" if probability >= 0.35 else
            "bajo"
        )

        return {
            "probability": round(probability, 4),
            "risk_level": risk_level,
            "contributions": contributions,
            "model_version": self.version,
        }

    def save(self, path: str | None = None):
        """Save model weights to disk."""
        save_path = Path(path or MODEL_PATH)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "weights": self.weights,
            "bias": self.bias,
            "version": self.version,
        }
        save_path.write_text(json.dumps(data, indent=2))
        logger.info("Flood model saved to %s", save_path)

    @classmethod
    def load(cls, path: str | None = None) -> "FloodModel":
        """Load model weights from disk, or return default."""
        load_path = Path(path or MODEL_PATH)
        if load_path.exists():
            data = json.loads(load_path.read_text())
            return cls(
                weights=data["weights"],
                bias=data["bias"],
                version=data.get("version", "1.0.0"),
            )
        return cls()

    def train_from_events(
        self,
        events: list[dict[str, Any]],
        learning_rate: float = 0.01,
        epochs: int = 100,
    ) -> dict[str, Any]:
        """Train weights from historical flood events.

        Each event should have:
            - features: ZoneFeatures dict
            - flooded: bool (ground truth)

        Uses simple gradient descent on log-loss.

        Args:
            events: List of training events.
            learning_rate: Learning rate for gradient descent.
            epochs: Number of training epochs.

        Returns:
            Training summary with loss history.
        """
        if len(events) < 5:
            return {"error": "Need at least 5 events to train", "count": len(events)}

        # Extract features and labels
        feature_names = list(self.weights.keys())
        X = []
        y = []

        for event in events:
            feat = event["features"]
            normalized = {
                "hand_mean": max(0, min(1, 1 - feat.get("hand_mean", 0) / 5.0)),
                "hand_min": max(0, min(1, 1 - feat.get("hand_min", 0) / 3.0)),
                "twi_mean": max(0, min(1, (feat.get("twi_mean", 0) - 5) / 15.0)),
                "twi_max": max(0, min(1, (feat.get("twi_max", 0) - 10) / 15.0)),
                "slope_mean": max(0, min(1, 1 - feat.get("slope_mean", 0) / 5.0)),
                "flow_acc_log_max": max(0, min(1, np.log1p(feat.get("flow_acc_max", 0)) / 15.0)),
                "flow_acc_log_mean": max(0, min(1, np.log1p(feat.get("flow_acc_mean", 0)) / 10.0)),
                "water_pct_current": max(0, min(1, feat.get("water_pct_current", 0) / 20.0)),
                "water_pct_historical": max(0, min(1, feat.get("water_pct_historical", 0) / 15.0)),
                "rainfall_48h": max(0, min(1, feat.get("rainfall_48h", 0) / 100.0)),
                "rainfall_7d": max(0, min(1, feat.get("rainfall_7d", 0) / 200.0)),
                "rainfall_30d": max(0, min(1, feat.get("rainfall_30d", 0) / 400.0)),
            }
            X.append([normalized.get(f, 0) for f in feature_names])
            y.append(1.0 if event["flooded"] else 0.0)

        X = np.array(X)
        y = np.array(y)
        weights = np.array([self.weights[f] for f in feature_names])
        bias = self.bias

        losses = []
        for epoch in range(epochs):
            # Forward pass
            z = X @ weights + bias
            pred = 1 / (1 + np.exp(-z))  # sigmoid
            pred = np.clip(pred, 1e-7, 1 - 1e-7)

            # Log loss
            loss = -np.mean(y * np.log(pred) + (1 - y) * np.log(1 - pred))
            losses.append(float(loss))

            # Backward pass
            error = pred - y
            grad_w = X.T @ error / len(y)
            grad_b = np.mean(error)

            weights -= learning_rate * grad_w
            bias -= learning_rate * grad_b

        # Update model
        for i, f in enumerate(feature_names):
            self.weights[f] = round(float(weights[i]), 6)
        self.bias = round(float(bias), 6)
        self.version = f"trained-{len(events)}events"

        return {
            "events": len(events),
            "epochs": epochs,
            "initial_loss": round(losses[0], 4),
            "final_loss": round(losses[-1], 4),
            "weights": self.weights,
            "bias": self.bias,
        }


def predict_flood_for_zone(
    zone_features: dict[str, Any],
    model_path: str | None = None,
) -> dict[str, Any]:
    """Predict flood probability for a zone given its features.

    Args:
        zone_features: Dict with HAND, TWI, slope, flow_acc stats.
        model_path: Optional path to trained model weights.

    Returns:
        Prediction result with probability and risk level.
    """
    model = FloodModel.load(model_path)
    features = ZoneFeatures(**zone_features)
    return model.predict(features)
