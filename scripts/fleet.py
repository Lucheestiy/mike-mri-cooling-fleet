#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "inventory" / "fleet_hosts.yml"
GROUPS_PATH = ROOT / "inventory" / "fleet_groups.yml"
REPORTS_DIR = ROOT / "reports"
FLEET_OPS = ROOT / "scripts" / "fleet_ops.py"
SSH_CONFIG_PATH = Path("/home/mlweb/.ssh/config.d/mri_pi_fleet.conf")
DEFAULT_KEY = "/home/mlweb/.ssh/mri_pi_fleet_ed25519"
DEFAULT_PASSWORD_ENV = "MRI_PI_PASSWORD"

CHECK_COMMAND = (
    "bash -lc '"
    "count=$(apt list --upgradable 2>/dev/null | tail -n +2 | wc -l); "
    "reboot=no; "
    "[ -f /var/run/reboot-required ] && reboot=yes; "
    "printf \"count=%s reboot=%s\\n\" \"$count\" \"$reboot\"; "
    "if dpkg --audit >/dev/null 2>&1; then echo dpkg=clean; else echo dpkg=dirty; fi'"
)

FULL_UPGRADE_COMMAND = (
    "sudo -S -p '' bash -lc "
    "\"apt-get update && "
    "DEBIAN_FRONTEND=noninteractive apt-get -y full-upgrade && "
    "apt-get -y autoremove\""
)


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


def load_group_map(path: Path) -> dict[str, dict]:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data.get("groups") or {}


def latest_report(action: str) -> tuple[Path | None, dict | None]:
    candidates = sorted(REPORTS_DIR.glob(f"{action}_*.json"))
    if not candidates:
        return None, None
    path = candidates[-1]
    return path, json.loads(path.read_text(encoding="utf-8"))


def best_audit_report(expected_count: int) -> tuple[Path | None, dict | None]:
    candidates = sorted(REPORTS_DIR.glob("audit_*.json"))
    ranked: list[tuple[int, str, Path, dict]] = []
    for path in candidates:
        payload = json.loads(path.read_text(encoding="utf-8"))
        result_count = len(payload.get("results") or [])
        exact_match = 1 if result_count == expected_count else 0
        ranked.append((exact_match, result_count, path.name, path, payload))
    if not ranked:
        return None, None
    ranked.sort()
    _, _, _, path, payload = ranked[-1]
    return path, payload


def dynamic_groups(expected_count: int) -> dict[str, dict]:
    path, payload = best_audit_report(expected_count)
    if not payload:
        return {}

    ok_hosts = [item["inventory_name"] for item in payload["results"] if item["status"] == "ok"]
    bad_hosts = [item["inventory_name"] for item in payload["results"] if item["status"] != "ok"]
    source = path.name if path else "latest audit"
    return {
        "reachable": {
            "description": f"Hosts marked ok in {source}",
            "members": ok_hosts,
        },
        "offline": {
            "description": f"Hosts not reachable in {source}",
            "members": bad_hosts,
        },
    }


def inventory_map(hosts: list[dict]) -> dict[str, dict]:
    return {host["inventory_name"]: host for host in hosts}


def host_lookup_values(host: dict) -> set[str]:
    values = {
        host["inventory_name"].lower(),
        str(host.get("ansible_host", "")).lower(),
        str(host.get("ansible_user", "")).lower(),
        str(host.get("mri_label", "")).lower(),
        str(host.get("mri_site", "")).lower(),
    }
    return {value for value in values if value}


def label_alias(label: str) -> str:
    alias = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return alias


