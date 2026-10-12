"""R25 Core publication transaction, with no unbound production CLI.

Runtime is a new adapter contract, not a claim that these methods are installed
on the server. The adapter must enforce CORE_RELEASE_CONTRACT.md. In particular
it owns the Linux lease, accepted-artifact registry, process identity checks,
durable filesystem journal and compare-and-swap CURRENT. This module never
executes candidate-provided code, chooses arbitrary live paths, or overrides
the installed legacy hash allowlists.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import ContextManager, Protocol


@dataclass(frozen=True)
class Release:
    commit_sha: str
    artifact_sha256: str
    accepted_record_sha256: str


@dataclass(frozen=True)
class RecoveryPlan:
    transaction_id: str
    current: Release
    candidate: Release
    snapshot_id: str
    phase: str


@dataclass(frozen=True)
class Result:
    outcome: str
    release: Release
    transaction_id: str | None = None


class Refused(RuntimeError):
    pass


class PublicationFailed(RuntimeError):
    def __init__(self, transaction_id, recovered, primary, recovery=None):
        super().__init__("publication_failed_restored" if recovered else "publication_failed_recovery_required")
        self.transaction_id = transaction_id
        self.recovered = recovered
        # Preserve error classes without exposing arbitrary commands/configuration.
        self.primary_failure = type(primary).__name__
        self.recovery_failure = type(recovery).__name__ if recovery else None


class Runtime(Protocol):
    """Every method runs under the same validated deployment lease.

    All arguments are references to trusted private state. They are never
    interpreted as arbitrary shell commands or arbitrary target paths.
    """
    def lease(self) -> ContextManager[None]: ...
    def current(self) -> Release: ...
    def verify_current(self, current: Release) -> None: ...
    def verify_rollback_source(self, current: Release) -> None:
        """Optional identity-only source check for an unhealthy business feature.

        The target still passes full compatibility and post-restore acceptance.
        Adapters without this method retain verify_current's existing behavior.
        """
        ...
    def verify_candidate(self, candidate: Release) -> None: ...
    def require_compatible(self, target: Release) -> None:
        """Authoritative readonly DB/media checks, including retained huaniao."""
        ...
    def require_no_active_work(self) -> None: ...
    def snapshot(self, current: Release, candidate: Release) -> str:
        """Guard space and files; immutable complete backup before process stop."""
        ...
    def begin(self, current: Release, candidate: Release, snapshot_id: str) -> str: ...
    def record(self, transaction_id: str, phase: str, **evidence) -> None:
        """Durable write-ahead journal, atomic replace plus directory fsync."""
        ...
    def stop_owned_java(self, current: Release) -> None:
        """Use existing owned watchdog/Java stop; preserve Web/AI/Tunnel."""
        ...
    def install_candidate(self, candidate: Release, snapshot_id: str) -> None:
        """Fixed owned file set only; validate pair/control mappings after writes."""
        ...
    def start_and_verify(self, release: Release) -> None:
        """Owned PID/ticks/argv, both JARs, real HTTP/PG contract and watchdog."""
        ...
    def commit_current(self, new: Release, expected: Release) -> None:
        """Compare and atomically replace CURRENT after health verification."""
        ...
    def load_recovery(self, transaction_id: str) -> RecoveryPlan:
        """Validate IDs/journal/checksums; no caller-supplied path evaluation."""
        ...
    def validate_recovery(self, plan: RecoveryPlan) -> None:
        """Verify full backup + known owned live states; reject foreign drift."""
        ...
    def stop_for_restore(self, plan: RecoveryPlan) -> None:
        """Stop only the journal-bound owned Java/watchdog, including partial states."""
        ...
    def restore_snapshot(self, plan: RecoveryPlan) -> None:
        """Complete file/control restore after stop, restored start and checks.

        Restore CURRENT only after restored version is healthy, with a CAS
        allowing only the journal's previous/candidate pointer values.
        """
        ...
    def verify_restored(self, plan: RecoveryPlan) -> None: ...


RECOVERABLE = {"STOP_INTENT", "STOPPED", "INSTALL_INTENT", "INSTALLED",
               "START_INTENT", "ACCEPTED", "CURRENT_COMMIT_INTENT",
               "RECOVERY_REQUIRED", "RESTORE_STOP_INTENT", "RESTORE_STOPPED", "RESTORE_INTENT"}


class Publisher:
    def __init__(self, runtime: Runtime):
        self.runtime = runtime

    def _restore(self, plan):
        rt = self.runtime
        rt.validate_recovery(plan)
        # Re-read live DB state. Earlier acceptance/zero counts do not authorize
        # a later downgrade once records/reservations or in-flight work exist.
        rt.require_compatible(plan.current)
        rt.require_no_active_work()
        rt.record(plan.transaction_id, "RESTORE_STOP_INTENT")
        try:
            rt.stop_for_restore(plan)
            rt.record(plan.transaction_id, "RESTORE_STOPPED")
            # A still-running candidate may accept work between the first query
            # and its stop. Recheck before restoring old bytes.
            rt.require_compatible(plan.current)
            rt.require_no_active_work()
            rt.record(plan.transaction_id, "RESTORE_INTENT")
            rt.restore_snapshot(plan)
            rt.verify_restored(plan)
            rt.record(plan.transaction_id, "RESTORED")
            return Result("RESTORED", plan.current, plan.transaction_id)
        except BaseException as error:
            # Also applies to explicit recover/rollback, which do not pass
            # through publish's failure handler. The service may already be
            # stopped, so preserve a consistent actionable failure state.
            try:
                rt.record(plan.transaction_id, "RECOVERY_REQUIRED", recovery_failure_class=type(error).__name__)
            except BaseException:
                pass
            raise

    def publish(self, candidate):
        rt = self.runtime
        with rt.lease():
            current = rt.current()
            rt.verify_current(current)
            rt.verify_candidate(candidate)
            rt.require_compatible(candidate)
            if current == candidate:
                return Result("CURRENT_VERIFIED_NOOP", current)
            # Require a compatible recovery target before entering this ordinary
            # no-schema-change path. Incompatible upgrade belongs elsewhere.
            rt.require_compatible(current)
            rt.require_no_active_work()
            snapshot_id = rt.snapshot(current, candidate)
            transaction_id = rt.begin(current, candidate, snapshot_id)
            plan = RecoveryPlan(transaction_id, current, candidate, snapshot_id, "PREPARED")
            rt.record(transaction_id, "PREPARED")
            try:
                rt.record(transaction_id, "STOP_INTENT")
                rt.stop_owned_java(current)
                rt.record(transaction_id, "STOPPED")
                # Catch work submitted between the first query and the owned
                # stop; do not silently proceed with a now-stale idle proof.
                rt.require_no_active_work()
                rt.require_compatible(candidate)
                rt.record(transaction_id, "INSTALL_INTENT")
                rt.install_candidate(candidate, snapshot_id)
                rt.record(transaction_id, "INSTALLED")
                rt.record(transaction_id, "START_INTENT")
                rt.start_and_verify(candidate)
                rt.record(transaction_id, "ACCEPTED")
                rt.record(transaction_id, "CURRENT_COMMIT_INTENT")
                rt.commit_current(candidate, expected=current)
                rt.record(transaction_id, "COMMITTED")
                return Result("COMMITTED", candidate, transaction_id)
            except BaseException as primary:
                # A failed CURRENT commit can have an unknown write outcome.
                # The adapter inspects actual files/pointer under the lease;
                # never assume an exception means that nothing was written.
                try:
                    rt.record(transaction_id, "RECOVERY_REQUIRED", failure_class=type(primary).__name__)
                    plan = rt.load_recovery(transaction_id)
                    self._restore(plan)
                except BaseException as recovery:
                    # If journal storage itself failed, a second journal write
                    # must not hide the original and recovery error classes.
                    try:
                        rt.record(transaction_id, "RECOVERY_REQUIRED", recovery_failure_class=type(recovery).__name__)
                    except BaseException:
                        pass
                    raise PublicationFailed(transaction_id, False, primary, recovery) from primary
                raise PublicationFailed(transaction_id, True, primary) from primary

    def recover(self, transaction_id):
        rt = self.runtime
        with rt.lease():
            plan = rt.load_recovery(transaction_id)
            if plan.phase == "COMMITTED":
                rt.verify_current(plan.candidate)
                return Result("COMMITTED_VERIFIED_NOOP", plan.candidate, transaction_id)
            if plan.phase == "RESTORED":
                rt.verify_restored(plan)
                return Result("RESTORED_VERIFIED_NOOP", plan.current, transaction_id)
            if plan.phase == "PREPARED":
                # No stop/install intent was entered. Abort only after proving
                # that all current files and the running version are original.
                rt.validate_recovery(plan)
                rt.verify_restored(plan)
                rt.record(transaction_id, "RESTORED")
                return Result("PREPARED_ABORTED_UNCHANGED", plan.current, transaction_id)
            if plan.phase not in RECOVERABLE:
                raise Refused("recovery_state_not_eligible")
            return self._restore(plan)

    def rollback(self, transaction_id):
        """Explicit rollback after success; current pointer must still match.

        This is the new release contract, not the old migration writer's
        record-essential-regression escape hatch. Both versions must remain
        compatible with authoritative live data at the time of rollback.
        """
        rt = self.runtime
        with rt.lease():
            plan = rt.load_recovery(transaction_id)
            if plan.phase != "COMMITTED" or rt.current() != plan.candidate:
                raise Refused("rollback_current_changed_or_not_committed")
            verify_source = getattr(rt, 'verify_rollback_source', rt.verify_current)
            verify_source(plan.candidate)
            return self._restore(plan)
