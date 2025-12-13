from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from pydantic.config import ConfigDict
import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.models_sqlalchemy import get_db
from app.models_sqlalchemy.models import EbayAccount
from app.services.auth import admin_required
from app.services.ebay_account_service import ebay_account_service


router = APIRouter(prefix="/api/admin/ebay/business-policies", tags=["admin-ebay-business-policies"])


class BusinessPolicyDto(BaseModel):
    id: str
    policy_type: str
    policy_id: str
    policy_name: str
    policy_description: Optional[str] = None
    is_default: bool
    is_active: bool
    sort_order: int


class BusinessPoliciesResponseDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    shipping: List[BusinessPolicyDto] = Field(default_factory=list)
    payment: List[BusinessPolicyDto] = Field(default_factory=list)
    return_: List[BusinessPolicyDto] = Field(default_factory=list, alias="return")


class BusinessPoliciesDefaultsDto(BaseModel):
    shipping_policy_id: Optional[str] = None
    payment_policy_id: Optional[str] = None
    return_policy_id: Optional[str] = None


class BusinessPolicyCreateDto(BaseModel):
    account_key: str = Field("default", min_length=1)
    marketplace_id: str = Field("EBAY_US", min_length=1)
    policy_type: str = Field(..., description="SHIPPING | PAYMENT | RETURN")
    policy_id: int = Field(..., ge=1)
    policy_name: str = Field(..., min_length=1)
    policy_description: Optional[str] = None
    is_default: bool = False
    sort_order: int = 0
    is_active: bool = True


class BusinessPolicyUpdateDto(BaseModel):
    policy_name: Optional[str] = None
    policy_description: Optional[str] = None
    is_default: Optional[bool] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


@router.get("", response_model=BusinessPoliciesResponseDto, dependencies=[Depends(admin_required)])
async def list_business_policies(
    account_key: str = Query("default"),
    marketplace_id: str = Query("EBAY_US"),
    db: Session = Depends(get_db),
) -> BusinessPoliciesResponseDto:
    rows = db.execute(
        text(
            """
            SELECT
              id::text AS id,
              policy_type,
              policy_id,
              policy_name,
              policy_description,
              is_default,
              is_active,
              sort_order
            FROM public.ebay_business_policies
            WHERE account_key = :account_key
              AND marketplace_id = :marketplace_id
            ORDER BY policy_type, is_default DESC, sort_order ASC, policy_name ASC
            """
        ),
        {"account_key": account_key, "marketplace_id": marketplace_id},
    ).mappings().all()

    out: Dict[str, List[BusinessPolicyDto]] = {"SHIPPING": [], "PAYMENT": [], "RETURN": []}
    for r in rows:
        dto = BusinessPolicyDto(
            id=str(r["id"]),
            policy_type=str(r["policy_type"]),
            policy_id=str(r["policy_id"]),
            policy_name=str(r["policy_name"]),
            policy_description=r.get("policy_description"),
            is_default=bool(r.get("is_default")),
            is_active=bool(r.get("is_active")),
            sort_order=int(r.get("sort_order") or 0),
        )
        out.get(dto.policy_type, []).append(dto)

    return BusinessPoliciesResponseDto(
        shipping=out["SHIPPING"],
        payment=out["PAYMENT"],
        return_=out["RETURN"],
    )


@router.get("/defaults", response_model=BusinessPoliciesDefaultsDto, dependencies=[Depends(admin_required)])
async def get_business_policy_defaults(
    account_key: str = Query("default"),
    marketplace_id: str = Query("EBAY_US"),
    db: Session = Depends(get_db),
) -> BusinessPoliciesDefaultsDto:
    row = db.execute(
        text(
            """
            SELECT shipping_policy_id, payment_policy_id, return_policy_id
            FROM public.ebay_business_policies_defaults
            WHERE account_key = :account_key AND marketplace_id = :marketplace_id
            """
        ),
        {"account_key": account_key, "marketplace_id": marketplace_id},
    ).first()

    if not row:
        return BusinessPoliciesDefaultsDto()

    return BusinessPoliciesDefaultsDto(
        shipping_policy_id=str(row[0]) if row[0] is not None else None,
        payment_policy_id=str(row[1]) if row[1] is not None else None,
        return_policy_id=str(row[2]) if row[2] is not None else None,
    )


