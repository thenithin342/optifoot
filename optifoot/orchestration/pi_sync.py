"""
Sync capture files with the Raspberry Pi over SSH (paramiko).

Environment overrides: PI_HOST, PI_USER, PI_PASSWORD

Local captures land in: <repo>/captures/
Remote: /home/pi/New folder/captures/
"""
from __future__ import annotations

import os
import shlex
import stat
import time
import urllib.error
import urllib.request
from pathlib import Path

import paramiko

from optifoot.paths import REPO_ROOT, CAPTURES_DIR

PI_SRC_DIR = REPO_ROOT / "pi_src"

REMOTE_CAPTURES = "/home/pi/New folder/captures"
REMOTE_CAPTURE_SCRIPT = "/home/pi/New folder/capture_two_images.py"
REMOTE_HARDWARE_SCRIPT = "/home/pi/New folder/capture_hardware.py"
REMOTE_WEB_SERVER_SCRIPT = "/home/pi/New folder/capture_web_interface.py"


def parse_auto_capture_basenames(log: str) -> tuple[str, str] | None:
    """Parse `AUTO_CAPTURE_OK <650.png> <850.png>` from remote script output."""
    for raw in log.splitlines():
        line = raw.strip()
        if not line.startswith("AUTO_CAPTURE_OK "):
            continue
        parts = line[len("AUTO_CAPTURE_OK ") :].split()
        if len(parts) >= 2:
            return parts[0], parts[1]
    return None


def download_capture_basenames(
    basename_650: str,
    basename_850: str,
    local_dir: Path | None = None,
) -> tuple[Path, Path]:
    """SFTP only the two files from this capture (not the whole Pi captures folder)."""
    dest = local_dir or CAPTURES_DIR
    dest.mkdir(parents=True, exist_ok=True)

    ssh = _connect()
    sftp = ssh.open_sftp()
    out: list[Path] = []
    for name in (basename_650, basename_850):
        remote_path = f"{REMOTE_CAPTURES}/{name}"
        local_path = dest / name
        sftp.get(remote_path, str(local_path))
        out.append(local_path)
        print(f"  {name} -> {local_path}")
    sftp.close()
    ssh.close()
    print(f"Downloaded {len(out)} new capture file(s) to {dest}")
    return out[0], out[1]


def _ssh_params() -> dict:
    return {
        "hostname": os.environ.get("PI_HOST", "10.66.136.37"),
        "username": os.environ.get("PI_USER", "pi"),
        "password": os.environ.get("PI_PASSWORD", "pi123"),
        "timeout": 15,
    }


def _connect() -> paramiko.SSHClient:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(**_ssh_params())
    return ssh


def download_captures(local_dir: Path | None = None) -> list[Path]:
    """Download all files from the Pi captures folder. Returns list of written local paths."""
    dest = local_dir or CAPTURES_DIR
    dest.mkdir(parents=True, exist_ok=True)

    ssh = _connect()
    sftp = ssh.open_sftp()
    try:
        names = sftp.listdir(REMOTE_CAPTURES)
    except OSError as e:
        sftp.close()
        ssh.close()
        raise RuntimeError(
            f"Cannot list {REMOTE_CAPTURES} on Pi (create it or run capture once). {e}"
        ) from e

    written: list[Path] = []
    for name in sorted(names):
        remote_path = f"{REMOTE_CAPTURES}/{name}"
        try:
            attr = sftp.stat(remote_path)
        except OSError:
            continue
        if not stat.S_ISREG(attr.st_mode):
            continue
        local_path = dest / name
        sftp.get(remote_path, str(local_path))
        written.append(local_path)
        print(f"  {name} -> {local_path}")

    sftp.close()
    ssh.close()
    print(f"Downloaded {len(written)} file(s) to {dest}")
    return written


