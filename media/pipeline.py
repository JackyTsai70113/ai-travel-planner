from __future__ import annotations

import hashlib
import json
import re
import shutil
import struct
from pathlib import Path
from typing import Any

KINDS = {"hero", "place", "lodging", "restaurant", "route", "illustration", "icon"}
VISIBILITIES = {"public", "private"}
DISALLOWED_URL = re.compile(r"(?:google\.(?:com|co\.)|maps\.google|gstatic\.com|maps\.app|fbcdn|pinimg)", re.I)
GENERIC_ALT = re.compile(r"^(?:image|img|photo|dsc|untitled)[_-]?[0-9.]*$", re.I)


class MediaValidationError(ValueError):
    pass


def _dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if data.startswith(b"\xff\xd8"):
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            i += 2
            if marker in {0xD8, 0xD9}:
                continue
            length = struct.unpack(">H", data[i:i + 2])[0]
            if marker in range(0xC0, 0xC4):
                return struct.unpack(">HH", data[i + 3:i + 7])[::-1]
            i += length
    if path.suffix.lower() == ".svg":
        text = data.decode("utf-8", errors="replace")
        match = re.search(r'<svg[^>]*(?:width="([0-9.]+)"[^>]*height="([0-9.]+)"|viewBox="[^\"]*?\s+([0-9.]+)\s+([0-9.]+)")', text, re.I)
        if match:
            values = [value for value in match.groups() if value]
            return round(float(values[-2])), round(float(values[-1]))
    raise MediaValidationError(f"cannot determine image dimensions: {path}")


def validate_manifest(manifest: dict[str, Any], root: Path) -> list[str]:
    errors: list[str] = []
    if manifest.get("version") != "1.0.0":
        errors.append("version must be 1.0.0")
    if not manifest.get("tripId"):
        errors.append("tripId is required")
    assets = manifest.get("assets")
    if not isinstance(assets, list) or not assets:
        errors.append("assets must be a non-empty array")
        return errors
    seen: set[str] = set()
    for index, asset in enumerate(assets):
        prefix = f"assets[{index}]"
        if not isinstance(asset, dict):
            errors.append(f"{prefix} must be an object")
            continue
        asset_id = asset.get("id")
        if not isinstance(asset_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", asset_id):
            errors.append(f"{prefix}.id must be a stable kebab-case ID")
        elif asset_id in seen:
            errors.append(f"{prefix}.id duplicates {asset_id}")
        else:
            seen.add(asset_id)
        if asset.get("kind") not in KINDS:
            errors.append(f"{prefix}.kind is not approved")
        source = asset.get("sourcePath")
        source_path = (root / source).resolve() if isinstance(source, str) else None
        if not isinstance(source, str) or source_path is None or root.resolve() not in source_path.parents:
            errors.append(f"{prefix}.sourcePath must stay inside the media root")
        elif not source_path.is_file():
            errors.append(f"{prefix}.sourcePath does not exist: {source}")
        if not isinstance(asset.get("alt"), str) or not asset["alt"].strip() or GENERIC_ALT.fullmatch(asset.get("alt", "").strip()):
            errors.append(f"{prefix}.alt must describe the image")
        for required in ("attributionId", "license"):
            if not isinstance(asset.get(required), str) or not asset[required].strip():
                errors.append(f"{prefix}.{required} is required")
        if asset.get("visibility") not in VISIBILITIES:
            errors.append(f"{prefix}.visibility must be public or private")
        source_url = asset.get("sourceUrl")
        if source_url and DISALLOWED_URL.search(source_url):
            errors.append(f"{prefix}.sourceUrl matches a prohibited hotlink pattern")
        focal = asset.get("focalPoint")
        if focal is not None and (not isinstance(focal, dict) or any(not isinstance(focal.get(axis), (int, float)) or not 0 <= focal[axis] <= 1 for axis in ("x", "y"))):
            errors.append(f"{prefix}.focalPoint values must be between 0 and 1")
    return errors


def build(manifest_path: Path, output_dir: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = manifest_path.parent
    errors = validate_manifest(manifest, root)
    if errors:
        raise MediaValidationError("media manifest rejected:\n" + "\n".join(f"- {error}" for error in errors))
    staging = output_dir.with_name(output_dir.name + ".staging")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    built: list[dict[str, Any]] = []
    for asset in manifest["assets"]:
        source = (root / asset["sourcePath"]).resolve()
        digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
        width, height = _dimensions(source)
        variants = []
        for variant_width in (390, 768, 1440):
            if variant_width > width:
                continue
            variant_name = f"{asset['id']}-{digest}-{variant_width}{source.suffix.lower()}"
            target = staging / variant_name
            if not target.exists():
                shutil.copyfile(source, target)
            variants.append({"width": variant_width, "path": variant_name, "format": source.suffix.lower().lstrip(".")})
        built.append({**asset, "width": width, "height": height, "aspectRatio": round(width / height, 6), "hash": digest, "variants": variants})
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    staging.rename(output_dir)
    result = {"version": manifest["version"], "tripId": manifest["tripId"], "assets": built}
    (output_dir / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result
