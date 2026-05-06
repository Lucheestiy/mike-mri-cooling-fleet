#!/usr/bin/env python3
"""
pi_sensor_refactored.py – Refactored MRI helium-compressor and primary cooling monitor
Author: Mike L. (refactored by Claude)
Description: Headless version with proper class structure and modular design.
"""
import os
import time
import logging
from logging.handlers import RotatingFileHandler, MemoryHandler
from collections import deque
from enum import Enum, auto
from pathlib import Path
import socket
import subprocess
import json
import shutil
import tempfile
import threading
import hashlib
from datetime import datetime, timezone
from typing import Dict, Optional, List, Tuple, Any

import requests
from dotenv import load_dotenv
from w1thermsensor import W1ThermSensor, errors as w1_errors

# ---------------------------------------------------------------------
# Configuration Management
# ---------------------------------------------------------------------
class SensorConfig:
    """Manages sensor configuration from environment variables"""

    def __init__(self):
        # Load .env from project root
        env_path = Path(__file__).resolve().parent.parent / ".env"
        load_dotenv(dotenv_path=env_path)

        # Basic configuration
        self.LOG_PATH = os.getenv("LOG_PATH", "logs/pi_sensor.log")
        self.BACKEND_URL = os.getenv("BACKEND_URL")
        self.ALERTER_METRICS_URL = os.getenv("ALERTER_METRICS_URL")

        # Development environment URL (optional)
        self.DEV_BACKEND_URL = os.getenv("DEV_BACKEND_URL")
        self.ENABLE_DUAL_STREAMING = os.getenv("ENABLE_DUAL_STREAMING", "false").lower() == "true"

        # SD Card wear prevention
        self.MEMORY_ONLY_MODE = os.getenv("MEMORY_ONLY_MODE", "false").lower() == "true"
        self.WEAR_LEVELING = os.getenv("WEAR_LEVELING", "true").lower() == "true"
        self.RAM_LOG_CAPACITY = int(os.getenv("RAM_LOG_CAPACITY", "1000"))
        self.DISK_SYNC_INTERVAL = int(os.getenv("DISK_SYNC_INTERVAL", "3600"))

        # Sensor IDs
        self.PROBE_IN_ID = os.getenv("PROBE_IN_ID")
        self.PROBE_OUT_ID = os.getenv("PROBE_OUT_ID")
        self.PROBE_PRIMARY_IN_ID = os.getenv("PROBE_PRIMARY_IN_ID")
        self.PROBE_PRIMARY_OUT_ID = os.getenv("PROBE_PRIMARY_OUT_ID")
        self.PROBE_ROOM_ID = os.getenv("PROBE_ROOM_ID")

        # Polling configuration
        self.AVG_WINDOW = int(os.getenv("AVG_WINDOW", "5"))
        self.POLL_SEC = int(os.getenv("POLL_SEC", "10"))
        self.INVALID_SENSOR_RESTART_THRESHOLD = int(os.getenv("INVALID_SENSOR_RESTART_THRESHOLD", "3"))
        self.SENSOR_DISCOVERY_TIMEOUT_SEC = int(os.getenv("SENSOR_DISCOVERY_TIMEOUT_SEC", "90"))
        self.SENSOR_DISCOVERY_INTERVAL_SEC = int(os.getenv("SENSOR_DISCOVERY_INTERVAL_SEC", "5"))
        self.SENSOR_RESCAN_TIMEOUT_SEC = int(os.getenv("SENSOR_RESCAN_TIMEOUT_SEC", "20"))
        self.SENSOR_RESCAN_INTERVAL_SEC = int(os.getenv("SENSOR_RESCAN_INTERVAL_SEC", "5"))

        # Site identification
        self.SITE_NAME = os.getenv("SITE_NAME", "GMC")
        self.SCANNER_ID = os.getenv("SCANNER_ID", "MR2")

        # Offset configuration
        self.OFFSET_FILE_PATH = Path(__file__).resolve().parent / "sensor_offsets.json"

    def validate(self) -> bool:
        """Validate required configuration"""
        if not self.BACKEND_URL:
            logging.error("BACKEND_URL is required but not set")
            return False

        required_probes = [
            self.PROBE_IN_ID, self.PROBE_OUT_ID,
            self.PROBE_PRIMARY_IN_ID, self.PROBE_PRIMARY_OUT_ID
        ]

        if not all(required_probes):
            logging.error("Required probe IDs are missing")
            return False

        return True

