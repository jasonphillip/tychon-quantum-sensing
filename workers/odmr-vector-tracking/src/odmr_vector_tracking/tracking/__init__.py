"""Trackers.

Planned modules:
- ``classical`` — lock-in + per-line PID with nearest-peak association (the Γ/2-limited
  baseline that loses lock at inter-axis crossings).
- ``learned`` — physics-informed KalmanNet-style recurrent filter + attention data-association
  head; outputs 4 axis-projections (Σ Bᵢ = 0) for closed-form BLUE inversion to a 3D vector.
"""
