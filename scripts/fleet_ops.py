#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml


FACTS_SCRIPT = r"""python3 - <<'EOF'
import ast
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit


def sh(cmd: str) -> str:
    return subprocess.run(cmd, shell=True, text=True, capture_output=True).stdout.strip()


def read_text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def directory_bytes(path: str) -> int | None:
    value = sh(f"du -sb {path} 2>/dev/null | awk '{{print $1}}'")
    try:
        return int(value)
    except ValueError:
        return None


def file_sha256(path: str) -> str:
    try:
        with open(path, "rb") as handle:
            digest = hashlib.sha256()
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
            return digest.hexdigest()
    except OSError:
        return ""


def file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def service_state(name: str) -> dict:
    return {
        "active": sh(f"systemctl is-active {name} 2>/dev/null || true"),
        "enabled": sh(f"systemctl is-enabled {name} 2>/dev/null || true"),
    }


def service_details(name: str) -> dict:
    details = service_state(name)
    for key in (
        "FragmentPath", "User", "Group", "WorkingDirectory", "ExecStart",
        "Restart", "RestartUSec", "StartLimitIntervalUSec", "StartLimitBurst",
        "MainPID", "ActiveEnterTimestampMonotonic", "DropInPaths",
        "NoNewPrivileges", "PrivateTmp", "ProtectSystem", "ProtectHome",
    ):
        details[key.lower()] = sh(f"systemctl show {name} -p {key} --value 2>/dev/null")
    fragment = details.get("fragmentpath", "")
    details["unit_verify"] = sh(
        f"systemd-analyze verify {fragment} 2>&1" if fragment and Path(fragment).is_file() else "true"
    )
    return details


BASE_PACKAGES = ("python3", "python3-venv", "python3-pip", "git", "cron", "rsync")
SUPPORT_PACKAGES = (
    "ca-certificates",
    "curl",
    "jq",
    "network-manager",
    "openssh-server",
    "rsyslog",
    "tailscale",
)
REQUIRED_OPERATIONAL_PACKAGES = BASE_PACKAGES + SUPPORT_PACKAGES
OPTIONAL_DIAGNOSTIC_PACKAGES = ("ethtool", "iw", "nvme-cli", "smartmontools")
BACKGROUND_SERVICES = (
    "gdm.service",
    "cups.service",
    "cups-browsed.service",
    "bluetooth.service",
    "avahi-daemon.service",
    "ModemManager.service",
    "colord.service",
    "fwupd.service",
    "rsyslog.service",
)


def package_versions(names: tuple[str, ...]) -> dict:
    versions = {}
    for name in names:
        result = subprocess.run(
            ["dpkg-query", "-W", "-f=${Status}\t${Version}", name],
            text=True,
            capture_output=True,
        )
        fields = result.stdout.strip().split("\t", 1)
        versions[name] = (
            fields[1]
            if result.returncode == 0
            and len(fields) == 2
            and fields[0] == "install ok installed"
            else None
        )
    return versions


def apt_config_value(config: str, key: str) -> str:
    value = ""
    prefix = key + " "
    for line in config.splitlines():
        if line.startswith(prefix):
            value = line[len(prefix):].strip().rstrip(";").strip('"')
    return value


SAFE_SENSOR_KEYS = {
    "SITE_ID", "SITE_NAME", "SCANNER_ID", "BACKEND_URL", "POLL_SEC", "AVG_WINDOW",
    "MEMORY_ONLY_MODE", "WEAR_LEVELING", "RAM_LOG_CAPACITY", "DISK_SYNC_INTERVAL",
    "LOG_PATH", "PROBE_IN_ID", "PROBE_OUT_ID", "PROBE_PRIMARY_IN_ID",
    "PROBE_PRIMARY_OUT_ID", "PROBE_ROOM_ID", "ONE_WIRE_GPIO_PIN",
    "SENSOR_1_ID", "SENSOR_2_ID", "SENSOR_3_ID", "SENSOR_4_ID", "SENSOR_5_ID",
    "LOG_LEVEL",
    "ENABLE_DUAL_STREAMING", "INVALID_SENSOR_RESTART_THRESHOLD",
    "SENSOR_DISCOVERY_TIMEOUT_SEC", "SENSOR_DISCOVERY_INTERVAL_SEC",
    "SENSOR_RESCAN_TIMEOUT_SEC", "SENSOR_RESCAN_INTERVAL_SEC",
    "REQUEST_TIMEOUT_SEC",
}


def sensor_config(service: dict) -> dict:
    working_dir = service.get("workingdirectory", "")
    candidates = []
    if working_dir:
        candidates.extend([Path(working_dir) / ".env", Path(working_dir) / "src" / ".env"])
    candidates.extend([
        Path.home() / "mike-mri-cooling" / ".env",
        Path.home() / "mike-mri-cooling" / "src" / ".env",
        Path("/opt/cv-room-monitor/.env"),
    ])
    values = {}
    source = ""
    for path in candidates:
        raw = read_text(str(path))
        if not raw:
            continue
        source = str(path)
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() in SAFE_SENSOR_KEYS:
                values[key.strip()] = value.strip().strip("'\"")
        if values:
            break
    return {"path": source, "values": values}


def application_details(service: dict) -> dict:
    exec_start = service.get("execstart", "")
    match = re.search(r"argv\[\]=(.+?)\s+;", exec_start)
    script_path = ""
    if match:
        for token in match.group(1).split():
            if token.endswith(".py"):
                script_path = token
    path = Path(script_path)
    if not script_path or not path.is_file():
        return {"path": script_path, "sha256": "", "size": None, "modified_epoch": None}
    try:
        payload = path.read_bytes()
        stat = path.stat()
    except OSError:
        return {"path": script_path, "sha256": "", "size": None, "modified_epoch": None}
    return {
        "path": script_path,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "normalized_sha256": hashlib.sha256(
            b"\n".join(
                line.rstrip()
                for line in payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n")
            )
        ).hexdigest(),
        "size": stat.st_size,
        "modified_epoch": int(stat.st_mtime),
        "writes_log_files": any(
            marker in payload
            for marker in (b"FileHandler", b"RotatingFileHandler", b"TimedRotatingFileHandler")
        ),
    }


def sensor_runtime_details(service: dict) -> dict:
    exec_start = service.get("execstart", "")
    executable_match = re.search(r"\bpath=([^\s;]+)", exec_start)
    executable = executable_match.group(1) if executable_match else ""
    direct_dependencies = ("python-dotenv", "requests", "w1thermsensor")
    result = {
        "executable": executable,
        "python_version": "",
        "direct_dependencies": {name: None for name in direct_dependencies},
        "complete": False,
    }
    if not executable or not os.access(executable, os.X_OK):
        return result
    probe = r'''
import importlib.metadata as metadata
import json
import sys

names = ("python-dotenv", "requests", "w1thermsensor")
versions = {}
for name in names:
    try:
        versions[name] = metadata.version(name)
    except metadata.PackageNotFoundError:
        versions[name] = None
print(json.dumps({"python_version": sys.version.split()[0], "direct_dependencies": versions}))
'''
    try:
        completed = subprocess.run(
            [executable, "-c", probe],
            text=True,
            capture_output=True,
            timeout=10,
        )
        payload = json.loads(completed.stdout) if completed.returncode == 0 else {}
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        payload = {}
    versions = payload.get("direct_dependencies")
    if isinstance(versions, dict):
        result["direct_dependencies"] = {
            name: str(versions[name]) if versions.get(name) else None
            for name in direct_dependencies
        }
    result["python_version"] = str(payload.get("python_version") or "")
    result["complete"] = all(result["direct_dependencies"].values())
    return result


def python_runtime_details(executable: Path, direct_dependencies: tuple[str, ...]) -> dict:
    # Report whether an optional Python workload can start after an OS ABI change.
    result = {
        "executable": str(executable),
        "python_version": "",
        "direct_dependencies": {name: None for name in direct_dependencies},
        "complete": False,
    }
    if not executable.is_file() or not os.access(executable, os.X_OK):
        return result
    probe = f'''\nimport importlib.metadata as metadata\nimport json\nimport sys\nnames = {direct_dependencies!r}\nversions = {{}}\nfor name in names:\n    try:\n        versions[name] = metadata.version(name)\n    except metadata.PackageNotFoundError:\n        versions[name] = None\nprint(json.dumps({{"python_version": sys.version.split()[0], "direct_dependencies": versions}}))\n'''
    try:
        completed = subprocess.run(
            [str(executable), "-c", probe], text=True, capture_output=True, timeout=10
        )
        payload = json.loads(completed.stdout) if completed.returncode == 0 else {}
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        payload = {}
    versions = payload.get("direct_dependencies")
    if isinstance(versions, dict):
        result["direct_dependencies"] = {
            name: str(versions[name]) if versions.get(name) else None
            for name in direct_dependencies
        }
    result["python_version"] = str(payload.get("python_version") or "")
    result["complete"] = all(result["direct_dependencies"].values())
    return result


def python_entrypoint_import(executable: Path, working_directory: Path, module: str) -> dict:
    result = {"module": module, "ok": False, "error": ""}
    if not executable.is_file() or not os.access(executable, os.X_OK):
        result["error"] = "runtime executable unavailable"
        return result
    try:
        completed = subprocess.run(
            [str(executable), "-c", f"import {module}"],
            cwd=working_directory,
            text=True,
            capture_output=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        result["error"] = str(exc)[-1000:]
        return result
    result["ok"] = completed.returncode == 0
    if completed.returncode:
        result["error"] = (completed.stderr or completed.stdout).strip()[-1000:]
    return result


def wifi_facts() -> list[dict]:
    interfaces = []
    for path in sorted(glob.glob("/sys/class/net/*/wireless")):
        iface = path.split("/")[-2]
        link = sh(f"iw dev {iface} link 2>/dev/null")
        signal = re.search(r"signal:\s*(-?\d+)\s*dBm", link)
        ssid = re.search(r"SSID:\s*(.+)", link)
        bssid = re.search(r"^Connected to\s+([0-9a-f:]+)", link, re.M | re.I)
        frequency = re.search(r"freq:\s*([0-9.]+)", link)
        rx = re.search(r"rx bitrate:\s*([^\n]+)", link)
        tx = re.search(r"tx bitrate:\s*([^\n]+)", link)
        power_save_match = re.search(
            r"Power save:\s*(on|off)",
            sh(f"iw dev {iface} get power_save 2>/dev/null"),
            re.I,
        )
        quality = None
        proc_wireless = read_text("/proc/net/wireless")
        quality_match = re.search(
            rf"^\s*{re.escape(iface)}:\s+\S+\s+([0-9.]+)\s+(-?[0-9.]+)",
            proc_wireless,
            re.M,
        )
        if quality_match:
            quality = float(quality_match.group(1).rstrip("."))
            if not signal:
                signal_value = float(quality_match.group(2).rstrip("."))
            else:
                signal_value = int(signal.group(1))
        else:
            signal_value = int(signal.group(1)) if signal else None
        driver = os.path.basename(os.path.realpath(f"/sys/class/net/{iface}/device/driver"))
        interfaces.append({
            "interface": iface,
            "ssid": ssid.group(1).strip() if ssid else "",
            "bssid": bssid.group(1).lower() if bssid else "",
            "signal_dbm": signal_value,
            "link_quality": quality,
            "frequency_mhz": float(frequency.group(1)) if frequency else None,
            "rx_bitrate": rx.group(1).strip() if rx else "",
            "tx_bitrate": tx.group(1).strip() if tx else "",
            "power_save": power_save_match.group(1).lower() if power_save_match else "unknown",
            "driver": driver,
            "adapter_kind": "onboard" if iface == "wlan0" and driver == "brcmfmac" else "external",
        })
    return interfaces


def sensor_offsets() -> dict:
    candidates = [
        "/opt/mri/pi-sensor/sensor_offsets.json",
        str(Path.home() / "mike-mri-cooling" / "sensor_offsets.json"),
        str(Path.home() / "mike-mri-cooling" / "src" / "sensor_offsets.json"),
        str(Path.home() / "mri-cooling" / "sensor_offsets.json"),
        str(Path.home() / "mri-cooling" / "src" / "sensor_offsets.json"),
    ]
    for path in candidates:
        raw = read_text(path)
        if not raw:
            continue
        try:
            return {"path": path, "values": json.loads(raw)}
        except json.JSONDecodeError:
            return {"path": path, "error": "invalid JSON"}
    return {"path": "", "values": {}}


SAFE_CAMERA_KEYS = {
    "SITE_ID", "CAMERA_BACKEND_URL", "CAPTURE_INTERVAL", "IMAGE_WIDTH",
    "IMAGE_HEIGHT", "UPLOAD_ENABLED", "UPLOAD_MODE", "OCR_CROP_COORDS",
    "DEBUG_SAVE_IMAGES", "CALIBRATION_MODE", "CALIBRATION_URL",
    "SHUTTER_SPEED", "GAIN", "CAPTURES_PER_SESSION",
}


def camera_details(edge_dir: Path) -> dict:
    if not edge_dir.is_dir():
        return {"installed": False, "safe_config": {}, "core_files": {}, "schedules": []}

    values = {}
    env_path = edge_dir / ".env"
    for raw_line in read_text(str(env_path)).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in SAFE_CAMERA_KEYS:
            continue
        value = value.strip().strip("'\"")
        if key.endswith("_URL"):
            try:
                parsed = urlsplit(value)
                host = parsed.hostname or ""
                if parsed.port:
                    host += f":{parsed.port}"
                value = urlunsplit((parsed.scheme, host, parsed.path, "", ""))
            except (TypeError, ValueError):
                value = "<redacted-invalid-url>"
        values[key] = value

    def normalized_camera_text(payload: bytes) -> str:
        text = payload.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
        replacements = {
            str(edge_dir): "/opt/coolmri-camera/edge",
            str(edge_dir.parent): "/opt/coolmri-camera",
        }
        site_id = values.get("SITE_ID", "")
        if site_id:
            replacements[site_id] = "<SITE_ID>"
        for old, new in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
            text = text.replace(old, new)
        return text

    def semantic_payload(path: Path, text: str) -> bytes:
        if path.suffix == ".py":
            try:
                return ast.dump(ast.parse(text), include_attributes=False).encode()
            except SyntaxError:
                pass
        normalized_lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            normalized_lines.append(stripped)
        return "\n".join(normalized_lines).encode()

    core_files = {}
    scheduled_source_text = ""
    for name in (
        "scheduled_capture.py", "retry_failed_sessions.py",
        "run_scheduled_capture.sh", "run_retry_check.sh",
        "prune_failed_sessions.py", "run_prune_failed_sessions.sh",
        "prune_failed_sessions.sh", "cleanup_old_data.sh",
    ):
        path = edge_dir / name
        try:
            payload = path.read_bytes()
        except OSError:
            continue
        normalized_text = normalized_camera_text(payload)
        if name == "scheduled_capture.py":
            scheduled_source_text = normalized_text
        details = {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "semantic_sha256": hashlib.sha256(semantic_payload(path, normalized_text)).hexdigest(),
            "size": len(payload),
        }
        if name == "scheduled_capture.py":
            version_match = re.search(
                r'^CAMERA_AGENT_VERSION\s*=\s*["\']([^"\']+)["\']',
                normalized_text,
                re.M,
            )
            if version_match:
                details["reported_version"] = version_match.group(1)
        if path.suffix == ".py":
            try:
                tree = ast.parse(normalized_text)
                details["function_semantic_sha256"] = {
                    node.name: hashlib.sha256(
                        ast.dump(node, include_attributes=False).encode()
                    ).hexdigest()
                    for node in tree.body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
            except SyntaxError:
                details["syntax_valid"] = False
        core_files[name] = details
    fingerprint_input = "\n".join(
        f"{name}:{details['sha256']}" for name, details in sorted(core_files.items())
    ).encode()
    semantic_fingerprint_input = "\n".join(
        f"{name}:{details['semantic_sha256']}" for name, details in sorted(core_files.items())
    ).encode()
    behavior_config_keys = {
        "SITE_ID", "CAMERA_BACKEND_URL", "IMAGE_WIDTH", "IMAGE_HEIGHT",
        "UPLOAD_ENABLED", "UPLOAD_MODE", "OCR_CROP_COORDS",
        "DEBUG_SAVE_IMAGES", "SHUTTER_SPEED", "GAIN", "CAPTURES_PER_SESSION",
    }
    direct_env_keys = set(re.findall(
        r"os\.getenv\(\s*['\"]([A-Z0-9_]+)['\"]",
        scheduled_source_text,
    ))
    direct_env_keys.update(re.findall(
        r"env_(?:bool|int)\(\s*['\"]([A-Z0-9_]+)['\"]",
        scheduled_source_text,
    ))
    config_mapping_unknown = "load_config" in scheduled_source_text
    ignored_safe_keys = (
        []
        if config_mapping_unknown
        else sorted(
            key for key in values
            if key in behavior_config_keys and key not in direct_env_keys
        )
    )

    cron_sources = []
    try:
        user_cron = subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True, timeout=5
        ).stdout
        cron_sources.append(("user", user_cron))
    except (OSError, subprocess.TimeoutExpired):
        pass
    for path in sorted(Path("/etc/cron.d").glob("*")):
        raw = read_text(str(path))
        if raw:
            cron_sources.append((f"cron.d/{path.name}", raw))

    schedules = []
    edge_text = str(edge_dir)
    for source, raw in cron_sources:
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or edge_text not in stripped:
                continue
            fields = stripped.split()
            command_index = next(
                (index for index, field in enumerate(fields) if edge_text in field), None
            )
            if command_index is None or len(fields) < 6:
                continue
            runner = Path(fields[command_index]).name
            numeric_arguments = []
            for field in fields[command_index + 1:]:
                if field.startswith(">") or field in {"2>&1", "&>"}:
                    break
                if field.isdigit():
                    numeric_arguments.append(field)
            schedules.append({
                "source": source,
                "schedule": " ".join(fields[:5]),
                "runner": runner,
                "numeric_arguments": numeric_arguments,
            })

    return {
        "installed": True,
        "safe_config": values,
        "core_files": core_files,
        "fingerprint": hashlib.sha256(fingerprint_input).hexdigest() if core_files else "",
        "semantic_fingerprint": hashlib.sha256(semantic_fingerprint_input).hexdigest() if core_files else "",
        "direct_env_keys": sorted(direct_env_keys),
        "ignored_safe_config_keys": ignored_safe_keys,
        "config_mapping_unknown": config_mapping_unknown,
        "schedules": schedules,
    }


macs = {}
for path in sorted(glob.glob("/sys/class/net/*/address")):
    iface = path.split("/")[-2]
    try:
        with open(path, encoding="utf-8") as handle:
            macs[iface] = handle.read().strip()
    except OSError:
        pass

disk = shutil.disk_usage("/")
run_disk = shutil.disk_usage("/run")
meminfo = {}
for line in read_text("/proc/meminfo").splitlines():
    key, separator, value = line.partition(":")
    if not separator:
        continue
    match = re.match(r"\s*(\d+)", value)
    if match:
        meminfo[key] = int(match.group(1)) * 1024
memory_total_bytes = meminfo.get("MemTotal", 0)
memory_available_bytes = meminfo.get("MemAvailable", 0)
swap_total_bytes = meminfo.get("SwapTotal", 0)
swap_free_bytes = meminfo.get("SwapFree", 0)
swap_devices = []
for row in read_text("/proc/swaps").splitlines()[1:]:
    fields = row.split()
    if fields:
        swap_devices.append({
            "device": Path(fields[0]).name,
            "kind": fields[1] if len(fields) > 1 else "",
        })
kernel_oom_events = sh(
    "timeout 10s journalctl -k -b --no-pager -n 5000 2>/dev/null | "
    "grep -Ec 'Out of memory:|Killed process .* total-vm' || true"
)
try:
    oom_events_since_boot = int(kernel_oom_events or 0)
except ValueError:
    oom_events_since_boot = 0
cpu_temp_raw = read_text("/sys/class/thermal/thermal_zone0/temp")
try:
    cpu_temp_c = round(float(cpu_temp_raw) / 1000, 1)
except (TypeError, ValueError):
    cpu_temp_c = None

mounts = read_text("/proc/mounts")
root_source = sh("findmnt -n -o SOURCE / 2>/dev/null")
root_fstype = sh("findmnt -n -o FSTYPE / 2>/dev/null")
root_options = sh("findmnt -n -o OPTIONS / 2>/dev/null")
boot_config = "\n".join(
    read_text(path)
    for path in sorted(glob.glob("/boot/firmware/*.txt") + glob.glob("/boot/*.txt"))
)
one_wire_ids = [Path(path).name for path in sorted(glob.glob("/sys/bus/w1/devices/28-*"))]
sensor_service = service_details("mri-sensor.service")
cv_sensor_service = service_details("cv-room-sensor.service")
expected_service = cv_sensor_service if cv_sensor_service.get("active") == "active" else sensor_service
effective_sensor_config = sensor_config(expected_service)
application = application_details(expected_service)
sensor_runtime = sensor_runtime_details(expected_service)
privileged_status_raw = sh("sudo -n /usr/local/sbin/coolmri-pi-status 2>/dev/null")
privileged_status = {}
for status_line in privileged_status_raw.splitlines():
    key, separator, value = status_line.partition("=")
    if separator and key in {"one_wire_pin", "pin_state", "throttled"}:
        privileged_status[key] = value
configured_pin = effective_sensor_config.get("values", {}).get("ONE_WIRE_GPIO_PIN", "")
if not configured_pin:
    pin_match = re.search(r"^\s*dtoverlay=w1-gpio(?:[^\n]*?gpiopin=(\d+))?", boot_config, re.M)
    configured_pin = (pin_match.group(1) if pin_match and pin_match.group(1) else "4")
configured_pin = privileged_status.get("one_wire_pin") or configured_pin
camera_services = {}
for unit in ["mri-camera-edge.service", "camera-ocr.service", "camera.service"]:
    state = service_state(unit)
    if state["active"] not in {"", "unknown", "inactive"} or state["enabled"] not in {"", "not-found", "disabled"}:
        camera_services[unit] = state

throttled_raw = privileged_status.get("throttled") or sh("vcgencmd get_throttled 2>/dev/null")
throttled_match = re.search(r"0x([0-9a-fA-F]+)", throttled_raw)
throttled = int(throttled_match.group(1), 16) if throttled_match else None
uptime_raw = read_text("/proc/uptime").split()
uptime_seconds = int(float(uptime_raw[0])) if uptime_raw else None
load_parts = read_text("/proc/loadavg").split()
root_parent = sh(f"lsblk -ndo PKNAME {root_source} 2>/dev/null")
root_block = root_parent or Path(root_source).name
block_stat_parts = read_text(f"/sys/class/block/{root_block}/stat").split()
try:
    sectors_written = int(block_stat_parts[6])
except (IndexError, ValueError):
    sectors_written = None
try:
    block_identity_raw = sh(
        f"lsblk -J -b -d -o NAME,TRAN,MODEL,SERIAL,SIZE /dev/{root_block} 2>/dev/null"
    )
    block_identity = (json.loads(block_identity_raw).get("blockdevices") or [{}])[0]
except (json.JSONDecodeError, IndexError):
    block_identity = {}
bytes_written_since_boot = sectors_written * 512 if sectors_written is not None else None
average_mib_written_per_day = (
    round(bytes_written_since_boot / 1048576 / uptime_seconds * 86400, 1)
    if bytes_written_since_boot is not None and uptime_seconds
    else None
)
storage_smart_raw = sh("sudo -n /usr/local/sbin/coolmri-storage-health 2>/dev/null")
try:
    storage_smart = json.loads(storage_smart_raw) if storage_smart_raw else {}
except json.JSONDecodeError:
    storage_smart = {}
camera_edge_dir = Path.home() / "mri-cooling-camera" / "edge"
camera_software = camera_details(camera_edge_dir)
camera_runtime = python_runtime_details(
    camera_edge_dir.parent / "venv" / "bin" / "python3",
    ("numpy", "Pillow", "python-dotenv", "requests"),
)
camera_entrypoint = python_entrypoint_import(
    camera_edge_dir.parent / "venv" / "bin" / "python3",
    camera_edge_dir,
    "scheduled_capture",
) if camera_edge_dir.is_dir() else {"module": "scheduled_capture", "ok": False, "error": "camera not installed"}
camera_runtime["entrypoint_import"] = camera_entrypoint
camera_runtime["complete"] = bool(camera_runtime.get("complete") and camera_entrypoint.get("ok"))
camera_logs_dir = camera_edge_dir / "logs"
camera_failed_dir = camera_edge_dir / "failed_sessions"
camera_log_target = str(camera_logs_dir.resolve()) if camera_logs_dir.exists() else ""
camera_log_bytes = directory_bytes(camera_log_target) if camera_log_target else 0
camera_logs_memory_only = bool(
    camera_logs_dir.is_symlink()
    and (camera_log_target == "/run" or camera_log_target.startswith("/run/"))
)
camera_failed_sessions = len(list(camera_failed_dir.glob("*"))) if camera_failed_dir.is_dir() else 0
journald_effective_config = sh("systemd-analyze cat-config systemd/journald.conf 2>/dev/null")
journald_volatile = bool(re.search(r"^Storage=volatile\s*$", journald_effective_config, re.M))
def restricted_service_helper(path_text: str) -> dict:
    path = Path(path_text)
    result = {
        "installed": path.is_file(),
        "control": False,
        "logs": False,
        "sha256": file_sha256(path_text),
    }
    if not path.is_file():
        return result
    try:
        sensor_helper_result = subprocess.run(
            ["sudo", "-n", str(path), "status"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        result["control"] = sensor_helper_result.returncode in (0, 3)
        sensor_helper_logs_result = subprocess.run(
            ["sudo", "-n", str(path), "recent-logs"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        result["logs"] = sensor_helper_logs_result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        pass
    return result


def backup_export_helper() -> dict:
    path_text = "/usr/local/sbin/pi-backup-export"
    path = Path(path_text)
    expected_sha256 = "1e29c0c0ade513a4abae4b612c11202f1a1b7e12b32a2777960b030e4427472c"
    helper_sha256 = file_sha256(path_text)
    result = {
        "installed": path.is_file(),
        "check": False,
        "sha256": helper_sha256,
        "canonical": helper_sha256 == expected_sha256,
    }
    if not path.is_file() or helper_sha256 != expected_sha256:
        return result
    try:
        check_result = subprocess.run(
            ["sudo", "-n", path_text, "check"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        result["check"] = (
            check_result.returncode == 0
            and check_result.stdout.startswith("backup-export-ready user=")
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
    return result


mri_service_helper = restricted_service_helper("/usr/local/sbin/mri-sensor-service")
cv_service_helper = restricted_service_helper("/usr/local/sbin/cv-sensor-service")
pi_backup_export = backup_export_helper()
expected_service_helper = cv_service_helper if cv_sensor_service.get("active") == "active" else mri_service_helper
base_package_versions = package_versions(BASE_PACKAGES)
required_package_versions = package_versions(REQUIRED_OPERATIONAL_PACKAGES)
optional_diagnostic_versions = package_versions(OPTIONAL_DIAGNOSTIC_PACKAGES)
background_services = {name: service_state(name) for name in BACKGROUND_SERVICES}
snapd_version = package_versions(("snapd",)).get("snapd")
snap_stack = {
    "assessed": True,
    "installed": bool(snapd_version),
    "package_version": snapd_version,
    "responding": None,
    "listed_count": 0,
}
if snapd_version:
    try:
        snap_list = subprocess.run(
            ["timeout", "8", "snap", "list"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        snap_stack["responding"] = snap_list.returncode == 0
        if snap_stack["responding"]:
            snap_lines = [line for line in snap_list.stdout.splitlines() if line.strip()]
            snap_stack["listed_count"] = max(0, len(snap_lines) - 1)
    except OSError:
        snap_stack["responding"] = False
apt_config = sh("apt-config dump 2>/dev/null")
unattended_upgrades_version = package_versions(("unattended-upgrades",)).get(
    "unattended-upgrades"
)
held_packages = sorted(
    package for package in sh("apt-mark showhold 2>/dev/null").splitlines() if package
)
boot_current_state = read_text("/boot/firmware/current/state")
boot_new_state = read_text("/boot/firmware/new/state")
boot_current_kernel_sha256 = ""
boot_new_kernel_sha256 = ""
if boot_new_state == "unknown":
    boot_current_kernel_sha256 = file_sha256("/boot/firmware/current/vmlinuz")
    boot_new_kernel_sha256 = file_sha256("/boot/firmware/new/vmlinuz")
boot_firmware_configured = sh(
    "findmnt --fstab --evaluate -n -o SOURCE,FSTYPE,OPTIONS "
    "--target /boot/firmware 2>/dev/null"
).split(None, 2)
boot_firmware_configured_source = boot_firmware_configured[0] if boot_firmware_configured else ""
boot_firmware_configured_fstype = boot_firmware_configured[1] if len(boot_firmware_configured) > 1 else ""
boot_firmware_configured_options = boot_firmware_configured[2] if len(boot_firmware_configured) > 2 else ""
boot_firmware_source = sh("findmnt -n -o SOURCE /boot/firmware 2>/dev/null")
boot_firmware_source_read_only = None
if boot_firmware_source:
    source_ro = subprocess.run(
        ["lsblk", "-dnro", "RO", boot_firmware_source],
        text=True,
        capture_output=True,
    ).stdout.strip()
    if source_ro in {"0", "1"}:
        boot_firmware_source_read_only = source_ro == "1"
kernel_storage_events = sh(
    "timeout 10s journalctl -k -b --no-pager -n 5000 2>/dev/null | "
    "grep -E 'controller is down; will reset|faulty power saving mode enabled' || true"
)
boot_firmware_mount_events = sh(
    "timeout 10s journalctl -b -u boot-firmware.mount --no-pager -n 5000 "
    "2>/dev/null || true"
)
rsyslog_pilot_evidence_path = Path(
    "/var/lib/coolmri-fleet/rsyslog-ram-pilot.json"
)
rsyslog_pilot_applied_epoch = None
rsyslog_pilot_evidence = {}
try:
    raw_rsyslog_pilot_evidence = json.loads(
        rsyslog_pilot_evidence_path.read_text(encoding="utf-8")
    )
    if (
        raw_rsyslog_pilot_evidence.get("kind") == "rsyslog_ram_pilot"
        and raw_rsyslog_pilot_evidence.get("inventory_name")
        and raw_rsyslog_pilot_evidence.get("profile") in {"mri", "cv"}
        and isinstance(raw_rsyslog_pilot_evidence.get("applied_epoch"), int)
    ):
        rsyslog_pilot_applied_epoch = raw_rsyslog_pilot_evidence["applied_epoch"]
        rsyslog_pilot_evidence = {
            "inventory_name": str(raw_rsyslog_pilot_evidence["inventory_name"]),
            "profile": raw_rsyslog_pilot_evidence["profile"],
        }
except (OSError, ValueError, TypeError, json.JSONDecodeError):
    pass

tailscale_source_paths = [Path("/etc/apt/sources.list")]
tailscale_source_paths.extend(sorted(Path("/etc/apt/sources.list.d").glob("*.list")))
tailscale_source_paths.extend(sorted(Path("/etc/apt/sources.list.d").glob("*.sources")))
tailscale_official_source_files = []
for source_path in tailscale_source_paths:
    try:
        active_lines = [
            line.strip()
            for line in source_path.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    except OSError:
        continue
    if any("pkgs.tailscale.com/stable/" in line for line in active_lines):
        tailscale_official_source_files.append(str(source_path))

upgradable_rows = sh("LC_ALL=C apt list --upgradable 2>/dev/null | tail -n +2").splitlines()
upgradable_names = sorted({row.split("/", 1)[0] for row in upgradable_rows if "/" in row})
upgrade_simulation = sh("LC_ALL=C apt-get -s -o Debug::NoLocking=true upgrade --with-new-pkgs 2>/dev/null")
eligible_names = sorted(set(re.findall(r"^Inst\s+(\S+)", upgrade_simulation, re.M)))
deferred_names = sorted(set(upgradable_names) - set(eligible_names))
eligible_candidates = {}
for match in re.finditer(
    r"^Inst\s+(\S+)(?:\s+\[[^\]]+\])?\s+\((\S+)",
    upgrade_simulation,
    re.M,
):
    candidate_name, candidate_version = match.groups()
    eligible_candidates[candidate_name] = {
        "package": candidate_name.split(":", 1)[0],
        "version": candidate_version,
    }

apt_archive_paths = sorted(Path("/var/cache/apt/archives").glob("*.deb"))
cached_package_versions = set()
for archive_path in apt_archive_paths:
    # APT archive names are package_version_arch.deb. Versions may contain an
    # encoded epoch (for example %3a), so decode fields before comparison.
    fields = archive_path.name[:-4].rsplit("_", 2)
    if len(fields) == 3 and archive_path.stat().st_size > 0:
        cached_package_versions.add((unquote(fields[0]), unquote(fields[1])))
cache_assessed = len(eligible_candidates) == len(eligible_names)
cached_candidate_names = sorted(
    name
    for name, candidate in eligible_candidates.items()
    if (candidate["package"], candidate["version"]) in cached_package_versions
)
missing_cached_candidate_names = sorted(set(eligible_names) - set(cached_candidate_names))

print(json.dumps({
    "hostname": sh("hostname"),
    "os": sh(". /etc/os-release && printf '%s %s' \"$NAME\" \"$VERSION\""),
    "kernel": sh("uname -srmo"),
    "boot_management": {
        "firmware_mount_options": sh("findmnt -n -o OPTIONS /boot/firmware 2>/dev/null"),
        "firmware_source": boot_firmware_source,
        "firmware_configured_source": boot_firmware_configured_source,
        "firmware_configured_fstype": boot_firmware_configured_fstype,
        "firmware_configured_mount_options": boot_firmware_configured_options,
        "firmware_source_read_only": boot_firmware_source_read_only,
        "firmware_source_write_protected_at_boot": "source write-protected, mounted read-only" in boot_firmware_mount_events,
        "nvme_controller_resets_since_boot": kernel_storage_events.count("controller is down; will reset"),
        "nvme_power_saving_warning": "faulty power saving mode enabled" in kernel_storage_events,
        "piboot_try_installed": Path("/usr/sbin/piboot-try").is_file(),
        "current_state": boot_current_state,
        "new_state": boot_new_state,
        "old_state": read_text("/boot/firmware/old/state"),
        "current_kernel_sha256": boot_current_kernel_sha256,
        "new_kernel_sha256": boot_new_kernel_sha256,
    },
    "uptime": sh("uptime -p"),
    "last_boot": sh("who -b 2>/dev/null || true"),
    "tailscale_ips": sh("tailscale ip -4 2>/dev/null || true").splitlines(),
    "link_brief": sh("ip -brief link"),
    "addr_brief": sh("ip -brief addr"),
    "route": sh("ip route"),
    "macs": macs,
    "disk_root": sh("df -h /"),
    "disk": {
        "source": root_source,
        "filesystem": root_fstype,
        "options": root_options,
        "total_bytes": disk.total,
        "used_bytes": disk.used,
        "free_bytes": disk.free,
        "used_percent": round((disk.used / disk.total) * 100, 1) if disk.total else None,
        "root_read_only": "ro" in root_options.split(","),
    },
    "memory": sh("free -h"),
    "memory_bytes": {
        "total": memory_total_bytes,
        "available": memory_available_bytes,
    },
    "ram_budget": {
        "total_bytes": memory_total_bytes,
        "available_bytes": memory_available_bytes,
        "available_percent": round(
            memory_available_bytes / memory_total_bytes * 100, 1
        ) if memory_total_bytes else None,
        "swap_total_bytes": swap_total_bytes,
        "swap_used_bytes": max(0, swap_total_bytes - swap_free_bytes),
        "swap_devices": swap_devices,
        "zram_active": any(item["device"].startswith("zram") for item in swap_devices),
        "run": {
            "filesystem": sh("findmnt -n -o FSTYPE /run 2>/dev/null"),
            "options": sh("findmnt -n -o OPTIONS /run 2>/dev/null"),
            "total_bytes": run_disk.total,
            "used_bytes": run_disk.used,
            "free_bytes": run_disk.free,
            "used_percent": round(run_disk.used / run_disk.total * 100, 1) if run_disk.total else None,
        },
        "oom_events_since_boot": oom_events_since_boot,
    },
    "cpu_temp_c": cpu_temp_c,
    "load": [float(value) for value in load_parts[:3]] if len(load_parts) >= 3 else [],
    "uptime_seconds": uptime_seconds,
    "throttled_flags": throttled,
    "wifi": wifi_facts(),
    "services": {
        "mri_sensor": sensor_service,
        "cv_sensor": cv_sensor_service,
        "camera": camera_services,
        "tailscaled": service_state("tailscaled.service"),
        "cron": service_state("cron.service"),
    },
    "snap_stack": snap_stack,
    "operational_stack": {
        "architecture": sh("dpkg --print-architecture 2>/dev/null || uname -m"),
        "default_target": sh("systemctl get-default 2>/dev/null"),
        "python_version": sh("python3 --version 2>&1"),
        "systemd_version": sh("systemd --version 2>/dev/null | head -n 1"),
        "timezone": sh("timedatectl show -p Timezone --value 2>/dev/null"),
        "ntp_synchronized": sh("timedatectl show -p NTPSynchronized --value 2>/dev/null").lower() == "yes",
        "version_codename": sh(". /etc/os-release && printf '%s' \"${VERSION_CODENAME:-}\""),
        # base_packages remains for readers of pre-expansion reports. New
        # assessments use the complete required_packages support layer.
        "base_packages": base_package_versions,
        "required_packages": required_package_versions,
        "package_channels": {
            "tailscale": {
                "channel": "official_stable" if tailscale_official_source_files else "distribution",
                "official_source_configured": bool(tailscale_official_source_files),
            },
        },
        "optional_diagnostic_packages": optional_diagnostic_versions,
        "background_services": background_services,
    },
    "package_manager": {
        "busy": sh("if systemctl is-active --quiet apt-daily-upgrade.service || systemctl is-active --quiet apt-daily.service || pgrep -x apt-get >/dev/null || pgrep -x dpkg >/dev/null || pgrep -f '^/usr/bin/python3 /usr/bin/unattended-upgrade$' >/dev/null; then printf yes; else printf no; fi") == "yes",
        "active_units": sh("systemctl list-units --state=active --no-legend 'apt-daily*.service' 2>/dev/null | awk '{print $1}'").splitlines(),
    },
    "update_policy": {
        "unattended_upgrades_version": unattended_upgrades_version,
        "apt_daily_timer": service_state("apt-daily.timer"),
        "apt_daily_upgrade_timer": service_state("apt-daily-upgrade.timer"),
        "update_package_lists": apt_config_value(
            apt_config, "APT::Periodic::Update-Package-Lists"
        ),
        "unattended_upgrade": apt_config_value(
            apt_config, "APT::Periodic::Unattended-Upgrade"
        ),
        "automatic_reboot": apt_config_value(
            apt_config, "Unattended-Upgrade::Automatic-Reboot"
        ),
        "automatic_reboot_with_users": apt_config_value(
            apt_config, "Unattended-Upgrade::Automatic-Reboot-WithUsers"
        ),
        "automatic_reboot_time": apt_config_value(
            apt_config, "Unattended-Upgrade::Automatic-Reboot-Time"
        ),
        "held_packages": held_packages,
    },
    "application": application,
    "sensor_runtime": sensor_runtime,
    "restricted_helpers": {
        "sensor_service_installed": expected_service_helper["installed"],
        "sensor_service_control": expected_service_helper["control"],
        "sensor_service_logs": expected_service_helper["logs"],
        "mri_sensor_service": mri_service_helper,
        "cv_sensor_service": cv_service_helper,
        "disk_backup_installed": Path("/usr/local/sbin/mri-backup-disk").is_file(),
        "pi_backup_export": pi_backup_export,
        "pi_status_installed": Path("/usr/local/sbin/coolmri-pi-status").is_file(),
        "pi_status_readable": bool(privileged_status_raw),
        "pi_status_sha256": file_sha256("/usr/local/sbin/coolmri-pi-status"),
        "sudo_compat": {
            "installed": (Path.home() / ".local/bin/sudo-rs-ansible-compat").is_file(),
            "executable": os.access(Path.home() / ".local/bin/sudo-rs-ansible-compat", os.X_OK),
            "sha256": file_sha256(str(Path.home() / ".local/bin/sudo-rs-ansible-compat")),
        },
    },
    "sensor_config": effective_sensor_config,
    "one_wire": {
        "enabled_in_boot_config": bool(re.search(r"^\s*dtoverlay=w1-gpio", boot_config, re.M)),
        "sensor_ids": one_wire_ids,
        "count": len(one_wire_ids),
    },
    "sensor_offsets": sensor_offsets(),
    "ram_optimization": {
        "app_memory_only": (
            effective_sensor_config.get("values", {}).get("MEMORY_ONLY_MODE", "").lower() == "true"
            or not application.get("writes_log_files", False)
        ),
        "app_wear_leveling": effective_sensor_config.get("values", {}).get("WEAR_LEVELING", "").lower() == "true",
        "var_log_tmpfs": bool(re.search(r"\s/var/log\s+tmpfs\s", mounts)),
        "tmp_tmpfs": bool(re.search(r"\s/tmp\s+tmpfs\s", mounts)),
        "journald_volatile": journald_volatile,
        "persistent_journal": Path("/var/log/journal").is_dir() and not journald_volatile,
        "persistent_journal_directory": Path("/var/log/journal").is_dir(),
        "journal_runtime_max_use": next(
            (match.group(1) for match in re.finditer(r"^RuntimeMaxUse=(\S+)\s*$", journald_effective_config, re.M)),
            "",
        ),
        "journal_runtime_bytes": directory_bytes("/run/log/journal"),
        "journal_persistent_bytes": directory_bytes("/var/log/journal"),
        "journal_disk_usage": sh("journalctl --disk-usage 2>/dev/null"),
        "rsyslog_ram_pilot": {
            "evidence_available": bool(rsyslog_pilot_evidence),
            "applied_epoch": rsyslog_pilot_applied_epoch,
            **rsyslog_pilot_evidence,
        },
    },
    "gpio": {
        "one_wire_pin": configured_pin,
        "pin_state": privileged_status.get("pin_state") or sh(f"pinctrl get {configured_pin} 2>/dev/null || raspi-gpio get {configured_pin} 2>/dev/null || true"),
        "boot_overlays": sorted(set(re.findall(r"^\s*dtoverlay=([^#\s]+)", boot_config, re.M))),
    },
    "hardware": {
        "model": read_text("/proc/device-tree/model").rstrip("\x00"),
        "usb": sh("lsusb 2>/dev/null"),
    },
    "storage_health": {
        "root_block_device": root_block,
        "transport": block_identity.get("tran") or "",
        "model": (block_identity.get("model") or "").strip(),
        "serial": (block_identity.get("serial") or "").strip(),
        "size_bytes": block_identity.get("size"),
        "sectors_written_since_boot": sectors_written,
        "bytes_written_since_boot": bytes_written_since_boot,
        "average_mib_written_per_day_since_boot": average_mib_written_per_day,
        "smartctl_available": bool(sh("command -v smartctl 2>/dev/null")),
        "nvme_cli_available": bool(sh("command -v nvme 2>/dev/null")),
        "smart": storage_smart,
    },
    "camera_logging": {
        "installed": camera_edge_dir.is_dir(),
        "logs_path": str(camera_logs_dir) if camera_edge_dir.is_dir() else "",
        "logs_target": camera_log_target,
        "memory_only": camera_logs_memory_only,
        "log_bytes": camera_log_bytes,
        "failed_sessions": camera_failed_sessions,
        "retry_state_durable": camera_failed_dir.is_dir() and not str(camera_failed_dir.resolve()).startswith("/run/"),
        "software": camera_software,
        "runtime": camera_runtime,
    },
    "packages_upgradable": str(len(upgradable_names)),
    "package_maintenance": {
        "listed_count": len(upgradable_names),
        "eligible_count": len(eligible_names),
        "deferred_count": len(deferred_names),
        "eligible_names": eligible_names,
        "deferred_names": deferred_names,
    },
    "package_cache": {
        "assessed": cache_assessed,
        "complete": cache_assessed and not missing_cached_candidate_names,
        "candidate_count": len(eligible_names),
        "cached_candidate_count": len(cached_candidate_names),
        "missing_candidate_names": missing_cached_candidate_names,
        "archive_count": len(apt_archive_paths),
        "archive_bytes": sum(file_size(path) for path in apt_archive_paths),
    },
    "reboot_required": Path("/var/run/reboot-required").exists(),
}, sort_keys=True))
EOF"""

