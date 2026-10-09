"""Dataset contract + loaders for the v1 time-series ODMR tracker datasets.

- ``contract`` — v1 manifest + HDF5 schema validation (consumer side of the orchestrator-owned
  data contract; see ``docs/design/03_data_contract.md``).
- ``loaders`` — read the contract HDF5 into numpy / torch batches.
"""

from odmr_vector_tracking.data.contract import (
    CONTRACT_VERSION,
    DATASET_SCHEMA,
    REQUIRED_MANIFEST_FIELDS,
    REQUIRED_UNITS,
    VALID_SPLITS,
    ContractViolation,
    validate_dataset_dir,
    validate_manifest,
    validate_sequence_dataset,
)
from odmr_vector_tracking.data.loaders import SequenceDataset, SequenceDatasetLoader

__all__ = [
    "CONTRACT_VERSION",
    "DATASET_SCHEMA",
    "REQUIRED_MANIFEST_FIELDS",
    "REQUIRED_UNITS",
    "VALID_SPLITS",
    "ContractViolation",
    "validate_dataset_dir",
    "validate_manifest",
    "validate_sequence_dataset",
    "SequenceDataset",
    "SequenceDatasetLoader",
]
