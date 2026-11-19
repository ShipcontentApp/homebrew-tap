"""Build the Apple Silicon release archive with pinned binary wheels."""

import argparse
import gzip
import hashlib
from pathlib import Path
import platform
import re
import subprocess
import sys
import tarfile
import tempfile

CLI = Path(__file__).resolve().parents[1] / "cli"


def add_file(archive, source, name):
    entry = tarfile.TarInfo(name)
    entry.size = source.stat().st_size
    entry.mode = 0o644
    with source.open("rb") as stream:
        archive.addfile(entry, stream)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Directory for the release asset")
    args = parser.parse_args()
    if sys.platform != "darwin" or platform.machine() != "arm64" or sys.version_info[:2] != (3, 14):
        parser.error("Build on Apple Silicon macOS using Python 3.14.")
    version = re.search(r'^VERSION = "([0-9]+\.[0-9]+\.[0-9]+)"$', (CLI / "shipcontent.py").read_text(), re.M)[1]
    root = f"shipcontent-{version}"
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / f"{root}-arm64.tar.gz"
    wheels = Path(tempfile.mkdtemp(prefix="shipcontent-release-"))
    try:
        subprocess.run([sys.executable, "-m", "pip", "download", "--disable-pip-version-check",
                        "--only-binary=:all:", "--require-hashes", "-r", str(CLI / "requirements.txt"),
                        "--dest", str(wheels)], check=True)
        # Stable timestamps, file modes and ownership keep the checksum reproducible.
        with target.open("xb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for name in ("shipcontent.py", "shipcontent_auth.py", "requirements.txt"):
                    add_file(archive, CLI / name, f"{root}/{name}")
                for wheel in sorted(wheels.glob("*.whl")):
                    add_file(archive, wheel, f"{root}/wheelhouse/{wheel.name}")
        with target.open("rb") as artifact:
            print(hashlib.file_digest(artifact, "sha256").hexdigest(), target.name)
    finally:
        subprocess.run(["/usr/bin/trash", str(wheels)], check=True)


if __name__ == "__main__":
    main()
