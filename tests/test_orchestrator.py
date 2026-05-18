import unittest

from orchestrator import InterSliceMigrationOrchestrator, MigrationState


class TestInterSliceMigrationOrchestrator(unittest.TestCase):
    def setUp(self) -> None:
        self.orchestrator = InterSliceMigrationOrchestrator()

    def test_happy_path_migration(self) -> None:
        session = self.orchestrator.prepare_migration(
            session_id="ue-1001",
            source_slice="embb",
            target_slice="urllc",
            payload={"smf_context": "ctx-1"},
        )
        self.assertEqual(session.state, MigrationState.PREPARED)

        self.orchestrator.transfer_context("ue-1001", 60)
        session = self.orchestrator.transfer_context("ue-1001", 40)
        self.assertEqual(session.transfer_progress, 100)
        self.assertEqual(session.state, MigrationState.TRANSFERRING)

        committed = self.orchestrator.commit_migration("ue-1001")
        self.assertEqual(committed.state, MigrationState.COMMITTED)
        self.assertEqual(committed.source_slice, "urllc")
        self.assertIn("migration_committed", committed.events)

    def test_commit_requires_full_transfer(self) -> None:
        self.orchestrator.prepare_migration(
            session_id="ue-1002",
            source_slice="embb",
            target_slice="mmtc",
            payload={"amf_context": "ctx-2"},
        )
        self.orchestrator.transfer_context("ue-1002", 25)
        with self.assertRaisesRegex(ValueError, "100%"):
            self.orchestrator.commit_migration("ue-1002")

    def test_rollback_resets_progress(self) -> None:
        self.orchestrator.prepare_migration(
            session_id="ue-1003",
            source_slice="mmtc",
            target_slice="urllc",
            payload={"pcf_context": "ctx-3"},
        )
        self.orchestrator.transfer_context("ue-1003", 50)
        rolled_back = self.orchestrator.rollback_migration("ue-1003")

        self.assertEqual(rolled_back.state, MigrationState.ROLLED_BACK)
        self.assertEqual(rolled_back.transfer_progress, 0)
        self.assertIn("migration_rolled_back", rolled_back.events)


if __name__ == "__main__":
    unittest.main()
