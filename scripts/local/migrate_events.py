#!/usr/bin/env python3
"""Migrate events from iiagentdev_backup.events → iiagentdev.application_events.

Maps old snake_case event types to new dotted event names and groups.
Skips events whose session_id doesn't exist in the new sessions table.
"""

import json
import uuid

import psycopg2
import psycopg2.extras

# ── Connection strings ─────────────────────────────────────────────────
OLD_DSN = "dbname=iiagentdev_backup user=iiagent password=iiagent host=localhost port=5433"
NEW_DSN = "dbname=iiagentdev user=iiagent password=iiagent host=localhost port=5433"

# ── Event type mapping: old_type → (new_event_type, event_group) ──────
EVENT_TYPE_MAP = {
    "user_message": ("session.user_message", "session"),
    "processing": ("agent.processing", "agent"),
    "agent_initialized": ("sandbox.initialized", "sandbox"),
    "agent_thinking": ("agent.reasoning", "agent"),
    "agent_response": ("agent.response", "agent"),
    "agent_response_interrupted": ("agent.response.interrupted", "agent"),
    "tool_call": ("agent.tool.call", "agent"),
    "tool_result": ("agent.tool.result", "agent"),
    "complete": ("agent.complete", "agent"),
    "status_update": ("agent.status.update", "agent"),
    "metrics_update": ("billing.llm.usage", "billing"),
    "sandbox_status": ("sandbox.status_changed", "sandbox"),
    "error": ("system.error", "system"),
    "sub_agent_complete": ("agent.sub_agent.complete", "agent"),
    "sub_agent_interrupted": ("agent.response.interrupted", "agent"),
    "model_compact": ("agent.model.compact", "agent"),
}

# The dev@localhost user who now owns all data
DEV_USER_ID = "eac4f4fd-0aa6-4f98-b6fb-91156deb670b"


def migrate():
    old_conn = psycopg2.connect(OLD_DSN)
    new_conn = psycopg2.connect(NEW_DSN)

    try:
        # Get valid session IDs from new DB
        with new_conn.cursor() as cur:
            cur.execute("SELECT id FROM sessions")
            valid_sessions = {str(row[0]) for row in cur.fetchall()}

        print(f"Found {len(valid_sessions)} sessions in new DB")

        # Check existing events to avoid duplicates
        with new_conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM application_events")
            existing = cur.fetchone()[0]
        print(f"Existing application_events: {existing}")

        if existing > 0:
            print("application_events already has data — aborting to prevent duplicates")
            return

        # Read old events
        with old_conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("""
                SELECT id, session_id, type, content, source, created_at, run_id
                FROM events
                ORDER BY created_at ASC
            """)
            old_events = cur.fetchall()

        print(f"Read {len(old_events)} events from backup")

        # Transform and insert
        inserted = 0
        skipped_session = 0
        skipped_type = 0

        with new_conn.cursor() as cur:
            for ev in old_events:
                old_type = ev["type"]
                session_id = ev["session_id"]

                # Skip if session doesn't exist in new DB
                if session_id not in valid_sessions:
                    skipped_session += 1
                    continue

                # Map event type
                mapping = EVENT_TYPE_MAP.get(old_type)
                if not mapping:
                    skipped_type += 1
                    print(f"  Unknown event type: {old_type}")
                    continue

                new_type, event_group = mapping

                # Parse content (old is json, new is jsonb)
                content = ev["content"]
                if isinstance(content, str):
                    content = json.loads(content)

                # Enrich content with run_id and origin for frontend compatibility
                if content is None:
                    content = {}
                if ev["run_id"] and "run_id" not in content:
                    content["run_id"] = str(ev["run_id"])

                # Add origin field that frontend expects
                origin_map = {
                    "agent.response": "RunContentEvent",
                    "agent.reasoning": "RunContentEvent",
                    "agent.processing": "RunStartedEvent",
                    "agent.complete": "RunCompletedEvent",
                    "agent.tool.call": "ToolCallStartedEvent",
                    "agent.tool.result": "ToolCallCompletedEvent",
                    "agent.response.interrupted": "RunContentEvent",
                    "agent.sub_agent.complete": "RunCompletedEvent",
                    "session.user_message": "UserMessageEvent",
                }
                if "origin" not in content and new_type in origin_map:
                    content["origin"] = origin_map[new_type]

                # Use existing UUID id or generate new one
                event_id = ev["id"]
                try:
                    uuid.UUID(event_id)
                except (ValueError, AttributeError):
                    event_id = str(uuid.uuid4())

                cur.execute(
                    """
                    INSERT INTO application_events
                        (id, event_type, event_group, session_id, run_id, user_id, content, created_at, updated_at)
                    VALUES (%s, %s, %s, %s::uuid, %s::uuid, %s::uuid, %s::jsonb, %s, %s)
                """,
                    (
                        event_id,
                        new_type,
                        event_group,
                        session_id,
                        str(ev["run_id"]) if ev["run_id"] else None,
                        DEV_USER_ID,
                        json.dumps(content),
                        ev["created_at"],
                        ev["created_at"],  # updated_at = created_at for migrated data
                    ),
                )
                inserted += 1

            new_conn.commit()

        print("\nMigration complete:")
        print(f"  Inserted:        {inserted}")
        print(f"  Skipped (no session): {skipped_session}")
        print(f"  Skipped (unknown type): {skipped_type}")

        # Verify
        with new_conn.cursor() as cur:
            cur.execute(
                "SELECT event_type, count(*) FROM application_events GROUP BY event_type ORDER BY count(*) DESC"
            )
            print("\nNew event type distribution:")
            for row in cur.fetchall():
                print(f"  {row[0]}: {row[1]}")

    finally:
        old_conn.close()
        new_conn.close()


if __name__ == "__main__":
    migrate()
