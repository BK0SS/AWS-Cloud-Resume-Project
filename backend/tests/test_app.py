"""Unit tests for the visitor counter Lambda.

We use `moto` to mock DynamoDB so the tests run offline and in CI without
any AWS credentials.
"""

from __future__ import annotations

import importlib
import json
import os
from typing import Iterator

import boto3
import pytest
from moto import mock_aws


TABLE_NAME = "VisitorCounter-Test"


@pytest.fixture
def app_module(monkeypatch: pytest.MonkeyPatch) -> Iterator:
    """Spin up a mocked DynamoDB table and (re)import the handler."""
    monkeypatch.setenv("TABLE_NAME", TABLE_NAME)
    monkeypatch.setenv("COUNTER_ID", "site")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")

    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-west-2")
        ddb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        ).wait_until_exists()

        # Import after env vars are set so the module picks them up.
        import backend.src.app as app  # noqa: WPS433

        importlib.reload(app)
        yield app


def _event(method: str = "POST") -> dict:
    return {"requestContext": {"http": {"method": method}}}


def test_first_call_returns_one(app_module) -> None:
    resp = app_module.lambda_handler(_event(), context=None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body == {"count": 1}


def test_counter_increments(app_module) -> None:
    for expected in (1, 2, 3, 4):
        resp = app_module.lambda_handler(_event(), context=None)
        assert json.loads(resp["body"])["count"] == expected


def test_options_preflight_returns_cors(app_module) -> None:
    resp = app_module.lambda_handler(_event("OPTIONS"), context=None)
    assert resp["statusCode"] == 200
    assert resp["headers"]["Access-Control-Allow-Origin"] == "*"
    assert "POST" in resp["headers"]["Access-Control-Allow-Methods"]
