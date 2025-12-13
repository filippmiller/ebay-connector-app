from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.user import User
from app.models_sqlalchemy import get_db
from app.services.auth import admin_required
from app.services.ebay_flow_catalog_generator import generate_auto_flows


router = APIRouter(prefix="/api/admin/ebay-flows", tags=["admin-ebay-flows"])


class FlowListItem(BaseModel):
    flow_key: str
    title: str
    summary: Optional[str] = None
    category: Optional[str] = None
    keywords: List[str] = []
    generated_at: Optional[str] = None
    updated_at: Optional[str] = None


class FlowDetail(BaseModel):
    flow_key: str
    title: str
    summary: Optional[str] = None
    category: Optional[str] = None
    keywords: List[str] = []
    graph: Dict[str, Any]
    source: Dict[str, Any]
    generated_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class RegenerateResponse(BaseModel):
    status: str
    total_upserted: int
    skipped_manual: int


@router.get("", dependencies=[Depends(admin_required)])
async def list_flows(
    q: Optional[str] = Query(None, description="Full-text search query"),
    category: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),  # noqa: ARG001
) -> Dict[str, Any]:
    """Search/list flow catalog entries."""

    where: List[str] = []
    params: Dict[str, Any] = {"limit": limit, "offset": offset}

    if category:
        where.append("category = :category")
        params["category"] = category

    if q:
        # Use expression index idx_ebay_flow_catalog_search_tsv_gin
        where.append(
            "to_tsvector('simple', coalesce(flow_key,'') || ' ' || coalesce(title,'') || ' ' || coalesce(summary,'') || ' ' || coalesce(array_to_string(keywords,' '),'')) "
            "@@ plainto_tsquery('simple', :q)"
        )
        params["q"] = q

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    base_sql = f"""
        SELECT
            flow_key,
            title,
            summary,
            category,
            keywords,
            generated_at,
            updated_at
        FROM public.ebay_flow_catalog
        {where_sql}
        ORDER BY updated_at DESC, id DESC
        LIMIT :limit OFFSET :offset
    """

    count_sql = f"""
        SELECT COUNT(*)
        FROM public.ebay_flow_catalog
        {where_sql}
    """

    rows = db.execute(text(base_sql), params).mappings().all()
    total = db.execute(text(count_sql), params).scalar() or 0

    def _iso(dt: Any) -> Optional[str]:
        try:
            return dt.astimezone(timezone.utc).isoformat() if dt else None
        except Exception:
            return None

    items: List[FlowListItem] = []
    for r in rows:
        items.append(
            FlowListItem(
                flow_key=r.get("flow_key"),
                title=r.get("title"),
                summary=r.get("summary"),
                category=r.get("category"),
                keywords=list(r.get("keywords") or []),
                generated_at=_iso(r.get("generated_at")),
                updated_at=_iso(r.get("updated_at")),
            )
        )

    return {"rows": [i.model_dump() for i in items], "total": int(total), "limit": limit, "offset": offset}


@router.get("/{flow_key}", response_model=FlowDetail, dependencies=[Depends(admin_required)])
async def get_flow(
    flow_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),  # noqa: ARG001
) -> FlowDetail:
    row = db.execute(
        text(
            """
            SELECT flow_key, title, summary, category, keywords, graph, source,
                   generated_at, created_at, updated_at
            FROM public.ebay_flow_catalog
            WHERE flow_key = :flow_key
            LIMIT 1
            """
        ),
        {"flow_key": flow_key},
    ).mappings().one_or_none()

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="flow_not_found")

    def _iso(dt: Any) -> Optional[str]:
        try:
            return dt.astimezone(timezone.utc).isoformat() if dt else None
        except Exception:
            return None

    return FlowDetail(
        flow_key=row.get("flow_key"),
        title=row.get("title"),
        summary=row.get("summary"),
        category=row.get("category"),
        keywords=list(row.get("keywords") or []),
        graph=row.get("graph") or {"nodes": {}, "edges": []},
        source=row.get("source") or {},
        generated_at=_iso(row.get("generated_at")),
        created_at=_iso(row.get("created_at")),
        updated_at=_iso(row.get("updated_at")),
    )


@router.post("/regenerate", response_model=RegenerateResponse, dependencies=[Depends(admin_required)])
async def regenerate_flows(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),  # noqa: ARG001
) -> RegenerateResponse:
    """Regenerate (upsert) auto-discovered flows into Supabase table.

    Safety: rows whose source.mode == 'manual' are not overwritten.
    """

    flows = generate_auto_flows()

    skipped_manual = 0
    upserted = 0

    now = datetime.now(timezone.utc)

    for f in flows:
        flow_key = f.get("flow_key")
        if not flow_key:
            continue

        existing_mode = db.execute(
            text(
                """
                SELECT COALESCE(source->>'mode', '') AS mode
                FROM public.ebay_flow_catalog
                WHERE flow_key = :flow_key
                LIMIT 1
                """
            ),
            {"flow_key": flow_key},
        ).scalar()

        if existing_mode and str(existing_mode).lower() == "manual":
            skipped_manual += 1
            continue

        db.execute(
            text(
                """
                INSERT INTO public.ebay_flow_catalog
                    (flow_key, title, summary, category, keywords, graph, source, generated_at)
                VALUES
                    (:flow_key, :title, :summary, :category, :keywords, :graph::jsonb, :source::jsonb, :generated_at)
                ON CONFLICT (flow_key) DO UPDATE
                SET
                    title = EXCLUDED.title,
                    summary = EXCLUDED.summary,
                    category = EXCLUDED.category,
                    keywords = EXCLUDED.keywords,
                    graph = EXCLUDED.graph,
                    source = EXCLUDED.source,
                    generated_at = EXCLUDED.generated_at
                """
            ),
            {
                "flow_key": flow_key,
                "title": f.get("title") or flow_key,
                "summary": f.get("summary"),
                "category": f.get("category"),
                "keywords": f.get("keywords") or [],
                "graph": f.get("graph") or {"nodes": {}, "edges": []},
                "source": f.get("source") or {"mode": "auto"},
                "generated_at": now,
            },
        )
        upserted += 1

    db.commit()

    return RegenerateResponse(status="ok", total_upserted=upserted, skipped_manual=skipped_manual)
