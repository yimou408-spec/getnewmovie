"""Offline regressions for fresh-checkout and subsequent-pull startup."""
import pytest

from scripts import movie_demo


def test_frontend_dependencies_follow_the_checked_out_lockfile(tmp_path, monkeypatch):
    folder = tmp_path / "teammate checkout"
    folder.mkdir()
    lock = folder / "package-lock.json"
    lock.write_text('{"version":1}', encoding="utf-8")
    calls = []
    monkeypatch.setattr(movie_demo.shutil, "which", lambda _: "npm.cmd")

    def run(command, **kwargs):
        calls.append(command[1:])
        assert kwargs["cwd"] == folder
        if command[1] == "ci":
            (folder / "node_modules").mkdir(exist_ok=True)

    monkeypatch.setattr(movie_demo.subprocess, "run", run)
    movie_demo.build_frontend(folder)
    assert calls == [["ci", "--no-audit", "--no-fund"], ["run", "build"]]
    calls.clear()
    movie_demo.build_frontend(folder)
    assert calls == [["run", "build"]]
    calls.clear()
    lock.write_text('{"version":2}', encoding="utf-8")
    movie_demo.build_frontend(folder)
    assert calls == [["ci", "--no-audit", "--no-fund"], ["run", "build"]]


def test_failed_dependency_install_is_retried_on_next_start(tmp_path, monkeypatch):
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(movie_demo.shutil, "which", lambda _: "npm.cmd")
    calls = []

    def run(command, **kwargs):
        calls.append(command[1])
        (tmp_path / "node_modules").mkdir(exist_ok=True)
        raise movie_demo.subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(movie_demo.subprocess, "run", run)
    for _ in range(2):
        with pytest.raises(movie_demo.subprocess.CalledProcessError):
            movie_demo.build_frontend(tmp_path)
    assert calls == ["ci", "ci"]


def test_existing_unstamped_node_modules_are_not_assumed_current(tmp_path, monkeypatch):
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    monkeypatch.setattr(movie_demo.shutil, "which", lambda _: "npm.cmd")
    calls = []
    monkeypatch.setattr(movie_demo.subprocess, "run", lambda command, **_: calls.append(command[1]))
    movie_demo.build_frontend(tmp_path)
    assert calls == ["ci", "run"]
