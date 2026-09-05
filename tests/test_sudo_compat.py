import os
import pty
import select
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "sudo-rs-ansible-compat"


def test_pty_does_not_echo_become_password(tmp_path):
    fake_sudo = tmp_path / "fake-sudo"
    fake_sudo.write_text(
        "#!/usr/bin/env bash\n"
        "IFS= read -r password\n"
        "printf 'child-ok\\n'\n",
        encoding="utf-8",
    )
    fake_sudo.chmod(0o700)

    master, slave = pty.openpty()
    env = os.environ.copy()
    env["SUDO_BINARY"] = str(fake_sudo)
    process = subprocess.Popen(
        [str(WRAPPER), "-S", "-p", "BECOME-SUCCESS-test"],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=env,
        close_fds=True,
    )
    os.close(slave)
    secret = "never-print-this-password"

    output = bytearray()
    deadline = time.monotonic() + 5
    prompt_seen = False
    while time.monotonic() < deadline:
        ready, _, _ = select.select([master], [], [], 0.1)
        if ready:
            try:
                output.extend(os.read(master, 4096))
            except OSError:
                break
            if not prompt_seen and b"BECOME-SUCCESS-test" in output:
                prompt_seen = True
                os.write(master, f"{secret}\n".encode())
        if process.poll() is not None and not ready:
            break
    process.wait(timeout=2)
    os.close(master)

    rendered = output.decode(errors="replace")
    assert process.returncode == 0
    assert prompt_seen
    assert "BECOME-SUCCESS-test" in rendered
    assert "child-ok" in rendered
    assert secret not in rendered
