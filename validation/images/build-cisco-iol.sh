#!/usr/bin/env bash
# Turn a Cisco CML-Free refplat ISO into containerlab-ready IOL images (L3 + L2).
#
# Newer CML refplats ship IOL as an OCI image (CML's own /iol-runner wrapper),
# not the raw .iol binary vrnetlab expects. So we:
#   1. mount the ISO, docker-load the iol-xe / ioll2-xe OCI tarballs
#   2. docker cp the actual IOL binary out of each loaded image
#   3. feed those to srl-labs/vrnetlab's cisco_iol builder (the wrapper that
#      gives containerlab networking, serial, startup-config, health)
#   4. build as linux/amd64 (IOL is x86; it runs under emulation on Apple Silicon)
#
# Result: vrnetlab/cisco_iol:<ver> (L3 router) and vrnetlab/cisco_iol:L2-<ver> (L2 switch)
#
#   ./build-cisco-iol.sh [path/to/refplat.iso]
#
# Requires: docker, git, make, and (macOS) hdiutil / (Linux) mount.
set -euo pipefail
cd "$(dirname "$0")"

ISO="${1:-$(ls refplat-*/*.iso 2>/dev/null | head -1)}"
[[ -f "$ISO" ]] || { echo "ERROR: refplat ISO not found. Pass it as an argument."; exit 1; }
echo "using ISO: $ISO"

VRNETLAB_DIR="vrnetlab"
MNT="$(mktemp -d)"
PLATFORM="linux/amd64"

mount_iso()   { case "$(uname)" in
                  Darwin) hdiutil attach -nobrowse -readonly -mountpoint "$MNT" "$ISO" >/dev/null ;;
                  *)      sudo mount -o loop,ro "$ISO" "$MNT" ;;
                esac; }
unmount_iso() { case "$(uname)" in
                  Darwin) hdiutil detach "$MNT" >/dev/null 2>&1 || true ;;
                  *)      sudo umount "$MNT" 2>/dev/null || true ;;
                esac; rmdir "$MNT" 2>/dev/null || true; }
trap unmount_iso EXIT

# ver_from_dir iol-xe-17-18-02 -> 17.18.02
ver_from_dir() { echo "${1##*-xe-}" | tr '-' '.'; }

# extract_binary <oci-tarball> <dest.bin>  (load image, copy the .iol out)
extract_binary() {
  local tarball="$1" dest="$2" img cid bin
  img="$(docker load -i "$tarball" 2>/dev/null | sed -n 's/^Loaded image: //p')"
  echo "  loaded $img" >&2
  cid="$(docker create "$img")"
  # the real IOL binary is the *.iol file (not the binary.iol symlink)
  bin="$(docker export "$cid" | tar t 2>/dev/null | grep -E '\.iol$' | grep -v '^binary' | head -1)"
  docker cp "$cid:/$bin" "$dest"
  docker rm "$cid" >/dev/null
  docker rmi "$img" >/dev/null 2>&1 || true
}

mount_iso

L3_DIR="$(ls -d "$MNT"/virl-base-images/iol-xe-* 2>/dev/null | grep -v serial | head -1)"
L2_DIR="$(ls -d "$MNT"/virl-base-images/ioll2-xe-* 2>/dev/null | head -1)"
[[ -n "$L3_DIR" ]] || { echo "ERROR: no iol-xe-* on ISO"; exit 1; }
VER="$(ver_from_dir "$(basename "$L3_DIR")")"
echo "IOL version: $VER"

if [[ ! -d "$VRNETLAB_DIR" ]]; then
  echo "cloning srl-labs/vrnetlab..."
  git clone --depth 1 https://github.com/srl-labs/vrnetlab.git "$VRNETLAB_DIR" >/dev/null
fi
IOL_DIR="$VRNETLAB_DIR/cisco/iol"

echo "extracting L3 IOL binary..."
extract_binary "$L3_DIR"/iol-xe-*.tar.gz "$IOL_DIR/cisco_iol-$VER.bin"
if [[ -n "$L2_DIR" ]]; then
  echo "extracting L2 IOL binary..."
  extract_binary "$L2_DIR"/ioll2-xe-*.tar.gz "$IOL_DIR/cisco_iol-L2-$VER.bin"
fi

echo "building vrnetlab images (platform $PLATFORM; emulated on arm64)..."
( cd "$IOL_DIR" && DOCKER_DEFAULT_PLATFORM="$PLATFORM" make docker-image )

# clean the large intermediate binaries
rm -f "$IOL_DIR"/cisco_iol-*.bin

echo "========================================================"
echo "  built images:"
docker images vrnetlab/cisco_iol --format '   {{.Repository}}:{{.Tag}}   ({{.Size}})'
echo "========================================================"
echo "use in containerlab:  kind: cisco_iol, image: vrnetlab/cisco_iol:$VER   (add type: l2 for the L2-$VER tag)"
