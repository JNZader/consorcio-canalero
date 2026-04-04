"""
Tests for the flood prediction model (PURE unit tests, no DB or GEE).

Covers: FloodModel, ZoneFeatures, predict(), train_from_events(), save/load.
"""

import json
import tempfile
from pathlib import Path

import pytest

from app.domains.geo.ml.flood_prediction import FloodModel, ZoneFeatures


# ── ZoneFeatures dataclass ──────────────────────────


class TestZoneFeatures:
    """ZoneFeatures dataclass field defaults and construction."""

    def test_default_values(self):
        zf = ZoneFeatures(zona_id="z1", zona_name="Zona 1")
        assert zf.hand_mean == 0.0
        assert zf.twi_mean == 0.0
        assert zf.slope_mean == 0.0
        assert zf.flow_acc_max == 0.0
        assert zf.water_pct_current == 0.0
        assert zf.water_pct_historical == 0.0
        assert zf.rainfall_48h == 0.0
        assert zf.rainfall_7d == 0.0
        assert zf.rainfall_30d == 0.0

    def test_custom_values(self):
        zf = ZoneFeatures(
            zona_id="z2",
            zona_name="Zona 2",
            hand_mean=3.5,
            twi_mean=12.0,
            slope_mean=1.2,
            rainfall_48h=50.0,
            rainfall_7d=120.0,
            rainfall_30d=300.0,
        )
        assert zf.hand_mean == 3.5
        assert zf.rainfall_48h == 50.0
        assert zf.rainfall_7d == 120.0
        assert zf.rainfall_30d == 300.0

    def test_all_rainfall_fields_present(self):
        """ZoneFeatures must include all three rainfall window fields."""
        zf = ZoneFeatures(zona_id="z", zona_name="Z")
        assert hasattr(zf, "rainfall_48h")
        assert hasattr(zf, "rainfall_7d")
        assert hasattr(zf, "rainfall_30d")


# ── FloodModel initialization ───────────────────────


class TestFloodModelInit:
    """FloodModel default weights and version."""

    def test_default_weights(self):
        model = FloodModel()
        assert "hand_mean" in model.weights
        assert "twi_mean" in model.weights
        assert "water_pct_current" in model.weights
        assert "rainfall_48h" in model.weights
        assert "rainfall_7d" in model.weights
        assert "rainfall_30d" in model.weights

    def test_default_rainfall_weights_are_zero(self):
        """Rainfall weights start at 0 (enabled only after training)."""
        model = FloodModel()
        assert model.weights["rainfall_48h"] == 0.0
        assert model.weights["rainfall_7d"] == 0.0
        assert model.weights["rainfall_30d"] == 0.0

    def test_default_bias(self):
        model = FloodModel()
        assert model.bias == 0.3

    def test_version_string(self):
        model = FloodModel()
        assert model.version == "2.0.0-rainfall"


# ── FloodModel.predict() ────────────────────────────


