#!/bin/bash
# zlib 1.4 and expat 2.10.0, compiled on the calling Debian image and packed
# as zlib1g / libexpat1. dpkg then replaces the trixie libraries instead of
# leaving a second copy. Versions are the upstream releases. Checksums are of
# the GitHub release tarballs named below.
set -euo pipefail

ZLIB_URL="https://github.com/madler/zlib/releases/download/v1.4/zlib-1.4.tar.gz"
ZLIB_SHA256="02dd159783677a749c04adbdd02b55b8a2bcc7e054f51b76b549199a916ad584"
ZLIB_DEB_VERSION="1:1.4-1+consorcio1"

EXPAT_URL="https://github.com/libexpat/libexpat/releases/download/R_2_10_0/expat-2.10.0.tar.gz"
EXPAT_SHA256="5466a341f9c692ef7a958a6881311be597f8e1ce345984cf78414f54793dea4c"
EXPAT_DEB_VERSION="2.10.0-1+consorcio1"

MULTIARCH="$(dpkg-architecture -qDEB_HOST_MULTIARCH)"
ARCH="$(dpkg-architecture -qDEB_HOST_ARCH)"
OUT=/out
rm -rf "$OUT"
mkdir -p "$OUT"
work="$(mktemp -d)"
cd "$work"

fetch() {
    local url="$1" dest="$2" sum="$3"
    python3 - "$url" "$dest" << 'PY'
import sys
import urllib.request

urllib.request.urlretrieve(sys.argv[1], sys.argv[2])
PY
    echo "${sum}  ${dest}" | sha256sum -c -
}

fetch "$ZLIB_URL" zlib.tar.gz "$ZLIB_SHA256"
fetch "$EXPAT_URL" expat.tar.gz "$EXPAT_SHA256"
tar -xzf zlib.tar.gz
tar -xzf expat.tar.gz

# gzwrite fix shipped in zlib 1.4 (df84af25; Debian links CVE-2026-76844
# to that commit) and the expat 2.10.0 note for CVE-2026-113351.
grep -q 'state->strm.avail_in = 0;' zlib-1.4/gzwrite.c
grep -q 'state->strm.next_in = state->in;' zlib-1.4/gzwrite.c
grep -q 'CVE-2026-113351' expat-2.10.0/Changes

(
    cd zlib-1.4
    ./configure --prefix=/usr --libdir="/usr/lib/${MULTIARCH}"
    make -j"$(nproc)"
    make test
    make install DESTDIR="${work}/zlib-install"
)

(
    cd expat-2.10.0
    ./configure --prefix=/usr --libdir="/usr/lib/${MULTIARCH}" --disable-static
    make -j"$(nproc)"
    make check
    make install DESTDIR="${work}/expat-install"
)

pack() {
    local name="$1" version="$2" src="$3" glob="$4"
    local homepage="$5" summary="$6" upstream_url="$7" upstream_sha="$8"
    local license="$9"
    local root="${work}/pkg-${name}"
    local libdir="${root}/usr/lib/${MULTIARCH}"
    rm -rf "$root"
    mkdir -p "$root/DEBIAN" "$libdir" "${root}/usr/share/doc/${name}"
    cp -a ${src}/usr/lib/${MULTIARCH}/${glob} "$libdir/"
    find "$libdir" -type f -name '*.a' -delete
    find "$libdir" -type l -name '*.so' -delete
    cp "$license" "${root}/usr/share/doc/${name}/copyright"
    cat > "${root}/usr/share/doc/${name}/UPSTREAM" << EOF
url: ${upstream_url}
sha256: ${upstream_sha}
deb_version: ${version}
EOF
    local size
    size="$(du -sk "${root}/usr" | cut -f1)"
    cat > "${root}/DEBIAN/control" << EOF
Package: ${name}
Version: ${version}
Architecture: ${ARCH}
Maintainer: Javier Zader <127463636+JNZader@users.noreply.github.com>
Section: libs
Priority: optional
Homepage: ${homepage}
Installed-Size: ${size}
Description: ${summary}
 Compiled from the upstream tarball recorded in
 /usr/share/doc/${name}/UPSTREAM. Replaces the trixie package of the
 same name so the previous shared library is removed from dpkg and disk.
EOF
    (
        cd "$root"
        find usr -type f -print0 | sort -z | xargs -0 md5sum
    ) > "${root}/DEBIAN/md5sums"
    dpkg-deb --root-owner-group -Zxz --build "$root" "${OUT}/${name}.deb"
}

pack zlib1g "$ZLIB_DEB_VERSION" "${work}/zlib-install" 'libz.so.1*' \
    "https://zlib.net/" \
    "zlib 1.4 shared library (upstream release)" \
    "$ZLIB_URL" "$ZLIB_SHA256" \
    zlib-1.4/README
pack libexpat1 "$EXPAT_DEB_VERSION" "${work}/expat-install" 'libexpat.so.1*' \
    "https://libexpat.github.io/" \
    "expat 2.10.0 shared library (upstream release)" \
    "$EXPAT_URL" "$EXPAT_SHA256" \
    expat-2.10.0/COPYING

python3 - << 'PY'
import subprocess
import sys
from pathlib import Path

expected = {
    "zlib1g.deb": "libz.so.1.4",
    "libexpat1.deb": "libexpat.so.1.13.1",
}
for name, need in expected.items():
    listing = subprocess.check_output(["dpkg-deb", "-c", f"/out/{name}"], text=True)
    if need not in listing:
        sys.exit(f"{name} does not contain {need}\n{listing}")
    for line in listing.splitlines():
        path = line.split()[-1]
        if path.endswith(".so") or path.endswith(".a"):
            sys.exit(f"{name} ships a non-runtime library: {path}")
print("runtime packages contain libz.so.1.4 and libexpat.so.1.13.1")
PY