def upload_capture_script(local_script: Path | None = None) -> None:
    """Push capture_two_images.py from this repo to the Pi."""
    src = local_script or (PI_SRC_DIR / "capture_two_images.py")
    if not src.is_file():
        raise FileNotFoundError(src)

    ssh = _connect()
    sftp = ssh.open_sftp()
    sftp.put(str(src), REMOTE_CAPTURE_SCRIPT)
    sftp.close()

    _, stdout, stderr = ssh.exec_command(f'ls -la "{REMOTE_CAPTURE_SCRIPT}"')
    out = (stdout.read() + stderr.read()).decode().strip()
    print(out)
    print("Upload complete.")
    ssh.close()


def upload_web_interface_script(local_script: Path | None = None) -> None:
    """Push capture_web_interface.py (browser UI) to the Pi."""
    src = local_script or (PI_SRC_DIR / "capture_web_interface.py")
    if not src.is_file():
        raise FileNotFoundError(src)

    ssh = _connect()
    sftp = ssh.open_sftp()
    sftp.put(str(src), REMOTE_WEB_SERVER_SCRIPT)
    sftp.close()
    ssh.close()
    print("Uploaded capture_web_interface.py")


def upload_capture_hardware(local_script: Path | None = None) -> None:
    """Push capture_hardware.py (no GUI deps; required by capture_web_interface)."""
    src = local_script or (PI_SRC_DIR / "capture_hardware.py")
    if not src.is_file():
        raise FileNotFoundError(src)
    ssh = _connect()
    sftp = ssh.open_sftp()
    sftp.put(str(src), REMOTE_HARDWARE_SCRIPT)
    sftp.close()
    ssh.close()
    print("Uploaded capture_hardware.py")


def upload_pi_capture_bundle() -> None:
    """Push capture_hardware + capture_two_images + capture_web_interface."""
    upload_capture_hardware()
    upload_capture_script()
    upload_web_interface_script()


def tail_remote_capweb_log(max_bytes: int = 8000) -> str:
    """Last bytes of Pi /tmp/capweb.log (web server stderr/stdout)."""
    ssh = _connect()
    cmd = f"tail -c {max_bytes} /tmp/capweb.log 2>/dev/null || echo '(no /tmp/capweb.log yet)'"
    _stdin, stdout, _stderr = ssh.exec_command(cmd)
    data = stdout.read().decode(errors="replace")
    ssh.close()
    return data.strip()


def list_remote_capture_basenames() -> set[str]:
    """Basenames in Pi captures/ (regular listing, no dotfiles)."""
    ssh = _connect()
    sftp = ssh.open_sftp()
    try:
        names = set()
        for n in sftp.listdir(REMOTE_CAPTURES):
            if n.startswith("."):
                continue
            try:
                st = sftp.stat(f"{REMOTE_CAPTURES}/{n}")
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode):
                names.add(n)
        return names
    finally:
        sftp.close()
        ssh.close()


