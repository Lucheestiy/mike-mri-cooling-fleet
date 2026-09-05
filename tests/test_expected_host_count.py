import ast
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
COUNTED_MODULES = (
    ROOT / "dashboard" / "app.py",
    ROOT / "scripts" / "optimization_observation.py",
    ROOT / "scripts" / "camera_proof_planner.py",
    ROOT / "scripts" / "fleet_last_known.py",
)


def inventory_host_count() -> int:
    payload = yaml.safe_load((ROOT / "inventory" / "fleet_hosts.yml").read_text())
    return len(payload["all"]["children"]["fleet_ops"]["hosts"])


def expected_hosts_default(path: Path) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "EXPECTED_HOSTS"
            for target in node.targets
        ):
            continue
        value = node.value
        if isinstance(value, ast.Constant):
            return int(value.value)
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "int"
            and isinstance(value.args[0], ast.Call)
        ):
            return int(value.args[0].args[1].value)
    raise AssertionError(f"EXPECTED_HOSTS default not found in {path}")


def test_every_consumer_matches_the_managed_inventory_size():
    expected = inventory_host_count()
    assert expected == 28
    assert all(expected_hosts_default(path) == expected for path in COUNTED_MODULES)

    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    configured = compose["services"]["dashboard"]["environment"]["FLEET_EXPECTED_HOSTS"]
    assert int(configured) == expected
