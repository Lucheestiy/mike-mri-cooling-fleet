import datetime as dt
import importlib.util
import json
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "backup_coverage.py"
SPEC = importlib.util.spec_from_file_location("backup_coverage", MODULE_PATH)
backup_coverage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backup_coverage)


class RestoreStatusTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 7, 15, 23, 0, tzinfo=dt.timezone.utc)

    def test_successful_recent_restore_is_current(self):
        item = {
            "repository": "agcmr3",
            "status": "success",
            "completed_at": "2026-07-15T22:00:00+00:00",
        }
        parsed = backup_coverage.parse_restore_tests(json.dumps(item), self.now)
        self.assertTrue(parsed[0]["recent"])

    def test_failed_or_stale_restore_is_not_current(self):
        failed = {
            "repository": "gmcep3",
            "status": "failure",
            "completed_at": "2026-07-15T22:00:00+00:00",
        }
        stale = {
            "repository": "agcmr3",
            "status": "success",
            "completed_at": "2026-01-01T00:00:00+00:00",
        }
        output = "\n".join((json.dumps(failed), json.dumps(stale), "not-json"))
        parsed = backup_coverage.parse_restore_tests(output, self.now)
        self.assertEqual([item["recent"] for item in parsed], [False, False])

    def test_successful_backup_status_requires_valid_completed_marker(self):
        valid = {
            "repository": "gcmcmr2",
            "status": "success",
            "snapshot_id": "abc123",
            "completed_at": "2026-07-15T22:00:00+00:00",
        }
        failed = dict(valid, repository="vwm2", status="failure")
        missing_time = {"repository": "vwm3", "status": "success"}
        parsed = backup_coverage.parse_successful_backup_status(
            "\n".join((json.dumps(valid), json.dumps(failed), json.dumps(missing_time))),
            self.now,
        )
        self.assertEqual(set(parsed), {"gcmcmr2"})
        self.assertEqual(parsed["gcmcmr2"]["item"]["snapshot_id"], "abc123")

    def test_json_stream_accepts_pretty_printed_adjacent_objects(self):
        first = {"repository": "agcmr2", "status": "success"}
        second = {"repository": "vwm3", "status": "success"}
        output = json.dumps(first, indent=2) + "\n" + json.dumps(second, indent=2)
        self.assertEqual(
            backup_coverage.parse_json_stream(output), [first, second]
        )

    def test_prepared_onboarding_requires_both_target_and_repository(self):
        status = backup_coverage.prepared_onboarding_status(
            {"gcmcmr2", "vwm2"}, {"gcmcmr2", "vwm3"}, {"gcmcmr2", "vwm2"}
        )
        by_name = {item["repository"]: item for item in status}
        self.assertTrue(by_name["gcmcmr2"]["onboarded"])
        self.assertFalse(by_name["vwm2"]["onboarded"])
        self.assertFalse(by_name["vwm3"]["onboarded"])
        self.assertEqual(set(by_name), set(backup_coverage.PREPARED_ONBOARDING_TARGETS))

    def test_prepared_onboarding_rejects_empty_initialized_repository(self):
        status = backup_coverage.prepared_onboarding_status(
            {"agcmr2"}, {"agcmr2"}, set()
        )
        agcmr2 = next(item for item in status if item["repository"] == "agcmr2")
        self.assertTrue(agcmr2["repository_present"])
        self.assertFalse(agcmr2["first_backup_verified"])
        self.assertFalse(agcmr2["onboarded"])

    def test_restore_verifier_status_distinguishes_install_and_authorization(self):
        self.assertEqual(
            backup_coverage.restore_verifier_status(False, False),
            "hub_sudo_install_required",
        )
        self.assertEqual(
            backup_coverage.restore_verifier_status(True, False),
            "authorization_missing",
        )
        self.assertEqual(
            backup_coverage.restore_verifier_status(False, True),
            "verifier_missing",
        )
        self.assertEqual(
            backup_coverage.restore_verifier_status(True, True),
            "ready",
        )

    def test_restore_sweep_status_requires_enabled_timer_and_clean_last_run(self):
        timer = {"UnitFileState": "enabled", "ActiveState": "active"}
        self.assertEqual(backup_coverage.restore_sweep_status(timer, {}), "ready")
        self.assertEqual(
            backup_coverage.restore_sweep_status(timer, {"Result": "exit-code"}),
            "last_run_failed",
        )
        self.assertEqual(
            backup_coverage.restore_sweep_status(
                {"UnitFileState": "disabled", "ActiveState": "inactive"}, {}
            ),
            "timer_not_ready",
        )

    def test_batch_completion_requires_every_configured_target_in_service_window(self):
        now = dt.datetime(2026, 7, 17, 9, 0, tzinfo=dt.timezone(dt.timedelta(hours=-4)))
        statuses = {
            "agcmr1": {"completed": dt.datetime(2026, 7, 17, 5, 38, 12, tzinfo=now.tzinfo)},
            "agcmr2": {"completed": dt.datetime(2026, 7, 16, 22, 0, 0, tzinfo=now.tzinfo)},
        }
        result = backup_coverage.batch_completion(
            {"agcmr1", "agcmr2"},
            statuses,
            "Fri 2026-07-17 05:30:01 EDT",
            "Fri 2026-07-17 05:38:13 EDT",
            now,
        )
        self.assertFalse(result["complete"])
        self.assertEqual(result["completed_targets"], ["agcmr1"])
        self.assertEqual(result["missing_targets"], ["agcmr2"])

    def test_batch_completion_accepts_all_targets_within_finish_grace(self):
        now = dt.datetime(2026, 7, 17, 9, 0, tzinfo=dt.timezone(dt.timedelta(hours=-4)))
        statuses = {
            "one": {"completed": dt.datetime(2026, 7, 17, 5, 31, tzinfo=now.tzinfo)},
            "two": {"completed": dt.datetime(2026, 7, 17, 5, 39, tzinfo=now.tzinfo)},
        }
        result = backup_coverage.batch_completion(
            {"one", "two"}, statuses,
            "Fri 2026-07-17 05:30:01 EDT", "Fri 2026-07-17 05:38:13 EDT", now,
        )
        self.assertTrue(result["complete"])

    def test_batch_completion_uses_in_window_history_after_a_targeted_refresh(self):
        timezone = dt.timezone(dt.timedelta(hours=-4))
        now = dt.datetime(2026, 7, 17, 17, 15, tzinfo=timezone)
        result = backup_coverage.batch_completion(
            {"agcmr1", "agcmr2"},
            [
                {"repository": "agcmr1", "completed": dt.datetime(2026, 7, 17, 16, 1, tzinfo=timezone)},
                {"repository": "agcmr1", "completed": dt.datetime(2026, 7, 17, 17, 9, tzinfo=timezone)},
                {"repository": "agcmr2", "completed": dt.datetime(2026, 7, 17, 16, 2, tzinfo=timezone)},
            ],
            "Fri 2026-07-17 15:50:12 EDT",
            "Fri 2026-07-17 16:22:33 EDT",
            now,
        )
        self.assertTrue(result["complete"])
        self.assertEqual(result["completed_targets"], ["agcmr1", "agcmr2"])
        self.assertEqual(result["completed_count"], 2)


if __name__ == "__main__":
    unittest.main()
