"""odmr-vector-tracking — learned through-crossing tracking for NV vector magnetometry.

Maintains per-axis ODMR resonance identity through frequency-space crossings to extend
vector-magnetometer dynamic range without a larger bias field. Physics is imported from
``nv_sensor_sim``; deployable models hand off to ``polarfire-hybrid-control`` as TFLite.
"""

__version__ = "0.0.1"
