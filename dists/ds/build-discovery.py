#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build DS discovery with upstream's devkitPro configuration and plugin rules."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess


def engine_names(path):
    return [line.strip() for line in path.read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path, help="out-of-tree directory without spaces")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--engines", help="comma-separated engine subset for a smoke build")
    parser.add_argument("--static", action="store_true", help="use built-in engines for diagnostics")
    parser.add_argument("--configure-only", action="store_true")
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[2]
    build = args.build.resolve()
    if args.jobs < 1 or any(c.isspace() for c in str(build)):
        parser.error("use a positive job count and a build path without whitespace")
    if build == source or source in build.parents:
        parser.error("keep generated output outside the source checkout")
    engines = args.engines.split(",") if args.engines else engine_names(source / "dists/ds/discovery-engines.txt")
    if not engines or any(not name or not all(c.isalnum() or c == "_" for c in name) for name in engines):
        parser.error("invalid engine list")
    sdk = Path(os.environ.get("DEVKITPRO", "/opt/devkitpro")).resolve()
    arm = Path(os.environ.get("DEVKITARM", sdk / "devkitARM")).resolve()
    if any(c.isspace() for c in str(sdk) + str(arm)):
        parser.error("the upstream DS configure target requires SDK paths without whitespace")
    for needed in (arm / "bin/arm-none-eabi-g++", sdk / "calico/bin/ds7_maine.elf",
                   sdk / "tools/bin/ndstool", sdk / "portlibs/nds/lib/libmad.a"):
        if not needed.is_file():
            parser.error("missing SDK input: " + str(needed))
    build.mkdir(parents=True, exist_ok=True)
    alias = build / "source"
    if not alias.exists():
        alias.symlink_to(source, target_is_directory=True)
    if alias.resolve() != source:
        parser.error("build/source belongs to another checkout")
    env = {**os.environ, "DEVKITPRO": str(sdk), "DEVKITARM": str(arm),
           "CXX": str(arm / "bin/arm-none-eabi-g++"),
           "CXXFLAGS": "-DSCUMMVM_DS_COMMAND_LINE",
           "PKG_CONFIG_LIBDIR": str(sdk / "portlibs/nds/lib/pkgconfig"),
           "PATH": f"{arm}/bin:{sdk}/tools/bin:" + os.environ["PATH"]}
    def run(*command):
        subprocess.run([str(v) for v in command], cwd=build, env=env, check=True)
    # Check that the opt-in does not change normal upstream or explicit-disable builds.
    for definitions, disabled in (([], True), (["-DSCUMMVM_DS_COMMAND_LINE"], False),
                                  (["-DSCUMMVM_DS_COMMAND_LINE", "-DDISABLE_COMMAND_LINE"], True)):
        macros = subprocess.check_output([env["CXX"], "-E", "-dM", "-x", "c++",
                   "-DARM9", "-D__NDS__", "-D__DS__", "-I" + str(sdk / "libnds/include"),
                   "-I" + str(sdk / "calico/include"), "-include",
                   str(source / "backends/platform/ds/portdefs.h"), *definitions, "/dev/null"],
                   text=True)
        if ("#define DISABLE_COMMAND_LINE" in macros) != disabled:
            raise RuntimeError("DS parser opt-in contract failed")
    flags = ["--host=ds", "--disable-all-engines", "--enable-engine=" + ",".join(engines),
             "--enable-release", "--disable-debug", "--enable-mad", "--enable-zlib",
             "--disable-ogg", "--disable-vorbis", "--disable-flac", "--disable-tremor",
             "--disable-libcurl", "--disable-sdlnet"]
    if not args.static:
        flags += ["--enable-plugins", "--default-dynamic"]
    run(alias / "configure", *flags)
    if args.configure_only:
        return
    if not args.static:
        # Upstream renames these members to .twl.o. Recreate archives so an
        # incremental ar update cannot retain an older, renamed object too.
        for archive in ("audio/libaudio.a", "image/libimage.a", "video/libvideo.a"):
            (build / archive).unlink(missing_ok=True)
    run("make", "-j" + str(args.jobs))
    binary = build / "scummvm.nds"
    header = binary.read_bytes()[:512]
    if len(header) != 512 or not all(struct.unpack_from("<I", header, off)[0] for off in (0x20, 0x2c, 0x30, 0x3c)):
        raise RuntimeError("incomplete ARM9/ARM7 image")
    modules = sorted(p.name for p in (build / "romfs/plugins").glob("*.plg"))
    if not args.static:
        missing = {name + ".plg" for name in engines} | {"detection.plg"}
        missing.difference_update(modules)
        if missing:
            raise RuntimeError("missing engine modules: " + ", ".join(sorted(missing)))
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=source))
    compiler = subprocess.check_output([str(arm / "bin/arm-none-eabi-g++"), "--version"], text=True).splitlines()[0]
    libraries = ("libnds/lib/libnds9.a", "libnds/lib/libmm9.a", "calico/lib/libcalico_ds9.a",
                 "libnds/lib/libfilesystem.a", "libnds/lib/libfat.a",
                 "portlibs/nds/lib/libmad.a", "portlibs/nds/lib/libz.a")
    sdk_hashes = {name: hashlib.sha256((sdk / name).read_bytes()).hexdigest() for name in libraries}
    manifest = {"source_commit": commit, "source_dirty": dirty, "compiler": compiler,
                "configure": flags, "engines": engines, "modules": modules,
                "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                "sdk_libraries_sha256": sdk_hashes,
                "arm7_sha256": hashlib.sha256((sdk / "calico/bin/ds7_maine.elf").read_bytes()).hexdigest()}
    (build / "discovery-build.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(binary)


if __name__ == "__main__":
    main()
