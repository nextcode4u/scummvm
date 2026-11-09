# Gloam discovery branch

This branch follows ScummVM's upstream Nintendo DS port and its devkitPro SDK.
Its starting point is the upstream v2026.4.0 release. Gloam itself continues to
use BlocksDS; applications launched by Gloam do not need to use the same SDK.

The BlocksDS experiment remains on `experimental/ds-blocksds-discovery` as a
reference. Do not merge its filesystem replacements or SDK build substitutions
into this branch.

## Build

Install devkitPro's Nintendo DS development packages. The static discovery build was compiled with devkitARM r67.1, libnds 2.0.2, Calico 1.2.0, maxmod-nds 2.1.0 and
ndstool 2.3.1. These are SDK package versions; libnds 1.8.3 is not a devkitARM
version. Use upstream's compiler configuration, ARM7 and packaging rules.

For a small discovery test build, use an empty build directory and a source path
without spaces (a symlink is sufficient):

```sh
export DEVKITPRO=/opt/devkitpro
export DEVKITARM="$DEVKITPRO/devkitARM"
export PATH="$DEVKITARM/bin:$DEVKITPRO/tools/bin:$PATH"
export PKG_CONFIG_LIBDIR="$DEVKITPRO/portlibs/nds/lib/pkgconfig"
CXX="$DEVKITARM/bin/arm-none-eabi-g++" CXXFLAGS=-DSCUMMVM_DS_COMMAND_LINE \
  /path/to/scummvm/configure --host=ds --disable-all-engines \
  --enable-engine=lure --enable-release --disable-debug \
  --disable-mad --disable-ogg --disable-vorbis --disable-flac --disable-tremor \
  --disable-libcurl --disable-sdlnet
make -j4
```

This static Lure build is a diagnostic target, not the full DS engine package.
The opt-in define enables upstream's existing command-line parser. Without it,
the original DS parser setting is preserved. Gloam supplies discovery arguments
for `/roms/ScummVM/titles/`; ScummVM owns game detection and its configuration.

## Scope

The maintained delta is the parser opt-in and this guide. The earlier timer,
filesystem and BlocksDS build changes are not carried over. The upstream SDK
build has discovered Lure from a clean game list, preserved an existing volume
setting and reached the game intro in the development emulator. This does not
establish broader engine, audio, game-save, return or physical-device support.

## Upstream updates

Use a normal full-history clone for maintenance; unshallow a diagnostic checkout
before merging later releases. Keep each local fix in its own commit. Fetch and
merge a chosen upstream release into this branch; do not squash upstream history
or rewrite a published branch. Review the small upstream-to-fork diff after each
update and drop local workarounds once upstream provides an equivalent fix.

Build using the normal SDK, then check ordinary GUI startup, discovery, repeated
scans, game launch, input/audio and cold save readback. Verify that scans preserve
existing settings. A supported binary release and add-on installer update need
these checks plus source/license companions. Physical DSi testing is still needed.
