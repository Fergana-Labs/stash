#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DOCKERHUB_USER="${DOCKERHUB_USER:-idocker1688}"
VERSION="$(awk '/^version:/ { print $2; exit }' lazycat/package.yml)"
TAG="${TAG:-lazycat-${VERSION}-amd64}"
PLATFORM="linux/amd64"

copy_image() {
  local image="$1"
  local lazycat_image

  lazycat_image="$(lzc-cli appstore copy-image "$image" --arch amd64 --trace-level quiet | tail -n 1)"
  if [[ "$lazycat_image" != registry.lazycat.cloud/* ]]; then
    echo "copy-image did not return a Lazycat registry image for $image: $lazycat_image" >&2
    exit 1
  fi

  echo "$lazycat_image"
}

build_push_copy() {
  local service="$1"
  local dockerfile="$2"
  local context="$3"
  local image="${DOCKERHUB_USER}/stash-${service}:${TAG}"

  docker buildx build \
    --platform "$PLATFORM" \
    -t "$image" \
    --push \
    -f "$dockerfile" \
    "$context"

  docker buildx imagetools inspect "$image" | grep -q 'linux/amd64'
  copy_image "$image"
}

backend_image="$(build_push_copy backend backend/Dockerfile .)"
frontend_image="$(build_push_copy frontend frontend/Dockerfile frontend)"
collab_image="$(build_push_copy collab collab/Dockerfile collab)"
postgres_image="$(copy_image pgvector/pgvector:pg16)"
redis_image="$(copy_image redis:7-alpine)"

python3 - "$backend_image" "$frontend_image" "$collab_image" "$postgres_image" "$redis_image" <<'PY'
from pathlib import Path
import sys

backend, frontend, collab, postgres, redis = sys.argv[1:]
manifest = Path("lazycat/lzc-manifest.yml")
service_images = {
    "postgres": postgres,
    "redis": redis,
    "backend": backend,
    "worker": backend,
    "beat": backend,
    "frontend": frontend,
    "collab": collab,
}

lines = manifest.read_text().splitlines()
current_service = None
updated_services = set()

for index, line in enumerate(lines):
    if line.startswith("  ") and not line.startswith("    ") and line.endswith(":"):
        current_service = line.strip().removesuffix(":")
        continue

    if current_service in service_images and line.startswith("    image: "):
        lines[index] = f"    image: {service_images[current_service]}"
        updated_services.add(current_service)

missing = sorted(set(service_images) - updated_services)
if missing:
    raise SystemExit(f"missing manifest image entries for services: {', '.join(missing)}")

manifest.write_text("\n".join(lines) + "\n")

Path("lazycat/lzc-build.yml").write_text(
    "manifest: ./lzc-manifest.yml\n"
    "pkgout: ./\n"
    "icon: ./lzc-icon.png\n"
)
PY

echo "Updated lazycat/lzc-manifest.yml with Lazycat registry images:"
echo "backend=$backend_image"
echo "frontend=$frontend_image"
echo "collab=$collab_image"
echo "postgres=$postgres_image"
echo "redis=$redis_image"
