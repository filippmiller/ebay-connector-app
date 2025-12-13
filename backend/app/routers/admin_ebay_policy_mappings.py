from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models_sqlalchemy import get_db
from app.services.auth import admin_required


router = APIRouter(prefix="/api/admin/ebay/policy-mappings", tags=["admin-ebay-policy-mappings"])


class ShippingGroupPolicyMappingDto(BaseModel):
    id: str
    account_key: str
    marketplace_id: str
    shipping_group_id: int
    shipping_type: str
    domestic_only_flag: Optional[bool] = None
    shipping_policy_id: Optional[str] = None
    payment_policy_id: Optional[str] = None
    return_policy_id: Optional[str] = None
    is_active: bool
    notes: Optional[str] = None


class ShippingGroupPolicyMappingCreateDto(BaseModel):
    account_key: str = Field("default", min_length=1)
    marketplace_id: str = Field("EBAY_US", min_length=1)

    shipping_group_id: int = Field(..., ge=1)
    shipping_type: str = Field(..., min_length=1, description="Flat | Calculated")
    domestic_only_flag: Optional[bool] = Field(None, description="null=any, true=domestic-only, false=international allowed")

    shipping_policy_id: Optional[int] = Field(None, ge=1)
    payment_policy_id: Optional[int] = Field(None, ge=1)
    return_policy_id: Optional[int] = Field(None, ge=1)

    is_active: bool = True
    notes: Optional[str] = None


@router.get("/shipping-groups", dependencies=[Depends(admin_required)])
async def list_shipping_group_mappings(
    account_key: str = Query("default"),
    marketplace_id: str = Query("EBAY_US"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    rows = db.execute(
        text(
            """
            SELECT
              id::text AS id,
              account_key,
              marketplace_id,
              shipping_group_id,
              shipping_type,
              domestic_only_flag,
              shipping_policy_id,
              payment_policy_id,
              return_policy_id,
              is_active,
              notes
            FROM public.ebay_shipping_group_policy_mappings
            WHERE account_key = :account_key
              AND marketplace_id = :marketplace_id
            ORDER BY shipping_group_id ASC, shipping_type ASC,
                     domestic_only_flag NULLS FIRST,
                     is_active DESC,
                     id DESC
            """
        ),
        {"account_key": account_key, "marketplace_id": marketplace_id},
    ).mappings().all()

    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            ShippingGroupPolicyMappingDto(
                id=str(r.get("id")),
                account_key=str(r.get("account_key") or "default"),
                marketplace_id=str(r.get("marketplace_id") or "EBAY_US"),
                shipping_group_id=int(r.get("shipping_group_id") or 0),
                shipping_type=str(r.get("shipping_type") or ""),
                domestic_only_flag=r.get("domestic_only_flag"),
                shipping_policy_id=str(r.get("shipping_policy_id")) if r.get("shipping_policy_id") is not None else None,
                payment_policy_id=str(r.get("payment_policy_id")) if r.get("payment_policy_id") is not None else None,
                return_policy_id=str(r.get("return_policy_id")) if r.get("return_policy_id") is not None else None,
                is_active=bool(r.get("is_active")),
                notes=r.get("notes"),
            ).model_dump()
        )

    return {"rows": out, "total": len(out)}


@router.post("/shipping-groups", dependencies=[Depends(admin_required)])
async def upsert_shipping_group_mapping(
    payload: ShippingGroupPolicyMappingCreateDto,
    db: Session = Depends(get_db),
) -> ShippingGroupPolicyMappingDto:
    st = payload.shipping_type.strip()
    if st.lower() not in {"flat", "calculated"}:
        raise HTTPException(status_code=400, detail="invalid_shipping_type")
    # Normalize casing to match SKU_catalog convention
    st_norm = "Flat" if st.lower() == "flat" else "Calculated"

    try:
        row = db.execute(
            text(
                """
                INSERT INTO public.ebay_shipping_group_policy_mappings
                  (account_key, marketplace_id, shipping_group_id, shipping_type, domestic_only_flag,
                   shipping_policy_id, payment_policy_id, return_policy_id, is_active, notes)
                VALUES
                  (:account_key, :marketplace_id, :shipping_group_id, :shipping_type, :domestic_only_flag,
                   :shipping_policy_id, :payment_policy_id, :return_policy_id, :is_active, :notes)
                ON CONFLICT (account_key, marketplace_id, shipping_group_id, shipping_type, domestic_only_flag)
                DO UPDATE SET
                  shipping_policy_id = EXCLUDED.shipping_policy_id,
                  payment_policy_id  = EXCLUDED.payment_policy_id,
                  return_policy_id   = EXCLUDED.return_policy_id,
                  is_active          = EXCLUDED.is_active,
                  notes              = EXCLUDED.notes,
                  updated_at         = NOW()
                RETURNING
                  id::text AS id,
                  account_key,
                  marketplace_id,
                  shipping_group_id,
                  shipping_type,
                  domestic_only_flag,
                  shipping_policy_id,
                  payment_policy_id,
                  return_policy_id,
                  is_active,
                  notes
                """
            ),
            {
                "account_key": payload.account_key,
                "marketplace_id": payload.marketplace_id,
                "shipping_group_id": int(payload.shipping_group_id),
                "shipping_type": st_norm,
                "domestic_only_flag": payload.domestic_only_flag,
                "shipping_policy_id": int(payload.shipping_policy_id) if payload.shipping_policy_id else None,
                "payment_policy_id": int(payload.payment_policy_id) if payload.payment_policy_id else None,
                "return_policy_id": int(payload.return_policy_id) if payload.return_policy_id else None,
                "is_active": bool(payload.is_active),
                "notes": payload.notes,
            },
        ).mappings().first()
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"failed_to_upsert_mapping: {exc}")

    if not row:
        raise HTTPException(status_code=500, detail="failed_to_upsert_mapping")

    return ShippingGroupPolicyMappingDto(
        id=str(row.get("id")),
        account_key=str(row.get("account_key") or "default"),
        marketplace_id=str(row.get("marketplace_id") or "EBAY_US"),
        shipping_group_id=int(row.get("shipping_group_id") or 0),
        shipping_type=str(row.get("shipping_type") or ""),
        domestic_only_flag=row.get("domestic_only_flag"),
        shipping_policy_id=str(row.get("shipping_policy_id")) if row.get("shipping_policy_id") is not None else None,
        payment_policy_id=str(row.get("payment_policy_id")) if row.get("payment_policy_id") is not None else None,
        return_policy_id=str(row.get("return_policy_id")) if row.get("return_policy_id") is not None else None,
        is_active=bool(row.get("is_active")),
        notes=row.get("notes"),
    )


@router.delete("/shipping-groups/{mapping_id}", dependencies=[Depends(admin_required)])
async def delete_shipping_group_mapping(
    mapping_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        res = db.execute(
            text(
                """
                DELETE FROM public.ebay_shipping_group_policy_mappings
                WHERE id::text = :id
                """
            ),
            {"id": mapping_id},
        )
        db.commit()
        return {"deleted": int(res.rowcount or 0)}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"failed_to_delete_mapping: {exc}")
