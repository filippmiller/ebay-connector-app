from datetime import datetime, timezone
from typing import Optional

from app.models_sqlalchemy import SessionLocal
from app.models_sqlalchemy.models import EbayAccount, EbayToken


def _to_utc(dt) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def main() -> None:
    target_user = "mil_243"  # ebay_user_id from your logs

    db = SessionLocal()
    try:
        accounts = (
            db.query(EbayAccount)
            .filter(EbayAccount.ebay_user_id == target_user)
            .all()
        )
        now = datetime.now(timezone.utc)
        out = []
        for acc in accounts:
            token: Optional[EbayToken] = (
                db.query(EbayToken)
                .filter(EbayToken.ebay_account_id == acc.id)
                .one_or_none()
            )
            if not token:
                out.append({
                    "account_id": acc.id,
                    "house_name": acc.house_name,
                    "has_token": False,
                })
                continue

            expires_at_utc = _to_utc(token.expires_at)
            expires_in = None
            if expires_at_utc is not None:
                expires_in = int((expires_at_utc - now).total_seconds())

            out.append({
                "account_id": acc.id,
                "house_name": acc.house_name,
                "ebay_user_id": acc.ebay_user_id,
                "token_id": token.id,
                "has_refresh_token": bool(token.refresh_token),
                "expires_at": expires_at_utc.isoformat() if expires_at_utc else None,
                "expires_in_seconds": expires_in,
                "refresh_error": token.refresh_error,
            })

        import json
        print(json.dumps(out, ensure_ascii=False, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
