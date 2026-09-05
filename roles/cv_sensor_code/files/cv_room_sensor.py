#!/usr/bin/env python3
"""
DS18B20 publisher for CV equipment room temperature monitoring.
Maps up to five probes into the existing CoolMRI-compatible metrics payload.
"""
from __future__ import annotations

import logging
import os
import socket
import time
from collections import deque
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv
from w1thermsensor import W1ThermSensor


ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

BACKEND_URL = os.getenv("BACKEND_URL", "https://cv.coolmri.com/api/metrics")
SITE_ID = os.getenv("SITE_ID", "IR3")
POLL_SEC = int(os.getenv("POLL_SEC", "10"))
AVG_WINDOW = int(os.getenv("AVG_WINDOW", "5"))
REQUEST_TIMEOUT_SEC = int(os.getenv("REQUEST_TIMEOUT_SEC", "10"))

DEFAULT_SENSOR_IDS = {
    "temp_1": "28-11f00087cb40",
    "temp_2": "28-2d7c0087acdc",
    "temp_3": "28-66730087b1b2",
    "temp_4": "28-6af500878e71",
}

SENSOR_NAMES = [f"temp_{index}" for index in range(1, 6)]


def configured_sensor_ids() -> dict[str, str]:
    env_values = [
        os.getenv(f"SENSOR_{index}_ID")
        for index in range(1, len(SENSOR_NAMES) + 1)
    ]
    if any(value is not None for value in env_values):
        return {
            name: sensor_id
            for name, value in zip(SENSOR_NAMES, env_values)
            if (sensor_id := (value or "").strip())
        }
    return DEFAULT_SENSOR_IDS.copy()


def setup_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def get_pi_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except Exception:
        return "unknown"


def discover_sensors(sensor_ids: dict[str, str]) -> dict[str, W1ThermSensor]:
    available = {f"28-{sensor.id}": sensor for sensor in W1ThermSensor.get_available_sensors()}
    if not sensor_ids:
        sensor_ids = {
            name: sensor_id
            for name, sensor_id in zip(SENSOR_NAMES, sorted(available))
        }
    matched: dict[str, W1ThermSensor] = {}

    for name, sensor_id in sensor_ids.items():
        sensor = available.get(sensor_id)
        if sensor is None:
            logging.warning("Configured %s sensor is missing: %s", name, sensor_id)
            continue
        matched[name] = sensor
        logging.info("Matched %s: %s", name, sensor_id)

    logging.info("Matched %s of %s configured sensors", len(matched), len(sensor_ids))
    return matched


def average(history: deque[float]) -> Optional[float]:
    if not history:
        return None
    return round(sum(history) / len(history), 3)


def read_temperatures(sensors: dict[str, W1ThermSensor], histories: dict[str, deque[float]]) -> dict[str, Optional[float]]:
    for name, sensor in sensors.items():
        try:
            histories[name].append(float(sensor.get_temperature()))
        except Exception as exc:
            logging.warning("Failed reading %s: %s", name, exc)
    return {name: average(history) for name, history in histories.items()}


def build_payload(readings: dict[str, Optional[float]]) -> dict[str, object]:
    return {
        "site_id": SITE_ID,
        "timestamp": int(time.time()),
        "pi_ip": get_pi_ip(),
        "helium_in": readings.get("temp_1"),
        "helium_out": readings.get("temp_2"),
        "helium_delta": None,
        "primary_in": readings.get("temp_3"),
        "primary_out": readings.get("temp_4"),
        "primary_delta": None,
        "room_temp": readings.get("temp_5"),
    }


def publish(payload: dict[str, object]) -> None:
    response = requests.post(BACKEND_URL, json=payload, timeout=REQUEST_TIMEOUT_SEC)
    response.raise_for_status()


def main() -> int:
    setup_logging()
    if not BACKEND_URL:
        raise RuntimeError("BACKEND_URL is required")

    sensor_ids = configured_sensor_ids()
    logging.info("Starting CV room sensor publisher for %s -> %s", SITE_ID, BACKEND_URL)
    if not sensor_ids:
        logging.info("No sensor IDs configured; using auto-discovery")
    sensors = discover_sensors(sensor_ids)
    if not sensor_ids:
        sensor_ids = {
            name: f"28-{sensor.id}"
            for name, sensor in sensors.items()
        }
    histories = {name: deque(maxlen=AVG_WINDOW) for name in sensor_ids}

    while True:
        if len(sensors) < len(sensor_ids):
            sensors = discover_sensors(sensor_ids)

        readings = read_temperatures(sensors, histories)
        payload = build_payload(readings)
        logging.info(
            "%s temps: %s",
            SITE_ID,
            ", ".join(f"{name}={value if value is not None else '--'}" for name, value in readings.items()),
        )

        try:
            publish(payload)
        except Exception as exc:
            logging.error("Publish failed: %s", exc)

        time.sleep(POLL_SEC)


if __name__ == "__main__":
    raise SystemExit(main())