def resolve_targets(
    selectors: list[str],
    hosts_by_name: dict[str, dict],
    groups: dict[str, dict],
) -> list[dict]:
    if not selectors:
        selectors = ["all"]

    resolved: list[str] = []
    seen_hosts: set[str] = set()

    def add_host(name: str) -> None:
        if name not in seen_hosts:
            resolved.append(name)
            seen_hosts.add(name)

    def expand(selector: str, stack: set[str]) -> None:
        token = selector.strip()
        token_lower = token.lower()

        if token_lower == "all":
            for name in hosts_by_name:
                add_host(name)
            return

        if token in hosts_by_name:
            add_host(token)
            return

        if token in groups:
            if token in stack:
                raise SystemExit(f"Recursive group reference detected for {token}.")
            for member in groups[token].get("members") or []:
                expand(str(member), stack | {token})
            return

        matches = [
            name for name, host in hosts_by_name.items() if token_lower in host_lookup_values(host)
        ]
        if len(matches) == 1:
            add_host(matches[0])
            return
        if len(matches) > 1:
            match_text = ", ".join(matches)
            raise SystemExit(f"Selector {token!r} is ambiguous: {match_text}")
        raise SystemExit(f"Unknown host or group selector: {token}")

    for selector in selectors:
        expand(selector, set())

    return [hosts_by_name[name] for name in hosts_by_name if name in seen_hosts]


def latest_audit_status(expected_count: int) -> dict[str, dict]:
    _, payload = best_audit_report(expected_count)
    if not payload:
        return {}
    return {item["inventory_name"]: item for item in payload["results"]}


def fleet_ops_python() -> str:
    candidate = ROOT / ".venv" / "bin" / "python"
    return str(candidate if candidate.exists() else Path(sys.executable))


def run_fleet_ops(action: str, selected_hosts: list[dict], args: argparse.Namespace) -> int:
    command = [fleet_ops_python(), str(FLEET_OPS), action]
    if selected_hosts:
        host_csv = ",".join(host["inventory_name"] for host in selected_hosts)
        command.extend(["--hosts", host_csv])
    if action == "audit" and args.no_bootstrap:
        command.append("--no-bootstrap")
    if getattr(args, "connect_timeout", None):
        command.extend(["--connect-timeout", str(args.connect_timeout)])
    if getattr(args, "command_timeout", None):
        command.extend(["--command-timeout", str(args.command_timeout)])
    return subprocess.run(command, cwd=ROOT).returncode


def require_password(env_name: str) -> str:
    value = os.environ.get(env_name, "")
    if not value:
        raise SystemExit(f"{env_name} must be exported before this action.")
    return value


def ssh_base_command(host: dict) -> list[str]:
    return [
        "ssh",
        "-i",
        host.get("ansible_ssh_private_key_file") or DEFAULT_KEY,
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        f"{host['ansible_user']}@{host['ansible_host']}",
    ]


def run_check(selected_hosts: list[dict], args: argparse.Namespace) -> int:
    failures = 0
    for host in selected_hosts:
        command = ssh_base_command(host) + [CHECK_COMMAND]
        print(f"[check] {host['inventory_name']} ({host.get('mri_label', host['inventory_name'])})")
        result = subprocess.run(command, text=True, capture_output=True, timeout=args.command_timeout)
        output = (result.stdout or result.stderr).strip()
        if result.returncode != 0:
            failures += 1
            print(f"  failed: {output or 'no output'}")
            continue
        for line in output.splitlines():
            print(f"  {line}")
    return 1 if failures else 0


def run_full_upgrade(selected_hosts: list[dict], args: argparse.Namespace) -> int:
    password = require_password(args.password_env)
    failures = 0
    for host in selected_hosts:
        command = ssh_base_command(host) + [FULL_UPGRADE_COMMAND]
        label = host.get("mri_label", host["inventory_name"])
        print(f"[full-upgrade] {host['inventory_name']} ({label})", flush=True)
        result = subprocess.run(
            command,
            text=True,
            input=password + "\n",
            timeout=args.command_timeout,
        )
        if result.returncode != 0:
            failures += 1
            print(f"[full-upgrade] {host['inventory_name']} failed with rc={result.returncode}", flush=True)
    return 1 if failures else 0


def expand_group_members(
    name: str,
    groups: dict[str, dict],
    hosts_by_name: dict[str, dict],
    stack: set[str] | None = None,
) -> list[str]:
    stack = stack or set()
    if name in stack:
        raise SystemExit(f"Recursive group reference detected for {name}.")

    members: list[str] = []
    seen: set[str] = set()
    for member in groups[name].get("members") or []:
        token = str(member)
        if token in hosts_by_name:
            if token not in seen:
                members.append(token)
                seen.add(token)
            continue
        if token in groups:
            for nested in expand_group_members(token, groups, hosts_by_name, stack | {name}):
                if nested not in seen:
                    members.append(nested)
                    seen.add(nested)
    return members


