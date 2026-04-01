"""Model architectures for ODMR spectral inversion."""

from tychon_odmr_ml.models.cnn1d import OdmrCNN1D
from tychon_odmr_ml.models.fcnn import OdmrFCNN
from tychon_odmr_ml.models.mlp import OdmrMLP

__all__ = ["OdmrCNN1D", "OdmrFCNN", "OdmrMLP"]