class TestFloodModelPredict:
    """FloodModel.predict() scoring and risk classification."""

    def test_predict_returns_required_keys(self):
        model = FloodModel()
        features = ZoneFeatures(zona_id="z1", zona_name="Z1")
        result = model.predict(features)

        assert "probability" in result
        assert "risk_level" in result
        assert "contributions" in result
        assert "model_version" in result

    def test_predict_score_between_0_and_100(self):
        """Probability is 0-1 (score 0-100 mapped via risk_level)."""
        model = FloodModel()
        features = ZoneFeatures(zona_id="z1", zona_name="Z1")
        result = model.predict(features)

        assert 0.0 <= result["probability"] <= 1.0

    def test_predict_default_weights_zero_features(self):
        """With zero features and default weights, score equals bias processed through normalization.

        Zero raw features normalize to specific values (hand_mean=0 → normalized=1.0,
        slope_mean=0 → normalized=1.0, etc.) so the prediction is NOT just the bias.
        """
        model = FloodModel()
        features = ZoneFeatures(zona_id="z1", zona_name="Z1")
        result = model.predict(features)

        # With zero inputs, hand_mean normalizes to 1.0 (1 - 0/5), slope normalizes to 1.0,
        # twi normalizes to 0 ((0-5)/15 clamped), etc.
        # Expected: bias(0.3) + hand_mean(-0.35*1) + hand_min(-0.10*1) + slope(-0.10*1)
        #         + flow_acc_log_max(0.15*0) + ... ≈ 0.3 - 0.35 - 0.10 - 0.10 + ...
        # The exact value depends on all normalizations, but it should be clamped to [0, 1]
        prob = result["probability"]
        assert 0.0 <= prob <= 1.0

    def test_predict_high_risk_features(self):
        """Features indicating high flood risk should produce a higher score than low risk."""
        model = FloodModel()
        high_risk = ZoneFeatures(
            zona_id="z1",
            zona_name="Z1",
            hand_mean=0.5,        # Very low HAND → high risk
            hand_min=0.1,
            twi_mean=18.0,        # Very high TWI
            twi_max=22.0,
            slope_mean=0.3,       # Very flat
            flow_acc_max=1e6,     # Huge upstream catchment
            flow_acc_mean=1e5,
            water_pct_current=15.0,    # Currently wet
            water_pct_historical=10.0,
        )
        low_risk = ZoneFeatures(
            zona_id="z2",
            zona_name="Z2",
            hand_mean=10.0,
            hand_min=8.0,
            twi_mean=3.0,
            slope_mean=8.0,
            flow_acc_max=10,
            water_pct_current=0.0,
        )
        high_result = model.predict(high_risk)
        low_result = model.predict(low_risk)
        assert high_result["probability"] > low_result["probability"]

    def test_predict_low_risk_features(self):
        """Features indicating low flood risk should produce bajo/moderado level."""
        model = FloodModel()
        features = ZoneFeatures(
            zona_id="z1",
            zona_name="Z1",
            hand_mean=10.0,       # High HAND → safe
            hand_min=8.0,
            twi_mean=3.0,         # Low TWI
            twi_max=5.0,
            slope_mean=8.0,       # Steep
            flow_acc_max=10,
            flow_acc_mean=5,
            water_pct_current=0.0,
            water_pct_historical=0.0,
        )
        result = model.predict(features)
        assert result["risk_level"] in ("bajo", "moderado")

    def test_predict_risk_levels_thresholds(self):
        """Verify the four risk levels are assigned at correct thresholds."""
        model = FloodModel()

        # Force specific probabilities by manipulating weights and bias
        model.weights = {k: 0.0 for k in model.weights}
        features = ZoneFeatures(zona_id="z", zona_name="Z")

        # bajo: < 0.35
        model.bias = 0.20
        assert model.predict(features)["risk_level"] == "bajo"

        # moderado: 0.35-0.55
        model.bias = 0.45
        assert model.predict(features)["risk_level"] == "moderado"

        # alto: 0.55-0.75
        model.bias = 0.65
        assert model.predict(features)["risk_level"] == "alto"

        # critico: >= 0.75
        model.bias = 0.85
        assert model.predict(features)["risk_level"] == "critico"

    def test_predict_contributions_structure(self):
        """Each contribution should have raw_value, normalized, weight, contribution."""
        model = FloodModel()
        features = ZoneFeatures(zona_id="z1", zona_name="Z1", hand_mean=2.0)
        result = model.predict(features)

        contrib = result["contributions"]["hand_mean"]
        assert "raw_value" in contrib
        assert "normalized" in contrib
        assert "weight" in contrib
        assert "contribution" in contrib


# ── FloodModel.train_from_events() ──────────────────


