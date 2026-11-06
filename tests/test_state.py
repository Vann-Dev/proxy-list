import json
import tempfile
import unittest
from pathlib import Path

from proxy_state import ProxyState

NOW = 1_800_000_000.0
HOUR = 3600.0


class ProxyStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "state.json"

    def tearDown(self):
        self.temp.cleanup()

    def test_missing_state_file_is_empty(self):
        state = ProxyState.load(self.path)
        self.assertEqual(state.entries, {})
        self.assertFalse(state.should_skip("8.8.8.8:8080", NOW))

    def test_corrupt_state_file_is_ignored(self):
        self.path.write_text("{not json", encoding="utf-8")
        self.assertEqual(ProxyState.load(self.path).entries, {})

    def test_proxy_is_skipped_after_repeated_failures(self):
        state = ProxyState.load(self.path, min_failures=2, skip_hours=24)
        state.record("8.8.8.8:8080", ok=False, now=NOW)
        self.assertFalse(state.should_skip("8.8.8.8:8080", NOW))
        state.record("8.8.8.8:8080", ok=False, now=NOW)
        self.assertTrue(state.should_skip("8.8.8.8:8080", NOW + HOUR))

    def test_skip_expires_and_proxy_is_retried(self):
        state = ProxyState.load(self.path, min_failures=2, skip_hours=24)
        state.record("8.8.8.8:8080", ok=False, now=NOW)
        state.record("8.8.8.8:8080", ok=False, now=NOW)
        self.assertFalse(state.should_skip("8.8.8.8:8080", NOW + 25 * HOUR))

    def test_success_resets_consecutive_failures(self):
        state = ProxyState.load(self.path, min_failures=2, skip_hours=24)
        state.record("8.8.8.8:8080", ok=False, now=NOW)
        state.record("8.8.8.8:8080", ok=True, now=NOW + HOUR)
        state.record("8.8.8.8:8080", ok=False, now=NOW + 2 * HOUR)
        self.assertFalse(state.should_skip("8.8.8.8:8080", NOW + 3 * HOUR))
        entry = state.entries["8.8.8.8:8080"]
        self.assertEqual(entry["successes"], 1)
        self.assertEqual(entry["failures"], 2)
        self.assertEqual(entry["consecutive_failures"], 1)

    def test_skipping_can_be_disabled(self):
        state = ProxyState.load(self.path, min_failures=1, skip_hours=0)
        state.record("8.8.8.8:8080", ok=False, now=NOW)
        self.assertFalse(state.should_skip("8.8.8.8:8080", NOW))

    def test_prune_drops_stale_entries(self):
        state = ProxyState.load(self.path)
        state.record("8.8.8.8:8080", ok=True, now=NOW)
        state.record("1.1.1.1:8080", ok=True, now=NOW + 30 * 24 * HOUR)
        removed = state.prune(max_age_days=14, now=NOW + 30 * 24 * HOUR)
        self.assertEqual(removed, 1)
        self.assertNotIn("8.8.8.8:8080", state.entries)
        self.assertIn("1.1.1.1:8080", state.entries)

    def test_save_and_load_roundtrip(self):
        state = ProxyState.load(self.path)
        state.record("8.8.8.8:8080", ok=True, now=NOW)
        state.save(now=NOW)

        reloaded = ProxyState.load(self.path, min_failures=2, skip_hours=24)
        self.assertEqual(reloaded.entries["8.8.8.8:8080"]["successes"], 1)
        self.assertEqual(reloaded.entries["8.8.8.8:8080"]["last_ok"], "2027-01-15T08:00:00Z")

        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], 1)
        self.assertEqual(payload["updated_at"], "2027-01-15T08:00:00Z")


if __name__ == "__main__":
    unittest.main()
