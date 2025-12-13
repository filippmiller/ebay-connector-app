"""Backfill parsed_body JSONB for existing ebay_messages rows.

Run with the same Python environment as the backend, with DATABASE_URL set.

Example:

    python -m backend.scripts.backfill_parsed_message_bodies
"""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.services.message_parser import parse_ebay_message_html


BATCH_SIZE = 100


def get_engine() -> Engine:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set")
    return create_engine(url)


def backfill_batch(engine: Engine) -> int:
    """Process a single batch of messages with NULL parsed_body.

    Returns the number of rows updated.
    """

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, body
                FROM ebay_messages
                WHERE parsed_body IS NULL
                  AND body IS NOT NULL
                ORDER BY id
                LIMIT :limit
                """
            ),
            {"limit": BATCH_SIZE},
        ).mappings().all()

        if not rows:
            return 0

        updated = 0
        for row in rows:
            msg_id = row["id"]
            body_html = row["body"] or ""
            parsed: dict[str, Any] | None = None
            try:
                if body_html:
                    parsed_model = parse_ebay_message_html(body_html)
                    parsed = parsed_model.dict(exclude_none=True)
            except Exception as exc:  # noqa: BLE001
                # Parsing errors should never abort the whole backfill; log to stderr and continue.
                print(f"[WARN] Failed to parse message {msg_id}: {exc}")
                parsed = None

            conn.execute(
                text("UPDATE ebay_messages SET parsed_body = :parsed WHERE id = :id"),
                {"id": msg_id, "parsed": parsed},
            )
            updated += 1

        return updated


def main() -> None:
    engine = get_engine()
    total = 0
    while True:
        batch = backfill_batch(engine)
        if batch == 0:
            break
        total += batch
        print(f"Updated {batch} messages in this batch (running total={total})")

    print(f"Done. Total messages updated: {total}")


if __name__ == "__main__":  # pragma: no cover - manual script entry point
    main()
