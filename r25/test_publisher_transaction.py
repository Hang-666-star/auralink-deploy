"""Fault injection into the actual transaction core; no production adapter."""
from contextlib import contextmanager
from dataclasses import replace
import unittest

from publisher_transaction import Publisher, PublicationFailed, RecoveryPlan, Refused, Release

OLD = Release("a" * 40, "b" * 64, "c" * 64)
NEW = Release("d" * 40, "e" * 64, "f" * 64)


class RuntimeFixture:
    def __init__(self, failure=None):
        self.events = []
        self.held = False
        self.selected = OLD
        self.live = OLD
        self.phase = None
        self.failure = failure
        self.failed = False
        self.downgrade_blocked = False
        self.foreign_drift = False

    def event(self, name):
        assert self.held, "operation escaped shared lease"
        self.events.append(name)
        if self.failure == name and not self.failed:
            self.failed = True
            raise RuntimeError("injected failure")

    @contextmanager
    def lease(self):
        assert not self.held
        self.held = True
        self.events.append("lease_acquired")
        try: yield
        finally:
            self.held = False
            self.events.append("lease_released")

    def current(self): self.event("current"); return self.selected
    def verify_current(self, current):
        self.event("verify_current")
        if current != self.selected or current != self.live: raise Refused("current_mismatch")
    def verify_candidate(self, candidate): self.event("verify_candidate")
    def require_compatible(self, target):
        self.event("compatible_old" if target == OLD else "compatible_new")
        if target == OLD and self.downgrade_blocked: raise Refused("retained_huaniao")
    def require_no_active_work(self): self.event("idle")
    def snapshot(self, current, candidate): self.event("snapshot"); return "snapshot-1"
    def begin(self, current, candidate, snapshot_id):
        self.event("begin")
        self.plan = RecoveryPlan("transaction-1", current, candidate, snapshot_id, "PREPARED")
        return self.plan.transaction_id
    def record(self, transaction_id, phase, **evidence):
        self.event("record_" + phase)
        self.phase = phase
    def stop_owned_java(self, current): self.event("stop")
    def install_candidate(self, candidate, snapshot_id):
        self.live = candidate  # Partial write may precede an exception.
        self.event("install")
    def start_and_verify(self, release): self.event("start_verify")
    def commit_current(self, new, expected):
        if self.selected != expected: raise Refused("current_compare_failed")
        self.selected = new  # Simulate commit succeeded but acknowledgement lost.
        self.event("commit_current")
    def load_recovery(self, transaction_id):
        self.event("load_recovery")
        return replace(self.plan, phase=self.phase)
    def validate_recovery(self, plan):
        self.event("validate_recovery")
        if self.foreign_drift: raise Refused("foreign_drift")
    def stop_for_restore(self, plan): self.event("stop_for_restore")
    def restore_snapshot(self, plan):
        self.event("restore")
        self.live = self.selected = plan.current
    def verify_restored(self, plan):
        self.event("verify_restored")
        if self.live != plan.current or self.selected != plan.current: raise Refused("restore_mismatch")