SUDO_COMPAT = '"$HOME/.local/bin/sudo-rs-ansible-compat"'

UPDATE_SCRIPT = (
    f"{SUDO_COMPAT} -S -p '' bash -lc "
    "\"apt-get update && "
    "DEBIAN_FRONTEND=noninteractive apt-get -y upgrade --with-new-pkgs && "
    "apt-get -y autoremove\""
)

DOWNLOAD_SCRIPT = (
    f"{SUDO_COMPAT} -S -p '' bash -lc "
    "\"apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=30 "
    "-o Acquire::https::Timeout=30 update && "
    "DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::Retries=3 "
    "-o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 -y --download-only "
    "upgrade --with-new-pkgs\""
)

BASELINE_BODY = """
required="python3 python3-venv python3-pip git cron rsync ca-certificates curl jq network-manager openssh-server rsyslog tailscale"
missing=""
for package in $required; do
    if ! dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -qx 'install ok installed'; then
        missing="$missing $package"
    fi
done
if [ -z "$missing" ]; then
    printf '%s\n' 'operational baseline already aligned'
else
    apt-get update && DEBIAN_FRONTEND=noninteractive apt-get -y --no-remove install $missing
fi
""".strip()
BASELINE_SCRIPT = f"{SUDO_COMPAT} -S -p '' bash -lc {shlex.quote(BASELINE_BODY)}"

