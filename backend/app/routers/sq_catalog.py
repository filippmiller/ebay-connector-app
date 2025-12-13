from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, asc, desc, func, select, text
from sqlalchemy.sql.sqltypes import String, Text, CHAR, VARCHAR, Unicode, UnicodeText, Integer, BigInteger, Numeric

from app.models_sqlalchemy import get_db
from app.models_sqlalchemy.models import (
    SqItem,
    SqInternalCategory,
    SqShippingGroup,
    ItemCondition,
    Warehouse,
    tbl_parts_models_table,
    tbl_parts_category_table,
)
from app.services.auth import get_current_user
from ..utils.logger import logger
from app.models.sq_item import (
    SqItemCreate,
    SqItemUpdate,
    SqItemRead,
    SqItemListItem,
    SqItemListResponse,
)


router = APIRouter(prefix="/api/sq", tags=["sq_catalog"])

DEFAULT_POLICY_ACCOUNT_KEY = "default"
DEFAULT_POLICY_MARKETPLACE_ID = "EBAY_US"


def _load_sku_business_policies(db: Session, *, sku_catalog_id: int) -> dict:
    row = db.execute(
        text(
            """
            SELECT
              account_key,
              marketplace_id,
              shipping_policy_id,
              payment_policy_id,
              return_policy_id
            FROM public.ebay_sku_business_policies
            WHERE sku_catalog_id = :sku_catalog_id
              AND account_key = :account_key
              AND marketplace_id = :marketplace_id
            LIMIT 1
            """
        ),
        {
            "sku_catalog_id": int(sku_catalog_id),
            "account_key": DEFAULT_POLICY_ACCOUNT_KEY,
            "marketplace_id": DEFAULT_POLICY_MARKETPLACE_ID,
        },
    ).mappings().first()
    if not row:
        return {
            "ebay_policy_account_key": DEFAULT_POLICY_ACCOUNT_KEY,
            "ebay_policy_marketplace_id": DEFAULT_POLICY_MARKETPLACE_ID,
            "ebay_shipping_policy_id": None,
            "ebay_payment_policy_id": None,
            "ebay_return_policy_id": None,
        }
    return {
        "ebay_policy_account_key": str(row.get("account_key") or DEFAULT_POLICY_ACCOUNT_KEY),
        "ebay_policy_marketplace_id": str(row.get("marketplace_id") or DEFAULT_POLICY_MARKETPLACE_ID),
        "ebay_shipping_policy_id": row.get("shipping_policy_id"),
        "ebay_payment_policy_id": row.get("payment_policy_id"),
        "ebay_return_policy_id": row.get("return_policy_id"),
    }


