from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from pydantic.config import ConfigDict
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models_sqlalchemy import get_db
from app.services.auth import admin_required


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


