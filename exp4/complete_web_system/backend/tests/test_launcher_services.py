import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location("service_processes", Path(__file__).resolve().parents[2] / "service_processes.py")
services = importlib.util.module_from_spec(spec)
spec.loader.exec_module(services)


def test_services_require_exact_project_command_and_directory(tmp_path):
    backend = tmp_path / "backend"
    frontend = tmp_path / "frontend"
    api = ["python.exe", "-m", "uvicorn", "app.main:app", "--port", "8000"]
    assert services.service_kind(api, backend, tmp_path) == "api"
    assert services.service_kind(api, tmp_path / "other", tmp_path) is None
    assert services.service_kind(["python.exe", "-m", "uvicorn", "other:app"], backend, tmp_path) is None
    assert services.service_kind(["python.exe", "-m", "worker.main"], backend, tmp_path) == "worker"
    assert services.service_kind(["python.exe", "-m", "worker.main"], tmp_path / "other", tmp_path) is None
    assert services.service_kind(["node.exe", str(frontend / "node_modules/vite/bin/vite.js")], frontend, tmp_path) == "frontend"
    assert services.service_kind(["node.exe", str(tmp_path / "other/vite.js")], frontend, tmp_path) is None
    assert services.service_kind(api + ["--app-dir", str(tmp_path / "other")], backend, tmp_path) is None


def test_discovery_collapses_windows_venv_children(monkeypatch):
    class Fake:
        def __init__(self, pid, parent): self.pid, self.parent = pid, parent
        def cmdline(self): return ["python", "-m", "uvicorn", "app.main:app"]
        def cwd(self): return str(services.ROOT / "backend")
        def ppid(self): return self.parent
        def create_time(self): return 100
        def net_connections(self, kind):
            from types import SimpleNamespace
            return [SimpleNamespace(status=services.psutil.CONN_LISTEN, laddr=SimpleNamespace(port=8000))] if self.pid == 2 else []
    rows = {1: Fake(1, 100), 2: Fake(2, 1)}
    monkeypatch.setattr(services.psutil, "process_iter", lambda: list(rows.values()))
    monkeypatch.setattr(services.psutil, "Process", lambda pid: rows[pid])
    result = services.discover()
    assert len(result) == 1
    assert result[0]["id"] == 1
    assert result[0]["ports"] == [8000]


def test_stop_refuses_unrelated_process(monkeypatch):
    class Unrelated:
        pid = 123
        def cmdline(self): return ["python", "-m", "http.server"]
        def cwd(self): return str(services.ROOT)
        def terminate(self): raise AssertionError("Must never terminate unrelated service")
    monkeypatch.setattr(services.psutil, "Process", lambda pid: Unrelated())
    with pytest.raises(RuntimeError, match="Refusing"):
        services.stop(123)