def _upsert_sku_business_policies(
    db: Session,
    *,
    sku_catalog_id: int,
    account_key: str,
    marketplace_id: str,
    shipping_policy_id: int | None,
    payment_policy_id: int | None,
    return_policy_id: int | None,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO public.ebay_sku_business_policies
              (sku_catalog_id, account_key, marketplace_id, shipping_policy_id, payment_policy_id, return_policy_id)
            VALUES
              (:sku_catalog_id, :account_key, :marketplace_id, :shipping_policy_id, :payment_policy_id, :return_policy_id)
            ON CONFLICT (sku_catalog_id, account_key, marketplace_id)
            DO UPDATE SET
              shipping_policy_id = EXCLUDED.shipping_policy_id,
              payment_policy_id  = EXCLUDED.payment_policy_id,
              return_policy_id   = EXCLUDED.return_policy_id,
              updated_at         = NOW()
            """
        ),
        {
            "sku_catalog_id": int(sku_catalog_id),
            "account_key": account_key,
            "marketplace_id": marketplace_id,
            "shipping_policy_id": shipping_policy_id,
            "payment_policy_id": payment_policy_id,
            "return_policy_id": return_policy_id,
        },
    )


@router.get("/models/search")
async def search_models(
    q: str = Query(..., min_length=1, description="Search term for legacy parts models table"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    """Live search endpoint for legacy ``tbl_parts_models`` table.

    Returns a compact list of ``{id, label}`` entries that can be used by the
    SKU create/edit form for model typeahead. The implementation is defensive
    and tolerates environments where the underlying table does not exist.
    """

    table = tbl_parts_models_table
    if table is None:
        return {"items": [], "total": 0}

    # Identify candidate ID and display label columns using simple heuristics
    string_types = (String, Text, CHAR, VARCHAR, Unicode, UnicodeText)
    numeric_types = (Integer, BigInteger, Numeric)

    columns = list(table.columns)
    if not columns:
        return {"items": [], "total": 0}

    id_col = None
    label_col = None

    for col in columns:
        if id_col is None and isinstance(col.type, numeric_types):
            id_col = col

        if isinstance(col.type, string_types):
            name_lower = col.name.lower()
            if any(key in name_lower for key in ("model", "name", "title", "part")):
                label_col = label_col or col

    if label_col is None:
        # Fallback: first text-like column
        for col in columns:
            if isinstance(col.type, string_types):
                label_col = col
                break

    if label_col is None:
        return {"items": [], "total": 0}

    if id_col is None:
        id_col = columns[0]

    # Use a contains search so that queries like "L500" match anywhere in the
    # model label. This is triggered explicitly from the UI (on Enter) so we
    # can afford a broader match.
    like = f"%{q}%"
    stmt = (
        select(id_col, label_col)
        .where(label_col.ilike(like))
        .order_by(label_col.asc())
        .limit(limit)
    )

    rows = db.execute(stmt).fetchall()
    items = [
        {"id": row[0], "label": str(row[1])}
        for row in rows
        if row[1] is not None
    ]

    return {"items": items, "total": len(items)}


@router.get("/parts-models")
async def list_parts_models(
    search: Optional[str] = Query(None, description="Search term for model name"),
    brand_id: Optional[int] = Query(None, description="Filter by brand ID"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    """List/search parts models from tbl_parts_models table.
    
    Returns full model records including all condition scores for the Models modal grid.
    """
    
    table = tbl_parts_models_table
    if table is None:
        return {"items": [], "total": 0}
    
    # Build query dynamically using raw SQL for maximum compatibility
    where_clauses = []
    params = {}
    
    if search:
        where_clauses.append('LOWER("Model") LIKE :search')
        params['search'] = f'%{search.lower()}%'
    
    if brand_id is not None:
        where_clauses.append('"Brand_ID" = :brand_id')
        params['brand_id'] = brand_id
    
    where_clause = ' AND '.join(where_clauses) if where_clauses else '1=1'
    
    # Count total
    count_query = text(f'SELECT COUNT(*) FROM "tbl_parts_models" WHERE {where_clause}')
    total = db.execute(count_query, params).scalar() or 0
    
    # Fetch paginated results
    fetch_query = text(f'''
        SELECT 
            "ID" as id,
            "Model_ID" as model_id,
            "Brand_ID" as brand_id,
            "Model" as model,
            "oc_filter_Model_ID" as oc_filter_model_id,
            "oc_filter_Model_ID2" as oc_filter_model_id2,
            "BuyingPrice" as buying_price,
            "working",
            "motherboard",
            "battery",
            "hdd",
            "keyboard",
            "memory",
            "screen",
            "casing",
            "drive",
            "damage",
            "cd",
            "adapter",
            "record_created",
            "do_not_buy"
        FROM "tbl_parts_models"
        WHERE {where_clause}
        ORDER BY "Model" ASC
        LIMIT :limit OFFSET :offset
    ''')
    
    params['limit'] = limit
    params['offset'] = offset
    
    rows = db.execute(fetch_query, params).fetchall()
    
    items = []
    for row in rows:
        items.append({
            'id': row.id,
            'model_id': row.model_id,
            'brand_id': row.brand_id,
            'model': row.model or '',
            'oc_filter_model_id': row.oc_filter_model_id,
            'oc_filter_model_id2': row.oc_filter_model_id2,
            'buying_price': row.buying_price or 0,
            'working': row.working or 0,
            'motherboard': row.motherboard or 0,
            'battery': row.battery or 0,
            'hdd': row.hdd or 0,
            'keyboard': row.keyboard or 0,
            'memory': row.memory or 0,
            'screen': row.screen or 0,
            'casing': row.casing or 0,
            'drive': row.drive or 0,
            'damage': row.damage or 0,
            'cd': row.cd or 0,
            'adapter': row.adapter or 0,
            'record_created': row.record_created.isoformat() if row.record_created else None,
            'do_not_buy': row.do_not_buy or False,
        })
    
    return {"items": items, "total": total}


@router.post("/parts-models")
async def create_parts_model(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    """Create a new parts model in ``tbl_parts_models``.

    This endpoint is used by the SKU → Models → Add Model flow. It inserts a
    single row into the legacy laptop models dictionary table and returns the
    fully-populated row so the UI can immediately select it.
    """

    table = tbl_parts_models_table
    if table is None:
        raise HTTPException(
            status_code=503,
            detail="tbl_parts_models table not available in this environment",
        )

    # Validate required field – model name is the only strictly required
    # attribute today. All scoring/price fields are optional and default to 0.
    model_name = (payload.get("model") or "").strip()
    if not model_name:
        raise HTTPException(status_code=400, detail="Model name is required")

    # Compute the next numeric ID explicitly. The legacy tbl_parts_models table
    # has a NOT NULL "ID" column without a PostgreSQL sequence/identity in some
    # environments, so we emulate the old behaviour with MAX(ID) + 1.
    try:
        max_id = db.execute(select(func.max(table.c.ID))).scalar()
        next_id = int(max_id or 0) + 1
    except Exception as e:  # pragma: no cover - defensive logging in prod
        logger.exception("Failed to compute next ID for tbl_parts_models", exc_info=e)
        raise HTTPException(
            status_code=500,
            detail=f"Database error: failed to compute next ID for tbl_parts_models: {e}",
        )

    # Prepare insert with safe defaults for all NOT NULL fields.
    insert_data = {
        "ID": next_id,
        "Model_ID": payload.get("model_id") or 0,
        "Brand_ID": payload.get("brand_id") or 0,
        "Model": model_name,
        "oc_filter_Model_ID": payload.get("oc_filter_model_id") or 0,
        "oc_filter_Model_ID2": payload.get("oc_filter_model_id2") or 0,
        "BuyingPrice": payload.get("buying_price", 0) or 0,
        "working": payload.get("working", 0) or 0,
        "motherboard": payload.get("motherboard", 0) or 0,
        "battery": payload.get("battery", 0) or 0,
        "hdd": payload.get("hdd", 0) or 0,
        "keyboard": payload.get("keyboard", 0) or 0,
        "memory": payload.get("memory", 0) or 0,
        "screen": payload.get("screen", 0) or 0,
        "casing": payload.get("casing", 0) or 0,
        "drive": payload.get("drive", 0) or 0,
        "damage": payload.get("damage", 0) or 0,
        "cd": payload.get("cd", 0) or 0,
        "adapter": payload.get("adapter", 0) or 0,
        "do_not_buy": bool(payload.get("do_not_buy", False)),
    }

    # Use SQLAlchemy Core against the reflected legacy table instead of
    # hand-written SQL to avoid quoting/RETURNING issues across environments.
    insert_stmt = (
        table.insert()
        .values(**insert_data)
        .returning(
            table.c.ID.label("id"),
            table.c.Model_ID.label("model_id"),
            table.c.Brand_ID.label("brand_id"),
            table.c.Model.label("model"),
            table.c.oc_filter_Model_ID.label("oc_filter_model_id"),
            table.c.oc_filter_Model_ID2.label("oc_filter_model_id2"),
            table.c.BuyingPrice.label("buying_price"),
            table.c.working,
            table.c.motherboard,
            table.c.battery,
            table.c.hdd,
            table.c.keyboard,
            table.c.memory,
            table.c.screen,
            table.c.casing,
            table.c.drive,
            table.c.damage,
            table.c.cd,
            table.c.adapter,
            table.c.record_created,
            table.c.do_not_buy,
        )
    )

    try:
        result = db.execute(insert_stmt)
        row = result.fetchone()
        db.commit()

        if not row:
            raise HTTPException(status_code=500, detail="Failed to create model")

        return {
            "id": row.id,
            "model_id": row.model_id,
            "brand_id": row.brand_id,
            "model": row.model or "",
            "oc_filter_model_id": row.oc_filter_model_id,
            "oc_filter_model_id2": row.oc_filter_model_id2,
            "buying_price": row.buying_price or 0,
            "working": row.working or 0,
            "motherboard": row.motherboard or 0,
            "battery": row.battery or 0,
            "hdd": row.hdd or 0,
            "keyboard": row.keyboard or 0,
            "memory": row.memory or 0,
            "screen": row.screen or 0,
            "casing": row.casing or 0,
            "drive": row.drive or 0,
            "damage": row.damage or 0,
            "cd": row.cd or 0,
            "adapter": row.adapter or 0,
            "record_created": row.record_created.isoformat() if row.record_created else None,
            "do_not_buy": bool(row.do_not_buy),
        }
    except HTTPException:
        # Preserve explicit HTTP errors (validation, missing table, etc.).
        db.rollback()
        raise
    except Exception as e:  # pragma: no cover - defensive logging for prod only
        db.rollback()
        logger.exception("Failed to create parts model", exc_info=e)
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/items", response_model=SqItemListResponse)
async def list_sq_items(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sku: Optional[str] = Query(None),
    model_id: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    shipping_group: Optional[str] = Query(None),
    condition_id: Optional[int] = Query(None),
    has_alert: Optional[bool] = Query(None),
    search: Optional[str] = Query(None, description="Full-text search across SKU, title, description, part_number, MPN, UPC"),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> SqItemListResponse:
    """Paginated list of SQ catalog items for the SKU grid.

    This endpoint is separate from the generic ``/api/grids`` infrastructure so
    the SKU tab and migration tools can rely on a stable, explicit contract.
    """

    query = db.query(SqItem)

    if sku:
        like = f"%{sku}%"
        query = query.filter(SqItem.sku.ilike(like))

    if model_id is not None:
        query = query.filter(SqItem.model_id == model_id)

    if category:
        query = query.filter(SqItem.category == category)

    if shipping_group:
        query = query.filter(SqItem.shipping_group == shipping_group)

    if condition_id is not None:
        query = query.filter(SqItem.condition_id == condition_id)

    if has_alert is True:
        query = query.filter(SqItem.alert_flag.is_(True))
    elif has_alert is False:
        query = query.filter(or_(SqItem.alert_flag.is_(False), SqItem.alert_flag.is_(None)))

    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                SqItem.sku.ilike(like),
                SqItem.title.ilike(like),
                SqItem.description.ilike(like),
                SqItem.part_number.ilike(like),
                SqItem.mpn.ilike(like),
                SqItem.upc.ilike(like),
                SqItem.part.ilike(like),
            )
        )

    total = query.count()

    # Default sort: newest first by record_updated/record_created/id
    query = query.order_by(desc(SqItem.record_updated.nullslast()), desc(SqItem.record_created.nullslast()), desc(SqItem.id))

    offset = (page - 1) * page_size
    rows = query.offset(offset).limit(page_size).all()

    items = [
        SqItemListItem.model_validate(
            {
                "id": r.id,
                "sku": r.sku,
                "model": r.model,
                "category": r.category,
                "condition_id": r.condition_id,
                "part_number": r.part_number,
                "price": r.price,
                "title": r.title,
                "brand": r.brand,
                "alert_flag": r.alert_flag,
                "shipping_group": r.shipping_group,
                "pic_url1": r.pic_url1,
                "record_created": r.record_created,
                "record_updated": r.record_updated,
                "record_status": r.record_status,
            }
        )
        for r in rows
    ]

    return SqItemListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/items/{item_id}", response_model=SqItemRead)
async def get_sq_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> SqItemRead:
    """Return full detail for a single SQ catalog item."""

    logger.info(f"Fetching SQ Item ID: {item_id}")
    item = db.query(SqItem).filter(SqItem.id == item_id).first()
    if not item:
        logger.warning(f"SQ Item ID {item_id} NOT FOUND")
        raise HTTPException(status_code=404, detail="SQ item not found")

    # Populate model name from legacy table if available
    if item.model_id and tbl_parts_models_table is not None:
        try:
            logger.info(f"Looking up Model ID {item.model_id} for Item {item_id}")
            stmt = select(tbl_parts_models_table.c.Model).where(tbl_parts_models_table.c.ID == item.model_id)
            model_name = db.execute(stmt).scalar()
            if model_name:
                item.model = str(model_name)
                logger.info(f"Found model name: {item.model}")
            else:
                logger.warning(f"Model ID {item.model_id} yielded no name")
        except Exception as e:
            logger.warning(f"Failed to resolve model name for ID {item.model_id}: {e}")
    else:
        logger.info(f"Skipping model lookup. Model ID: {item.model_id}, Table Reflected: {tbl_parts_models_table is not None}")

    # Coerce DB booleans that may be stored as numeric/text into real bools to
    # satisfy strict Pydantic parsing.
    bool_fields = {
        "alert_flag",
        "domestic_only_flag",
        "external_category_flag",
        "use_standard_template_for_external_category_flag",
        "use_ebay_motors_site_flag",
        "custom_template_flag",
        "color_flag",
        "epid_flag",
        "record_status_flag",
        "clone_sku_flag",
        "one_time_auction",
        "manual_condition_value_flag",
        "use_ebay_id",
    }

    # Fields that should always be serialized to string to satisfy Pydantic when
    # DB returns Decimals/ints.
    string_fields = {
        "external_category_id",
        "external_category_name",
        "category",
        "sku",
        "sku2",
        "model_id",
        "shipping_group",
        "site_id",
        "item_grade_id",
        "condition_id",
        "part_id",
    }

    data: dict = {}
    for attr in item.__mapper__.attrs:  # type: ignore[attr-defined]
        key = attr.key
        value = getattr(item, key, None)
        if key in bool_fields:
            if value is None:
                data[key] = None
            elif isinstance(value, bool):
                data[key] = value
            else:
                try:
                    data[key] = bool(int(value))
                except Exception:
                    # Last resort: truthy conversion
                    data[key] = bool(value)
        elif key in string_fields:
            if value is None:
                data[key] = None
            else:
                data[key] = str(value)
        else:
            data[key] = value

    # Attach per-SKU business policies (Trading SellerProfiles IDs)
    try:
        data.update(_load_sku_business_policies(db, sku_catalog_id=int(item.id)))
    except Exception as exc:
        # Defensive: never fail SKU read because policies mapping table is missing
        logger.warning("Failed to load ebay_sku_business_policies for sku_catalog_id=%s: %s", item.id, exc)
        data.update(
            {
                "ebay_policy_account_key": DEFAULT_POLICY_ACCOUNT_KEY,
                "ebay_policy_marketplace_id": DEFAULT_POLICY_MARKETPLACE_ID,
                "ebay_shipping_policy_id": None,
                "ebay_payment_policy_id": None,
                "ebay_return_policy_id": None,
            }
        )

    result = SqItemRead.model_validate(data)
    # Log the result dict (excluding huge fields if any) to verify content
    logger.info(f"Returning Item Data: SKU={result.sku}, Title={result.title}, Price={result.price}")
    return result


@router.post("/items", response_model=SqItemRead)
async def create_sq_item(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> SqItemRead:
    """Create a new SQ catalog item for the SKU popup form.

    Вместо строгой Pydantic-модели на вход (``SqItemCreate``) мы принимаем
    произвольный словарь и валидируем только те поля, которые действительно
    обязательны для формы SKU. Это устраняет HTTP 422 из FastAPI при
    неидеальном типе/значении и делает валидацию полностью управляемой
    приложением.

    Правила:
    * ``title`` обязателен, не более 80 символов.
    * ``model`` обязателен (но текстово, без связи с tbl_parts_models).
    * ``price`` > 0.
    * ``condition_id`` обязателен.
    * ``shipping_group`` обязателен.
    * При внутренней категории (``external_category_flag`` == False)
      ``category`` также обязательна.
    * Остальные поля опциональны и прокидываются как есть.
    """

    now = datetime.now(timezone.utc)

    # Normalise payload keys for easier access
    # NOTE: payload уже JSON-словарь из FastAPI, без дополнительной модели.
    title = (payload.get("title") or "").strip()
    model = (payload.get("model") or "").strip()
    raw_price = payload.get("price")
    condition_id = payload.get("condition_id")
    shipping_group = (payload.get("shipping_group") or "").strip()
    external_category_flag = bool(payload.get("external_category_flag"))
    category = payload.get("category")
    model_id = payload.get("model_id")

    # Optional per-SKU business policy IDs (stored outside SKU_catalog)
    policy_account_key = str(payload.get("ebay_policy_account_key") or DEFAULT_POLICY_ACCOUNT_KEY).strip() or DEFAULT_POLICY_ACCOUNT_KEY
    policy_marketplace_id = str(payload.get("ebay_policy_marketplace_id") or DEFAULT_POLICY_MARKETPLACE_ID).strip() or DEFAULT_POLICY_MARKETPLACE_ID
    try:
        shipping_policy_id = int(payload["ebay_shipping_policy_id"]) if payload.get("ebay_shipping_policy_id") not in (None, "", "null") else None
    except Exception:
        shipping_policy_id = None
    try:
        payment_policy_id = int(payload["ebay_payment_policy_id"]) if payload.get("ebay_payment_policy_id") not in (None, "", "null") else None
    except Exception:
        payment_policy_id = None
    try:
        return_policy_id = int(payload["ebay_return_policy_id"]) if payload.get("ebay_return_policy_id") not in (None, "", "null") else None
    except Exception:
        return_policy_id = None

    # Canonical mapping: the legacy SKU_catalog table uses the ``Part``
    # column for the short human-friendly title. Ensure we always copy
    # the validated ``title`` into ``part`` when the client does not
    # provide an explicit part value, so that an empty Internal part
    # name field in the form cannot wipe out the title.
    existing_part = (payload.get("part") or "").strip()
    if title and not existing_part:
        payload["part"] = title

    # --- High-level validation mirroring the UI rules ----------------------
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")
    if len(title) > 80:
        raise HTTPException(status_code=400, detail="Title must be at most 80 characters")

    if not model:
        raise HTTPException(status_code=400, detail="Model is required")

    # Robust parsing of price: поддерживаем числа и строки вида "123.45" или "123,45".
    try:
        if raw_price is None:
            price_val = None
        elif isinstance(raw_price, (int, float, Decimal)):
            price_val = Decimal(str(raw_price))
        elif isinstance(raw_price, str):
            cleaned = raw_price.strip().replace(",", ".")
            price_val = Decimal(cleaned)
        else:
            raise ValueError(f"Unsupported price type: {type(raw_price)!r}")
    except Exception:
        raise HTTPException(
            status_code=400,
            detail=f"Price must be a valid number (got {raw_price!r} of type {type(raw_price).__name__})",
        )

    if price_val is None or price_val <= 0:
        raise HTTPException(status_code=400, detail="Price must be greater than 0")

    if not shipping_group:
        raise HTTPException(status_code=400, detail="Shipping group is required")

    if condition_id is None:
        raise HTTPException(status_code=400, detail="Condition is required")

    # When not using external/eBay category, internal category is required.
    if not external_category_flag:
        if category is None or str(category).strip() == "":
            raise HTTPException(status_code=400, detail="Internal category is required")

    # Patch back the normalised / converted values into payload
    payload = dict(payload)
    # Remove virtual fields so they don't get set as ad-hoc attributes on SqItem.
    payload.pop("ebay_policy_account_key", None)
    payload.pop("ebay_policy_marketplace_id", None)
    payload.pop("ebay_shipping_policy_id", None)
    payload.pop("ebay_payment_policy_id", None)
    payload.pop("ebay_return_policy_id", None)
    payload["title"] = title
    payload["model"] = model
    payload["price"] = price_val
    payload["shipping_group"] = shipping_group
    payload["condition_id"] = int(condition_id)

    # Model_ID is NOT NULL in the legacy SKU_catalog table и должен ссылаться
    # на реальную запись в tbl_parts_models. Если model_id отсутствует или не
    # парсится в число – это ошибка клиента.
    if model_id is None:
        raise HTTPException(status_code=400, detail="Model ID is required (select model from catalog)")
    try:
        payload["model_id"] = int(model_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Model ID must be numeric")
    if not external_category_flag:
        payload["category"] = str(category).strip()

    item = SqItem()
    for key, value in payload.items():
        # SQLAlchemy / Postgres спокойно проигнорируют неизвестные атрибуты
        # (они просто не будут замаплены на колонки), поэтому сетим всё как есть.
        setattr(item, key, value)

    # --- Auto-generated numeric SKU ----------------------------------------
    if not item.sku:
        # ``SKU`` is stored as a numeric column on SKU_catalog. We still treat
        # it as a logical string in the API, but generation is purely numeric
        # using the legacy pattern MAX(SKU)+1.
        max_sku = db.query(func.max(SqItem.sku)).scalar()
        try:
            current_max = int(max_sku) if max_sku is not None else 0
        except (TypeError, ValueError):
            current_max = 0
        item.sku = current_max + 1
    else:
        # Ensure uniqueness when user provides an explicit SKU.
        existing = db.query(SqItem).filter(SqItem.sku == item.sku).first()
        if existing:
            raise HTTPException(status_code=400, detail="SKU must be unique")

    # --- Defaults mirroring legacy behaviour -------------------------------
    if not item.market:
        item.market = "eBay"

    # In the legacy system UseEbayID was stored as a text flag ("Y"/"N"). We
    # keep that contract even though the column is a plain Text field.
    if not item.use_ebay_id:
        item.use_ebay_id = "Y"

    # Record / status defaults
    if item.price is not None and item.price_updated is None:
        item.price_updated = now

    if item.record_status is None:
        item.record_status = 1
    if item.record_status_flag is None:
        item.record_status_flag = True
    if item.checked_status is None:
        item.checked_status = False

    # Audit fields
    username = (
        getattr(current_user, "username", None)
        or getattr(current_user, "email", None)
        or "system"
    )
    if not item.record_created:
        item.record_created = now
    item.record_created_by = username
    item.record_updated = now
    item.record_updated_by = username

    # Shipping / listing sensible defaults
    if not item.listing_type:
        item.listing_type = "FixedPriceItem"
    if not item.listing_duration:
        item.listing_duration = "GTC"
    if item.listing_duration_in_days is None:
        item.listing_duration_in_days = None

    # --- Ensure ID for legacy SKU_catalog table -----------------------------
    # В прод-таблице "SKU_catalog" колонка "ID" помечена NOT NULL, но в некоторых
    # средах для неё нет sequence/identity. SQLAlchemy ожидает, что БД сама
    # сгенерирует ID, но Postgres выбрасывает NotNullViolation. Чтобы не
    # трогать схему в проде, мы эмитируем старое поведение: ID = MAX(ID) + 1.
    if item.id is None:
        try:
            max_id = db.query(func.max(SqItem.id)).scalar()
            next_id = int(max_id or 0) + 1
            item.id = next_id
        except Exception as exc:  # pragma: no cover - защитный лог только для прод
            logger.exception("Failed to compute next ID for SKU_catalog", exc_info=exc)
            raise HTTPException(
                status_code=500,
                detail=f"Database error: failed to compute next ID for SKU_catalog: {exc}",
            )

    db.add(item)
    try:
        # Persist per-SKU policy mapping in the same transaction.
        _upsert_sku_business_policies(
            db,
            sku_catalog_id=int(item.id),
            account_key=policy_account_key,
            marketplace_id=policy_marketplace_id,
            shipping_policy_id=shipping_policy_id,
            payment_policy_id=payment_policy_id,
            return_policy_id=return_policy_id,
        )
        db.commit()
        db.refresh(item)
    except Exception as e:  # pragma: no cover - defensive for prod
        db.rollback()
        logger.exception("Failed to create SQ item", exc_info=e)
        raise HTTPException(status_code=500, detail=f"Failed to create SKU: {e}")

    # IMPORTANT: Return using the same coercion logic as GET /items/{id}
    # because legacy SKU_catalog columns often store booleans/ids as text/numeric.
    return await get_sq_item(item.id, db=db, current_user=current_user)


@router.put("/items/{item_id}", response_model=SqItemRead)
async def update_sq_item(
    item_id: int,
    payload: SqItemUpdate,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> SqItemRead:
    """Update an existing SQ catalog item.

    Only fields present in the payload are patched; audit fields are updated
    automatically. When the price changes, the previous value is moved to
    ``previous_price`` and ``price_updated`` is refreshed.
    """

    item = db.query(SqItem).filter(SqItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="SQ item not found")

    # Capture old price before patching
    old_price = item.price

    data = payload.model_dump(exclude_unset=True)

    # Handle virtual policy mapping fields separately (stored in public.ebay_sku_business_policies)
    policy_account_key = str(data.pop("ebay_policy_account_key", None) or DEFAULT_POLICY_ACCOUNT_KEY).strip() or DEFAULT_POLICY_ACCOUNT_KEY
    policy_marketplace_id = str(data.pop("ebay_policy_marketplace_id", None) or DEFAULT_POLICY_MARKETPLACE_ID).strip() or DEFAULT_POLICY_MARKETPLACE_ID
    try:
        shipping_policy_id = int(data.pop("ebay_shipping_policy_id")) if "ebay_shipping_policy_id" in data and data.get("ebay_shipping_policy_id") not in (None, "", "null") else None
    except Exception:
        shipping_policy_id = None
    try:
        payment_policy_id = int(data.pop("ebay_payment_policy_id")) if "ebay_payment_policy_id" in data and data.get("ebay_payment_policy_id") not in (None, "", "null") else None
    except Exception:
        payment_policy_id = None
    try:
        return_policy_id = int(data.pop("ebay_return_policy_id")) if "ebay_return_policy_id" in data and data.get("ebay_return_policy_id") not in (None, "", "null") else None
    except Exception:
        return_policy_id = None

    # Same Part/Title semantics as in create_sq_item: if the client
    # sends a non-empty title but leaves part empty/unspecified, treat
    # the title as the canonical Part value on SKU_catalog.
    if "title" in data:
        title_val = (data.get("title") or "").strip()
        existing_part = (data.get("part") or "").strip()
        if title_val and not existing_part:
            data["part"] = title_val

    for key, value in data.items():
        setattr(item, key, value)

    now = datetime.now(timezone.utc)

    # If price changed and a new price was provided, update history fields.
    if "price" in data and item.price is not None and item.price != old_price:
        item.previous_price = old_price
        item.price_updated = now

    username = (
        getattr(current_user, "username", None)
        or getattr(current_user, "email", None)
        or "system"
    )
    item.record_updated = now
    item.record_updated_by = username

    try:
        _upsert_sku_business_policies(
            db,
            sku_catalog_id=int(item.id),
            account_key=policy_account_key,
            marketplace_id=policy_marketplace_id,
            shipping_policy_id=shipping_policy_id,
            payment_policy_id=payment_policy_id,
            return_policy_id=return_policy_id,
        )
        db.commit()
        db.refresh(item)
    except Exception as e:  # pragma: no cover - defensive for prod
        db.rollback()
        logger.exception("Failed to update SQ item id=%s", item_id, exc_info=e)
        raise HTTPException(status_code=500, detail=f"Failed to update SKU: {e}")

    # IMPORTANT: Return using the same coercion logic as GET /items/{id}
    # so response serialization never 500s on legacy column types.
    return await get_sq_item(item_id, db=db, current_user=current_user)


@router.post("/items/bulk-delete")
async def bulk_delete_sq_items(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    """Delete multiple SKU items by ID.

    Double-confirmation is handled on the client side. This endpoint simply
    executes the deletion for the provided list of IDs.
    """
    ids = payload.get("ids", [])
    if not ids:
        return {"count": 0}

    # Use SQLAlchemy delete for efficiency
    try:
        # Clean up per-SKU policy mappings first (best-effort; does not assume FK).
        try:
            db.execute(
                text("DELETE FROM public.ebay_sku_business_policies WHERE sku_catalog_id = ANY(:ids)"),
                {"ids": ids},
            )
        except Exception as exc:
            logger.warning("Failed to delete ebay_sku_business_policies for ids=%s: %s", ids, exc)
        stmt = (
            SqItem.__table__.delete()
            .where(SqItem.id.in_(ids))
        )
        result = db.execute(stmt)
        db.commit()
        count = result.rowcount
        logger.info(f"Deleted {count} SKU items for user {current_user.id}")
        return {"count": count}
    except Exception as e:
        db.rollback()
        logger.exception("Failed to bulk delete SKU items", exc_info=e)
        raise HTTPException(status_code=500, detail="Failed to delete items")


async def _debug_print_categories_and_shipping(db):
    try:
        # 1) simply count rows
        count_sql = text('SELECT COUNT(*) AS cnt FROM "tbl_parts_category"')
        count_row = db.execute(count_sql).fetchone()
        logger.info("DEBUG tbl_parts_category COUNT = %s", count_row[0] if count_row else 0)
    except Exception as exc:
        logger.exception("DEBUG ERROR counting tbl_parts_category", exc_info=exc)

    try:
        # 2) show first 3 rows
        sample_sql = text('''
            SELECT "CategoryID", "CategoryDescr", "eBayCategoryName"
            FROM "tbl_parts_category"
            ORDER BY "CategoryID"
            LIMIT 3
        ''')
        rows = db.execute(sample_sql).fetchall()
        logger.info("DEBUG tbl_parts_category SAMPLE = %s", rows)
    except Exception as exc:
        logger.exception("DEBUG ERROR sampling tbl_parts_category", exc_info=exc)

    try:
        # SHIPPING GROUPS
        count_sql2 = text('SELECT COUNT(*) AS cnt FROM "tbl_internalshippinggroups"')
        count_row2 = db.execute(count_sql2).fetchone()
        logger.info("DEBUG tbl_internalshippinggroups COUNT = %s", count_row2[0] if count_row2 else 0)

        sample_sql2 = text('''
            SELECT "ID", "Name", "Active"
            FROM "tbl_internalshippinggroups"
            ORDER BY "ID"
            LIMIT 6
        ''')
        rows2 = db.execute(sample_sql2).fetchall()
        logger.info("DEBUG tbl_internalshippinggroups SAMPLE = %s", rows2)
    except Exception as exc:
        logger.exception("DEBUG ERROR sampling tbl_internalshippinggroups", exc_info=exc)


@router.get("/dictionaries")
async def get_sq_dictionaries(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    """Return dictionaries used by the SQ Create/Edit form."""
    
    # Check DB connection details
    from app.models_sqlalchemy import engine
    logger.info("SQ dictionaries DB URL host=%s db=%s", engine.url.host, engine.url.database)
    
    # Run debug queries
    await _debug_print_categories_and_shipping(db)

    # ---- INTERNAL CATEGORIES ----
    internal_categories = []
    try:
        # Try querying with explicit "tbl_parts_category" first (no schema).
        # Use correct casing.
        rows = db.execute(
            text(
                'SELECT "CategoryID", "CategoryDescr", "eBayCategoryName" '
                'FROM "tbl_parts_category" ORDER BY "CategoryID"'
            )
        ).fetchall()
    except Exception as exc1:
        # Fallback: try public."tbl_parts_category" explicitly if previous failed
        try:
            rows = db.execute(
                text(
                    'SELECT "CategoryID", "CategoryDescr", "eBayCategoryName" '
                    'FROM public."tbl_parts_category" ORDER BY "CategoryID"'
                )
            ).fetchall()
        except Exception as exc2:
            logger.exception("Failed to load internal categories from tbl_parts_category", exc_info=exc2)
            rows = []

    if rows:
        for row in rows:
            # Use index-based access to avoid column name ambiguity
            cat_id = row[0]
            descr = str(row[1] or "").strip()
            ebay_name = str(row[2] or "").strip()
            
            parts = [str(cat_id)]
            if descr:
                parts.append(descr)
            if ebay_name:
                parts.append(ebay_name)
            label = " — ".join(parts)
            
            internal_categories.append(
                {"id": cat_id, "code": str(cat_id), "label": label, "category_id": cat_id, "category_descr": descr, "ebay_category_name": ebay_name}
            )
    else:
        # AUDIT 2025-11-21:
        # Internal categories are loaded from tbl_parts_category (NOT from sq_internal_categories).
        # If the query returns 0 rows, we log a warning and return an empty list to the UI.
        logger.warning("Internal categories: 0 rows loaded from tbl_parts_category")

    # ---- SHIPPING GROUPS ----
    shipping_groups = []
    try:
        # ID, Name, Description, Active
        # Try without schema first
        rows = db.execute(
            text(
                'SELECT DISTINCT "ID", "Name", "Active" '
                'FROM "tbl_internalshippinggroups" '
                'WHERE "Active" = true '
                'ORDER BY "ID"'
            )
        ).fetchall()
    except Exception:
        try:
            # Fallback to public schema
            rows = db.execute(
                text(
                    'SELECT DISTINCT "ID", "Name", "Active" '
                    'FROM public."tbl_internalshippinggroups" '
                    'WHERE "Active" = true '
                    'ORDER BY "ID"'
                )
            ).fetchall()
        except Exception as exc:
            logger.exception("Failed to load shipping groups from tbl_internalshippinggroups", exc_info=exc)
            rows = []

    if rows:
        for row in rows:
            # Use index-based access
            s_id = row[0]
            s_name = str(row[1] or "").strip()
            s_active = row[2]
            label = f"{s_id}: {s_name}"
            shipping_groups.append({
                "id": s_id,
                "code": str(s_id),
                "name": s_name,
                "label": label,
                "active": s_active
            })
    else:
        # AUDIT 2025-11-21:
        # Shipping groups are loaded from tbl_internalshippinggroups.
        logger.warning("Shipping groups: 0 rows loaded from tbl_internalshippinggroups")

    conditions = (
        db.query(ItemCondition)
        .order_by(ItemCondition.sort_order.asc(), ItemCondition.code.asc())
        .all()
    )
    warehouses = db.query(Warehouse).order_by(asc(Warehouse.id)).all()

    listing_types = [
        {"code": "FixedPriceItem", "label": "Fixed price"},
        {"code": "Auction", "label": "Auction"},
    ]

    listing_durations = [
        {"code": "GTC", "label": "Good 'Til Cancelled", "days": None},
        {"code": "30", "label": "30 days", "days": 30},
        {"code": "7", "label": "7 days", "days": 7},
    ]

    sites = [
        {"code": "EBAY-US", "label": "eBay US", "site_id": 0},
    ]

    # ---- EBAY BUSINESS POLICIES (read-only for SKU form) ----
    policies_rows = []
    defaults_row = None
    try:
        policies_rows = db.execute(
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
            {"account_key": DEFAULT_POLICY_ACCOUNT_KEY, "marketplace_id": DEFAULT_POLICY_MARKETPLACE_ID},
        ).mappings().all()

        defaults_row = db.execute(
            text(
                """
                SELECT shipping_policy_id, payment_policy_id, return_policy_id
                FROM public.ebay_business_policies_defaults
                WHERE account_key = :account_key AND marketplace_id = :marketplace_id
                """
            ),
            {"account_key": DEFAULT_POLICY_ACCOUNT_KEY, "marketplace_id": DEFAULT_POLICY_MARKETPLACE_ID},
        ).first()
    except Exception as exc:
        logger.warning("Failed to load ebay_business_policies dictionaries: %s", exc)
        policies_rows = []
        defaults_row = None

    policies_out = {"shipping": [], "payment": [], "return": []}
    for r in (policies_rows or []):
        pt = str(r.get("policy_type") or "").upper()
        entry = {
            "id": str(r.get("id")),
            "policy_type": pt,
            "policy_id": str(r.get("policy_id")),
            "policy_name": str(r.get("policy_name") or ""),
            "policy_description": r.get("policy_description"),
            "is_default": bool(r.get("is_default")),
            "is_active": bool(r.get("is_active")),
            "sort_order": int(r.get("sort_order") or 0),
        }
        if pt == "SHIPPING":
            policies_out["shipping"].append(entry)
        elif pt == "PAYMENT":
            policies_out["payment"].append(entry)
        elif pt == "RETURN":
            policies_out["return"].append(entry)

    policies_defaults = {
        "shipping_policy_id": str(defaults_row[0]) if defaults_row and defaults_row[0] is not None else None,
        "payment_policy_id": str(defaults_row[1]) if defaults_row and defaults_row[1] is not None else None,
        "return_policy_id": str(defaults_row[2]) if defaults_row and defaults_row[2] is not None else None,
    }

    return {
        "internal_categories": internal_categories,
        "shipping_groups": shipping_groups,
        "conditions": [
            {"id": cond.id, "code": cond.code, "label": cond.label}
            for cond in conditions
        ],
        "warehouses": [
            {"id": w.id, "name": w.name, "location": w.location, "warehouse_type": w.warehouse_type}
            for w in warehouses
        ],
        "listing_types": listing_types,
        "listing_durations": listing_durations,
        "sites": sites,
        "ebay_business_policies": policies_out,
        "ebay_business_policy_defaults": policies_defaults,
    }
