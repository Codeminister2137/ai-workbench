"""Wake-path self-test: checks report pass/fail without raising."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/wake-self-test.py"
SPEC = importlib.util.spec_from_file_location("wake_self_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class _Proc:
    def __init__(self, stdout):
        self.stdout = stdout


def test_wake_armed_matches_network_adapter():
    ok, detail = mod.check_wake_armed(
        runner=lambda *a, **k: _Proc("Realtek Gaming 2.5GbE Family Controller\r\n")
    )
    assert ok and "Realtek" in detail


def test_wake_armed_fails_without_network_adapter():
    ok, detail = mod.check_wake_armed(runner=lambda *a, **k: _Proc("HID Keyboard Device\r\n"))
    assert not ok and "no network adapter" in detail


def test_wake_armed_runner_error_is_failure():
    def boom(*args, **kwargs):
        raise OSError("no powercfg")

    ok, detail = mod.check_wake_armed(runner=boom)
    assert not ok and "OSError" in detail


def test_public_ip_ok_and_none():
    assert mod.check_public_ip(lookup=lambda: "1.2.3.4") == (True, "1.2.3.4")
    ok, _ = mod.check_public_ip(lookup=lambda: None)
    assert not ok


def test_ddns_pending_without_config(monkeypatch):
    monkeypatch.delenv("WAKE_DDNS_HOSTNAME", raising=False)
    monkeypatch.setattr(mod.loop_notify, "ROOT", Path("/nonexistent-root-xyz"))
    ok, detail = mod.check_ddns()
    assert ok and detail.startswith("pending")


def test_ddns_resolves_and_reports(monkeypatch):
    monkeypatch.setenv("WAKE_DDNS_HOSTNAME", "pc.example.com")
    ok, detail = mod.check_ddns(resolve=lambda host: "9.9.9.9")
    assert ok and detail == "pc.example.com -> 9.9.9.9"


def test_ddns_reads_dotenv_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("WAKE_DDNS_HOSTNAME", raising=False)
    monkeypatch.setattr(mod.loop_notify, "ROOT", tmp_path)
    (tmp_path / ".env").write_text("WAKE_DDNS_HOSTNAME=pc.example.com\n", encoding="utf-8")
    ok, detail = mod.check_ddns(resolve=lambda host: "9.9.9.9")
    assert ok and detail == "pc.example.com -> 9.9.9.9"


def test_smtp_login_success_and_failure():
    class _Smtp:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def ehlo(self):
            pass

        def starttls(self, context=None):
            pass

        def login(self, user, password):
            pass

    ok, detail = mod.check_smtp_login(read_config=lambda: ("a@b.c", "pw"), smtp_class=_Smtp)
    assert ok and detail.startswith("login ok")
    ok, _ = mod.check_smtp_login(read_config=lambda: None, smtp_class=_Smtp)
    assert not ok


def test_lan_ip_ok_when_forward_target_held():
    ok, detail = mod.check_lan_ip(probe=lambda: "192.168.1.12")
    assert ok and "192.168.1.12" in detail


def test_lan_ip_fails_on_drift():
    ok, detail = mod.check_lan_ip(probe=lambda: "192.168.1.34")
    assert not ok and "drift" in detail and "192.168.1.34" in detail


def test_lan_ip_fails_when_undeterminable():
    ok, _ = mod.check_lan_ip(probe=lambda: None)
    assert not ok


def test_lan_ip_probe_error_is_failure():
    def boom():
        raise OSError("no route")

    ok, detail = mod.check_lan_ip(probe=boom)
    assert not ok and "OSError" in detail


def test_lan_ip_registered_in_checks():
    assert "lan_ip" in [name for name, _ in mod.CHECKS]