def print_groups(groups: dict[str, dict], hosts_by_name: dict[str, dict]) -> None:
    for name in sorted(groups):
        members = expand_group_members(name, groups, hosts_by_name)
        description = groups[name].get("description", "")
        print(f"{name:16} {len(members):>2}  {description}")


def print_hosts(selected_hosts: list[dict], expected_count: int) -> None:
    status_map = latest_audit_status(expected_count)
    print("name             alias                    status                  host             user     label")
    for host in selected_hosts:
        alias = label_alias(host.get("mri_label", host["inventory_name"]))
        audit = status_map.get(host["inventory_name"], {})
        status = audit.get("status", "unknown")
        label = host.get("mri_label", host["inventory_name"])
        print(
            f"{host['inventory_name']:16} {alias:24} {status:22} "
            f"{host['ansible_host']:16} {host['ansible_user']:8} {label}"
        )


def render_ssh_config(selected_hosts: list[dict]) -> str:
    lines = [
        "# Managed by /home/mlweb/mri-cooling-pi-fleet/fleet",
        "# Refresh with: /home/mlweb/mri-cooling-pi-fleet/fleet ssh-config",
        "",
    ]

    for host in selected_hosts:
        aliases = [host["inventory_name"]]
        alias = label_alias(host.get("mri_label", host["inventory_name"]))
        if alias and alias not in aliases:
            aliases.append(alias)
        lines.extend(
            [
                f"# {host.get('mri_label', host['inventory_name'])} - {host.get('mri_site', '')}",
                f"Host {' '.join(aliases)}",
                f"    HostName {host['ansible_host']}",
                f"    User {host['ansible_user']}",
                f"    IdentityFile {host.get('ansible_ssh_private_key_file') or DEFAULT_KEY}",
                "    IdentitiesOnly yes",
                "    StrictHostKeyChecking accept-new",
                "    ServerAliveInterval 30",
                "    ServerAliveCountMax 3",
                "",
            ]
        )

        for alt_user in host.get("mri_alt_users") or []:
            alt_alias = f"{host['inventory_name']}-{alt_user}"
            label_alt = f"{alias}-{alt_user}" if alias else alt_alias
            lines.extend(
                [
                    f"Host {alt_alias} {label_alt}",
                    f"    HostName {host['ansible_host']}",
                    f"    User {alt_user}",
                    f"    IdentityFile {host.get('ansible_ssh_private_key_file') or DEFAULT_KEY}",
                    "    IdentitiesOnly yes",
                    "    StrictHostKeyChecking accept-new",
                    "    ServerAliveInterval 30",
                    "    ServerAliveCountMax 3",
                    "",
                ]
            )

    return "\n".join(lines).rstrip() + "\n"


def write_ssh_config(selected_hosts: list[dict]) -> None:
    SSH_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    SSH_CONFIG_PATH.write_text(render_ssh_config(selected_hosts), encoding="utf-8")
    SSH_CONFIG_PATH.chmod(0o600)
    os.chmod(SSH_CONFIG_PATH.parent, 0o700)
    print(f"Wrote {SSH_CONFIG_PATH}")


