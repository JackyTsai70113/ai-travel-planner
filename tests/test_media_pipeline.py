from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from media.pipeline import MediaValidationError, build, validate_manifest


SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="720"><rect width="1440" height="720"/></svg>'


class MediaPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "route.svg").write_text(SVG, encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def manifest(self) -> dict:
        return {"version": "1.0.0", "tripId": "fixture", "assets": [{"id": "route", "kind": "route", "sourcePath": "route.svg", "alt": "自製路線插畫", "attributionId": "self", "license": "CC0-1.0", "visibility": "public"}]}

    def test_build_hashes_source_and_records_dimensions(self) -> None:
        path = self.root / "site-media.json"
        path.write_text(json.dumps(self.manifest()), encoding="utf-8")
        result = build(path, self.root / "dist")
        asset = result["assets"][0]
        self.assertEqual((asset["width"], asset["height"]), (1440, 720))
        self.assertEqual(len(asset["hash"]), 16)
        self.assertTrue((self.root / "dist" / "manifest.json").is_file())

    def test_rejects_missing_attribution_and_generic_alt(self) -> None:
        manifest = self.manifest()
        manifest["assets"][0]["alt"] = "image"
        manifest["assets"][0]["license"] = ""
        errors = validate_manifest(manifest, self.root)
        self.assertTrue(any("alt" in error for error in errors))
        self.assertTrue(any("license" in error for error in errors))

    def test_rejects_google_hotlink_and_missing_source(self) -> None:
        manifest = self.manifest()
        manifest["assets"][0]["sourceUrl"] = "https://maps.google.com/photo"
        manifest["assets"][0]["sourcePath"] = "missing.svg"
        errors = validate_manifest(manifest, self.root)
        self.assertTrue(any("hotlink" in error for error in errors))
        self.assertTrue(any("does not exist" in error for error in errors))

    def test_failed_build_does_not_leave_output(self) -> None:
        path = self.root / "site-media.json"
        bad = self.manifest()
        bad["assets"][0]["sourcePath"] = "missing.svg"
        path.write_text(json.dumps(bad), encoding="utf-8")
        with self.assertRaises(MediaValidationError):
            build(path, self.root / "dist")
        self.assertFalse((self.root / "dist").exists())


if __name__ == "__main__":
    unittest.main()