REBOOT_SCRIPT = (
    f"{SUDO_COMPAT} -S -p '' bash -lc \""
    "if [ -x /usr/sbin/piboot-try ] "
    "&& [ -f /boot/firmware/new/state ] "
    "&& grep -qx unknown /boot/firmware/new/state; then "
    "mount -o remount,rw /boot/firmware "
    "&& exec /usr/sbin/piboot-try --reboot; "
    "else exec reboot; fi\""
)
DEFAULT_KEY = "/home/mlweb/.ssh/mri_pi_fleet_ed25519"
REBOOT_STABILITY_SECONDS = 30
MRI_SNAPSHOT_URL = "https://api.coolmri.com/api/sites/snapshot"
CV_SNAPSHOT_URL = "https://cv.coolmri.com/api/sites/snapshot"
BACKUP_REPOSITORIES = {
    "agcmr1": "agcmr1",
    "agcmr2": "agcmr2",
    "agcmr3": "agcmr3",
    "oswmr1": "oswmr1",
    "oswmr2": "oswmr2nvme",
    "svimr1": "svimr1",
    "svimr2": "svimr2",
    "gbh": "gbh",
    "shmr": "shmr",
    "muncymr": "muncymr",
    "jsmr": "jsmr",
    "gr": "gr",
    "pittstonsola": "pittston-sola",
    "pittstonvida": "pittston-vida",
    "gcmcsola": "gcmc-sola",
    "gcmcmr2": "gcmcmr2",
    "gswbsola": "gswb-sola",
    "gwvskyra": "gwv-skyra",
    "gmcir3": "gmcir3",
    "gmcep3": "gmcep3",
    "gmcep1and2": "gmcep1and2",
    "vwm2": "vwm2",
    "vwm3": "vwm3",
    "glh": "glh",
}
NEARBY_PILOT_HOSTS = {
    "agcmr1", "agcmr2", "agcmr3", "gmcep1and2", "gmcep3", "gmcir3",
}


