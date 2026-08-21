from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from src.web_publisher import build_all, build_trip, init_site


ROOT = Path(__file__).resolve().parents[1]


class WebPublisherTests(unittest.TestCase):
    def test_build_all_emits_two_trip_registry_and_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "site"
            results = build_all(ROOT / "site-configs", output)
            self.assertEqual({result.slug for result in results}, {"awaji-2026", "kyushu-2026"})
            registry = json.loads((output / "registry.json").read_text())
            self.assertEqual(registry["schema_version"], "trip-registry-v1")
            self.assertEqual({item["theme_id"] for item in registry["trips"]}, {"setouchi-awaji", "snow-kyushu"})
            self.assertEqual({item["duration_days"] for item in registry["trips"]}, {3, 5})
            self.assertTrue((output / "trips/awaji-2026/index.html").exists())
            self.assertTrue((output / "trips/kyushu-2026/public-bundle.json").exists())
            for result in results:
                report = json.loads(result.report_path.read_text())
                self.assertEqual(report["outputs"]["bundle_sha256"], result.bundle_sha256)

    def test_bundle_has_generic_contract_and_no_sensitive_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "site"
            build_all(ROOT / "site-configs", output)
            bundle = json.loads((output / "trips/kyushu-2026/public-bundle.json").read_text())
            self.assertEqual(bundle["schema_version"], "trip-public-bundle-v1")
            self.assertEqual(bundle["site"]["slug"], "kyushu-2026")
            text = json.dumps(bundle).lower()
            for secret in ("api_key", "password", "access_token", "booking_reference"):
                self.assertNotIn(secret, text)
            self.assertNotIn("awaji", text)

    def test_scaffold_contains_no_trip_facts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config, media = init_site("hokkaido-2027", "hokkaido-2027", "snow-hokkaido", Path(directory))
            self.assertIn("trip-site-v1", config.read_text())
            self.assertEqual(json.loads(media.read_text())["assets"], [])

    def test_published_trip_without_validation_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = json.loads((ROOT / "site-configs/kyushu-2026/site.json").read_text())
            config["publication_status"] = "published"
            config_path = root / "site.json"
            media_path = root / "site-media.json"
            trip_path = root / "trip.json"
            config_path.write_text(json.dumps(config))
            media_path.write_text((ROOT / "site-configs/kyushu-2026/site-media.json").read_text())
            trip_path.write_text((ROOT / "site-configs/kyushu-2026/trip.json").read_text())
            with self.assertRaises(ValueError):
                build_trip(trip_path, config_path, root / "out")

    def test_invalid_slug_and_private_trip_field_are_rejected_or_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = json.loads((ROOT / "site-configs/kyushu-2026/site.json").read_text())
            config["slug"] = "../escape"
            config_path = root / "site.json"
            config_path.write_text(json.dumps(config))
            with self.assertRaises(ValueError):
                build_trip(ROOT / "site-configs/kyushu-2026/trip.json", config_path, root / "out")

    def test_module_cli_is_available(self) -> None:
        result = subprocess.run(["python3", "-m", "src.web_publisher", "--help"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("build-all", result.stdout)

    def test_rebuild_keeps_public_projection_stable_except_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "site"
            build_all(ROOT / "site-configs", output)
            first_hashes = [item["bundle_sha256"] for item in json.loads((output / "registry.json").read_text())["trips"]]
            first = json.loads((output / "trips/kyushu-2026/public-bundle.json").read_text())
            build_all(ROOT / "site-configs", output)
            second_hashes = [item["bundle_sha256"] for item in json.loads((output / "registry.json").read_text())["trips"]]
            second = json.loads((output / "trips/kyushu-2026/public-bundle.json").read_text())
            first["build"].pop("generated_at", None)
            second["build"].pop("generated_at", None)
            self.assertEqual(first, second)
            self.assertEqual(first_hashes, second_hashes)


if __name__ == "__main__":
    unittest.main()
