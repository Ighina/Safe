from setuptools import setup, find_packages
from setuptools.command.develop import develop as _develop
from setuptools.command.install import install as _install
from setuptools.command.build_py import build_py as _build_py

import os
import sys
import shutil
import subprocess
from pathlib import Path


def _maybe_build_lean():
    """
    Run `lake update && lake build` in src/lean if available.

    Behavior:
    - Skips if SKIP_LEAN_BUILD=1.
    - Allows LAKE_BIN to point to a specific lake binary.
    - Prints warnings instead of failing hard (so pip install doesn't break).
    """
    if os.environ.get("SKIP_LEAN_BUILD", "") == "1":
        print("[setup.py] SKIP_LEAN_BUILD=1 -> skipping Lean build")
        return

    project_root = Path(__file__).resolve().parent
    lean_dir = project_root / "src" / "lean"
    if not lean_dir.exists():
        print(f"[setup.py] No Lean workspace at {lean_dir}, skipping.")
        return

    lake_bin = os.environ.get("LAKE_BIN") or shutil.which("lake")
    if not lake_bin:
        print("[setup.py] lake not found in PATH and LAKE_BIN not set; skipping Lean build.", file=sys.stderr)
        return

    env = os.environ.copy()
    try:
        print(f"[setup.py] Running: {lake_bin} update (cwd={lean_dir})")
        subprocess.check_call([lake_bin, "update"], cwd=str(lean_dir), env=env)
        print(f"[setup.py] Running: {lake_bin} build (cwd={lean_dir})")
        subprocess.check_call([lake_bin, "build"], cwd=str(lean_dir), env=env)
        print(f"[setup.py] Running: {lake_bin} build repl (cwd={lean_dir})")
        subprocess.check_call([lake_bin, "build", "repl"], cwd=str(lean_dir), env=env)
        print("[setup.py] Lean build completed.")
    except subprocess.CalledProcessError as e:
        # Do not hard-fail installs by default; allow override to fail if desired.
        if os.environ.get("LEAN_BUILD_STRICT", "") == "1":
            raise
        print(f"[setup.py] Warning: Lean build failed ({e}). Continuing installation.", file=sys.stderr)

class develop(_develop):
    def run(self):
        _maybe_build_lean()
        super().run()


class install(_install):
    def run(self):
        _maybe_build_lean()
        super().run()


class build_py(_build_py):
    def run(self):
        # Also hook regular builds so wheels trigger it (useful in CI).
        _maybe_build_lean()
        super().run()


setup(
    name="ruqola_libs",
    version="0.1",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "huggingface-hub[cli]",
        "openai",
        "python-dotenv",
        "transformers",
        "loguru",
        "ray[default]",
        "tqdm",
        "pandas",
        "easydict",
        "backoff",
        "httpx[socks]",
        "rank-bm25",
        "hydra-core",
        "sexpdata",
        "pylspclient",
        "pampy",
        "jsonlines",
        "dataclasses-json",
        "parglare",
        "protobuf",
        "tiktoken",
        "accelerate",
        "blobfile",
        "sentencepiece",
        "datasets",
        "vllm",
        "pytest",
    ],
    python_requires=">=3.9",
    cmdclass={
        "develop": develop,
        "install": install,
        "build_py": build_py,
    },
)
# To install the package, run:
# pip install -e .
# To uninstall the package, run:
# pip uninstall ruqola_libs