# ---------------------------------------------------------------------
# Logging Management
# ---------------------------------------------------------------------
class LoggingManager:
    """Manages logging setup with SD card wear prevention"""

    def __init__(self, config: SensorConfig):
        self.config = config

    def setup_logging(self):
        """Setup logging with SD card wear prevention strategies"""

        if self.config.MEMORY_ONLY_MODE:
            self._setup_memory_only_logging()
        else:
            self._setup_disk_logging()

    def _setup_memory_only_logging(self):
        """Setup pure RAM logging - no disk writes"""
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s",
            handlers=[console_handler]
        )
        logging.info("MEMORY_ONLY_MODE: All logging to console/RAM only - no disk writes")

    def _setup_disk_logging(self):
        """Setup disk logging with wear leveling"""
        # Wear leveling: rotate log directories based on date
        if self.config.WEAR_LEVELING:
            log_dir = self._get_wear_leveled_log_path()
        else:
            log_dir = Path(self.config.LOG_PATH).parent

        os.makedirs(log_dir, exist_ok=True)
        log_file = log_dir / "pi_sensor.log"

        # Create file handler with larger rotation to reduce write frequency
        file_handler = RotatingFileHandler(
            str(log_file),
            maxBytes=20*1024*1024,  # 20MB files
            backupCount=2,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.WARNING)

        # RAM buffer handler - holds logs in memory, flushes periodically
        memory_handler = MemoryHandler(
            capacity=self.config.RAM_LOG_CAPACITY,
            flushLevel=logging.ERROR,
            target=file_handler
        )

        # Console handler for immediate feedback
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)

        # Setup root logger
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s",
            handlers=[memory_handler, console_handler]
        )

        # Start periodic flush thread
        self._start_periodic_flush(memory_handler)

        logging.info(f"Logging to {log_file} with wear leveling: {self.config.WEAR_LEVELING}")

    def _get_wear_leveled_log_path(self) -> Path:
        """Get wear-leveled log path based on current date"""
        today = datetime.now()
        week_of_year = today.isocalendar()[1]

        # Rotate directory every 2 weeks to spread wear
        dir_suffix = f"week_{week_of_year // 2}"
        return Path(self.config.LOG_PATH).parent / dir_suffix

    def _start_periodic_flush(self, memory_handler: MemoryHandler):
        """Start periodic flush thread to prevent log loss"""
        def flush_logs():
            while True:
                time.sleep(self.config.DISK_SYNC_INTERVAL)
                try:
                    memory_handler.flush()
                    logging.debug("Periodic log flush completed")
                except Exception as e:
                    logging.error(f"Error during periodic log flush: {e}")

        flush_thread = threading.Thread(target=flush_logs, daemon=True)
        flush_thread.start()