def routed_wifi_signal(facts: dict) -> float | int | None:
    wifi = facts.get("wifi") or []
    route_interface = None
    for line in str(facts.get("route") or "").splitlines():
        fields = line.split()
        if fields and fields[0] == "default" and "dev" in fields:
            index = fields.index("dev") + 1
            if index < len(fields):
                route_interface = fields[index]
                break
    if route_interface:
        for item in wifi:
            if item.get("interface") == route_interface and isinstance(item.get("signal_dbm"), (int, float)):
                return item["signal_dbm"]
    signals = [item.get("signal_dbm") for item in wifi if isinstance(item.get("signal_dbm"), (int, float))]
    return max(signals) if signals else None


def configured_probe_ids(facts: dict, profile: str) -> list[str]:
    values = ((facts.get("sensor_config") or {}).get("values") or {})
    pattern = re.compile(r"^SENSOR_\d+_ID$" if profile == "cv" else r"^PROBE_.+_ID$")
    return sorted({
        str(value).strip()
        for key, value in values.items()
        if pattern.match(str(key)) and str(value).strip()
    })


def probe_recovery_evidence(facts: dict, profile: str, expected_facts: dict | None = None) -> dict:
    minimum_probes = 3 if profile == "cv" else 4
    expected_ids = configured_probe_ids(expected_facts or facts, profile)
    if not expected_ids and expected_facts is not None:
        expected_ids = configured_probe_ids(facts, profile)
    physical_ids = sorted(set((facts.get("one_wire") or {}).get("sensor_ids") or []))
    probe_count = int((facts.get("one_wire") or {}).get("count") or len(physical_ids))
    exact_mapping_available = bool(expected_ids)
    mapping_complete = (
        set(expected_ids) == set(physical_ids)
        if exact_mapping_available
        else probe_count >= minimum_probes
    )
    return {
        "probe_count": probe_count,
        "minimum_probes": minimum_probes,
        "expected_probe_count": len(expected_ids) if expected_ids else minimum_probes,
        "configured_probe_ids": expected_ids,
        "physical_probe_ids": physical_ids,
        "exact_mapping_available": exact_mapping_available,
        "mapping_complete": mapping_complete,
        "missing_probe_ids": sorted(set(expected_ids) - set(physical_ids)) if exact_mapping_available else [],
        "unexpected_probe_ids": sorted(set(physical_ids) - set(expected_ids)) if exact_mapping_available else [],
    }


