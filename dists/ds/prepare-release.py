#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepare local DS runtime, source and notice companions from a clean build."""

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_build(manifest, binary, lock):
    if manifest["source_dirty"]:
        raise ValueError("release builds require committed source")
    if sha256(binary) != manifest["sha256"]:
        raise ValueError("binary differs from its build manifest; rebuild first")
    for key in ("sdk_libraries_sha256", "arm7_sha256", "compiler_runtime_sha256"):
        if manifest[key] != lock[key]:
            raise ValueError("SDK differs from reviewed source pins: " + key)
    if not re.fullmatch(r"[0-9a-f]{40}", manifest["source_commit"]):
        raise ValueError("invalid source revision")


def safe_path(name):
    path = PurePosixPath(name)
    if not path.parts or path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError("unsafe archive path: " + name)
    return path


def download(url, target, expected=None):
    if not target.exists():
        temporary = target.with_suffix(target.suffix + ".download")
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        temporary.replace(target)
    if expected is not None and sha256(target) != expected:
        raise ValueError("download checksum mismatch: " + target.name)
    return target


def is_notice(name):
    base = PurePosixPath(name).name.upper()
    return base.startswith(("COPYING", "COPYRIGHT", "LICENSE", "LICENCE", "NOTICE", "AUTHORS"))


def sdk_notices(path):
    result = {}
    headers = set()
    if not tarfile.is_tarfile(path):
        return result
    with tarfile.open(path) as archive:
        for item in archive.getmembers():
            safe_path(item.name)
            if not item.isfile():
                continue
            if is_notice(item.name):
                result[item.name] = archive.extractfile(item).read()
            elif item.name.endswith((".c", ".h", ".cpp", ".S", ".s")):
                data = archive.extractfile(item).read()
                match = re.match(rb"\s*(/\*.*?\*/|(?://[^\n]*\n)+)", data, re.S)
                if match and (b"copyright" in match[0].lower() or b"SPDX-FileCopyrightText" in match[0]):
                    headers.add(match[0].strip())
    if headers:
        result[path.name + "-copyright-headers.txt"] = b"\n\n".join(sorted(headers)) + b"\n"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path)
    parser.add_argument("--repository", default="nextcode4u/scummvm")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cache", type=Path)
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[2]
    build = args.build.resolve()
    output = (args.output or build / "release").resolve()
    cache = (args.cache or build / "release-downloads").resolve()
    for folder in (output, cache):
        if folder == source or source in folder.parents:
            parser.error("keep generated archives and downloads outside the source checkout")
        folder.mkdir(parents=True, exist_ok=True)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository):
        parser.error("invalid repository name")
    manifest = json.loads((build / "discovery-build.json").read_text())
    lock = json.loads((source / "dists/ds/discovery-sdk.json").read_text())
    binary = build / "scummvm.nds"
    verify_build(manifest, binary, lock)
    revision = manifest["source_commit"]
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=source)
    if head != revision or dirty:
        raise ValueError("checkout differs from the recorded build")
    archive = download(f"https://codeload.github.com/{args.repository}/zip/{revision}", cache / ("scummvm-" + revision + ".zip"))
    notices = {}
    with zipfile.ZipFile(archive) as upstream:
        if upstream.testzip() is not None:
            raise ValueError("source archive CRC failure")
        roots = {safe_path(name).parts[0] for name in upstream.namelist()}
        if len(roots) != 1 or not next(iter(roots)).endswith("-" + revision):
            raise ValueError("source archive has a different revision")
        root = next(iter(roots))
        for filename in ("backends/platform/ds/portdefs.h", "backends/platform/ds/osystem_ds.cpp"):
            expected = subprocess.check_output(["git", "show", revision + ":" + filename], cwd=source)
            if upstream.read(root + "/" + filename) != expected:
                raise ValueError("source archive mismatch: " + filename)
        for name in upstream.namelist():
            if not name.endswith("/") and is_notice(name):
                notices["scummvm/" + name.split("/", 1)[1]] = upstream.read(name)
    dependencies = []
    for item in lock["sources"] + lock["runtime_notices"]:
        if safe_path(item["name"]).name != item["name"]:
            raise ValueError("invalid dependency filename")
        path = download(item["url"], cache / item["name"], item["sha256"])
        if item in lock["runtime_notices"]:
            notices["sdk/" + path.name] = path.read_bytes()
        else:
            dependencies.append(path)
            for name, text in sdk_notices(path).items():
                notices["sdk/" + name] = text
    notes = ("ScummVM DS discovery source and SDK inputs\n\n"
             + "ScummVM revision: " + revision + "\n"
             + "Extract scummvm-source.zip, enter its source directory, then run:\n"
             + "python3 dists/ds/build-discovery.py /tmp/scummvm-ds\n"
             + "An exported source build records no Git revision and cannot be repackaged as a verified release.\n"
             + "For release provenance, clone https://github.com/" + args.repository + ".git and checkout the revision above.\n"
             + "SDK package recipes: " + lock["sdk_recipe_reference"] + "\n"
             + "Toolchain recipes: " + lock["toolchain_recipe_reference"] + "\n"
             + "libmad and newlib use the included devkitPro patches (patch -p1).\n"
             + "SDK sources retain their notices; see discovery-sdk.json for hashes and origins.\n"
             + "The compiler and runtime toolchain are installed through devkitPro.\n")
    notices["SDK-SOURCES.txt"] = notes.encode()
    with zipfile.ZipFile(output / "licenses.zip", "w", zipfile.ZIP_DEFLATED) as target:
        for name, data in sorted(notices.items()):
            target.writestr(name, data)
    with zipfile.ZipFile(output / "source.zip", "w", zipfile.ZIP_STORED) as target:
        target.write(archive, "scummvm-source.zip")
        for path in dependencies:
            target.write(path, "sdk/" + path.name)
        for item in lock["runtime_notices"]:
            target.write(cache / item["name"], "sdk/notices/" + item["name"])
        target.write(source / "dists/ds/discovery-sdk.json", "sdk/discovery-sdk.json")
        target.writestr("BUILDING.txt", notes)
    shutil.copyfile(binary, output / "scummvm.nds")
    with zipfile.ZipFile(output / "scummvm-ds.zip", "w", zipfile.ZIP_DEFLATED) as target:
        target.write(binary, "scummvm.nds")
    (output / "build-info.json").write_text(json.dumps(manifest, indent=2) + "\n")
    names = ("scummvm.nds", "scummvm-ds.zip", "licenses.zip", "source.zip", "build-info.json")
    for name in ("scummvm-ds.zip", "licenses.zip", "source.zip"):
        with zipfile.ZipFile(output / name) as archive:
            if archive.testzip() is not None:
                raise ValueError("release archive CRC failure: " + name)
    (output / "SHA256SUMS").write_text("".join(sha256(output / name) + "  " + name + "\n" for name in names))
    print("Prepared local companions:", output)


if __name__ == "__main__":
    main()