# ---------------------------------------------------------------------
# Sensor Management
# ---------------------------------------------------------------------
class SensorManager:
    """Manages temperature sensor discovery and reading"""

    def __init__(self, config: SensorConfig):
        self.config = config
        self.sensors = {}
        self.offsets = {}

    def _probe_mapping(self) -> Dict[str, Optional[str]]:
        return {
            'helium_in': self.config.PROBE_IN_ID,
            'helium_out': self.config.PROBE_OUT_ID,
            'primary_in': self.config.PROBE_PRIMARY_IN_ID,
            'primary_out': self.config.PROBE_PRIMARY_OUT_ID,
            'room': self.config.PROBE_ROOM_ID,
        }

    def _required_sensor_names(self) -> List[str]:
        return ['helium_in', 'helium_out', 'primary_in', 'primary_out']

    def initialize_sensors(self) -> bool:
        """Initialize and match sensors to probe IDs"""
        try:
            # Load sensor offsets
            self._load_sensor_offsets()

            return self.refresh_sensor_mappings(
                reason="startup",
                timeout_sec=self.config.SENSOR_DISCOVERY_TIMEOUT_SEC,
                interval_sec=self.config.SENSOR_DISCOVERY_INTERVAL_SEC,
            )

        except Exception as e:
            logging.error(f"Error initializing sensors: {e}")
            return False

    def refresh_sensor_mappings(self, reason: str, timeout_sec: int, interval_sec: int) -> bool:
        """Refresh sensor mappings, retrying for a bounded interval when probes enumerate slowly."""
        deadline = time.monotonic() + max(timeout_sec, 0)
        attempt = 0
        last_missing: List[str] = []

        while True:
            attempt += 1
            available_sensors = W1ThermSensor.get_available_sensors()
            available_ids = [f"28-{sensor.id}" for sensor in available_sensors]
            self.sensors = {}

            logging.info(
                "Sensor discovery attempt %s for %s found %s temperature sensors",
                attempt,
                reason,
                len(available_sensors),
            )

            missing_sensors = self._match_sensors_to_probes(available_sensors)
            if not missing_sensors:
                if attempt > 1:
                    logging.info(
                        "Sensor discovery for %s recovered after %s attempts",
                        reason,
                        attempt,
                    )
                return True

            last_missing = missing_sensors
            remaining = deadline - time.monotonic()
            if remaining <= 0 or interval_sec <= 0:
                logging.error(
                    "Sensor discovery for %s failed after %s attempts; missing required sensors: %s; available IDs: %s",
                    reason,
                    attempt,
                    last_missing,
                    available_ids,
                )
                return False

            sleep_for = min(interval_sec, remaining)
            logging.warning(
                "Sensor discovery for %s missing %s; available IDs: %s; retrying in %.1fs",
                reason,
                ", ".join(last_missing),
                available_ids,
                sleep_for,
            )
            time.sleep(sleep_for)

    def _load_sensor_offsets(self):
        """Load sensor offsets from file"""
        try:
            if self.config.OFFSET_FILE_PATH.exists():
                with open(self.config.OFFSET_FILE_PATH, 'r') as f:
                    self.offsets = json.load(f)
                logging.info(f"Loaded {len(self.offsets)} sensor offsets")
            else:
                logging.info("No sensor offsets file found - using zero offsets")
        except Exception as e:
            logging.error(f"Error loading sensor offsets: {e}")
            self.offsets = {}

    def _match_sensors_to_probes(self, available_sensors: List[W1ThermSensor]) -> List[str]:
        """Match available sensors to configured probe IDs"""
        probe_mapping = self._probe_mapping()

        for sensor in available_sensors:
            # w1thermsensor returns ID without the "28-" prefix, but our config has it
            sensor_id_full = f"28-{sensor.id}"

            # Match sensor to probe
            for probe_name, probe_id in probe_mapping.items():
                if probe_id and sensor_id_full == probe_id:
                    self.sensors[probe_name] = sensor
                    logging.info(f"Matched {probe_name} sensor: {sensor_id_full}")
                    break

        # Validate required sensors
        return [name for name in self._required_sensor_names() if name not in self.sensors]

    def read_sensor_temperature(self, sensor_name: str) -> Optional[float]:
        """Read temperature from a specific sensor with offset correction"""
        if sensor_name not in self.sensors:
            return None

        try:
            sensor = self.sensors[sensor_name]
            temperature = sensor.get_temperature()

            # Apply offset correction
            # Note: offsets are stored with the full ID including "28-" prefix
            sensor_id = sensor.id
            sensor_id_full = f"28-{sensor_id}"
            offset = self.offsets.get(sensor_id_full, 0.0)
            corrected_temperature = temperature + offset

            logging.debug(f"Sensor {sensor_name} ({sensor_id_full}): {temperature:.2f}°C + {offset:.2f}°C = {corrected_temperature:.2f}°C")

            return corrected_temperature

        except Exception as e:
            logging.error(f"Error reading sensor {sensor_name}: {e}")
            return None

    def read_all_sensors(self) -> Dict[str, Optional[float]]:
        """Read all configured sensors"""
        readings = {}

        for sensor_name in self.sensors.keys():
            readings[sensor_name] = self.read_sensor_temperature(sensor_name)

        return readings