@router.post("", response_model=BusinessPolicyDto, dependencies=[Depends(admin_required)])
async def create_business_policy(
    payload: BusinessPolicyCreateDto,
    db: Session = Depends(get_db),
) -> BusinessPolicyDto:
    pt = payload.policy_type.strip().upper()
    if pt not in {"SHIPPING", "PAYMENT", "RETURN"}:
        raise HTTPException(status_code=400, detail="invalid_policy_type")

    try:
        # If setting new default, unset existing default for same scope/type.
        if payload.is_default:
            db.execute(
                text(
                    """
                    UPDATE public.ebay_business_policies
                    SET is_default = FALSE
                    WHERE account_key = :account_key
                      AND marketplace_id = :marketplace_id
                      AND policy_type = :policy_type
                      AND is_default = TRUE
                    """
                ),
                {
                    "account_key": payload.account_key,
                    "marketplace_id": payload.marketplace_id,
                    "policy_type": pt,
                },
            )

        row = db.execute(
            text(
                """
                INSERT INTO public.ebay_business_policies
                  (account_key, marketplace_id, policy_type, policy_id, policy_name, policy_description,
                   is_default, sort_order, is_active)
                VALUES
                  (:account_key, :marketplace_id, :policy_type, :policy_id, :policy_name, :policy_description,
                   :is_default, :sort_order, :is_active)
                RETURNING
                  id::text, policy_type, policy_id, policy_name, policy_description, is_default, is_active, sort_order
                """
            ),
            {
                "account_key": payload.account_key,
                "marketplace_id": payload.marketplace_id,
                "policy_type": pt,
                "policy_id": int(payload.policy_id),
                "policy_name": payload.policy_name,
                "policy_description": payload.policy_description,
                "is_default": bool(payload.is_default),
                "sort_order": int(payload.sort_order),
                "is_active": bool(payload.is_active),
            },
        ).mappings().first()
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"failed_to_create_policy: {exc}")

    if not row:
        raise HTTPException(status_code=500, detail="failed_to_create_policy")

    return BusinessPolicyDto(
        id=str(row["id"]),
        policy_type=str(row["policy_type"]),
        policy_id=str(row["policy_id"]),
        policy_name=str(row["policy_name"]),
        policy_description=row.get("policy_description"),
        is_default=bool(row.get("is_default")),
        is_active=bool(row.get("is_active")),
        sort_order=int(row.get("sort_order") or 0),
    )


