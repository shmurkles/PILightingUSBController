"""Power control backends.

    from pilight.power import create_backend

    backend = create_backend(config)
    backend.set_power(True)

The scheduler depends on this package's interface and nothing below it.
"""

from .base import (
    BackendConfigError,
    BackendUnavailableError,
    PermissionDeniedError,
    PowerBackend,
    PowerBackendError,
    SwitchFailedError,
    UnknownBackendError,
)
from .dryrun import DryRunBackend
from .factory import available_backends, create_backend
from .uhubctl import UhubctlBackend

__all__ = [
    "BackendConfigError",
    "BackendUnavailableError",
    "DryRunBackend",
    "PermissionDeniedError",
    "PowerBackend",
    "PowerBackendError",
    "SwitchFailedError",
    "UhubctlBackend",
    "UnknownBackendError",
    "available_backends",
    "create_backend",
]
