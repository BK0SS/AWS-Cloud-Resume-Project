"""Visitor counter Lambda handler.

Increments and returns a single counter stored in DynamoDB. Designed to be
invoked from an HTTP API (API Gateway v2 / Lambda proxy integration).

Environment variables
---------------------
TABLE_NAME  : DynamoDB table name (single-item table; PK="id", SK omitted).
COUNTER_ID  : Primary key value for the counter row (default: "site").
ALLOWED_ORIGIN : Origin allowed by CORS headers (default: "*").

Returns
-------
200 with JSON body: {"count": <int>}
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ.get("TABLE_NAME", "VisitorCounter")
COUNTER_ID = os.environ.get("COUNTER_ID", "site")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")

_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table(TABLE_NAME)


def _response(status: int, body: dict[str, Any]) -> dict[str, Any]:
    """Build an API-Gateway-compatible response with CORS headers."""
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
            "Access-Control-Allow-Methods": "POST,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps(body),
    }


def increment_counter() -> int:
    """Atomically increment the counter row and return the new value."""
    try:
        result = _table.update_item(
            Key={"id": COUNTER_ID},
            UpdateExpression="ADD #c :inc",
            ExpressionAttributeNames={"#c": "count"},
            ExpressionAttributeValues={":inc": 1},
            ReturnValues="UPDATED_NEW",
        )
        return int(result["Attributes"]["count"])
    except ClientError as exc:
        logger.exception("DynamoDB update failed: %s", exc)
        raise


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Entry point for API Gateway -> Lambda proxy integration."""
    method = (
        event.get("requestContext", {})
        .get("http", {})
        .get("method")
        or event.get("httpMethod")
        or "POST"
    )

    # Preflight
    if method == "OPTIONS":
        return _response(200, {"ok": True})

    try:
        count = increment_counter()
        return _response(200, {"count": count})
    except Exception:  # noqa: BLE001
        return _response(500, {"error": "internal_error"})