@router.put("/{policy_row_id}", response_model=BusinessPolicyDto, dependencies=[Depends(admin_required)])
async def update_business_policy(
    policy_row_id: str,
    payload: BusinessPolicyUpdateDto,
    db: Session = Depends(get_db),
) -> BusinessPolicyDto:
    """
    Update editable fields for a policy row.

    Notes:
    - policy_type and policy_id are treated as immutable identifiers.
    - If is_default is set to TRUE, we unset the existing default in the same scope/type.
    """
    row = db.execute(
        text(
            """
            SELECT
              id::text AS id,
              account_key,
              marketplace_id,
              policy_type,
              policy_id,
              policy_name,
              policy_description,
              is_default,
              is_active,
              sort_order
            FROM public.ebay_business_policies
            WHERE id::text = :id
            LIMIT 1
            """
        ),
        {"id": policy_row_id},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="policy_not_found")

    data = payload.model_dump(exclude_unset=True)
    if not data:
        # No changes requested; return current row
        return BusinessPolicyDto(
            id=str(row["id"]),
            policy_type=str(row["policy_type"]),
            policy_id=str(row["policy_id"]),
            policy_name=str(row["policy_name"]),
            policy_description=row.get("policy_description"),
            is_default=bool(row.get("is_default")),
            is_active=bool(row.get("is_active")),
            sort_order=int(row.get("sort_order") or 0),
        )

    try:
        # If setting as default, unset old default for same scope/type.
        if data.get("is_default") is True:
            db.execute(
                text(
                    """
                    UPDATE public.ebay_business_policies
                    SET is_default = FALSE
                    WHERE account_key = :account_key
                      AND marketplace_id = :marketplace_id
                      AND policy_type = :policy_type
                      AND is_default = TRUE
                      AND id::text <> :id
                    """
                ),
                {
                    "account_key": row["account_key"],
                    "marketplace_id": row["marketplace_id"],
                    "policy_type": row["policy_type"],
                    "id": policy_row_id,
                },
            )

        # Patch the row
        upd_cols: list[str] = []
        params: dict = {"id": policy_row_id}
        for key in ("policy_name", "policy_description", "is_default", "sort_order", "is_active"):
            if key in data:
                upd_cols.append(f"{key} = :{key}")
                params[key] = data[key]

        if upd_cols:
            db.execute(
                text(
                    f"""
                    UPDATE public.ebay_business_policies
                    SET {", ".join(upd_cols)}
                    WHERE id::text = :id
                    """
                ),
                params,
            )

        updated = db.execute(
            text(
                """
                SELECT
                  id::text AS id,
                  policy_type,
                  policy_id,
                  policy_name,
                  policy_description,
                  is_default,
                  is_active,
                  sort_order
                FROM public.ebay_business_policies
                WHERE id::text = :id
                LIMIT 1
                """
            ),
            {"id": policy_row_id},
        ).mappings().first()

        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"failed_to_update_policy: {exc}")

    if not updated:
        raise HTTPException(status_code=500, detail="failed_to_update_policy")

    return BusinessPolicyDto(
        id=str(updated["id"]),
        policy_type=str(updated["policy_type"]),
        policy_id=str(updated["policy_id"]),
        policy_name=str(updated["policy_name"]),
        policy_description=updated.get("policy_description"),
        is_default=bool(updated.get("is_default")),
        is_active=bool(updated.get("is_active")),
        sort_order=int(updated.get("sort_order") or 0),
    )


@router.delete("/{policy_row_id}", response_model=dict, dependencies=[Depends(admin_required)])
async def delete_business_policy(
    policy_row_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """Delete a policy row by id."""
    try:
        res = db.execute(
            text(
                """
                DELETE FROM public.ebay_business_policies
                WHERE id::text = :id
                """
            ),
            {"id": policy_row_id},
        )
        db.commit()
        return {"deleted": int(res.rowcount or 0)}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"failed_to_delete_policy: {exc}")


class SyncBusinessPoliciesRequestDto(BaseModel):
    """Sync policies from eBay Sell Account API into public.ebay_business_policies."""

    account_id: str = Field(..., min_length=1, description="Internal ebay_accounts.id (UUID)")
    account_key: Optional[str] = Field(None, description="Target account_key in ebay_business_policies; defaults to account_id")
    marketplace_id: Optional[str] = Field(None, description="Defaults to ebay_accounts.marketplace_id or EBAY_US")
    deactivate_missing: bool = False


async def _fetch_account_policies(access_token: str, path: str, list_key: str) -> list[dict]:
    """Fetch all pages from Sell Account API list endpoints."""
    items: list[dict] = []
    limit = 200
    offset = 0
    base = settings.ebay_api_base_url.rstrip("/")

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        while True:
            url = f"{base}{path}"
            resp = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                params={"limit": limit, "offset": offset},
            )
            try:
                data = resp.json() if resp.content else {}
            except Exception:
                data = {}

            if not (200 <= resp.status_code < 300):
                raise HTTPException(
                    status_code=resp.status_code,
                    detail={"message": "ebay_account_api_error", "path": path, "status": resp.status_code, "body": data or resp.text},
                )

            page = data.get(list_key) or []
            if isinstance(page, list):
                items.extend(page)
            else:
                # Some endpoints may return singular objects; keep defensive.
                break

            total = data.get("total")
            if total is None:
                # No pagination metadata; stop after first page.
                break
            try:
                total_int = int(total)
            except Exception:
                break

            offset += limit
            if offset >= total_int:
                break

    return items


