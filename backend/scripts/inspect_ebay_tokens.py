"""Inspect eBay token state for all accounts (masked, read-only).

Usage (from backend/ directory with DATABASE_URL configured):

    python -m scripts.inspect_ebay_tokens

This prints, for each EbayAccount:
- account id / house_name / ebay_user_id / org_id
- whether a refresh token exists
- masked prefix of the stored refresh token (to distinguish ENC: vs v^)
- current refresh_error (if any)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.models_sqlalchemy import get_db
from app.models_sqlalchemy.models import EbayAccount, EbayToken


@dataclass
class MaskedTokenInfo:
    has_refresh_token: bool
    stored_prefix: Optional[str]
    length: int


def _mask_refresh_token(raw: Optional[str]) -> MaskedTokenInfo:
    if not raw:
        return MaskedTokenInfo(False, None, 0)
    prefix_len = min(10, len(raw))
    return MaskedTokenInfo(True, raw[:prefix_len], len(raw))


def main() -> None:
    session = next(get_db())
    try:
        accounts = (
            session.query(EbayAccount)
            .order_by(EbayAccount.house_name.asc())
            .all()
        )
        print(f"Found {len(accounts)} ebay_accounts\n")

        for acc in accounts:
            token: Optional[EbayToken] = (
                session.query(EbayToken)
                .filter(EbayToken.ebay_account_id == acc.id)
                .order_by(EbayToken.updated_at.desc())
                .first()
            )

            masked = _mask_refresh_token(
                token.refresh_token if token and token.refresh_token else None
            )

            print("Account:")
            print(f"  id         : {acc.id}")
            print(f"  house_name : {acc.house_name}")
            print(f"  ebay_user  : {acc.ebay_user_id}")
            print(f"  org_id     : {acc.org_id}")

            print("  token:")
            print(f"    has_refresh_token : {masked.has_refresh_token}")
            print(f"    stored_prefix     : {masked.stored_prefix}")
            print(f"    length            : {masked.length}")
            if token is not None:
                print(f"    refresh_error     : {getattr(token, 'refresh_error', None)}")
                print(
                    f"    expires_at        : {getattr(token, 'expires_at', None)}"
                )
            print("")

    finally:
        session.close()


if __name__ == "__main__":  # pragma: no cover - manual diagnostic
    main()
