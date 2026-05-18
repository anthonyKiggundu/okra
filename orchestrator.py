from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class MigrationState(str, Enum):
    PENDING = "pending"
    PREPARED = "prepared"
    TRANSFERRING = "transferring"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"


@dataclass
class SessionContext:
    session_id: str
    source_slice: str
    target_slice: str
    payload: dict
    state: MigrationState = MigrationState.PENDING
    transfer_progress: int = 0
    events: list[str] = field(default_factory=list)

    def record(self, event: str) -> None:
        self.events.append(event)


class InterSliceMigrationOrchestrator:
    """
    Stateful orchestrator for inter-slice context migration in a 5G control plane.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, SessionContext] = {}

    def prepare_migration(
        self, session_id: str, source_slice: str, target_slice: str, payload: dict
    ) -> SessionContext:
        if source_slice == target_slice:
            raise ValueError("source_slice and target_slice must differ")
        if session_id in self._sessions:
            raise ValueError(f"migration already exists for session '{session_id}'")
        session = SessionContext(
            session_id=session_id,
            source_slice=source_slice,
            target_slice=target_slice,
            payload=dict(payload),
            state=MigrationState.PREPARED,
        )
        session.record("migration_prepared")
        self._sessions[session_id] = session
        return session

    def transfer_context(self, session_id: str, progress_increment: int) -> SessionContext:
        session = self._get(session_id)
        if session.state not in (MigrationState.PREPARED, MigrationState.TRANSFERRING):
            raise ValueError(f"cannot transfer context while state is '{session.state}'")
        if progress_increment <= 0:
            raise ValueError("progress_increment must be positive")
        session.state = MigrationState.TRANSFERRING
        session.transfer_progress = min(100, session.transfer_progress + progress_increment)
        session.record(f"context_transferred:{session.transfer_progress}")
        return session

    def commit_migration(self, session_id: str) -> SessionContext:
        session = self._get(session_id)
        if session.transfer_progress < 100:
            raise ValueError("context transfer must reach 100% before commit")
        if session.state not in (MigrationState.TRANSFERRING, MigrationState.PREPARED):
            raise ValueError(f"cannot commit migration while state is '{session.state}'")
        session.state = MigrationState.COMMITTED
        session.source_slice = session.target_slice
        session.record("migration_committed")
        return session

    def rollback_migration(self, session_id: str) -> SessionContext:
        session = self._get(session_id)
        if session.state in (MigrationState.COMMITTED, MigrationState.ROLLED_BACK):
            raise ValueError(f"cannot rollback migration while state is '{session.state}'")
        session.state = MigrationState.ROLLED_BACK
        session.transfer_progress = 0
        session.record("migration_rolled_back")
        return session

    def get_session(self, session_id: str) -> SessionContext:
        return self._get(session_id)

    def _get(self, session_id: str) -> SessionContext:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise KeyError(f"session '{session_id}' not found") from exc
