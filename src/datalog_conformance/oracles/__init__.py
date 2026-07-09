"""External-implementation oracles usable as conformance evaluators."""

from .clingo_oracle import (
    ClingoError,
    ClingoOracle,
    ClingoUnavailableError,
    ClingoUnsupportedError,
)
from .nemo import NemoError, NemoOracle, NemoUnavailableError, find_nmo
from .souffle import (
    SouffleError,
    SouffleOracle,
    SouffleUnavailableError,
    SouffleUnsupportedError,
    find_souffle,
)
from .swipl import (
    SwiPrologError,
    SwiPrologOracle,
    SwiPrologUnavailableError,
    SwiPrologUnsupportedError,
    find_swipl,
)

__all__ = [
    "ClingoError",
    "ClingoOracle",
    "ClingoUnavailableError",
    "ClingoUnsupportedError",
    "NemoError",
    "NemoOracle",
    "NemoUnavailableError",
    "SouffleError",
    "SouffleOracle",
    "SouffleUnavailableError",
    "SouffleUnsupportedError",
    "SwiPrologError",
    "SwiPrologOracle",
    "SwiPrologUnavailableError",
    "SwiPrologUnsupportedError",
    "find_nmo",
    "find_souffle",
    "find_swipl",
]