def package_maintenance_counts(facts: dict) -> dict[str, int]:
    package_maintenance = facts.get("package_maintenance") or {}

    def number(value: object, fallback: int = 0) -> int:
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return fallback

    listed = number(
        package_maintenance.get("listed_count"),
        number(facts.get("packages_upgradable")),
    )
    eligible = number(package_maintenance.get("eligible_count"), listed)
    deferred = number(package_maintenance.get("deferred_count"), max(0, listed - eligible))
    return {"listed": listed, "eligible": eligible, "deferred": deferred}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Routine MRI Pi fleet access, audit, update, and reboot helper."
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--inventory",
        default=str(Path(__file__).resolve().parents[1] / "inventory" / "fleet_hosts.yml"),
        help="Inventory file to read.",
    )
    common.add_argument(
        "--password-env",
        default="MRI_PI_PASSWORD",
        help="Environment variable holding the shared SSH/sudo password.",
    )
    common.add_argument(
        "--report-dir",
        default=str(Path(__file__).resolve().parents[1] / "reports"),
        help="Directory for JSON and Markdown reports.",
    )
    common.add_argument(
        "--hosts",
        help="Comma-separated inventory names, labels, or IPs to target. Default is all for audit.",
    )
    common.add_argument(
        "--all",
        action="store_true",
        help="Required for mutating actions when you intentionally want every host.",
    )
    common.add_argument(
        "--connect-timeout",
        type=int,
        default=6,
        help="SSH connect timeout in seconds.",
    )
    common.add_argument(
        "--command-timeout",
        type=int,
        default=60,
        help="Remote command timeout in seconds.",
    )
    common.add_argument(
        "--backup-coverage",
        default=str(Path(__file__).resolve().parents[1] / "reports" / "backup_coverage.json"),
        help="Backup coverage report used to gate mutating actions.",
    )
    common.add_argument(
        "--ignore-backup-gate",
        action="store_true",
        help="Explicitly allow a mutating action without recent backup evidence.",
    )
    common.add_argument(
        "--ignore-health-gate",
        action="store_true",
        help="Explicitly allow a mutating action when sensor health checks fail.",
    )
    common.add_argument(
        "--post-check-timeout",
        type=int,
        default=300,
        help="Seconds to wait for post-mutation local health and advancing telemetry.",
    )
    common.add_argument(
        "--skip-post-check",
        action="store_true",
        help="Explicitly skip automatic recovery and telemetry verification.",
    )

    subparsers = parser.add_subparsers(dest="action", required=True)

    audit = subparsers.add_parser(
        "audit",
        parents=[common],
        help="Check reachability, bootstrap key auth, and collect host facts.",
    )
    audit.add_argument(
        "--no-bootstrap",
        action="store_true",
        help="Do not attempt password-based key installation when key auth fails.",
    )

    subparsers.add_parser(
        "preflight",
        parents=[common],
        help="Read-only backup, sensor-health, and server-telemetry maintenance gates.",
    )

    subparsers.add_parser(
        "update",
        parents=[common],
        help="Run apt update/upgrade/autoremove on selected hosts.",
    )
    subparsers.add_parser(
        "download",
        parents=[common],
        help="Refresh APT metadata and pre-download eligible upgrades without installing them.",
    )
    subparsers.add_parser(
        "baseline",
        parents=[common],
        help="Install the common operational support packages on selected hosts.",
    )
    subparsers.add_parser(
        "reboot",
        parents=[common],
        help="Reboot selected hosts.",
    )

    return parser.parse_args()