# ---------------------------------------------------------------------
# Sensor Calibration
# ---------------------------------------------------------------------
class SensorCalibrator:
    """Handles sensor calibration and offset management"""

    def __init__(self, config: SensorConfig, sensor_manager: SensorManager):
        self.config = config
        self.sensor_manager = sensor_manager

    def calibrate_sensor(self, sensor_name: str, reference_temperature: float) -> bool:
        """Calibrate a sensor against a reference temperature"""
        if sensor_name not in self.sensor_manager.sensors:
            logging.error(f"Sensor {sensor_name} not found")
            return False

        try:
            # Read current sensor value
            current_reading = self.sensor_manager.read_sensor_temperature(sensor_name)
            if current_reading is None:
                logging.error(f"Failed to read sensor {sensor_name}")
                return False

            # Calculate offset
            sensor_id = self.sensor_manager.sensors[sensor_name].id
            sensor_id_full = f"28-{sensor_id}"
            offset = reference_temperature - current_reading

            # Update offset with full ID
            self.sensor_manager.offsets[sensor_id_full] = offset

            # Save offsets
            self._save_sensor_offsets()

            logging.info(f"Calibrated sensor {sensor_name} ({sensor_id_full}): offset = {offset:.2f}°C")
            return True

        except Exception as e:
            logging.error(f"Error calibrating sensor {sensor_name}: {e}")
            return False

    def _save_sensor_offsets(self):
        """Save sensor offsets to file"""
        try:
            with open(self.config.OFFSET_FILE_PATH, 'w') as f:
                json.dump(self.sensor_manager.offsets, f, indent=2)
            logging.info(f"Saved sensor offsets to {self.config.OFFSET_FILE_PATH}")
        except Exception as e:
            logging.error(f"Error saving sensor offsets: {e}")

# ---------------------------------------------------------------------
# Data Collection and Processing
# ---------------------------------------------------------------------
class SensorReader:
    """Handles sensor data collection and averaging"""

    def __init__(self, config: SensorConfig, sensor_manager: SensorManager):
        self.config = config
        self.sensor_manager = sensor_manager
        self.reading_history = {}
        self.invalid_cycle_count = 0

        # Initialize history buffers
        for sensor_name in ['helium_in', 'helium_out', 'primary_in', 'primary_out', 'room']:
            self.reading_history[sensor_name] = deque(maxlen=config.AVG_WINDOW)

    def _required_targets(self) -> List[str]:
        required_targets = ['helium_in', 'helium_out', 'primary_in', 'primary_out']
        if self.config.PROBE_ROOM_ID:
            required_targets.append('room')
        return required_targets

    def _find_invalid_targets(self, readings: Dict[str, Optional[float]]) -> List[str]:
        return [
            sensor_name for sensor_name in self._required_targets()
            if sensor_name not in self.sensor_manager.sensors or readings.get(sensor_name) is None
        ]

    def collect_sensor_readings(self) -> Dict[str, Optional[float]]:
        """Collect sensor readings and calculate averages"""
        readings = self.sensor_manager.read_all_sensors()

        invalid_targets = self._find_invalid_targets(readings)
        if invalid_targets:
            for sensor_name in invalid_targets:
                self.reading_history[sensor_name].clear()

            recovered = self.sensor_manager.refresh_sensor_mappings(
                reason=f"runtime invalid readings for {', '.join(invalid_targets)}",
                timeout_sec=self.config.SENSOR_RESCAN_TIMEOUT_SEC,
                interval_sec=self.config.SENSOR_RESCAN_INTERVAL_SEC,
            )
            if recovered:
                readings = self.sensor_manager.read_all_sensors()
                invalid_targets = self._find_invalid_targets(readings)

            if invalid_targets:
                for sensor_name in invalid_targets:
                    self.reading_history[sensor_name].clear()

        if invalid_targets:
            self.invalid_cycle_count += 1
            logging.warning(
                "Invalid sensor read cycle %s for %s",
                self.invalid_cycle_count,
                ", ".join(invalid_targets),
            )
            if self.invalid_cycle_count >= self.config.INVALID_SENSOR_RESTART_THRESHOLD:
                raise RuntimeError(
                    "Repeated invalid sensor reads for "
                    + ", ".join(invalid_targets)
                    + f" across {self.invalid_cycle_count} cycles"
                )
        else:
            self.invalid_cycle_count = 0

        # Add readings to history
        for sensor_name, reading in readings.items():
            if reading is not None:
                self.reading_history[sensor_name].append(reading)

        # Calculate averages
        averages = {}
        for sensor_name, history in self.reading_history.items():
            if history:
                averages[sensor_name] = sum(history) / len(history)
            else:
                averages[sensor_name] = None

        return averages

