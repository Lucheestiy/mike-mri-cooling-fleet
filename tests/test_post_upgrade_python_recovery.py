from pathlib import Path
import importlib.util

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = ROOT / "playbooks" / "post_upgrade_python_recovery.yml"
REBUILD_SCRIPT = ROOT / "scripts" / "rebuild_python_runtime.py"


def load_rebuild_module():
    spec = importlib.util.spec_from_file_location("rebuild_python_runtime", REBUILD_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_recovery_uses_sudo_rs_prompt_compatibility_wrapper() -> None:
    play = yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8"))[0]
    assert play["become"] is True
    assert play["vars"]["ansible_become_exe"] == (
        "/home/{{ ansible_user }}/.local/bin/sudo-rs-ansible-compat"
    )


def test_recovery_requires_explicit_limit_and_confirmation() -> None:
    text = PLAYBOOK.read_text(encoding="utf-8")
    assert "ansible_limit | default('') | length > 0" in text
    assert "python_recovery_confirm | bool" in text
    assert "Rebuild and retain the prior sensor venv" in text
    assert "Rebuild and retain a broken optional camera venv" in text


def test_relocated_venv_scripts_are_rewritten_after_atomic_rename(tmp_path: Path) -> None:
    module = load_rebuild_module()
    stage = tmp_path / ".venv.rebuild-123"
    venv = tmp_path / "venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    activate = bin_dir / "activate"
    pip = bin_dir / "pip"
    activate.write_text(f'VIRTUAL_ENV="{stage}"\n', encoding="utf-8")
    pip.write_text(f"#!{stage}/bin/python3\n", encoding="utf-8")
    python = bin_dir / "python3"
    python.symlink_to("/usr/bin/python3")

    assert module.relocated_roots(venv) == [stage]
    repaired = module.repair_relocated_scripts(venv, stage)

    assert repaired == ["activate", "pip"]
    assert str(stage) not in activate.read_text(encoding="utf-8")
    assert str(stage) not in pip.read_text(encoding="utf-8")
    assert str(venv) in activate.read_text(encoding="utf-8")
    assert str(venv) in pip.read_text(encoding="utf-8")
    assert python.is_symlink()
