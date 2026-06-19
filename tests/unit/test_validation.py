import pytest
from pydantic import ValidationError

from paygateway.schemas.payment import CreatePaymentRequest


@pytest.mark.unit
def test_valid_payment_request():
    req = CreatePaymentRequest(amount=5000, currency="usd")
    assert req.amount == 5000
    assert req.currency == "USD"


@pytest.mark.unit
def test_zero_amount_rejected():
    with pytest.raises(ValidationError):
        CreatePaymentRequest(amount=0, currency="usd")


@pytest.mark.unit
def test_negative_amount_rejected():
    with pytest.raises(ValidationError):
        CreatePaymentRequest(amount=-100, currency="usd")


@pytest.mark.unit
def test_invalid_currency_rejected():
    with pytest.raises(ValidationError):
        CreatePaymentRequest(amount=100, currency="toolong")


@pytest.mark.unit
def test_metadata_too_many_keys():
    meta = {f"key{i}": "val" for i in range(21)}
    with pytest.raises(ValidationError):
        CreatePaymentRequest(amount=100, currency="usd", metadata=meta)


@pytest.mark.unit
def test_metadata_key_too_long():
    with pytest.raises(ValidationError):
        CreatePaymentRequest(amount=100, currency="usd", metadata={"a" * 41: "v"})


@pytest.mark.unit
def test_currency_normalized_to_upper():
    req = CreatePaymentRequest(amount=100, currency="eur")
    assert req.currency == "EUR"