class TransactionTests(unittest.TestCase):
    def test_success_commits_current_only_after_acceptance(self):
        rt = RuntimeFixture()
        result = Publisher(rt).publish(NEW)
        self.assertEqual(result.outcome, "COMMITTED")
        self.assertLess(rt.events.index("snapshot"), rt.events.index("stop"))
        self.assertLess(rt.events.index("start_verify"), rt.events.index("commit_current"))
        self.assertEqual(rt.events.count("lease_acquired"), 1)
        self.assertEqual(rt.events[-1], "lease_released")

    def test_failed_initial_gate_never_stops_or_installs(self):
        for gate in ("verify_current", "verify_candidate", "compatible_new", "compatible_old", "idle", "snapshot"):
            rt = RuntimeFixture(gate)
            with self.subTest(gate=gate), self.assertRaises(RuntimeError): Publisher(rt).publish(NEW)
            self.assertNotIn("stop", rt.events)
            self.assertNotIn("install", rt.events)

    def test_failures_and_unknown_current_commit_outcome_restore_and_fail(self):
        for step in ("stop", "install", "start_verify", "commit_current", "record_COMMITTED"):
            rt = RuntimeFixture(step)
            with self.subTest(step=step), self.assertRaises(PublicationFailed) as caught:
                Publisher(rt).publish(NEW)
            self.assertTrue(caught.exception.recovered)
            self.assertEqual(rt.selected, OLD)
            self.assertEqual(rt.live, OLD)
            self.assertEqual(rt.phase, "RESTORED")

    def test_new_retained_data_forbids_downgrade_on_failure(self):
        rt = RuntimeFixture()
        def failed_acceptance(release):
            rt.event("start_verify")
            rt.downgrade_blocked = True
            raise RuntimeError("acceptance failed")
        rt.start_and_verify = failed_acceptance
        with self.assertRaises(PublicationFailed) as caught: Publisher(rt).publish(NEW)
        self.assertFalse(caught.exception.recovered)
        self.assertNotIn("restore", rt.events)
        self.assertEqual(rt.phase, "RECOVERY_REQUIRED")

    def test_foreign_drift_is_not_overwritten_during_recovery(self):
        rt = RuntimeFixture("install")
        rt.foreign_drift = True
        with self.assertRaises(PublicationFailed) as caught: Publisher(rt).publish(NEW)
        self.assertFalse(caught.exception.recovered)
        self.assertNotIn("restore", rt.events)

    def test_restore_rechecks_downgrade_after_candidate_stops(self):
        rt = RuntimeFixture("start_verify")
        def stop_for_restore(plan):
            rt.event("stop_for_restore")
            # Simulate retained data appearing after the first pre-stop query.
            rt.downgrade_blocked = True
        rt.stop_for_restore = stop_for_restore
        with self.assertRaises(PublicationFailed) as caught: Publisher(rt).publish(NEW)
        self.assertFalse(caught.exception.recovered)
        self.assertIn("stop_for_restore", rt.events)
        self.assertNotIn("restore", rt.events)
        self.assertEqual(rt.phase, "RECOVERY_REQUIRED")

    def test_explicit_rollback_rechecks_compatibility_and_pointer(self):
        rt = RuntimeFixture()
        publisher = Publisher(rt)
        publisher.publish(NEW)
        rt.downgrade_blocked = True
        with self.assertRaises(Refused): publisher.rollback("transaction-1")
        self.assertEqual(rt.selected, NEW)
        rt.downgrade_blocked = False
        self.assertEqual(publisher.rollback("transaction-1").outcome, "RESTORED")
        self.assertEqual(publisher.recover("transaction-1").outcome, "RESTORED_VERIFIED_NOOP")

    def test_repeated_exact_release_is_verified_noop(self):
        rt = RuntimeFixture()
        self.assertEqual(Publisher(rt).publish(OLD).outcome, "CURRENT_VERIFIED_NOOP")
        self.assertNotIn("snapshot", rt.events)
        self.assertNotIn("stop", rt.events)

    def test_explicit_rollback_post_stop_failure_records_recovery_required(self):
        rt = RuntimeFixture()
        publisher = Publisher(rt)
        publisher.publish(NEW)
        def stop_for_restore(plan):
            rt.event("stop_for_restore")
            rt.downgrade_blocked = True
        rt.stop_for_restore = stop_for_restore
        with self.assertRaises(Refused): publisher.rollback("transaction-1")
        self.assertEqual(rt.phase, "RECOVERY_REQUIRED")
        self.assertNotIn("restore", rt.events)

    def test_explicit_recovery_failure_records_recovery_required(self):
        rt = RuntimeFixture()
        publisher = Publisher(rt)
        publisher.publish(NEW)
        rt.phase = "RECOVERY_REQUIRED"  # Persisted interrupted transition.
        rt.failure = "restore"
        with self.assertRaises(RuntimeError): publisher.recover("transaction-1")
        self.assertEqual(rt.phase, "RECOVERY_REQUIRED")


if __name__ == "__main__":
    unittest.main()
