# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
DATA_ROOT = PROJECT_ROOT / "data"
DOCS_ROOT = PROJECT_ROOT / "docs"
TMP_ROOT = PROJECT_ROOT / "tmp"
VERSIONS_ROOT = PROJECT_ROOT / "versions"
COLLECTOR_PROTOCOL_VERSION = "collector.v1"
COLLECTOR_AGENT_VERSION = "7.9.3"
MIN_SUPPORTED_AGENT_VERSION = "7.9.3"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a version directory for OrderSystem.")
    parser.add_argument("version", help="Version number, for example 7.5.1 or v7.5.1.")
    parser.add_argument("--skip-git-pull", action="store_true", help="Skip git pull before building.")
    parser.add_argument("--build-exe", action="store_true", help="Run PyInstaller and copy exe files into bin/.")
    parser.add_argument("--build-agent", action="store_true", help="Build OrderCollectorAgent and copy it into bin/.")
    parser.add_argument("--keep-tmp", action="store_true", help="Keep tmp/build_version after the build.")
    return parser.parse_args()


def normalize_version(raw: str) -> str:
    version = raw.strip().lstrip("vV")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit("版本号必须遵循 主版本.次版本.修订号，例如 7.5.1")
    return f"v{version}"


def ensure_layout(version_dir: Path) -> None:
    for path in (
        SRC_ROOT,
        DATA_ROOT / "input",
        DATA_ROOT / "reference",
        DATA_ROOT / "output",
        DOCS_ROOT,
        TMP_ROOT,
        version_dir / "bin",
        version_dir / "logs",
        version_dir / "source",
        version_dir / "tests",
    ):
        path.mkdir(parents=True, exist_ok=True)


def find_git() -> str | None:
    found = shutil.which("git")
    if found:
        return found
    for candidate in (
        Path("C:/Program Files/Git/cmd/git.exe"),
        Path("C:/Program Files/Git/bin/git.exe"),
    ):
        if candidate.exists():
            return str(candidate)
    return None


def run_command(args: list[str], log_file: Path, cwd: Path = PROJECT_ROOT, env: dict[str, str] | None = None) -> int:
    with log_file.open("a", encoding="utf-8") as log:
        log.write(f"\n$ {' '.join(args)}\n")
        proc = subprocess.run(args, cwd=cwd, env=env, text=True, stdout=log, stderr=subprocess.STDOUT, check=False)
        log.write(f"exit_code={proc.returncode}\n")
        return proc.returncode


def stop_processes_using(path: Path) -> None:
    path = Path(path).resolve()
    if os.name != "nt" or not path.exists():
        return
    script = r"""
$target = [System.IO.Path]::GetFullPath($env:TARGET_DIR)
Get-Process | Where-Object {
  $_.Path -and [System.IO.Path]::GetFullPath($_.Path).StartsWith($target, [System.StringComparison]::OrdinalIgnoreCase)
} | Stop-Process -Force
"""
    env = os.environ.copy()
    env["TARGET_DIR"] = str(path)
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    time.sleep(0.5)


def copy_with_retry(source: Path, target: Path, attempts: int = 12) -> None:
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            shutil.copy2(source, target)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.5)
    if last_error:
        raise last_error


def pull_latest_source(skip: bool, log_file: Path) -> str:
    if skip:
        return "skipped"
    git = find_git()
    if not git:
        with log_file.open("a", encoding="utf-8") as log:
            log.write("git executable not found; skipped pull.\n")
        return "git-not-found"
    code = run_command([git, "pull", "--ff-only"], log_file)
    return "ok" if code == 0 else f"failed:{code}"


