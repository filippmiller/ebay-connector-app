from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models_sqlalchemy import get_db
from app.services.auth import admin_required


router = APIRouter(prefix="/api/admin/ebay/policy-mappings", tags=["admin-ebay-policy-mappings"])

DEFAULT_POLICY_ACCOUNT_KEY = "default"
DEFAULT_POLICY_MARKETPLACE_ID = "EBAY_US"


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


class SeedMappingsRequestDto(BaseModel):
    account_key: str = Field(DEFAULT_POLICY_ACCOUNT_KEY, min_length=1)
    marketplace_id: str = Field(DEFAULT_POLICY_MARKETPLACE_ID, min_length=1)
    include_domestic_variants: bool = True  # include {null,true,false}
    include_shipping_types: List[str] = Field(default_factory=lambda: ["Flat", "Calculated"])
    activate_seeded: bool = True
    notes: Optional[str] = "seeded"


class ApplyMappingsToSkusRequestDto(BaseModel):
    account_key: str = Field(DEFAULT_POLICY_ACCOUNT_KEY, min_length=1)
    marketplace_id: str = Field(DEFAULT_POLICY_MARKETPLACE_ID, min_length=1)
    only_missing: bool = True
    limit: int = Field(5000, ge=1, le=50000)


def _load_active_shipping_groups(db: Session) -> list[int]:
    """Load active legacy shipping group IDs from migrated table."""
    try:
        rows = db.execute(
            text('SELECT "ID" FROM "tbl_internalshippinggroups" WHERE "Active" = true ORDER BY "ID"'),
        ).fetchall()
    except Exception:
        rows = db.execute(
            text('SELECT "ID" FROM public."tbl_internalshippinggroups" WHERE "Active" = true ORDER BY "ID"'),
        ).fetchall()
    ids: list[int] = []
    for r in rows:
        try:
            ids.append(int(r[0]))
        except Exception:
            continue
    return ids


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


