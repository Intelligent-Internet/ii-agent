"""Cron job to extend sandbox timeouts for permanent sessions."""

from __future__ import annotations

import asyncio
import argparse
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.sessions.models import Session
from ii_agent.core.db import get_db_session_local
from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from ii_agent.agents.sandboxes.service import SandboxService

# Constants
TIMEOUT_EXTENSION_SECONDS = 7200  # 2 hours extension
BATCH_SIZE = 10  # Process sandboxes in batches to avoid overloading


class SandboxTimeoutExtender:
    """Service to extend sandbox timeouts for permanent sessions."""

    def __init__(self, sandbox_service: Optional[SandboxService] = None):
        if sandbox_service is None:
            from ii_agent.agents.sandboxes.service import SandboxService
            from ii_agent.agents.sandboxes.repository import SandboxRepository
            from ii_agent.core.config.settings import get_settings

            sandbox_service = SandboxService(
                config=get_settings(),
                sandbox_repo=SandboxRepository(),
            )
        self._sandbox_service = sandbox_service

    async def get_permanent_sessions(self, db: AsyncSession) -> List[Session]:
        """Get all permanent sessions that have an active sandbox."""
        from ii_agent.agents.sandboxes.models import AgentSandbox
        from ii_agent.agents.sandboxes.types import SandboxStatus

        result = await db.execute(
            select(Session).where(
                Session.status == "permanent",
                Session.id.in_(
                    select(AgentSandbox.session_id).where(
                        AgentSandbox.status != SandboxStatus.DELETED
                    )
                ),
            )
        )
        return result.scalars().all()

    async def extend_sandbox_timeout(
        self, db: AsyncSession, session: Session, timeout_seconds: int = TIMEOUT_EXTENSION_SECONDS
    ) -> bool:
        """Extend timeout for a single sandbox."""
        try:
            sandbox = await self._sandbox_service.get_sandbox_by_session_id(db, session.id)
            if not sandbox:
                logger.warning(f"No sandbox found for session {session.id}")
                return False

            # NOTE: do NOT pass ``db`` here. The cron shares one session
            # across an asyncio.gather() batch and never commits inline; the
            # short-lived self-managed session inside ``set_timeout`` (with
            # lock_timeout=5s + wait_for=10s backstops) is the correct path.
            await sandbox.set_timeout(timeout_seconds)

            logger.info(
                f"Extended timeout for sandbox (session: {session.id}) by {timeout_seconds} seconds"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to extend timeout for sandbox (session: {session.id}): {str(e)}")
            return False

    async def process_batch(
        self,
        db: AsyncSession,
        sessions: List[Session],
        timeout_seconds: int = TIMEOUT_EXTENSION_SECONDS,
    ) -> tuple[int, int]:
        """Process a batch of sessions concurrently."""
        tasks = [self.extend_sandbox_timeout(db, session, timeout_seconds) for session in sessions]
        results = await asyncio.gather(*tasks)

        success_count = sum(1 for r in results if r)
        failure_count = len(results) - success_count

        return success_count, failure_count

    async def run(self) -> dict:
        """Main method to run the timeout extension job."""
        start_time = datetime.now(timezone.utc)
        total_success = 0
        total_failure = 0

        logger.info("Starting sandbox timeout extension job")

        async with get_db_session_local() as db:
            try:
                sessions = await self.get_permanent_sessions(db)

                total_sessions = len(sessions)

                if total_sessions == 0:
                    logger.info("No permanent sessions with sandboxes found")
                    return {
                        "status": "success",
                        "message": "No permanent sessions to process",
                        "total_sessions": 0,
                        "successful": 0,
                        "failed": 0,
                        "duration_seconds": (
                            datetime.now(timezone.utc) - start_time
                        ).total_seconds(),
                    }

                logger.info(f"Found {total_sessions} permanent sessions with sandboxes")

                # Process sessions in batches
                for i in range(0, total_sessions, BATCH_SIZE):
                    batch = sessions[i : i + BATCH_SIZE]
                    success, failure = await self.process_batch(db, batch)
                    total_success += success
                    total_failure += failure

                    logger.info(
                        f"Batch {i // BATCH_SIZE + 1}: Success: {success}, Failure: {failure}"
                    )

                    # Small delay between batches to avoid overwhelming the system
                    if i + BATCH_SIZE < total_sessions:
                        await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Error during sandbox timeout extension job: {str(e)}")
                raise

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()

        result = {
            "status": "success" if total_failure == 0 else "partial",
            "message": f"Processed {total_success + total_failure} sessions",
            "total_sessions": total_success + total_failure,
            "successful": total_success,
            "failed": total_failure,
            "duration_seconds": duration,
        }

        logger.info(
            f"Sandbox timeout extension job completed: "
            f"Success: {total_success}, Failure: {total_failure}, "
            f"Duration: {duration:.2f}s"
        )

        return result


async def main():
    """Main entry point for the cron job."""
    parser = argparse.ArgumentParser(description="Extend sandbox timeouts for permanent sessions")
    parser.add_argument("--config-file", type=str, help="Path to configuration file", default=None)

    args = parser.parse_args()

    # Create extender instance
    extender = SandboxTimeoutExtender()

    # Run the job
    result = await extender.run()

    # Print result for cron logging
    print(f"Job result: {result}")

    return result


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