def copy_tree(source: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    if source.exists():
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    else:
        target.mkdir(parents=True, exist_ok=True)


def copy_test_data(version_dir: Path) -> None:
    copy_tree(DATA_ROOT / "input", version_dir / "tests" / "input")
    copy_tree(DATA_ROOT / "reference", version_dir / "tests" / "reference")


def run_regression_tests(version_dir: Path, log_file: Path) -> int:
    report = version_dir / "tests" / "report.log"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    env["ORDER_SORTER_DATA_DIR"] = str(version_dir / "tests" / "reference")
    env["ORDER_SORTER_OUTPUT_DIR"] = str(version_dir / "tests" / "output")
    env["ORDER_SORTER_TEMP_DIR"] = str(version_dir / "tests" / "tmp")
    report.write_text(f"Regression started: {datetime.now():%Y-%m-%d %H:%M:%S}\n", encoding="utf-8")
    code = run_command(
        [sys.executable, "-m", "unittest", "discover", "-s", str(SRC_ROOT / "tests"), "-p", "test_*.py"],
        report,
        env=env,
    )
    shutil.rmtree(version_dir / "tests" / "tmp", ignore_errors=True)
    with log_file.open("a", encoding="utf-8") as log:
        log.write(f"regression_tests={code}\n")
    return code


def create_source_snapshot(version: str, version_dir: Path) -> Path:
    artifact = version_dir / "source" / f"OrderSystem_source_{version}.zip"
    if artifact.exists():
        artifact.unlink()
    include_roots = (SRC_ROOT, PROJECT_ROOT / "scripts", DOCS_ROOT)
    with zipfile.ZipFile(artifact, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root in include_roots:
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if path.is_dir() or "__pycache__" in path.parts:
                    continue
                zf.write(path, path.relative_to(PROJECT_ROOT))
        requirements = PROJECT_ROOT / "requirements.txt"
        if requirements.exists():
            zf.write(requirements, requirements.relative_to(PROJECT_ROOT))
    return artifact


def create_release_package(version: str, version_dir: Path, executable_files: list[Path]) -> Path | None:
    if not executable_files:
        return None
    artifact = version_dir / "bin" / f"OrderSystem_{version}.zip"
    if artifact.exists():
        artifact.unlink()
    with zipfile.ZipFile(artifact, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in executable_files:
            zf.write(path, path.relative_to(version_dir / "bin"))
    return artifact


def create_agent_package(version: str, version_dir: Path, agent_exe: Path) -> Path:
    artifact = version_dir / "bin" / f"OrderCollectorAgent_{version}.zip"
    if artifact.exists():
        artifact.unlink()
    with zipfile.ZipFile(artifact, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(agent_exe, agent_exe.name)
    return artifact


def build_executables(version_dir: Path, log_file: Path) -> list[Path]:
    code = run_command([sys.executable, str(PROJECT_ROOT / "scripts" / "build_qt_windows.py")], log_file)
    if code != 0:
        raise SystemExit(f"PyInstaller build failed. See log: {log_file}")
    stop_processes_using(version_dir / "bin")
    dist_dirs = [path for path in (TMP_ROOT / "build").glob("dist_qt_*") if path.is_dir()]
    if not dist_dirs:
        raise SystemExit(f"PyInstaller output directory not found. See log: {log_file}")
    latest_dist = max(dist_dirs, key=lambda path: path.stat().st_mtime)
    copied: list[Path] = []
    for exe in latest_dist.glob("*.exe"):
        target = version_dir / "bin" / exe.name
        copy_with_retry(exe, target)
        copied.append(target)
    return copied


def build_collector_agent(version: str, version_dir: Path, log_file: Path) -> tuple[Path, Path]:
    plain_version = version.lstrip("vV")
    code = run_command(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "build_collector_agent.py"),
            "--version",
            plain_version,
            "--output-dir",
            str(version_dir / "bin"),
        ],
        log_file,
    )
    if code != 0:
        raise SystemExit(f"OrderCollectorAgent build failed. See log: {log_file}")
    agent_exe = version_dir / "bin" / f"OrderCollectorAgent_{version}.exe"
    if not agent_exe.exists():
        raise SystemExit(f"OrderCollectorAgent executable not found: {agent_exe}")
    agent_zip = create_agent_package(version, version_dir, agent_exe)
    return agent_exe, agent_zip


def write_release_manifest(
    version: str,
    version_dir: Path,
    agent_build_required: bool,
    agent_artifact: Path | None,
) -> Path:
    manifest = {
        "system_version": version.lstrip("vV"),
        "collector_agent_version": COLLECTOR_AGENT_VERSION,
        "collector_protocol_version": COLLECTOR_PROTOCOL_VERSION,
        "min_supported_agent_version": MIN_SUPPORTED_AGENT_VERSION,
        "compatible_agent_version": COLLECTOR_AGENT_VERSION,
        "agent_build_required": bool(agent_build_required),
        "agent_artifact": str(agent_artifact.relative_to(version_dir)) if agent_artifact else "",
        "agent_upgrade_required_for_existing_users": bool(agent_build_required),
        "release_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    path = version_dir / "release_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def append_version_log(version: str, version_dir: Path, git_status: str, test_code: int, artifacts: list[Path]) -> None:
    path = DOCS_ROOT / "version_log.md"
    if not path.exists():
        path.write_text("# 版本记录\n\n", encoding="utf-8")
    artifact_names = ", ".join(item.name for item in artifacts) if artifacts else "none"
    entry = (
        f"## {version} - {datetime.now():%Y-%m-%d %H:%M:%S}\n"
        f"- 目录: `{version_dir.as_posix()}`\n"
        f"- 拉取源码: {git_status}\n"
        f"- 回归测试: {'通过' if test_code == 0 else '失败'} ({test_code})\n"
        f"- 产物: {artifact_names}\n\n"
    )
    with path.open("a", encoding="utf-8") as log:
        log.write(entry)


def cleanup_tmp(keep_tmp: bool) -> None:
    build_tmp = TMP_ROOT / "build_version"
    build_tmp.mkdir(parents=True, exist_ok=True)
    if not keep_tmp:
        shutil.rmtree(build_tmp)
        shutil.rmtree(TMP_ROOT / "build", ignore_errors=True)


def main() -> int:
    args = parse_args()
    version = normalize_version(args.version)
    version_dir = VERSIONS_ROOT / version
    ensure_layout(version_dir)
    log_file = version_dir / "logs" / f"{datetime.now():%Y%m%d_%H%M%S}.log"
    git_status = pull_latest_source(args.skip_git_pull, log_file)
    copy_test_data(version_dir)
    test_code = run_regression_tests(version_dir, log_file)
    artifacts = [create_source_snapshot(version, version_dir)]
    if args.build_exe:
        executable_files = build_executables(version_dir, log_file)
        artifacts.extend(executable_files)
        release_package = create_release_package(version, version_dir, executable_files)
        if release_package:
            artifacts.append(release_package)
    agent_artifact = None
    if args.build_agent:
        agent_exe, agent_zip = build_collector_agent(version, version_dir, log_file)
        artifacts.extend([agent_exe, agent_zip])
        agent_artifact = agent_zip
    manifest = write_release_manifest(version, version_dir, args.build_agent, agent_artifact)
    artifacts.append(manifest)
    append_version_log(version, version_dir, git_status, test_code, artifacts)
    cleanup_tmp(args.keep_tmp)
    print(f"version_dir={version_dir}")
    print(f"test_report={version_dir / 'tests' / 'report.log'}")
    return test_code


if __name__ == "__main__":
    raise SystemExit(main())