@router.get("/shipping-groups/coverage", dependencies=[Depends(admin_required)])
async def get_shipping_group_mapping_coverage(
    account_key: str = Query(DEFAULT_POLICY_ACCOUNT_KEY),
    marketplace_id: str = Query(DEFAULT_POLICY_MARKETPLACE_ID),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Report missing mappings for active shipping groups.

    Coverage rules (minimal safety):
    - We consider a mapping \"covered\" when it exists, is_active=TRUE, and has shipping_policy_id setN.
    """
    try:
        group_ids = _load_active_shipping_groups(db)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"tbl_internalshippinggroups_not_available: {exc}")

    expected_types = ["Flat", "Calculated"]
    expected_dom = [None, True, False]

    existing = db.execute(
        text(
            """
            SELECT shipping_group_id, shipping_type, domestic_only_flag,
                   shipping_policy_id, payment_policy_id, return_policy_id, is_active
            FROM public.ebay_shipping_group_policy_mappings
            WHERE account_key = :account_key AND marketplace_id = :marketplace_id
            """
        ),
        {"account_key": account_key, "marketplace_id": marketplace_id},
    ).mappings().all()

    key_to_row = {}
    for r in existing:
        key = (int(r.get("shipping_group_id") or 0), str(r.get("shipping_type") or ""), r.get("domestic_only_flag"))
        key_to_row[key] = r

    missing: list[dict] = []
    covered = 0
    total_expected = 0

    for gid in group_ids:
        for st in expected_types:
            for dom in expected_dom:
                total_expected += 1
                row = key_to_row.get((gid, st, dom))
                if row and bool(row.get("is_active")) and row.get("shipping_policy_id") is not None:
                    covered += 1
                    continue
                missing.append(
                    {
                        "shipping_group_id": gid,
                        "shipping_type": st,
                        "domestic_only_flag": dom,
                        "reason": "missing_or_inactive_or_no_shipping_policy_id",
                    }
                )

    return {
        "account_key": account_key,
        "marketplace_id": marketplace_id,
        "active_shipping_groups": len(group_ids),
        "expected_combinations": total_expected,
        "covered_combinations": covered,
        "missing": missing,
    }


@router.post("/shipping-groups/seed", dependencies=[Depends(admin_required)])
async def seed_shipping_group_mappings(
    payload: SeedMappingsRequestDto,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Seed mapping rows for all active legacy shipping groups.

    Uses ON CONFLICT DO NOTHING so it is safe/idempotent.
    """
    try:
        group_ids = _load_active_shipping_groups(db)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"tbl_internalshippinggroups_not_available: {exc}")

    shipping_types = []
    for st in payload.include_shipping_types or []:
        s = (st or "").strip()
        if s.lower() == "flat":
            shipping_types.append("Flat")
        elif s.lower() == "calculated":
            shipping_types.append("Calculated")
    shipping_types = shipping_types or ["Flat", "Calculated"]

    dom_flags = [None, True, False] if payload.include_domestic_variants else [None]

    inserted = 0
    skipped = 0
    for gid in group_ids:
        for st in shipping_types:
            for dom in dom_flags:
                res = db.execute(
                    text(
                        """
                        INSERT INTO public.ebay_shipping_group_policy_mappings
                          (account_key, marketplace_id, shipping_group_id, shipping_type, domestic_only_flag,
                           shipping_policy_id, payment_policy_id, return_policy_id, is_active, notes)
                        VALUES
                          (:account_key, :marketplace_id, :shipping_group_id, :shipping_type, :domestic_only_flag,
                           NULL, NULL, NULL, :is_active, :notes)
                        ON CONFLICT (account_key, marketplace_id, shipping_group_id, shipping_type, domestic_only_flag)
                        DO NOTHING
                        """
                    ),
                    {
                        "account_key": payload.account_key,
                        "marketplace_id": payload.marketplace_id,
                        "shipping_group_id": int(gid),
                        "shipping_type": st,
                        "domestic_only_flag": dom,
                        "is_active": bool(payload.activate_seeded),
                        "notes": payload.notes,
                    },
                )
                # rowcount is 1 when inserted, 0 when conflict/do nothing
                if int(res.rowcount or 0) == 1:
                    inserted += 1
                else:
                    skipped += 1

    db.commit()
    return {
        "status": "ok",
        "account_key": payload.account_key,
        "marketplace_id": payload.marketplace_id,
        "shipping_groups": len(group_ids),
        "inserted": inserted,
        "skipped": skipped,
    }