# ---------------------------------------------------------------------
# Data Publishing
# ---------------------------------------------------------------------
class DataPublisher:
    """Handles publishing sensor data to backend"""

    def __init__(self, config: SensorConfig):
        self.config = config
        self.session = requests.Session()
        self.session.timeout = 30

    def publish_data(self, sensor_data: Dict[str, Optional[float]]) -> bool:
        """Publish sensor data to backend"""
        if not self.config.BACKEND_URL:
            logging.error("BACKEND_URL not configured")
            return False

        try:
            # Build payload
            payload = self._build_payload(sensor_data)

            # Send to backend
            response = self.session.post(
                self.config.BACKEND_URL,
                json=payload,
                timeout=30
            )

            if response.status_code in [200, 201]:
                logging.debug("Data published to production successfully")

                # Send heartbeat to alerter service if configured
                self._send_heartbeat(payload)

                # Send to development backend if dual streaming is enabled
                if self.config.ENABLE_DUAL_STREAMING and self.config.DEV_BACKEND_URL:
                    self._send_to_dev_backend(payload)

                return True
            else:
                logging.error(f"Failed to publish data: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logging.error(f"Error publishing data: {e}")
            return False

    def _build_payload(self, sensor_data: Dict[str, Optional[float]]) -> Dict[str, Any]:
        """Build payload for backend API"""
        # Calculate delta temperatures
        helium_in = sensor_data.get('helium_in')
        helium_out = sensor_data.get('helium_out')
        primary_in = sensor_data.get('primary_in')
        primary_out = sensor_data.get('primary_out')

        helium_delta = (
            helium_out - helium_in
            if helium_in is not None and helium_out is not None
            else None
        )
        primary_delta = (
            primary_out - primary_in
            if primary_in is not None and primary_out is not None
            else None
        )

        return {
            "site_id": f"{self.config.SITE_NAME}{self.config.SCANNER_ID}",
            "timestamp": int(datetime.now(timezone.utc).timestamp()),
            "helium_in": helium_in,
            "helium_out": helium_out,
            "helium_delta": helium_delta,
            "primary_in": primary_in,
            "primary_out": primary_out,
            "primary_delta": primary_delta,
            "room_temp": sensor_data.get('room'),
            "secondary_in": 0.0,  # Not used
            "secondary_out": 0.0,  # Not used
        }

    def _send_heartbeat(self, payload: Dict[str, Any]):
        """Send heartbeat to alerter service for Pi monitoring"""
        if not self.config.ALERTER_METRICS_URL:
            return

        try:
            # Send heartbeat with basic info for Pi monitoring
            heartbeat_payload = {
                "SiteID": payload.get("site_id"),
                "Timestamp": payload.get("timestamp"),
                "Pi_IP": self._get_pi_ip()
            }

            response = self.session.post(
                self.config.ALERTER_METRICS_URL,
                json=heartbeat_payload,
                timeout=5
            )

            if response.status_code in [200, 201]:
                logging.debug("Heartbeat sent to alerter service")
            else:
                logging.warning(f"Alerter heartbeat failed: {response.status_code}")

        except Exception as e:
            # Don't fail the main metric publish if alerter is down
            logging.debug(f"Could not send heartbeat to alerter: {e}")

    def _get_pi_ip(self) -> str:
        """Get the Pi's IP address"""
        try:
            import socket
            # Connect to a remote address to determine local IP
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return "unknown"

    def _send_to_dev_backend(self, payload: Dict[str, Any]):
        """Send data to development backend (non-blocking)"""
        try:
            # Create a copy of the payload
            dev_payload = payload.copy()

            # Send to development backend with shorter timeout
            response = self.session.post(
                self.config.DEV_BACKEND_URL,
                json=dev_payload,
                timeout=5  # Shorter timeout for dev
            )

            if response.status_code in [200, 201]:
                logging.debug("Data published to development successfully")
            else:
                logging.warning(f"Failed to publish to dev: {response.status_code}")

        except Exception as e:
            # Don't fail the main publish if dev backend is down
            logging.debug(f"Could not send to dev backend: {e}")

# ---------------------------------------------------------------------
# Main Application
# ---------------------------------------------------------------------
class PiSensorApplication:
    """Main application class"""

    def __init__(self):
        self.config = SensorConfig()
        self.logging_manager = LoggingManager(self.config)
        self.sensor_manager = SensorManager(self.config)
        self.sensor_calibrator = SensorCalibrator(self.config, self.sensor_manager)
        self.sensor_reader = SensorReader(self.config, self.sensor_manager)
        self.data_publisher = DataPublisher(self.config)

    def initialize(self) -> bool:
        """Initialize the application"""
        # Setup logging
        self.logging_manager.setup_logging()

        # Validate configuration
        if not self.config.validate():
            logging.error("Configuration validation failed")
            return False

        # Initialize sensors
        if not self.sensor_manager.initialize_sensors():
            logging.error("Sensor initialization failed")
            return False

        logging.info("Pi sensor application initialized successfully")
        return True

    def run(self):
        """Main application loop"""
        logging.info("Starting Pi sensor data collection")

        try:
            while True:
                # Collect sensor readings
                sensor_data = self.sensor_reader.collect_sensor_readings()

                # Log readings
                self._log_readings(sensor_data)

                # Publish data
                if not self.data_publisher.publish_data(sensor_data):
                    logging.warning("Failed to publish data - will retry next cycle")

                # Wait for next cycle
                time.sleep(self.config.POLL_SEC)

        except KeyboardInterrupt:
            logging.info("Shutting down Pi sensor application")
        except Exception as e:
            logging.error(f"Unexpected error in main loop: {e}")
            raise

    def _log_readings(self, sensor_data: Dict[str, float]):
        """Log sensor readings"""
        helium_in = sensor_data.get('helium_in')
        helium_out = sensor_data.get('helium_out')
        primary_in = sensor_data.get('primary_in')
        primary_out = sensor_data.get('primary_out')
        room = sensor_data.get('room')

        helium_delta = (
            helium_out - helium_in
            if helium_in is not None and helium_out is not None
            else None
        )
        primary_delta = (
            primary_out - primary_in
            if primary_in is not None and primary_out is not None
            else None
        )

        def _fmt(value: Optional[float]) -> str:
            return f"{value:.1f}°C" if value is not None else "missing"

        logging.info(
            f"Helium: {_fmt(helium_in)} → {_fmt(helium_out)} "
            f"(Δ{_fmt(helium_delta)}) | "
            f"Primary: {_fmt(primary_in)} → {_fmt(primary_out)} "
            f"(Δ{_fmt(primary_delta)}) | "
            f"Room: {_fmt(room)}"
        )

# ---------------------------------------------------------------------
# Calibration Functions
# ---------------------------------------------------------------------
def perform_calibration(num_samples=20, delay_between_samples_sec=5):
    """Performs automatic calibration by normalizing all sensors to the same temperature."""
    config = SensorConfig()
    logging_manager = LoggingManager(config)
    logging_manager.setup_logging()

    logging.info("Starting automatic calibration process...")
    logging.info("This will normalize all sensors to read the same temperature.")

    try:
        available_sensors = W1ThermSensor.get_available_sensors()
        logging.info(f"Found {len(available_sensors)} available sensors for calibration.")

        # Initialize sensor objects
        sensors_to_calibrate = {}

        for sensor in available_sensors:
            # w1thermsensor returns ID without the "28-" prefix, but our config has it
            sensor_id_full = f"28-{sensor.id}"
            logging.info(f"Checking sensor: {sensor_id_full}")

            if sensor_id_full == config.PROBE_IN_ID:
                sensors_to_calibrate["Helium In"] = (sensor, config.PROBE_IN_ID)
                logging.info(f"  -> Matched as Helium In")
            elif sensor_id_full == config.PROBE_OUT_ID:
                sensors_to_calibrate["Helium Out"] = (sensor, config.PROBE_OUT_ID)
                logging.info(f"  -> Matched as Helium Out")
            elif sensor_id_full == config.PROBE_PRIMARY_IN_ID:
                sensors_to_calibrate["Primary In"] = (sensor, config.PROBE_PRIMARY_IN_ID)
                logging.info(f"  -> Matched as Primary In")
            elif sensor_id_full == config.PROBE_PRIMARY_OUT_ID:
                sensors_to_calibrate["Primary Out"] = (sensor, config.PROBE_PRIMARY_OUT_ID)
                logging.info(f"  -> Matched as Primary Out")
            elif sensor_id_full == config.PROBE_ROOM_ID:
                sensors_to_calibrate["Room"] = (sensor, config.PROBE_ROOM_ID)
                logging.info(f"  -> Matched as Room")

        if not sensors_to_calibrate:
            logging.error("No configured sensors found for calibration!")
            logging.info("Available sensor IDs:")
            for sensor in available_sensors:
                logging.info(f"  - 28-{sensor.id}")
            logging.info("Configured sensor IDs in .env:")
            logging.info(f"  - PROBE_IN_ID: {config.PROBE_IN_ID}")
            logging.info(f"  - PROBE_OUT_ID: {config.PROBE_OUT_ID}")
            logging.info(f"  - PROBE_PRIMARY_IN_ID: {config.PROBE_PRIMARY_IN_ID}")
            logging.info(f"  - PROBE_PRIMARY_OUT_ID: {config.PROBE_PRIMARY_OUT_ID}")
            logging.info(f"  - PROBE_ROOM_ID: {config.PROBE_ROOM_ID}")
            return

        logging.info("\nEnsure all sensors are at the same temperature (e.g., in the same room/container).")
        input("Press Enter when ready to start calibration...")

        # Collect samples
        samples = {name: [] for name in sensors_to_calibrate}

        for i in range(num_samples):
            logging.info(f"Collecting sample {i+1}/{num_samples}...")

            for name, (sensor, sensor_id) in sensors_to_calibrate.items():
                try:
                    temp = sensor.get_temperature()
                    samples[name].append(temp)
                    logging.info(f"  {name}: {temp:.2f}°C")
                except Exception as e:
                    logging.error(f"  Error reading {name}: {e}")

            if i < num_samples - 1:
                time.sleep(delay_between_samples_sec)

        # Calculate averages for each sensor
        sensor_averages = {}
        for name, (sensor, sensor_id) in sensors_to_calibrate.items():
            if samples[name]:
                avg_temp = sum(samples[name]) / len(samples[name])
                sensor_averages[name] = (sensor_id, avg_temp)

        # Calculate the overall average temperature (reference temperature)
        all_temps = []
        for name, (sensor_id, avg_temp) in sensor_averages.items():
            all_temps.append(avg_temp)

        if not all_temps:
            logging.error("No valid temperature readings collected!")
            return

        reference_temp = sum(all_temps) / len(all_temps)

        # Calculate offsets to normalize all sensors to the reference temperature
        new_offsets = {}

        logging.info("\nCalibration Results:")
        logging.info("=" * 50)
        logging.info(f"Reference temperature (average of all sensors): {reference_temp:.2f}°C")
        logging.info("\nSensor calibration offsets:")

        for name, (sensor_id, avg_temp) in sensor_averages.items():
            # Offset = reference_temp - sensor_reading (so corrected = raw + offset)
            offset = reference_temp - avg_temp
            new_offsets[sensor_id] = round(offset, 2)

            logging.info(f"\n{name}:")
            logging.info(f"  Average reading: {avg_temp:.2f}°C")
            logging.info(f"  Offset: {offset:+.2f}°C")
            logging.info(f"  After calibration will read: {avg_temp + offset:.2f}°C")

        # Save offsets to file atomically
        _save_sensor_offsets_atomic(config.OFFSET_FILE_PATH, new_offsets)

        logging.info(f"\nCalibration complete! Offsets saved to {config.OFFSET_FILE_PATH}")
        logging.info(f"All sensors will now read approximately {reference_temp:.2f}°C when at the same temperature.")

        # Show the offset file content
        logging.info(f"\nOffset file content: {new_offsets}")

    except Exception as e:
        logging.error(f"Calibration failed: {e}")
        import traceback
        traceback.print_exc()

def _save_sensor_offsets_atomic(offset_file_path: Path, offsets: Dict[str, float]):
    """Save sensor offsets to file atomically"""
    try:
        # Write to temporary file first
        temp_file = offset_file_path.with_suffix('.tmp')
        with open(temp_file, 'w') as f:
            json.dump(offsets, f, indent=2)

        # Atomically replace the original file
        temp_file.replace(offset_file_path)
        logging.info(f"Saved sensor offsets to {offset_file_path}")
    except Exception as e:
        logging.error(f"Error saving sensor offsets: {e}")

# ---------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------
def main():
    """Main entry point"""
    app = PiSensorApplication()

    if not app.initialize():
        logging.error("Failed to initialize application")
        return 1

    try:
        app.run()
        return 0
    except Exception as e:
        logging.error(f"Application error: {e}")
        return 1

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--calibrate":
        perform_calibration()
    else:
        exit(main())
