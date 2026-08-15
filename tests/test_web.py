import json
import os
import threading
import time
import unittest
from http.client import HTTPConnection
from pathlib import Path
from tempfile import TemporaryDirectory

from src.renderer.build_site import build_site
from src.web import DashboardApp, create_server


FIXTURE = Path("fixtures/trips/japan-5-day-trip-v1.json")


class RecordedService:
    def __init__(self, trips, site): self.trips, self.site = trips, site; self.calls = []
    def plan(self, request, trip_id, progress):
        self.calls.append(request)
        for stage in ("parsing", "research", "candidate store", "routing", "planning", "optimizing", "validation / repair", "rendering"):
            progress(stage)
        trip = json.loads(FIXTURE.read_text())
        trip["id"] = trip_id
        target = self.trips / trip_id; target.mkdir(parents=True)
        (target / "trip.json").write_text(json.dumps(trip))
        rendered = self.site / trip_id; rendered.mkdir(parents=True)
        (rendered / "index.html").write_text(build_site(trip))
        return {"trip": trip}


class MissingService:
    def plan(self, request, trip_id, progress):
        exc = RuntimeError("configuration_missing: GOOGLE_MAPS_API_KEY")
        raise exc


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(); root = Path(self.tmp.name)
        self.service = RecordedService(root / "trips", root / "site")
        self.app = DashboardApp(trips_directory=root / "trips", site_directory=root / "site", service=self.service)
        self.server = create_server(self.app, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)

    def tearDown(self):
        self.conn.close(); self.server.shutdown(); self.server.server_close(); self.tmp.cleanup()

    def request(self, method, path, data=None):
        self.conn.request(method, path, data, {"Content-Type": "application/json"} if data else {})
        response = self.conn.getresponse(); return response.status, response.read().decode()

    def test_natural_language_submission_progress_and_trip_tabs(self):
        status, body = self.request("POST", "/api/plans", json.dumps({"request": "幫我規劃 5 天 4 夜德島＋神戶，2 大 1 個 2 歲小孩，台北出發"}))
        self.assertEqual(202, status); job = json.loads(body)
        for _ in range(40):
            status, body = self.request("GET", "/api/jobs/" + job["id"]); job = json.loads(body)
            if job["state"] != "running": break
            time.sleep(.02)
        self.assertEqual("complete", job["state"])
        self.assertEqual(["parsing", "research", "candidate store", "routing", "planning", "optimizing", "validation / repair", "rendering"], job["stages"])
        self.assertEqual(1, len(self.service.calls))
        status, body = self.request("GET", "/api/trips/" + job["trip_id"]); view = json.loads(body)
        self.assertEqual(200, status)
        for field in ("overview", "days", "routes", "restaurants", "flights", "hotels", "budget", "sources", "validation", "website_url", "trip_json_url"):
            self.assertIn(field, view)
        self.assertTrue((self.app.trips_directory / job["trip_id"] / "trip.json").exists())
        self.assertTrue((self.app.site_directory / job["trip_id"] / "index.html").exists())

    def test_missing_configuration_is_visible_without_secret(self):
        os.environ["DASHBOARD_TEST_SECRET"] = "very-secret-value-123"
        app = DashboardApp(trips_directory=self.app.trips_directory, site_directory=self.app.site_directory, service=MissingService())
        job = app.submit("test")
        for _ in range(40):
            if job.state != "running": break
            time.sleep(.02)
        self.assertEqual("failed", job.state)
        self.assertEqual("configuration_missing", job.error["code"])
        self.assertNotIn("very-secret-value-123", json.dumps(job.public()))

    def test_home_and_artifacts_do_not_expose_environment_values(self):
        os.environ["DASHBOARD_TEST_SECRET"] = "web-secret-777"
        status, page = self.request("GET", "/")
        self.assertEqual(200, status); self.assertIn("AI Travel Planner", page)
        self.assertNotIn("web-secret-777", page)
        status, body = self.request("GET", "/trips/../../etc/passwd")
        self.assertEqual(404, status)


if __name__ == "__main__": unittest.main()