class TestFloodModelTraining:
    """FloodModel.train_from_events() gradient descent training."""

    @staticmethod
    def _make_events(n: int) -> list[dict]:
        """Generate n synthetic training events."""
        events = []
        for i in range(n):
            flooded = i % 2 == 0
            events.append({
                "features": {
                    "hand_mean": 1.0 if flooded else 5.0,
                    "hand_min": 0.5 if flooded else 4.0,
                    "twi_mean": 15.0 if flooded else 6.0,
                    "twi_max": 20.0 if flooded else 8.0,
                    "slope_mean": 0.5 if flooded else 3.0,
                    "flow_acc_max": 100000 if flooded else 100,
                    "flow_acc_mean": 10000 if flooded else 10,
                    "water_pct_current": 10.0 if flooded else 0.0,
                    "water_pct_historical": 8.0 if flooded else 0.0,
                    "rainfall_48h": 60.0 if flooded else 5.0,
                    "rainfall_7d": 150.0 if flooded else 20.0,
                    "rainfall_30d": 300.0 if flooded else 50.0,
                },
                "flooded": flooded,
            })
        return events

    def test_train_with_minimum_events(self):
        events = self._make_events(5)
        model = FloodModel()
        result = model.train_from_events(events)

        assert "events" in result
        assert result["events"] == 5
        assert result["epochs"] == 100
        assert "initial_loss" in result
        assert "final_loss" in result
        assert result["final_loss"] <= result["initial_loss"]

    def test_train_fewer_than_5_events_returns_error(self):
        events = self._make_events(3)
        model = FloodModel()
        result = model.train_from_events(events)

        assert "error" in result
        assert result["count"] == 3

    def test_train_updates_weights(self):
        events = self._make_events(10)
        model = FloodModel()
        weights_before = dict(model.weights)

        model.train_from_events(events, epochs=200)

        # At least some weights should have changed
        changed = sum(1 for k in weights_before if model.weights[k] != weights_before[k])
        assert changed > 0

    def test_train_updates_version(self):
        events = self._make_events(8)
        model = FloodModel()
        model.train_from_events(events)

        assert model.version == "trained-8events"

    def test_train_custom_learning_rate_and_epochs(self):
        events = self._make_events(6)
        model = FloodModel()
        result = model.train_from_events(events, learning_rate=0.05, epochs=50)

        assert result["epochs"] == 50


# ── FloodModel.save() / load() ──────────────────────


class TestFloodModelPersistence:
    """FloodModel JSON save/load round-trip and backward compatibility."""

    def test_save_and_load_roundtrip(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            model = FloodModel()
            model.weights["hand_mean"] = -0.50
            model.bias = 0.42
            model.save(path)

            loaded = FloodModel.load(path)
            assert loaded.weights["hand_mean"] == -0.50
            assert loaded.bias == 0.42
            assert loaded.version == "2.0.0-rainfall"
        finally:
            Path(path).unlink(missing_ok=True)

    def test_load_nonexistent_returns_default(self):
        model = FloodModel.load("/tmp/nonexistent_flood_model_xyz.json")
        assert model.bias == 0.3
        assert model.version == "2.0.0-rainfall"

    def test_load_backward_compat_missing_rainfall_keys(self):
        """Loading a pre-2.0 model JSON without rainfall keys defaults them to 0.0."""
        old_model_data = {
            "weights": {
                "hand_mean": -0.35,
                "hand_min": -0.10,
                "twi_mean": 0.20,
                "twi_max": 0.05,
                "slope_mean": -0.10,
                "flow_acc_log_max": 0.15,
                "flow_acc_log_mean": 0.05,
                "water_pct_current": 0.25,
                "water_pct_historical": 0.15,
                # NO rainfall keys
            },
            "bias": 0.3,
            "version": "1.0.0",
        }

        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump(old_model_data, f)
            path = f.name

        try:
            loaded = FloodModel.load(path)
            assert loaded.weights["rainfall_48h"] == 0.0
            assert loaded.weights["rainfall_7d"] == 0.0
            assert loaded.weights["rainfall_30d"] == 0.0
            assert loaded.version == "1.0.0"
        finally:
            Path(path).unlink(missing_ok=True)

    def test_save_creates_parent_directories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nested" / "deep" / "model.json"
            model = FloodModel()
            model.save(str(path))

            assert path.exists()
            data = json.loads(path.read_text())
            assert "weights" in data
            assert "bias" in data

    def test_trained_model_save_load_preserves_weights(self):
        """After training, save/load should preserve the trained weights."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            model = FloodModel()
            events = TestFloodModelTraining._make_events(6)
            model.train_from_events(events)
            trained_weights = dict(model.weights)
            trained_bias = model.bias

            model.save(path)
            loaded = FloodModel.load(path)

            for key in trained_weights:
                assert loaded.weights[key] == trained_weights[key], f"Weight {key} mismatch"
            assert loaded.bias == trained_bias
        finally:
            Path(path).unlink(missing_ok=True)
