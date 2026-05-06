#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import yaml


FACTS_SCRIPT = r"""python3 - <<'EOF'
import glob
import json
import subprocess


def sh(cmd: str) -> str:
    return subprocess.run(cmd, shell=True, text=True, capture_output=True).stdout.strip()


macs = {}
for path in sorted(glob.glob("/sys/class/net/*/address")):
    iface = path.split("/")[-2]
    try:
        with open(path, encoding="utf-8") as handle:
            macs[iface] = handle.read().strip()
    except OSError:
        pass

print(json.dumps({
    "hostname": sh("hostname"),
    "os": sh(". /etc/os-release && printf '%s %s' \"$NAME\" \"$VERSION\""),
    "kernel": sh("uname -srmo"),
    "uptime": sh("uptime -p"),
    "last_boot": sh("who -b 2>/dev/null || true"),
    "tailscale_ips": sh("tailscale ip -4 2>/dev/null || true").splitlines(),
    "link_brief": sh("ip -brief link"),
    "addr_brief": sh("ip -brief addr"),
    "route": sh("ip route"),
    "macs": macs,
    "disk_root": sh("df -h /"),
    "memory": sh("free -h"),
    "packages_upgradable": sh("apt list --upgradable 2>/dev/null | tail -n +2 | wc -l"),
}, sort_keys=True))
EOF"""

UPDATE_SCRIPT = (
    "sudo -S -p '' bash -lc "
    "\"apt-get update && "
    "DEBIAN_FRONTEND=noninteractive apt-get -y upgrade && "
    "apt-get -y autoremove\""
)

REBOOT_SCRIPT = "sudo -S -p '' reboot"
DEFAULT_KEY = "/home/mlweb/.ssh/mri_pi_fleet_ed25519"


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
        default=45,
        help="Remote command timeout in seconds.",
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
        "update",
        parents=[common],
        help="Run apt update/upgrade/autoremove on selected hosts.",
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
    command = ["ssh"]
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


def try_key_auth(host: dict, user: str, connect_timeout: int) -> bool:
    command = ssh_command(
        host,
        user=user,
        remote_command="true",
        batch_mode=True,
        allow_pubkey=True,
        connect_timeout=connect_timeout,
    )
    result = run(command, timeout=connect_timeout + 6)
    return result.returncode == 0


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
    result = run(command, timeout=command_timeout)
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
        remote_command="sudo -S -p '' true",
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
    if action == "audit" and not selector_text:
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
    result = {
        "inventory_name": host["inventory_name"],
        "label": host.get("mri_label", host["inventory_name"]),
        "site": host.get("mri_site", ""),
        "host": host["ansible_host"],
        "primary_user": host["ansible_user"],
        "alt_users": host.get("mri_alt_users", []),
        "notes": host.get("mri_notes", ""),
        "port_22": False,
        "key_auth": False,
        "bootstrapped_key": False,
        "sudo_ok": False,
    }

    if not port_open(host["ansible_host"], timeout=min(3, args.connect_timeout)):
        result["status"] = "offline_or_unreachable"
        return result

    result["port_22"] = True
    candidate_users = [host["ansible_user"], *host.get("mri_alt_users", [])]

    for user in candidate_users:
        if try_key_auth(host, user, args.connect_timeout):
            result["login_user"] = user
            result["key_auth"] = True
            break

    if not result["key_auth"] and password and not args.no_bootstrap:
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

    if password:
        result["sudo_ok"] = check_sudo(host, result["login_user"], password, args.connect_timeout)

    result["status"] = "ok"
    return result


def audit_many(hosts: list[dict], password: str | None, args: argparse.Namespace) -> list[dict]:
    results = []
    for host in hosts:
        result = audit_host(host, password, args)
        results.append(result)
        print(
            f"{result['label']}: {result['status']}"
            f" user={result.get('login_user', result['primary_user'])}"
            f" bootstrapped={result['bootstrapped_key']}"
            f" sudo={result['sudo_ok']}",
            flush=True,
        )
    return results


def mutate_many(hosts: list[dict], password: str, args: argparse.Namespace) -> list[dict]:
    results = []
    remote_command = UPDATE_SCRIPT if args.action == "update" else REBOOT_SCRIPT
    for host in hosts:
        audited = audit_host(host, password, args)
        if audited["status"] != "ok":
            results.append(audited)
            print(f"{audited['label']}: skipped ({audited['status']})", flush=True)
            continue

        ok, output = run_sudo_action(
            host,
            audited["login_user"],
            password,
            remote_command,
            args.connect_timeout,
            max(args.command_timeout, 900 if args.action == "update" else 60),
        )
        audited["mutation_status"] = "ok" if ok else "failed"
        if output:
            audited["mutation_output"] = output[-4000:]
        results.append(audited)
        print(f"{audited['label']}: {args.action} {audited['mutation_status']}", flush=True)
    return results


def summarize(results: list[dict]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for item in results:
        key = item.get("mutation_status") or item["status"]
        summary[key] = summary.get(key, 0) + 1
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
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "inventory": str(Path(args.inventory).resolve()),
        "summary": summarize(results),
        "results": results,
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        f"# Fleet {args.action.title()} Report",
        "",
        f"- Generated: {payload['generated_at']}",
        f"- Inventory: `{payload['inventory']}`",
        f"- Summary: `{json.dumps(payload['summary'], sort_keys=True)}`",
        "",
        "| Host | IP | Status | Login | Bootstrapped | Sudo | Hostname | Tailscale IPs | MACs |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for item in results:
        facts = item.get("facts", {})
        mac_text = ", ".join(
            f"{name}={value}"
            for name, value in sorted((facts.get("macs") or {}).items())
            if value
        )
        tailscale_ips = ", ".join(facts.get("tailscale_ips") or [])
        lines.append(
            "| "
            + " | ".join(
                [
                    item["label"],
                    item["host"],
                    item.get("mutation_status") or item["status"],
                    item.get("login_user", item["primary_user"]),
                    "yes" if item["bootstrapped_key"] else "no",
                    "yes" if item["sudo_ok"] else "no",
                    facts.get("hostname", ""),
                    tailscale_ips,
                    mac_text,
                ]
            )
            + " |"
        )

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> int:
    args = parse_args()
    inventory_path = Path(args.inventory)
    hosts = load_inventory(inventory_path)
    selected_hosts = select_hosts(hosts, args.hosts, args.action, args.all)

    password = None
    if args.action in {"update", "reboot"}:
        password = require_password(args.password_env)
    elif args.action == "audit" and not args.no_bootstrap:
        password = os.environ.get(args.password_env)

    if args.action == "audit":
        results = audit_many(selected_hosts, password, args)
    else:
        results = mutate_many(selected_hosts, password, args)

    json_path, md_path = write_report(results, args)
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
