class GeoJobFenceLost(RuntimeError):
    """Raised when reconciliation or another worker invalidates execution."""