@router.post("/shipping-groups/apply-to-skus", dependencies=[Depends(admin_required)])
async def apply_shipping_group_mappings_to_skus(
    payload: ApplyMappingsToSkusRequestDto,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Bulk apply shipping-group mappings to per-SKU policy table.

    This upserts into public.ebay_sku_business_policies using the best matching
    row from public.ebay_shipping_group_policy_mappings (exact domestic match preferred).
    """
    # NOTE: We only apply when mapping yields at least shipping_policy_id.
    where_missing = ""
    if payload.only_missing:
        where_missing = """
          AND NOT EXISTS (
            SELECT 1 FROM public.ebay_sku_business_policies p
            WHERE p.sku_catalog_id = s."ID"
              AND p.account_key = :account_key
              AND p.marketplace_id = :marketplace_id
          )
        """

    sql = f"""
      INSERT INTO public.ebay_sku_business_policies
        (sku_catalog_id, account_key, marketplace_id, shipping_policy_id, payment_policy_id, return_policy_id)
      SELECT
        s."ID" AS sku_catalog_id,
        :account_key AS account_key,
        :marketplace_id AS marketplace_id,
        m.shipping_policy_id,
        m.payment_policy_id,
        m.return_policy_id
      FROM public."SKU_catalog" s
      JOIN LATERAL (
        SELECT shipping_policy_id, payment_policy_id, return_policy_id, domestic_only_flag, id
        FROM public.ebay_shipping_group_policy_mappings m
        WHERE m.account_key = :account_key
          AND m.marketplace_id = :marketplace_id
          AND m.is_active = TRUE
          AND m.shipping_group_id = COALESCE(NULLIF(s."ShippingGroup", 0), 0)
          AND m.shipping_type = COALESCE(NULLIF(s."ShippingType", ''), 'Flat')
          AND (
            m.domestic_only_flag IS NOT DISTINCT FROM s."DomesticOnlyFlag"
            OR m.domestic_only_flag IS NULL
          )
        ORDER BY
          (m.domestic_only_flag IS NOT DISTINCT FROM s."DomesticOnlyFlag") DESC,
          m.domestic_only_flag NULLS LAST,
          m.id DESC
        LIMIT 1
      ) m ON TRUE
      WHERE s."ShippingGroup" IS NOT NULL
        AND COALESCE(NULLIF(s."ShippingGroup", 0), 0) > 0
        AND m.shipping_policy_id IS NOT NULL
        {where_missing}
      ORDER BY s."ID" DESC
      LIMIT :limit
      ON CONFLICT (sku_catalog_id, account_key, marketplace_id)
      DO UPDATE SET
        shipping_policy_id = EXCLUDED.shipping_policy_id,
        payment_policy_id  = EXCLUDED.payment_policy_id,
        return_policy_id   = EXCLUDED.return_policy_id,
        updated_at         = NOW()
    """

    try:
        res = db.execute(
            text(sql),
            {
                "account_key": payload.account_key,
                "marketplace_id": payload.marketplace_id,
                "limit": int(payload.limit),
            },
        )
        db.commit()
        return {"status": "ok", "rowcount": int(res.rowcount or 0)}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"failed_to_apply_mappings_to_skus: {exc}")


@router.get("/skus/missing", dependencies=[Depends(admin_required)])
async def list_skus_missing_policy_mapping(
    account_key: str = Query(DEFAULT_POLICY_ACCOUNT_KEY),
    marketplace_id: str = Query(DEFAULT_POLICY_MARKETPLACE_ID),
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """List SKU_catalog rows that do not have an entry in ebay_sku_business_policies for the given scope."""
    count = db.execute(
        text(
            """
            SELECT COUNT(*)
            FROM public."SKU_catalog" s
            LEFT JOIN public.ebay_sku_business_policies p
              ON p.sku_catalog_id = s."ID"
             AND p.account_key = :account_key
             AND p.marketplace_id = :marketplace_id
            WHERE p.id IS NULL
            """
        ),
        {"account_key": account_key, "marketplace_id": marketplace_id},
    ).scalar() or 0

    rows = db.execute(
        text(
            """
            SELECT
              s."ID" AS sku_catalog_id,
              s."SKU" AS sku,
              s."ShippingGroup" AS shipping_group_id,
              s."ShippingType" AS shipping_type,
              s."DomesticOnlyFlag" AS domestic_only_flag
            FROM public."SKU_catalog" s
            LEFT JOIN public.ebay_sku_business_policies p
              ON p.sku_catalog_id = s."ID"
             AND p.account_key = :account_key
             AND p.marketplace_id = :marketplace_id
            WHERE p.id IS NULL
            ORDER BY s."ID" DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {"account_key": account_key, "marketplace_id": marketplace_id, "limit": limit, "offset": offset},
    ).mappings().all()

    out = []
    for r in rows:
        out.append(
            {
                "sku_catalog_id": int(r.get("sku_catalog_id") or 0),
                "sku": str(r.get("sku")) if r.get("sku") is not None else None,
                "shipping_group_id": int(r.get("shipping_group_id") or 0) if r.get("shipping_group_id") is not None else None,
                "shipping_type": str(r.get("shipping_type")) if r.get("shipping_type") is not None else None,
                "domestic_only_flag": r.get("domestic_only_flag"),
            }
        )

    return {"rows": out, "total": int(count), "limit": limit, "offset": offset}

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
