#!/usr/bin/env python3
"""Read-only validation of camera v3 fields against the live OpenAPI document."""

from __future__ import annotations

import argparse
import json
import urllib.request


ENDPOINT = "/api/camera/pressure"
V3_FIELDS = {
    "site_id",
    "return_pressure",
    "confidence",
    "source",
    "timestamp",
    "full_image_base64",
    "cropped_image_base64",
    "crop_coordinates",
}


def resolve(document: dict, value: dict) -> dict:
    reference = value.get("$ref")
    if not reference:
        return value
    current = document
    for part in reference.removeprefix("#/").split("/"):
        current = current[part]
    return current


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url", default="http://127.0.0.1:8003/openapi.json",
        help="OpenAPI URL; this command performs GET only.",
    )
    args = parser.parse_args()
    with urllib.request.urlopen(args.url, timeout=5) as response:
        document = json.load(response)
    operation = document["paths"][ENDPOINT]["post"]
    schema = operation["requestBody"]["content"]["application/json"]["schema"]
    schema = resolve(document, schema)
    properties = set(schema.get("properties") or {})
    required = set(schema.get("required") or [])
    missing = sorted(V3_FIELDS - properties)
    incompatible_required = sorted(required - V3_FIELDS)
    result = {
        "endpoint": ENDPOINT,
        "schema": schema.get("title") or "PressurePayload",
        "status_code": next(iter(operation.get("responses") or {}), "unknown"),
        "v3_fields": sorted(V3_FIELDS),
        "required": sorted(required),
        "missing_v3_fields": missing,
        "incompatible_required_fields": incompatible_required,
        "compatible": not missing and not incompatible_required,
    }
    print(json.dumps(result, indent=2))
    return 0 if result["compatible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