@router.post("/sync-from-ebay", dependencies=[Depends(admin_required)])
async def sync_business_policies_from_ebay(
    payload: SyncBusinessPoliciesRequestDto,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    account: EbayAccount | None = db.query(EbayAccount).filter(EbayAccount.id == payload.account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="ebay_account_not_found")
    if not account.is_active:
        raise HTTPException(status_code=400, detail="ebay_account_inactive")

    t = ebay_account_service.get_token(db, account.id)
    access_token = t.access_token if t else None
    if not access_token:
        raise HTTPException(status_code=400, detail="missing_oauth_token_for_account")

    account_key = (payload.account_key or account.id).strip()
    marketplace_id = (payload.marketplace_id or account.marketplace_id or "EBAY_US").strip() or "EBAY_US"

    # Sell Account API endpoints
    fulfillment = await _fetch_account_policies(access_token, "/sell/account/v1/fulfillment_policy", "fulfillmentPolicies")
    payment = await _fetch_account_policies(access_token, "/sell/account/v1/payment_policy", "paymentPolicies")
    returns = await _fetch_account_policies(access_token, "/sell/account/v1/return_policy", "returnPolicies")

    def _upsert_many(policy_type: str, rows: list[dict]) -> int:
        upserted = 0
        for r in rows:
            pid = r.get("fulfillmentPolicyId") or r.get("paymentPolicyId") or r.get("returnPolicyId") or r.get("policyId") or r.get("id")
            if pid is None:
                continue
            try:
                pid_int = int(pid)
            except Exception:
                continue

            name = (r.get("name") or r.get("policyName") or f"{policy_type} {pid_int}").strip()
            desc = r.get("description") or r.get("policyDescription")
            raw = json.dumps(r, ensure_ascii=False)
            db.execute(
                text(
                    """
                    INSERT INTO public.ebay_business_policies
                      (account_key, marketplace_id, policy_type, policy_id, policy_name, policy_description, is_active, raw_source)
                    VALUES
                      (:account_key, :marketplace_id, :policy_type, :policy_id, :policy_name, :policy_description, TRUE, :raw_source::jsonb)
                    ON CONFLICT (account_key, marketplace_id, policy_type, policy_id)
                    DO UPDATE SET
                      policy_name = EXCLUDED.policy_name,
                      policy_description = EXCLUDED.policy_description,
                      is_active = TRUE,
                      raw_source = EXCLUDED.raw_source,
                      updated_at = NOW()
                    """
                ),
                {
                    "account_key": account_key,
                    "marketplace_id": marketplace_id,
                    "policy_type": policy_type,
                    "policy_id": pid_int,
                    "policy_name": name,
                    "policy_description": desc,
                    "raw_source": raw,
                },
            )
            upserted += 1
        return upserted

    upserted_shipping = _upsert_many("SHIPPING", fulfillment)
    upserted_payment = _upsert_many("PAYMENT", payment)
    upserted_return = _upsert_many("RETURN", returns)

    deactivated = 0
    if payload.deactivate_missing:
        def _deactivate(policy_type: str, rows: list[dict]) -> int:
            ids: list[int] = []
            for r in rows:
                pid = r.get("fulfillmentPolicyId") or r.get("paymentPolicyId") or r.get("returnPolicyId") or r.get("policyId") or r.get("id")
                try:
                    ids.append(int(pid))
                except Exception:
                    continue
            if not ids:
                return 0
            res = db.execute(
                text(
                    """
                    UPDATE public.ebay_business_policies
                    SET is_active = FALSE, updated_at = NOW()
                    WHERE account_key = :account_key
                      AND marketplace_id = :marketplace_id
                      AND policy_type = :policy_type
                      AND policy_id <> ALL(:ids)
                    """
                ),
                {"account_key": account_key, "marketplace_id": marketplace_id, "policy_type": policy_type, "ids": ids},
            )
            return int(res.rowcount or 0)

        deactivated += _deactivate("SHIPPING", fulfillment)
        deactivated += _deactivate("PAYMENT", payment)
        deactivated += _deactivate("RETURN", returns)

    db.commit()
    return {
        "status": "ok",
        "account_id": account.id,
        "account_key": account_key,
        "marketplace_id": marketplace_id,
        "counts": {
            "shipping": upserted_shipping,
            "payment": upserted_payment,
            "return": upserted_return,
            "deactivated": deactivated,
        },
    }

