#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
dist_root="$repo_root/dist"

rm -rf "$dist_root"
mkdir -p "$dist_root/server" "$dist_root/.openai"
cp "$repo_root/site-worker/index.js" "$dist_root/server/index.js"
cp "$repo_root/.openai/hosting.json" "$dist_root/.openai/hosting.json"
echo "Built $dist_root"
