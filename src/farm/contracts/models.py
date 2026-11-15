"""Contract models. Stdlib and pydantic only (enforced by test_contracts_purity)."""
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


class InputMode(StrEnum):
    """How the farm injects input into a phone."""

    HID = "hid"  # ESP32-S3 USB HID, root-free
    ADB = "adb"  # Android Debug Bridge


class DeviceProfile(BaseModel):
    """Per-device configuration.

    input_modes is an ordered preference list: the first usable entry is tried
    first and the rest are fallbacks. One backend is active at a time; the lease
    enforces that, not this model.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    device_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    input_modes: Annotated[list[InputMode], Field(min_length=1)]

    @field_validator("input_modes")
    @classmethod
    def _no_duplicates(cls, modes: list[InputMode]) -> list[InputMode]:
        if len(set(modes)) != len(modes):
            raise ValueError("input_modes must not contain duplicates")
        return modes
