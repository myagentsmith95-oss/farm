"""Frame: one captured screen image plus the metadata needed to judge freshness."""
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class FrameSource(StrEnum):
    """Where a frame came from."""

    UVC = "uvc"  # HDMI / UVC capture card
    ADB_SCREENCAP = "adb_screencap"  # ADB screencap (ADB-only seats)


class Frame(BaseModel):
    """captured_ns comes from time.monotonic_ns() on the farm host, for every
    source, so freshness is comparable across sources. data holds encoded image
    bytes; contracts do not interpret pixels."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    width: Annotated[int, Field(gt=0)]
    height: Annotated[int, Field(gt=0)]
    captured_ns: Annotated[int, Field(ge=0)]
    source: FrameSource
    data: Annotated[bytes, Field(min_length=1)]
