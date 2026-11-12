# libvips in earlier Stash frontend images

Earlier self-hosted frontend images included the image library libvips through
the Next.js dependency sharp. The upstream binary packages distribute libvips
under the GNU Lesser General Public License, version 3 or later. The
[LGPLv3](LGPL-3.0.txt) and [GPLv3](GPL-3.0.txt) texts are included here.

Use the row for your image's tag to download the source and build scripts.
The versions below come from the frontend lockfiles for tagged releases.
The packaging repositories include the dependency versions, upstream patches,
and third-party notices for the prebuilt library.

| Stash frontend tag | libvips source | Library build scripts and wasm-vips revision | sharp source and WebAssembly build workflow |
| --- | --- | --- | --- |
| 0.1.28–0.1.287 | [8.17.3](https://github.com/libvips/libvips/tree/v8.17.3) | [sharp-libvips 1.2.4](https://github.com/lovell/sharp-libvips/tree/v1.2.4) · [wasm-vips ff6372f5](https://github.com/kleisauke/wasm-vips/tree/ff6372f538d42b1496c8a7d89a4db9ae204231ac) | [sharp 0.34.5](https://github.com/lovell/sharp/tree/v0.34.5) · [workflow](https://github.com/lovell/sharp/blob/v0.34.5/.github/workflows/ci.yml) |
| 0.1.288–0.1.367 | [8.18.3](https://github.com/libvips/libvips/tree/v8.18.3) | [sharp-libvips 1.3.2](https://github.com/lovell/sharp-libvips/tree/v1.3.2) · [wasm-vips 9ff73c56](https://github.com/kleisauke/wasm-vips/tree/9ff73c569c91ded6f8d8c7570967d0dadcf0134d) | [sharp 0.35.3](https://github.com/lovell/sharp/tree/v0.35.3) · [workflow](https://github.com/lovell/sharp/blob/v0.35.3/.github/workflows/ci.yml) |
| 0.1.368–0.1.488 | [8.18.7](https://github.com/libvips/libvips/tree/v8.18.7) | [sharp-libvips 1.3.4](https://github.com/lovell/sharp-libvips/tree/v1.3.4) · [wasm-vips dca91909](https://github.com/kleisauke/wasm-vips/tree/dca91909178800875b575eb896d1fe4ed0a27931) | [sharp 0.35.5](https://github.com/lovell/sharp/tree/v0.35.5) · [workflow](https://github.com/lovell/sharp/blob/v0.35.5/.github/workflows/ci.yml) |

For the native Linux build, follow the platform instructions in the matching
sharp-libvips repository. A self-hoster can replace the shared library at
`/app/node_modules/@img/sharp-libvips-linuxmusl-<arch>/lib/libvips-cpp.so.*`
with a compatible build at the same path (`x64` or `arm64`).

Images that contain `@img/sharp-wasm32` also carry a statically linked copy.
To change libvips in that module, run `./build/wasm.sh <wasm-vips-revision>`
from the matching sharp-libvips checkout. The table links the wasm-vips commit
current when each upstream package was built. Use the resulting headers and static libraries
in sharp's `@img/sharp-libvips-dev-wasm32` build dependency, then follow the
`build-emscripten` job in the matching sharp workflow to link and package the
replacement module.