def wait_for_new_capture_pair(
    before: set[str],
    *,
    timeout_sec: float = 900.0,
    poll_sec: float = 2.0,
) -> tuple[str, str]:
    """Block until a new *_650nm + matching *_850nm appear (both new vs `before`)."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        time.sleep(poll_sec)
        now = list_remote_capture_basenames()
        new = now - before
        for n650 in sorted(new):
            if not n650.endswith("_650nm.png"):
                continue
            prefix = n650.replace("_650nm.png", "")
            n850 = f"{prefix}_850nm.png"
            if n850 in new and n850 in now:
                return n650, n850
    raise TimeoutError(
        f"No new dual capture within {timeout_sec:.0f}s "
        "(click Capture 650 & 850 in the browser when ready)."
    )


def _http_ok(resp: object) -> bool:
    code = getattr(resp, "status", None)
    if code is None and hasattr(resp, "getcode"):
        code = resp.getcode()
    return code == 200


def wait_for_http_ready(
    host: str,
    port: int,
    *,
    path: str = "/",
    timeout_sec: float = 120.0,
) -> None:
    url = f"http://{host}:{port}{path}"
    deadline = time.monotonic() + timeout_sec
    last_err: str | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                if _http_ok(resp):
                    return
        except urllib.error.HTTPError as e:
            last_err = str(e)
            if e.code in (401, 403, 404):
                raise
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = str(e.reason) if hasattr(e, "reason") else str(e)
        time.sleep(0.8)
    log = tail_remote_capweb_log()
    raise TimeoutError(
        f"Pi web UI not reachable at {url} within {timeout_sec:.0f}s.\n"
        f"Last connection error: {last_err}\n\n"
        f"--- tail /tmp/capweb.log (on Pi) ---\n{log}\n"
        f"---\n"
        f"Hints: run on Pi `python3 capture_web_interface.py` manually; check firewall allows TCP {port}; "
        f"ensure `capture_hardware.py` is in the same folder on the Pi."
    )


def restart_remote_capture_web(port: int = 8765) -> None:
    """
    Kill old web UI, then start detached from SSH (setsid) so it keeps running
    after this connection closes.
    """
    ssh = _connect()
    sh_cmd = (
        f'cd "/home/pi/New folder" && exec python3 -u capture_web_interface.py --port {port}'
    )
    ssh = _connect()
    _in, _out, _err = ssh.exec_command('pkill -9 -f "capture_web_interface" 2>/dev/null || true')
    _out.channel.recv_exit_status()
    _in, _out, _err = ssh.exec_command('pkill -9 -f "capture_two_images" 2>/dev/null || true')
    _out.channel.recv_exit_status()
    ssh.close()
    time.sleep(1.0)
    
    ssh = _connect()
    # Ensure fresh log file
    ssh.exec_command(": > /tmp/capweb.log")
    
    # Launch in background
    ssh.exec_command(f"setsid sh -c {repr(sh_cmd)} </dev/null >>/tmp/capweb.log 2>&1 &")
    time.sleep(3.0)
    
    _stdin, stdout, stderr = ssh.exec_command('pgrep -af "[c]apture_web_interface.py" || echo __NO_PROCESS__')
    out = stdout.read().decode(errors="replace").strip()
    err = stderr.read().decode(errors="replace").strip()
    stdout.channel.recv_exit_status()
    ssh.close()
    time.sleep(1.0)
    if "__NO_PROCESS__" in out and "capture_web_interface.py" not in out:
        log = tail_remote_capweb_log()
        raise RuntimeError(
            "Web server did not stay running on the Pi.\n"
            f"pgrep: {out or '(empty)'}\nstderr: {err}\n\n"
            f"--- /tmp/capweb.log ---\n{log}"
        )
    print("(Pi) capture_web_interface:", out.splitlines()[0][:120])


def stop_remote_capture_web() -> None:
    ssh = _connect()
    _in, _out, _err = ssh.exec_command('pkill -9 -f "capture_web_interface" 2>/dev/null || true')
    _out.channel.recv_exit_status()
    ssh.close()


def run_remote_auto_capture(
    *,
    upload_script: bool = True,
    timeout_sec: int = 240,
) -> tuple[int, str, tuple[str, str] | None]:
    """
    Upload capture_two_images.py, then run it with --auto on the Pi (blocking).

    Returns (exit_status, combined_stdout_stderr_text, pair_basenames_or_none).
    """
    ssh = _connect()
    try:
        if upload_script:
            sftp = ssh.open_sftp()
            sftp.put(str(PI_SRC_DIR / "capture_hardware.py"), REMOTE_HARDWARE_SCRIPT)
            sftp.put(str(PI_SRC_DIR / "capture_two_images.py"), REMOTE_CAPTURE_SCRIPT)
            sftp.close()

        cmd = 'cd "/home/pi/New folder" && python3 capture_two_images.py --auto 2>&1'
        _stdin, stdout, _stderr = ssh.exec_command(cmd, get_pty=True)
        ch = stdout.channel
        deadline = time.monotonic() + timeout_sec
        while not ch.exit_status_ready():
            if time.monotonic() > deadline:
                ch.close()
                raise TimeoutError(
                    f"Remote capture exceeded {timeout_sec}s (camera or GPIO stuck?)."
                )
            time.sleep(0.25)
        exit_status = ch.recv_exit_status()
        text = stdout.read().decode(errors="replace")
        pair = parse_auto_capture_basenames(text)
        return exit_status, text, pair
    finally:
        ssh.close()
