from app.database import get_db
from app.models_sqlalchemy.ebay_workers import EbayTokenRefreshLog


def _fmt(dt):
    return dt.isoformat() if dt else ""


def main() -> None:
    db = next(get_db())
    try:
        logs = (
            db.query(EbayTokenRefreshLog)
            .order_by(EbayTokenRefreshLog.started_at.asc())
            .all()
        )

        print("# Token Refresh Worker Logs")
        print()
        print(f"Total records: {len(logs)}")
        print()
        print("| # | Log ID | Account ID | Started At (UTC) | Finished At (UTC) | Success | Error Code | Error Message | Old Expires At | New Expires At | Triggered By |")
        print("|---|--------|------------|------------------|-------------------|---------|-----------|---------------|----------------|----------------|-------------|")

        for idx, log in enumerate(logs, 1):
            msg = (log.error_message or "").replace("\n", " ").replace("|", "\\|")[:200]
            print(
                f"| {idx} | {log.id} | {log.ebay_account_id} | {_fmt(log.started_at)} | "
                f"{_fmt(log.finished_at)} | {log.success} | {log.error_code or ''} | {msg} | "
                f"{_fmt(log.old_expires_at)} | {_fmt(log.new_expires_at)} | {log.triggered_by} |"
            )
    finally:
        db.close()


if __name__ == "__main__":  # pragma: no cover
    main()
