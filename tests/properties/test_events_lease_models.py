"""DeviceEvent and Lease models."""
import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from farm.contracts.events import DeviceEvent, DeviceEventKind
from farm.contracts.lease import Lease


def make_event(**overrides):
    fields = dict(
        kind=DeviceEventKind.ATTACHED,
        by_id="usb-Espressif_ESP32-S3_1234-if00",
        by_path="pci-0000:00:14.0-usb-0:2:1.0",
        vendor_id="303a",
        product_id="1001",
        serial="1234",
        observed_ns=1,
    )
    fields.update(overrides)
    return DeviceEvent(**fields)


def make_lease(**overrides):
    fields = dict(device_id="seat-01", holder="runner-a", token=1, expires_ns=10)
    fields.update(overrides)
    return Lease(**fields)


@given(st.integers(min_value=0, max_value=2**62))
def test_event_accepts_valid_fields(observed_ns):
    event = make_event(observed_ns=observed_ns)
    assert event.observed_ns == observed_ns
    assert event.vendor_id == "303a"


def test_event_optional_fields_may_be_missing():
    event = make_event(by_path=None, serial=None)
    assert event.by_path is None and event.serial is None


@pytest.mark.parametrize(
    "name, kind",
    [("attached", DeviceEventKind.ATTACHED), ("detached", DeviceEventKind.DETACHED)],
)
def test_event_accepts_kind_names_as_strings(name, kind):
    assert make_event(kind=name).kind is kind


@pytest.mark.parametrize("blank", ["", "   "])
def test_event_rejects_blank_by_id(blank):
    with pytest.raises(ValidationError):
        make_event(by_id=blank)


def test_event_rejects_blank_by_path_when_given():
    with pytest.raises(ValidationError):
        make_event(by_path="")


@pytest.mark.parametrize("field", ["vendor_id", "product_id"])
@pytest.mark.parametrize("bad", ["", "303", "303A", "30gz", "303a1"])
def test_event_rejects_bad_usb_ids(field, bad):
    with pytest.raises(ValidationError):
        make_event(**{field: bad})


def test_event_rejects_negative_timestamp():
    with pytest.raises(ValidationError):
        make_event(observed_ns=-1)


def test_event_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        make_event(kind="changed")


def test_event_rejects_extra_fields():
    with pytest.raises(ValidationError):
        make_event(driver="cdc_acm")


def test_event_is_immutable():
    event = make_event()
    with pytest.raises(ValidationError):
        event.serial = "other"


def test_lease_accepts_valid_fields():
    lease = make_lease()
    assert (lease.device_id, lease.holder, lease.token) == ("seat-01", "runner-a", 1)


@pytest.mark.parametrize("bad", [0, -1])
def test_lease_rejects_non_positive_token(bad):
    with pytest.raises(ValidationError):
        make_lease(token=bad)


@pytest.mark.parametrize("field", ["device_id", "holder"])
def test_lease_rejects_blank_ids(field):
    with pytest.raises(ValidationError):
        make_lease(**{field: "  "})


def test_lease_rejects_negative_expiry():
    with pytest.raises(ValidationError):
        make_lease(expires_ns=-1)


def test_lease_rejects_extra_fields():
    with pytest.raises(ValidationError):
        make_lease(priority=1)


def test_lease_is_immutable():
    lease = make_lease()
    with pytest.raises(ValidationError):
        lease.holder = "runner-b"
