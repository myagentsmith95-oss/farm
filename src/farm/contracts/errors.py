"""Farm-level errors. Adapters translate library errors into these at the seam."""


class FarmError(Exception):
    """Base class for every error the farm raises on purpose."""


class UnsupportedAction(FarmError):
    """The backend cannot perform this kind of action."""


class InputError(FarmError):
    """Injecting input failed, or the backend is closed."""


class CaptureError(FarmError):
    """Capture failed, was never started, or is closed."""


class StaleFrame(FarmError):
    """No frame is fresh enough."""


class UnknownTemplate(FarmError):
    """The requested template is not registered with the matcher."""


class LeaseHeld(FarmError):
    """The device is already leased to a holder whose lease has not expired."""


class LeaseExpired(FarmError):
    """The lease expired, was released, or was taken over by a newer holder."""
