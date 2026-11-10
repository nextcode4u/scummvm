# Nintendo DS discovery branch

This branch follows ScummVM's upstream Nintendo DS port and its devkitPro SDK.
Its starting point is the upstream v2026.4.0 release. Compatible homebrew
launchers can pass command-line arguments without using the same SDK.

Use upstream filesystem and SDK build support; keep launcher integration
independent of toolchain replacements.

## Build

Install devkitPro's Nintendo DS development packages and `nds-libmad`. The
baseline was compiled with devkitARM r67.1, libnds 2.0.2, Calico 1.2.0,
maxmod-nds 2.1.0 and ndstool 2.3.1. Use upstream's compiler, matching ARM7,
plugin loader and packaging rules. libnds and devkitARM have separate version
numbers.

Build outside the source checkout:

```sh
python3 dists/ds/build-discovery.py /tmp/scummvm-ds --jobs=4
```

The default engine list in `discovery-engines.txt` matches the 43-module baseline
of the upstream 2.9.1 DS package, compiled here from current upstream source.
Modules are embedded in NitroFS along with their detection plugin and data.
Module presence is not a compatibility claim for every game in an engine.
The selected build enables zlib and MP3, with Ogg/Vorbis/FLAC disabled.

The same helper can build an extracted source archive without Git metadata.
Such builds record an unknown revision and are excluded from verified release
packaging; an export nested inside another repository cannot inherit its revision.

For a smaller diagnostic build, add `--engines=sky,lure`. `--static` embeds the
selected engines directly. `--configure-only` checks the SDK and generates build
configuration without compiling. The source-path symlink handles spaces in the
checkout; the build directory and SDK paths must not contain spaces because of
upstream configure assumptions.

The helper checks the parser's default, opt-in and explicit-disable behavior,
checks ARM9/ARM7 payloads and requested module presence, and records source,
compiler and SDK-library hashes in `discovery-build.json`. It recreates the three
archives renamed by upstream's TWL fixup so incremental archive updates cannot
retain stale renamed objects. It does not patch generated compiler/linker flags.

CI uses a digest-pinned official devkitPro image and builds the `sky,lure` dynamic
module subset. The manual workflow's `full` option builds the complete baseline.
CI requires no games, BIOS, NAND, SD images or emulator modification.

## Discovery and layout

Keep each game's data in its own directory. For example, place the application
at `/roms/ScummVM/scummvm.nds` and games below `/roms/ScummVM/titles/`. Configure
a compatible launcher to pass the following arguments, adjusting the path to
match your installation:

```text
--add --recursive --path=sd:/roms/ScummVM/titles --no-exit
```

This uses upstream's discovery code, then opens the normal ScummVM game list.
Repeated scans skip known target IDs and preserve their settings. Moving or
removing a game's folder does not automatically repair or remove an existing
entry: edit its path or remove the entry in ScummVM. Save files are not deleted
by discovery. Pass these options using your launcher's argument configuration;
this branch does not require a particular launcher or directory layout.
Game data, BIOS, firmware and NAND images are not included.

## Scope and validation

The maintained changes are the command-line opt-in, a DS save-cache startup fix,
and the isolated build, CI and release helpers. The save manager now registers
`.` as its default save directory so its first scan is not skipped when the
cache also starts with an empty directory name. Explicit user save paths retain
precedence. The earlier timer, filesystem and BlocksDS port changes are not
carried over.

The branch also backports upstream's
[`BASE: Fix __dso_handle definition`](https://github.com/scummvm/scummvm/commit/199a2b078e5f0d2a4871577d11bfc7e7413a9abe)
without modification. The build helper checks each module's initialized,
self-relocated destructor handle to reject stale pre-fix plugins.

The full 43-engine dynamic build and the smaller two-engine CI build compile.
Emulator tests cover discovery of Beneath a Steel Sky and Lure of the Temptress,
retention of existing game settings, and Lure gameplay. The static Lure build
also passes saving, cold-start save enumeration/restoration and returning to
ScummVM's launcher and then the calling homebrew launcher. These checks do not establish compatibility
for every engine or physical DS/DSi hardware.

A direct restore from the game list in the full dynamic build can stall during
detection-plugin unloading. This remains under investigation; successful static
save tests do not establish that this dynamic route is ready for release.
The Sky intro also produces nonzero stereo output in the emulator. Listening
checks, broader game coverage, flashcards and physical-device behavior still
need validation. Keep these builds experimental until the compatibility checks
pass.

## Local release companions

Use Python 3.11 or later. Commit and push the source first, then run a clean
build so its manifest identifies the exact published revision. Prepare packages
outside the checkout:

```sh
python3 -B dists/ds/test-discovery.py
python3 dists/ds/build-discovery.py /tmp/scummvm-ds --jobs=4
python3 dists/ds/prepare-release.py /tmp/scummvm-ds \
  --cache /tmp/scummvm-sdk-sources --output /tmp/scummvm-release
```

`prepare-release.py` verifies the binary, source revision, ARM7, SDK libraries
and compiler runtimes against the reviewed lock file. It downloads that exact
fork revision and checksum-pinned SDK sources and patches. A different SDK
requires a source and notice review before updating `discovery-sdk.json`.

The outputs are `scummvm.nds`, a runtime-only `scummvm-ds.zip`, `licenses.zip`,
`source.zip`, `build-info.json` and `SHA256SUMS`. Source and license companions
retain ScummVM and SDK notices; SDK source archives and patches are included in
the source package. Keep companions available alongside any distributed binary.
The script prepares local files only: it does not create a tag, publish a GitHub
release or update external installers. Generated files stay out of git.

## Upstream updates

Use a normal full-history clone for maintenance; unshallow a diagnostic checkout
before merging later releases. Keep each local fix in its own commit. Fetch and
merge a chosen upstream release into this branch; do not squash upstream history
or rewrite a published branch. Review the small upstream-to-fork diff after each
update and drop local workarounds once upstream provides an equivalent fix.

Build using the normal SDK, then check ordinary GUI startup, discovery, repeated
scans, game launch, input/audio and cold save readback. Verify that scans preserve
existing settings. A supported binary release needs
these checks plus source/license companions. Physical DSi testing is still needed.