def load_inventory(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    hosts: list[dict] = []

    def walk(node: dict) -> None:
        for name, variables in (node.get("hosts") or {}).items():
            item = dict(variables or {})
            item["inventory_name"] = name
            hosts.append(item)
        for child in (node.get("children") or {}).values():
            walk(child or {})

    walk(data.get("all") or {})
    return hosts


def require_password(env_name: str) -> str:
    value = os.environ.get(env_name, "")
    if not value:
        raise SystemExit(f"{env_name} is required for SSH bootstrap and sudo operations.")
    return value


def run(
    command: list[str],
    *,
    timeout: int,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        text=True,
        capture_output=True,
        timeout=timeout,
        input=input_text,
    )


def port_open(host: str, port: int = 22, timeout: int = 3) -> bool:
    sock = socket.socket()
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        try:
            sock.close()
        except OSError:
            pass


def load_tailscale_peer_status() -> dict[str, dict]:
    """Return non-sensitive controller-visible peer state keyed by Tailscale IP."""
    try:
        result = run(["tailscale", "status", "--json"], timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if result.returncode != 0:
        return {}
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}

    by_ip: dict[str, dict] = {}
    for peer in (payload.get("Peer") or {}).values():
        item = {
            "hostname": peer.get("HostName", ""),
            "dns_name": peer.get("DNSName", ""),
            "online": peer.get("Online") is True,
            "last_seen": peer.get("LastSeen", ""),
            "last_handshake": peer.get("LastHandshake", ""),
            "os": peer.get("OS", ""),
        }
        for ip in peer.get("TailscaleIPs") or []:
            by_ip[str(ip)] = item
    return by_ip


def ssh_command(
    host: dict,
    *,
    user: str,
    remote_command: str,
    batch_mode: bool,
    allow_pubkey: bool,
    connect_timeout: int,
) -> list[str]:
    key_path = host.get("ansible_ssh_private_key_file") or DEFAULT_KEY
    command = ["ssh", "-p", str(host.get("ansible_port") or 22)]
    if allow_pubkey:
        command.extend(["-i", key_path, "-o", "IdentitiesOnly=yes"])
    else:
        command.extend(
            [
                "-o",
                "PreferredAuthentications=password",
                "-o",
                "PubkeyAuthentication=no",
            ]
        )

    command.extend(
        [
            "-o",
            f"ConnectTimeout={connect_timeout}",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            f"BatchMode={'yes' if batch_mode else 'no'}",
            f"{user}@{host['ansible_host']}",
            remote_command,
        ]
    )
    return command


def try_key_auth(
    host: dict,
    user: str,
    connect_timeout: int,
    *,
    attempts: int = 3,
) -> bool:
    command = ssh_command(
        host,
        user=user,
        remote_command="true",
        batch_mode=True,
        allow_pubkey=True,
        connect_timeout=connect_timeout,
    )
    for attempt in range(max(1, attempts)):
        try:
            result = run(command, timeout=connect_timeout + 6)
        except subprocess.TimeoutExpired:
            result = None
        if result is not None and result.returncode == 0:
            return True
        if attempt + 1 < attempts:
            time.sleep(0.5)
    return False


def try_password_auth(host: dict, user: str, password: str, connect_timeout: int) -> bool:
    command = [
        "sshpass",
        "-p",
        password,
        *ssh_command(
            host,
            user=user,
            remote_command="true",
            batch_mode=False,
            allow_pubkey=False,
            connect_timeout=connect_timeout,
        ),
    ]
    result = run(command, timeout=connect_timeout + 6)
    return result.returncode == 0


def bootstrap_key(host: dict, user: str, password: str, connect_timeout: int) -> tuple[bool, str]:
    pubkey_path = Path(host.get("ansible_ssh_private_key_file") or DEFAULT_KEY).with_suffix(".pub")
    pubkey = pubkey_path.read_text(encoding="utf-8").strip()
    remote_command = (
        "umask 077; mkdir -p ~/.ssh; touch ~/.ssh/authorized_keys; "
        f"grep -qxF {json.dumps(pubkey)} ~/.ssh/authorized_keys || "
        f"printf '%s\\n' {json.dumps(pubkey)} >> ~/.ssh/authorized_keys"
    )
    command = [
        "sshpass",
        "-p",
        password,
        *ssh_command(
            host,
            user=user,
            remote_command=remote_command,
            batch_mode=False,
            allow_pubkey=False,
            connect_timeout=connect_timeout,
        ),
    ]
    result = run(command, timeout=connect_timeout + 12)
    stderr = (result.stderr or result.stdout).strip()
    return result.returncode == 0, stderr


def collect_facts(host: dict, user: str, connect_timeout: int, command_timeout: int) -> tuple[dict | None, str]:
    command = ssh_command(
        host,
        user=user,
        remote_command=FACTS_SCRIPT,
        batch_mode=True,
        allow_pubkey=True,
        connect_timeout=connect_timeout,
    )
    try:
        result = run(command, timeout=command_timeout)
    except subprocess.TimeoutExpired:
        return None, f"Fact collection timed out after {command_timeout} seconds"
    if result.returncode != 0 or not result.stdout.strip():
        return None, (result.stderr or result.stdout).strip()
    try:
        return json.loads(result.stdout), ""
    except json.JSONDecodeError as exc:
        return None, f"Failed to parse facts JSON: {exc}"


def check_sudo(host: dict, user: str, password: str, connect_timeout: int) -> bool:
    command = ssh_command(
        host,
        user=user,
        remote_command=f"{SUDO_COMPAT} -S -p '' true",
        batch_mode=True,
        allow_pubkey=True,
        connect_timeout=connect_timeout,
    )
    result = run(command, timeout=connect_timeout + 8, input_text=password + "\n")
    return result.returncode == 0


def run_sudo_action(
    host: dict,
    user: str,
    password: str,
    remote_command: str,
    connect_timeout: int,
    command_timeout: int,
) -> tuple[bool, str]:
    command = ssh_command(
        host,
        user=user,
        remote_command=remote_command,
        batch_mode=True,
        allow_pubkey=True,
        connect_timeout=connect_timeout,
    )
    result = run(command, timeout=command_timeout, input_text=password + "\n")
    output = (result.stdout or result.stderr).strip()
    return result.returncode == 0, output


def host_matches(host: dict, selector: str) -> bool:
    selector = selector.strip().lower()
    choices = {
        host["inventory_name"].lower(),
        str(host.get("mri_label", "")).lower(),
        str(host.get("ansible_host", "")).lower(),
        str(host.get("ansible_user", "")).lower(),
    }
    return selector in choices


def select_hosts(hosts: list[dict], selector_text: str | None, action: str, all_flag: bool) -> list[dict]:
    if action in {"audit", "preflight"} and not selector_text:
        return hosts

    if selector_text:
        selectors = [item.strip() for item in selector_text.split(",") if item.strip()]
        selected = [host for host in hosts if any(host_matches(host, item) for item in selectors)]
        if not selected:
            raise SystemExit("No hosts matched --hosts.")
        return selected

    if all_flag:
        return hosts

    raise SystemExit("Mutating actions require --hosts or --all.")


def audit_host(host: dict, password: str | None, args: argparse.Namespace) -> dict:
    management_port = int(host.get("ansible_port") or 22)
    result = {
        "inventory_name": host["inventory_name"],
        "label": host.get("mri_label", host["inventory_name"]),
        "site": host.get("mri_site", ""),
        "host": host["ansible_host"],
        "primary_user": host["ansible_user"],
        "alt_users": host.get("mri_alt_users", []),
        "notes": host.get("mri_notes", ""),
        "profile": host.get("fleet_profile", "mri"),
        "data_site_id": host.get("data_site_id", ""),
        "camera_management": host.get("camera_management", "none"),
        "port_22": False,
        "ssh_port": management_port,
        "ssh_port_open": False,
        "key_auth": False,
        "bootstrapped_key": False,
        "sudo_ok": None,
        "sudo_check": (
            "not_checked_read_only"
            if getattr(args, "action", "") == "preflight"
            else "not_checked_no_credential"
        ),
    }

    if management_port == 22:
        result["port_22"] = port_open(
            host["ansible_host"], port=22, timeout=min(3, args.connect_timeout)
        )
        result["ssh_port_open"] = result["port_22"]
    else:
        result["port_22"] = port_open(
            host["ansible_host"], port=22, timeout=min(3, args.connect_timeout)
        )
        result["ssh_port_open"] = port_open(
            host["ansible_host"],
            port=management_port,
            timeout=min(3, args.connect_timeout),
        )

    if not result["ssh_port_open"]:
        result["status"] = "offline_or_unreachable"
        return result
    candidate_users = [host["ansible_user"], *host.get("mri_alt_users", [])]

    for user in candidate_users:
        if try_key_auth(host, user, args.connect_timeout):
            result["login_user"] = user
            result["key_auth"] = True
            break

    if not result["key_auth"] and password and not getattr(args, "no_bootstrap", False):
        for user in candidate_users:
            if not try_password_auth(host, user, password, args.connect_timeout):
                continue
            ok, message = bootstrap_key(host, user, password, args.connect_timeout)
            if ok:
                result["bootstrapped_key"] = True
                if try_key_auth(host, user, args.connect_timeout):
                    result["login_user"] = user
                    result["key_auth"] = True
                    break
            result["bootstrap_message"] = message

    if not result["key_auth"]:
        result["status"] = "ssh_failed"
        return result

    facts, fact_error = collect_facts(
        host,
        result["login_user"],
        args.connect_timeout,
        args.command_timeout,
    )
    if facts is not None:
        result["facts"] = facts
    if fact_error:
        result["fact_error"] = fact_error

    if facts is None:
        result["status"] = "fact_collection_failed"
        return result

    if password:
        result["sudo_ok"] = check_sudo(host, result["login_user"], password, args.connect_timeout)
        result["sudo_check"] = "verified" if result["sudo_ok"] else "credential_failed"

    result["status"] = "ok"
    return result


def audit_many(hosts: list[dict], password: str | None, args: argparse.Namespace) -> list[dict]:
    results_by_name: dict[str, dict] = {}
    tailscale_peers = load_tailscale_peer_status()
    workers = min(8, max(1, len(hosts)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(audit_host, host, password, args): host
            for host in hosts
        }
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            peer = tailscale_peers.get(str(result.get("host") or ""))
            if peer:
                result["tailscale_peer"] = peer
            results_by_name[result["inventory_name"]] = result
            print(
                f"{result['label']}: {result['status']}"
                f" user={result.get('login_user', result['primary_user'])}"
                f" bootstrapped={result['bootstrapped_key']}"
                f" sudo={result['sudo_check']}",
                flush=True,
            )

    # A routed Pi can occasionally reject or time out one connection while the
    # controller opens the initial parallel wave.  Retry only transient SSH/fact
    # failures after every concurrent worker has drained; offline hosts and
    # successful rows are never repeated.
    for host in hosts:
        prior = results_by_name[host["inventory_name"]]
        if prior.get("status") not in {"ssh_failed", "fact_collection_failed"}:
            continue
        print(f"{prior['label']}: retrying read-only audit serially", flush=True)
        result = audit_host(host, password, args)
        peer = tailscale_peers.get(str(result.get("host") or ""))
        if peer:
            result["tailscale_peer"] = peer
        result["serial_retry_performed"] = True
        results_by_name[host["inventory_name"]] = result
        print(
            f"{result['label']}: serial retry {result['status']}"
            f" user={result.get('login_user', result['primary_user'])}",
            flush=True,
        )

    results = [results_by_name[host["inventory_name"]] for host in hosts]
    return results


def load_backup_coverage(path: str) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def mutation_safety_gates(host: dict, audited: dict, backup_coverage: dict) -> dict:
    repository = BACKUP_REPOSITORIES.get(host["inventory_name"], "")
    configured = {
        item.get("repository")
        for item in backup_coverage.get("configured_targets", [])
        if item.get("repository")
    }
    repositories = set(backup_coverage.get("repositories", []))
    repository_status = {
        item.get("repository"): item
        for item in backup_coverage.get("repository_status", [])
        if item.get("repository")
    }
    restore_status = {
        item.get("repository"): item
        for item in backup_coverage.get("restore_tests", [])
        if item.get("repository")
    }
    batch = backup_coverage.get("batch") or {}
    checked_at = backup_coverage.get("checked_at")
    coverage_age_seconds = None
    try:
        checked = dt.datetime.fromisoformat(checked_at)
        if checked.tzinfo is None:
            checked = checked.astimezone()
        coverage_age_seconds = max(
            0,
            int((dt.datetime.now(dt.timezone.utc) - checked.astimezone(dt.timezone.utc)).total_seconds()),
        )
    except (TypeError, ValueError):
        pass
    coverage_report_recent = (
        coverage_age_seconds is not None and coverage_age_seconds <= 2 * 60 * 60
    )
    batch_success = batch.get("result") == "success"
    restore_recent = bool(
        repository
        and restore_status.get(repository, {}).get("status") == "success"
        and restore_status.get(repository, {}).get("recent") is True
    )
    backup_ok = bool(
        repository
        and repository in configured
        and repository in repositories
        and repository_status.get(repository, {}).get("activity_recent") is True
        and (batch_success or restore_recent)
        and coverage_report_recent
    )

    facts = audited.get("facts") or {}
    profile = audited.get("profile", "mri")
    service_key = "cv_sensor" if profile == "cv" else "mri_sensor"
    service_active = (
        ((facts.get("services") or {}).get(service_key) or {}).get("active") == "active"
    )
    probe_evidence = probe_recovery_evidence(facts, profile)
    probe_count = probe_evidence["probe_count"]
    minimum_probes = probe_evidence["minimum_probes"]
    throttle_flags = facts.get("throttled_flags")
    disk_free = int((facts.get("disk") or {}).get("free_bytes") or 0)
    boot_options = str(
        (facts.get("boot_management") or {}).get("firmware_mount_options") or ""
    )
    boot_firmware_writable = "ro" not in boot_options.split(",")
    package_manager_busy = bool((facts.get("package_manager") or {}).get("busy"))
    wifi_signal = routed_wifi_signal(facts)
    nearby_pilot = host.get("inventory_name") in NEARBY_PILOT_HOSTS
    health_blockers = []
    if not service_active:
        health_blockers.append("sensor service inactive")
    if not probe_evidence["mapping_complete"]:
        if probe_evidence["exact_mapping_available"]:
            details = []
            if probe_evidence["missing_probe_ids"]:
                details.append("missing " + ", ".join(probe_evidence["missing_probe_ids"]))
            if probe_evidence["unexpected_probe_ids"]:
                details.append("unexpected " + ", ".join(probe_evidence["unexpected_probe_ids"]))
            health_blockers.append("configured probe mapping incomplete: " + "; ".join(details))
        else:
            health_blockers.append(f"only {probe_count} probes; require {minimum_probes}")
    if throttle_flags != 0:
        health_blockers.append(f"throttle flags {throttle_flags!r}")
    if disk_free < 1_000_000_000:
        health_blockers.append("less than 1 GB root-disk free")
    if not boot_firmware_writable:
        health_blockers.append("boot firmware filesystem is read-only")
    if package_manager_busy:
        health_blockers.append("package manager is busy")
    health_ok = not health_blockers
    return {
        "backup": {
            "ok": backup_ok,
            "repository": repository,
            "configured": repository in configured if repository else False,
            "covered": repository in repositories if repository else False,
            "activity_recent": repository_status.get(repository, {}).get("activity_recent"),
            "batch_success": batch_success,
            "restore_recent": restore_recent,
            "restore_status": restore_status.get(repository, {}).get("status"),
            "evidence_mode": (
                "complete_batch"
                if batch_success
                else "recent_decrypt_restore"
                if restore_recent
                else "insufficient"
            ),
            "coverage_checked_at": checked_at,
            "coverage_age_seconds": coverage_age_seconds,
            "coverage_report_recent": coverage_report_recent,
        },
        "health": {
            "ok": health_ok,
            "blockers": health_blockers,
            "service_active": service_active,
            "probe_count": probe_count,
            "minimum_probes": minimum_probes,
            "expected_probe_count": probe_evidence["expected_probe_count"],
            "probe_mapping_complete": probe_evidence["mapping_complete"],
            "exact_probe_mapping_available": probe_evidence["exact_mapping_available"],
            "missing_probe_ids": probe_evidence["missing_probe_ids"],
            "unexpected_probe_ids": probe_evidence["unexpected_probe_ids"],
            "throttle_flags": throttle_flags,
            "disk_free_bytes": disk_free,
            "boot_firmware_writable": boot_firmware_writable,
            "boot_firmware_mount_options": boot_options,
            "package_manager_busy": package_manager_busy,
            "routed_wifi_signal_dbm": wifi_signal,
            "nearby_pilot": nearby_pilot,
        },
    }


def telemetry_site_id(audited: dict) -> str:
    if audited.get("data_site_id"):
        return str(audited["data_site_id"])
    values = (((audited.get("facts") or {}).get("sensor_config") or {}).get("values") or {})
    return str(values.get("SITE_NAME") or values.get("SITE_ID") or values.get("SCANNER_ID") or "")


def fetch_telemetry(audited: dict) -> dict:
    site_id = telemetry_site_id(audited)
    url = CV_SNAPSHOT_URL if audited.get("profile") == "cv" else MRI_SNAPSHOT_URL
    result = {
        "site_id": site_id,
        "url": url,
        "last_updated": None,
        "age_seconds": None,
        "is_offline": None,
        "current": False,
    }
    if not site_id:
        result["error"] = "site ID unavailable"
        return result
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": "CoolMRI-Fleet-Ops/1.0"}
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            rows = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        result["error"] = str(exc)
        return result
    row = next((item for item in rows if item.get("id") == site_id), None)
    if row is None:
        result["error"] = "site absent from snapshot"
        return result
    last_updated = row.get("last_updated")
    age_seconds = time.time() - last_updated if isinstance(last_updated, (int, float)) else None
    result.update(
        {
            "last_updated": last_updated,
            "age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
            "is_offline": row.get("is_offline"),
            "current": bool(
                age_seconds is not None
                and -30 <= age_seconds <= 300
                and row.get("is_offline") is not True
            ),
        }
    )
    return result


def local_recovery_state(pre_audit: dict, post_audit: dict, action: str) -> dict:
    facts = post_audit.get("facts") or {}
    profile = post_audit.get("profile", pre_audit.get("profile", "mri"))
    service_key = "cv_sensor" if profile == "cv" else "mri_sensor"
    service_active = (
        ((facts.get("services") or {}).get(service_key) or {}).get("active") == "active"
    )
    probe_evidence = probe_recovery_evidence(
        facts, profile, expected_facts=pre_audit.get("facts") or {}
    )
    probe_count = probe_evidence["probe_count"]
    minimum_probes = probe_evidence["minimum_probes"]
    throttle_flags = facts.get("throttled_flags")
    pre_hash = (((pre_audit.get("facts") or {}).get("application") or {}).get("normalized_sha256"))
    post_hash = ((facts.get("application") or {}).get("normalized_sha256"))
    application_preserved = bool(pre_hash and post_hash and pre_hash == post_hash)
    pre_uptime = (pre_audit.get("facts") or {}).get("uptime_seconds")
    post_uptime = facts.get("uptime_seconds")
    reboot_requested = action == "reboot"
    reboot_observed = bool(
        reboot_requested
        and isinstance(post_uptime, int)
        and (
            (isinstance(pre_uptime, int) and post_uptime < pre_uptime)
            or post_uptime <= 300
        )
    )
    reboot_requirement_satisfied = not reboot_requested or reboot_observed
    pre_boot = (pre_audit.get("facts") or {}).get("boot_management") or {}
    post_boot = facts.get("boot_management") or {}
    boot_candidate_pending = action == "reboot" and pre_boot.get("new_state") == "unknown"
    pre_kernel = (pre_audit.get("facts") or {}).get("kernel")
    post_kernel = facts.get("kernel")
    current_candidate_hash = pre_boot.get("current_kernel_sha256")
    new_candidate_hash = pre_boot.get("new_kernel_sha256")
    candidate_kernel_differs = bool(
        current_candidate_hash
        and new_candidate_hash
        and current_candidate_hash != new_candidate_hash
    )
    kernel_advanced = bool(pre_kernel and post_kernel and pre_kernel != post_kernel)
    candidate_promoted = bool(
        post_boot.get("current_state") == "good"
        and not post_boot.get("new_state")
        and post_boot.get("old_state") == "good"
    )
    boot_candidate_verified = not boot_candidate_pending or bool(
        candidate_promoted and (not candidate_kernel_differs or kernel_advanced)
    )
    operational = facts.get("operational_stack") or {}
    base_packages = (
        operational.get("required_packages")
        or operational.get("base_packages")
        or {}
    )
    operational_baseline_aligned = bool(
        base_packages
        and all(base_packages.values())
        and operational.get("architecture") in {"arm64", "aarch64"}
        and operational.get("ntp_synchronized") is True
        and ((facts.get("services") or {}).get("cron") or {}).get("active") == "active"
        and ((facts.get("services") or {}).get("tailscaled") or {}).get("active") == "active"
    )
    baseline_verified = action != "baseline" or operational_baseline_aligned
    package_cache = facts.get("package_cache") or {}
    download_cache_verified = bool(
        action != "download"
        or (
            package_cache.get("assessed") is True
            and package_cache.get("complete") is True
            and int(package_cache.get("candidate_count") or 0)
            == int(package_cache.get("cached_candidate_count") or 0)
            and not (package_cache.get("missing_candidate_names") or [])
        )
    )
    ok = bool(
        post_audit.get("status") == "ok"
        and service_active
        and probe_evidence["mapping_complete"]
        and throttle_flags == 0
        and application_preserved
        and reboot_requirement_satisfied
        and boot_candidate_verified
        and baseline_verified
        and download_cache_verified
    )
    return {
        "ok": ok,
        "status": post_audit.get("status"),
        "service_active": service_active,
        "probe_count": probe_count,
        "minimum_probes": minimum_probes,
        "expected_probe_count": probe_evidence["expected_probe_count"],
        "probe_mapping_complete": probe_evidence["mapping_complete"],
        "exact_probe_mapping_available": probe_evidence["exact_mapping_available"],
        "missing_probe_ids": probe_evidence["missing_probe_ids"],
        "unexpected_probe_ids": probe_evidence["unexpected_probe_ids"],
        "throttle_flags": throttle_flags,
        "application_preserved": application_preserved,
        "pre_application_hash": pre_hash,
        "post_application_hash": post_hash,
        "pre_uptime_seconds": pre_uptime,
        "post_uptime_seconds": post_uptime,
        "reboot_requested": reboot_requested,
        "reboot_observed": reboot_observed,
        "reboot_requirement_satisfied": reboot_requirement_satisfied,
        "boot_candidate_pending": boot_candidate_pending,
        "candidate_kernel_differs": candidate_kernel_differs,
        "candidate_promoted": candidate_promoted,
        "boot_candidate_verified": boot_candidate_verified,
        "kernel_advanced": kernel_advanced,
        "pre_kernel": pre_kernel,
        "post_kernel": post_kernel,
        "pre_boot_management": pre_boot,
        "post_boot_management": post_boot,
        "operational_baseline_aligned": operational_baseline_aligned,
        "baseline_verified": baseline_verified,
        "download_cache_verified": download_cache_verified,
        "package_cache": package_cache,
        "packages_upgradable": facts.get("packages_upgradable"),
        "package_maintenance": facts.get("package_maintenance") or {},
        "reboot_required": facts.get("reboot_required"),
        "kernel": post_kernel,
    }


def verify_mutation(
    host: dict,
    pre_audit: dict,
    pre_telemetry: dict,
    password: str,
    args: argparse.Namespace,
) -> dict:
    deadline = time.monotonic() + max(30, args.post_check_timeout)
    last_audit = None
    local_state = {"ok": False, "status": "not checked"}
    stability_verified = args.action != "reboot"
    stable_since = None
    stable_uptime = None
    if args.action == "reboot":
        time.sleep(5)
    while time.monotonic() < deadline:
        last_audit = audit_host(host, password, args)
        local_state = local_recovery_state(pre_audit, last_audit, args.action)
        if local_state["ok"]:
            if args.action != "reboot":
                break
            now = time.monotonic()
            current_uptime = local_state.get("post_uptime_seconds")
            if (
                stable_since is None
                or not isinstance(current_uptime, int)
                or (isinstance(stable_uptime, int) and current_uptime < stable_uptime)
            ):
                stable_since = now
            stable_uptime = current_uptime
            if now - stable_since >= REBOOT_STABILITY_SECONDS:
                stability_verified = True
                break
        else:
            stable_since = None
            stable_uptime = None
        time.sleep(5)

    baseline_timestamp = pre_telemetry.get("last_updated")
    post_telemetry = fetch_telemetry(last_audit or pre_audit)
    telemetry_advanced = bool(
        post_telemetry.get("current")
        and isinstance(baseline_timestamp, (int, float))
        and isinstance(post_telemetry.get("last_updated"), (int, float))
        and post_telemetry["last_updated"] > baseline_timestamp
    )
    while local_state.get("ok") and stability_verified and not telemetry_advanced and time.monotonic() < deadline:
        time.sleep(5)
        post_telemetry = fetch_telemetry(last_audit or pre_audit)
        telemetry_advanced = bool(
            post_telemetry.get("current")
            and isinstance(baseline_timestamp, (int, float))
            and isinstance(post_telemetry.get("last_updated"), (int, float))
            and post_telemetry["last_updated"] > baseline_timestamp
        )
    return {
        "ok": bool(local_state.get("ok") and stability_verified and telemetry_advanced),
        "local": local_state,
        "stability_required_seconds": REBOOT_STABILITY_SECONDS if args.action == "reboot" else 0,
        "stability_verified": stability_verified,
        "telemetry": post_telemetry,
        "telemetry_advanced": telemetry_advanced,
        "post_audit": last_audit,
    }


def preflight_many(hosts: list[dict], args: argparse.Namespace) -> list[dict]:
    results = audit_many(hosts, None, args)
    inventory_by_name = {host["inventory_name"]: host for host in hosts}
    backup_coverage = load_backup_coverage(args.backup_coverage)
    for audited in results:
        if audited.get("status") != "ok":
            audited["preflight_status"] = "blocked"
            audited["preflight_blocked_reasons"] = [audited.get("status", "audit failed")]
            continue
        gates = mutation_safety_gates(
            inventory_by_name[audited["inventory_name"]], audited, backup_coverage
        )
        gates["telemetry"] = fetch_telemetry(audited)
        audited["safety_gates"] = gates
        blocked_reasons = []
        if not gates["backup"]["ok"]:
            blocked_reasons.append("backup gate")
        if not gates["health"]["ok"]:
            blocked_reasons.extend(f"health gate: {reason}" for reason in gates["health"]["blockers"])
        if not gates["telemetry"]["current"]:
            blocked_reasons.append("server telemetry gate")
        audited["preflight_status"] = "blocked" if blocked_reasons else "ready"
        audited["preflight_blocked_reasons"] = blocked_reasons
        print(
            f"{audited['label']}: preflight {audited['preflight_status']}"
            + (f" ({', '.join(blocked_reasons)})" if blocked_reasons else ""),
            flush=True,
        )
    return results


def mutate_many(hosts: list[dict], password: str, args: argparse.Namespace) -> list[dict]:
    results = []
    backup_coverage = load_backup_coverage(args.backup_coverage)
    remote_commands = {
        "update": UPDATE_SCRIPT,
        "baseline": BASELINE_SCRIPT,
        "reboot": REBOOT_SCRIPT,
    }
    remote_command = remote_commands[args.action]
    for host in hosts:
        audited = audit_host(host, password, args)
        if audited["status"] != "ok":
            results.append(audited)
            print(f"{audited['label']}: skipped ({audited['status']})", flush=True)
            continue

        gates = mutation_safety_gates(host, audited, backup_coverage)
        pre_telemetry = fetch_telemetry(audited)
        gates["telemetry"] = pre_telemetry
        audited["safety_gates"] = gates
        blocked_reasons = []
        if not gates["backup"]["ok"] and not args.ignore_backup_gate:
            blocked_reasons.append("backup gate")
        if not gates["health"]["ok"] and not args.ignore_health_gate:
            blocked_reasons.extend(f"health gate: {reason}" for reason in gates["health"]["blockers"])
        if not pre_telemetry["current"] and not args.ignore_health_gate:
            blocked_reasons.append("server telemetry gate")
        if blocked_reasons:
            audited["mutation_status"] = "blocked"
            audited["mutation_blocked_reasons"] = blocked_reasons
            results.append(audited)
            print(
                f"{audited['label']}: {args.action} blocked ({', '.join(blocked_reasons)})",
                flush=True,
            )
            continue

        audited["action_started_at"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        ok, output = run_sudo_action(
            host,
            audited["login_user"],
            password,
            remote_command,
            args.connect_timeout,
            max(args.command_timeout, 900 if args.action in {"update", "baseline"} else 60),
        )
        audited["action_finished_at"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        audited["mutation_status"] = "ok" if ok else "failed"
        if output:
            audited["mutation_output"] = output[-4000:]
        if ok and not args.skip_post_check:
            verification = verify_mutation(
                host, audited, pre_telemetry, password, args
            )
            audited["post_verification"] = verification
            if not verification["ok"]:
                audited["mutation_status"] = "verification_failed"
        elif ok:
            audited["post_verification"] = {
                "ok": None,
                "skipped": True,
                "reason": "--skip-post-check",
            }
        results.append(audited)
        print(f"{audited['label']}: {args.action} {audited['mutation_status']}", flush=True)
        if audited["mutation_status"] != "ok":
            print("Stopping serial mutation wave after failed verification.", flush=True)
            break
    return results


def download_safety_blockers(audited: dict) -> list[str]:
    """Return only the local conditions that make an APT pre-download unsafe.

    Downloading does not change installed software, services, kernels, or boot
    state, so it deliberately does not require the installation backup,
    application-health, Wi-Fi-quality, or telemetry gates.
    """
    facts = audited.get("facts") or {}
    disk_free = int((facts.get("disk") or {}).get("free_bytes") or 0)
    blockers = []
    if disk_free < 1_000_000_000:
        blockers.append("less than 1 GB root-disk free")
    if bool((facts.get("package_manager") or {}).get("busy")):
        blockers.append("package manager is busy")
    return blockers


def download_one(host: dict, password: str, args: argparse.Namespace) -> dict:
    audited = audit_host(host, password, args)
    if audited.get("status") != "ok":
        print(f"{audited['label']}: download skipped ({audited['status']})", flush=True)
        return audited

    blockers = download_safety_blockers(audited)
    audited["download_safety_blockers"] = blockers
    if blockers:
        audited["mutation_status"] = "blocked"
        audited["mutation_blocked_reasons"] = blockers
        print(f"{audited['label']}: download blocked ({', '.join(blockers)})", flush=True)
        return audited

    audited["action_started_at"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    ok, output = run_sudo_action(
        host,
        audited["login_user"],
        password,
        DOWNLOAD_SCRIPT,
        args.connect_timeout,
        max(args.command_timeout, 900),
    )
    audited["action_finished_at"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    audited["mutation_status"] = "ok" if ok else "failed"
    if output:
        audited["mutation_output"] = output[-4000:]

    if ok:
        post_audit = audit_host(host, password, args)
        local = local_recovery_state(audited, post_audit, "download")
        audited["post_verification"] = {
            "ok": local["ok"],
            "local": local,
            "post_audit": post_audit,
            "telemetry_advanced": None,
            "telemetry_not_required": True,
        }
        if not local["ok"]:
            audited["mutation_status"] = "verification_failed"

    print(f"{audited['label']}: download {audited['mutation_status']}", flush=True)
    return audited


def download_many(hosts: list[dict], password: str, args: argparse.Namespace) -> list[dict]:
    """Pre-download on independent Pis concurrently; preserve inventory ordering."""
    results_by_name: dict[str, dict] = {}
    workers = min(8, max(1, len(hosts)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(download_one, host, password, args): host
            for host in hosts
        }
        for future in concurrent.futures.as_completed(futures):
            host = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {
                    "inventory_name": host["inventory_name"],
                    "label": host.get("mri_label", host["inventory_name"]),
                    "host": host["ansible_host"],
                    "primary_user": host["ansible_user"],
                    "profile": host.get("fleet_profile", "mri"),
                    "status": "download_worker_failed",
                    "mutation_status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            results_by_name[host["inventory_name"]] = result
    return [results_by_name[host["inventory_name"]] for host in hosts]


def summarize(results: list[dict]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for item in results:
        key = item.get("mutation_status") or item.get("preflight_status") or item["status"]
        summary[key] = summary.get(key, 0) + 1
    return summary


def summarize_packages(results: list[dict]) -> dict[str, int]:
    summary = {"listed": 0, "eligible": 0, "deferred": 0}
    for item in results:
        if item.get("status") != "ok":
            continue
        counts = package_maintenance_counts(item.get("facts") or {})
        for key in summary:
            summary[key] += counts[key]
    return summary


def summarize_package_cache(results: list[dict]) -> dict[str, object]:
    summary: dict[str, object] = {
        "assessed_hosts": 0,
        "complete_hosts": 0,
        "candidate_versions": 0,
        "cached_candidate_versions": 0,
        "incomplete_hosts": [],
    }
    incomplete_hosts: list[dict[str, object]] = []
    for item in results:
        if item.get("status") != "ok":
            continue
        cache = (item.get("facts") or {}).get("package_cache") or {}
        if cache.get("assessed") is True:
            summary["assessed_hosts"] = int(summary["assessed_hosts"]) + 1
        if cache.get("complete") is True:
            summary["complete_hosts"] = int(summary["complete_hosts"]) + 1
        candidate_count = int(cache.get("candidate_count") or 0)
        cached_count = int(cache.get("cached_candidate_count") or 0)
        summary["candidate_versions"] = int(summary["candidate_versions"]) + candidate_count
        summary["cached_candidate_versions"] = (
            int(summary["cached_candidate_versions"]) + cached_count
        )
        if cache.get("assessed") is not True or cache.get("complete") is not True:
            incomplete_hosts.append({
                "inventory_name": item.get("inventory_name"),
                "candidate_versions": candidate_count,
                "cached_candidate_versions": cached_count,
                "missing_candidate_names": cache.get("missing_candidate_names") or [],
            })
    summary["incomplete_hosts"] = incomplete_hosts
    return summary


def write_report(results: list[dict], args: argparse.Namespace) -> tuple[Path, Path]:
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"{args.action}_{timestamp}"
    json_path = report_dir / f"{base_name}.json"
    md_path = report_dir / f"{base_name}.md"

    payload = {
        "action": args.action,
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "inventory": str(Path(args.inventory).resolve()),
        "summary": summarize(results),
        "package_maintenance": summarize_packages(results),
        "package_cache": summarize_package_cache(results),
        "results": results,
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        f"# Fleet {args.action.title()} Report",
        "",
        f"- Generated: {payload['generated_at']}",
        f"- Inventory: `{payload['inventory']}`",
        f"- Summary: `{json.dumps(payload['summary'], sort_keys=True)}`",
        f"- Packages: `{payload['package_maintenance']['eligible']} eligible / {payload['package_maintenance']['listed']} listed / {payload['package_maintenance']['deferred']} deferred`",
        f"- Current package cache: `{payload['package_cache']['cached_candidate_versions']}/{payload['package_cache']['candidate_versions']} exact candidate versions; {payload['package_cache']['complete_hosts']}/{payload['package_cache']['assessed_hosts']} assessed hosts complete`",
        "",
        "| Host | Profile | IP | Status | Login | OS | Wi-Fi | Disk | CPU | Sensor service | 1-Wire | Packages | Reboot |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for item in results:
        facts = item.get("facts", {})
        wifi = facts.get("wifi") or []
        wifi_text = ", ".join(
            f"{item.get('interface')}={item.get('signal_dbm')} dBm"
            for item in wifi
            if item.get("signal_dbm") is not None
        )
        disk = facts.get("disk") or {}
        service_key = "cv_sensor" if item.get("profile") == "cv" else "mri_sensor"
        sensor = ((facts.get("services") or {}).get(service_key) or {}).get("active", "")
        one_wire = facts.get("one_wire") or {}
        package_counts = package_maintenance_counts(facts)
        lines.append(
            "| "
            + " | ".join(
                [
                    item["label"],
                    item.get("profile", "mri"),
                    item["host"],
                    item.get("mutation_status") or item.get("preflight_status") or item["status"],
                    item.get("login_user", item["primary_user"]),
                    facts.get("os", ""),
                    wifi_text,
                    f"{disk.get('used_percent', '')}%",
                    f"{facts.get('cpu_temp_c', '')} C",
                    sensor,
                    str(one_wire.get("count", "")),
                    (
                        f"{package_counts['eligible']} eligible / "
                        f"{package_counts['listed']} listed / "
                        f"{package_counts['deferred']} deferred"
                        if item.get("status") == "ok" else ""
                    ),
                    "yes" if facts.get("reboot_required") else "no",
                ]
            )
            + " |"
        )

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for suffix in ("json", "md"):
        stale = sorted(report_dir.glob(f"{args.action}_*.{suffix}"), reverse=True)[500:]
        for path in stale:
            path.unlink(missing_ok=True)
    return json_path, md_path


def main() -> int:
    args = parse_args()
    inventory_path = Path(args.inventory)
    hosts = load_inventory(inventory_path)
    selected_hosts = select_hosts(hosts, args.hosts, args.action, args.all)

    password = None
    if args.action in {"update", "download", "baseline", "reboot"}:
        password = require_password(args.password_env)
    elif args.action == "audit" and not args.no_bootstrap:
        password = os.environ.get(args.password_env)

    if args.action == "audit":
        results = audit_many(selected_hosts, password, args)
    elif args.action == "preflight":
        results = preflight_many(selected_hosts, args)
    elif args.action == "download":
        results = download_many(selected_hosts, password, args)
    else:
        results = mutate_many(selected_hosts, password, args)

    json_path, md_path = write_report(results, args)
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