def run_ssh(host: dict, command_parts: list[str]) -> int:
    command = ssh_base_command(host)
    if command_parts:
        command.extend(command_parts)
    return subprocess.run(command).returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convenience wrapper for SSH and routine MRI Pi fleet maintenance."
    )
    parser.add_argument(
        "--inventory",
        default=str(INVENTORY_PATH),
        help="Inventory file to read.",
    )
    parser.add_argument(
        "--groups-file",
        default=str(GROUPS_PATH),
        help="Static group definition file.",
    )
    parser.add_argument(
        "--password-env",
        default=DEFAULT_PASSWORD_ENV,
        help="Environment variable holding the shared Pi password for sudo actions.",
    )

    subparsers = parser.add_subparsers(dest="action", required=True)

    list_parser = subparsers.add_parser("list", help="List hosts matching selectors.")
    list_parser.add_argument("targets", nargs="*", help="Host or group selectors.")

    groups_parser = subparsers.add_parser("groups", help="List static and dynamic groups.")
    groups_parser.add_argument("--dynamic-only", action="store_true", help="Show only dynamic groups.")

    ssh_parser = subparsers.add_parser("ssh", help="SSH to a host alias defined in the fleet config.")
    ssh_parser.add_argument("target", help="Inventory name, alias, label, IP, or group selecting one host.")
    ssh_parser.add_argument("command", nargs=argparse.REMAINDER, help="Optional remote command.")

    audit_parser = subparsers.add_parser("audit", help="Run fleet_ops audit on selectors.")
    audit_parser.add_argument("targets", nargs="*", help="Host or group selectors.")
    audit_parser.add_argument("--no-bootstrap", action="store_true", help="Do not try password SSH bootstrap.")
    audit_parser.add_argument("--connect-timeout", type=int, default=6)
    audit_parser.add_argument("--command-timeout", type=int, default=45)

    update_parser = subparsers.add_parser("update", help="Run fleet_ops update on selectors.")
    update_parser.add_argument("targets", nargs="+", help="Host or group selectors.")
    update_parser.add_argument("--connect-timeout", type=int, default=6)
    update_parser.add_argument("--command-timeout", type=int, default=900)

    reboot_parser = subparsers.add_parser("reboot", help="Run fleet_ops reboot on selectors.")
    reboot_parser.add_argument("targets", nargs="+", help="Host or group selectors.")
    reboot_parser.add_argument("--connect-timeout", type=int, default=6)
    reboot_parser.add_argument("--command-timeout", type=int, default=60)

    full_parser = subparsers.add_parser(
        "full-upgrade", help="Run apt update/full-upgrade/autoremove directly over SSH."
    )
    full_parser.add_argument("targets", nargs="+", help="Host or group selectors.")
    full_parser.add_argument("--command-timeout", type=int, default=2400)

    check_parser = subparsers.add_parser(
        "check", help="Show pending package count, reboot flag, and dpkg health."
    )
    check_parser.add_argument("targets", nargs="*", help="Host or group selectors.")
    check_parser.add_argument("--command-timeout", type=int, default=45)

    ssh_config_parser = subparsers.add_parser(
        "ssh-config", help="Render or write the generated fleet SSH config include."
    )
    ssh_config_parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print the config instead of writing it.",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    hosts = load_inventory(Path(args.inventory))
    hosts_by_name = inventory_map(hosts)
    static_groups = load_group_map(Path(args.groups_file))
    merged_groups = {**static_groups, **dynamic_groups(len(hosts_by_name))}

    if args.action == "groups":
        groups_to_print = (
            dynamic_groups(len(hosts_by_name)) if args.dynamic_only else merged_groups
        )
        print_groups(groups_to_print, hosts_by_name)
        return 0

    if args.action == "ssh":
        selected_hosts = resolve_targets([args.target], hosts_by_name, merged_groups)
        if len(selected_hosts) != 1:
            raise SystemExit("ssh requires a selector that resolves to exactly one host.")
        command_parts = args.command
        if command_parts[:1] == ["--"]:
            command_parts = command_parts[1:]
        return run_ssh(selected_hosts[0], command_parts)

    target_selectors = getattr(args, "targets", [])
    selected_hosts = resolve_targets(target_selectors, hosts_by_name, merged_groups)

    if args.action == "list":
        print_hosts(selected_hosts, len(hosts_by_name))
        return 0
    if args.action == "audit":
        return run_fleet_ops("audit", selected_hosts, args)
    if args.action == "update":
        return run_fleet_ops("update", selected_hosts, args)
    if args.action == "reboot":
        return run_fleet_ops("reboot", selected_hosts, args)
    if args.action == "check":
        return run_check(selected_hosts, args)
    if args.action == "full-upgrade":
        return run_full_upgrade(selected_hosts, args)
    if args.action == "ssh-config":
        if args.stdout:
            sys.stdout.write(render_ssh_config(selected_hosts))
        else:
            write_ssh_config(selected_hosts)
        return 0

    raise SystemExit(f"Unsupported action: {args.action}")


if __name__ == "__main__":
    raise SystemExit(main())
