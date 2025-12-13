from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class DiscoveredWorker:
    api_family: str
    class_name: str
    file_path: str


def _repo_root() -> Path:
    # backend/app/services/<this_file> -> backend/app/services -> backend/app -> backend
    return Path(__file__).resolve().parents[2]


def _discover_workers() -> List[DiscoveredWorker]:
    """Best-effort discovery of BaseWorker subclasses and their api_family.

    This is intentionally simple and safe:
    - parse python files under app/services/ebay_workers
    - look for a class FooWorker(BaseWorker)
    - find super().__init__(api_family="...") inside __init__

    If parsing fails for a file, we skip it.
    """

    workers_dir = _repo_root() / "app" / "services" / "ebay_workers"
    results: List[DiscoveredWorker] = []

    for path in sorted(workers_dir.glob("*_worker.py")):
        try:
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src)
        except Exception:
            continue

        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            # Check base class name contains BaseWorker (Name or Attribute)
            def _base_name(b: ast.expr) -> str:
                if isinstance(b, ast.Name):
                    return b.id
                if isinstance(b, ast.Attribute):
                    return b.attr
                return ""

            bases = [_base_name(b) for b in node.bases]
            if not any("BaseWorker" in (b or "") for b in bases):
                continue

            api_family = _extract_api_family_from_class(node)
            if not api_family:
                continue

            results.append(
                DiscoveredWorker(
                    api_family=api_family,
                    class_name=node.name,
                    file_path=str(path),
                )
            )

    # Dedup by api_family keeping the first (stable order due to sorted glob)
    dedup: Dict[str, DiscoveredWorker] = {}
    for w in results:
        if w.api_family not in dedup:
            dedup[w.api_family] = w

    return list(dedup.values())


def _extract_api_family_from_class(cls: ast.ClassDef) -> Optional[str]:
    for item in cls.body:
        if not isinstance(item, ast.FunctionDef):
            continue
        if item.name != "__init__":
            continue
        for stmt in ast.walk(item):
            if not isinstance(stmt, ast.Call):
                continue
            # super().__init__(...)
            fn = stmt.func
            if not isinstance(fn, ast.Attribute):
                continue
            if fn.attr != "__init__":
                continue
            if not isinstance(fn.value, ast.Call):
                continue
            if not isinstance(fn.value.func, ast.Name):
                continue
            if fn.value.func.id != "super":
                continue

            for kw in stmt.keywords or []:
                if kw.arg != "api_family":
                    continue
                if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    return kw.value.value

    return None


def _worker_specs() -> Dict[str, Dict[str, Any]]:
    """Manual enrichment for discovered workers.

    We keep this mapping intentionally short and human-maintained.
    Discovery finds the worker; this mapping describes its data flow nodes/edges.
    """

    return {
        "orders": {
            "title": "Orders sync (eBay Fulfillment API → ebay_orders / order_line_items)",
            "category": "sold",
            "keywords": ["orders", "sold", "order_line_items", "ebay_orders", "sync"],
            "ebay_calls": [
                {"type": "rest", "family": "fulfillment", "name": "Orders API (getOrders)", "notes": "Pulls seller orders and line items"},
            ],
            "tables": [
                {"table": "ebay_orders", "keys": ["order_id", "user_id"], "writes": True},
                {"table": "order_line_items", "keys": ["order_id", "line_item_id"], "writes": True},
            ],
            "entrypoints": [
                {"type": "endpoint", "method": "POST", "path": "/ebay/workers/run?api=orders", "notes": "Manual worker run"},
                {"type": "loop", "name": "app.workers.ebay_workers_loop", "notes": "Automatic 5-min scheduler"},
            ],
        },
        "transactions": {
            "title": "Transactions sync (Trading:GetSellerTransactions → ebay_transactions)",
            "category": "sold",
            "keywords": ["transactions", "sold", "GetSellerTransactions", "ebay_transactions", "sync"],
            "ebay_calls": [
                {"type": "trading", "call_name": "GetSellerTransactions", "notes": "Trading API XML"},
            ],
            "tables": [
                {"table": "ebay_transactions", "keys": ["transaction_id", "user_id"], "writes": True},
            ],
            "entrypoints": [
                {"type": "endpoint", "method": "POST", "path": "/ebay/workers/run?api=transactions", "notes": "Manual worker run"},
                {"type": "loop", "name": "app.workers.ebay_workers_loop", "notes": "Automatic 5-min scheduler"},
            ],
        },
        "offers": {
            "title": "Offers sync (Sell:Inventory/Offer → ebay_offers)",
            "category": "listing",
            "keywords": ["offers", "listing", "inventory", "ebay_offers", "sync"],
            "ebay_calls": [
                {"type": "rest", "family": "inventory", "name": "Sell Inventory API (offers)", "notes": "Syncs offers and their states"},
            ],
            "tables": [
                {"table": "ebay_offers", "keys": ["offer_id", "user_id"], "writes": True},
            ],
            "entrypoints": [
                {"type": "endpoint", "method": "POST", "path": "/ebay/workers/run?api=offers", "notes": "Manual worker run"},
                {"type": "loop", "name": "app.workers.ebay_workers_loop", "notes": "Automatic 5-min scheduler"},
            ],
        },
        "messages": {
            "title": "Messages sync (Messaging API → ebay_messages / emails_messages)",
            "category": "messages",
            "keywords": ["messages", "ebay_messages", "emails_messages", "sync"],
            "ebay_calls": [
                {"type": "rest", "family": "commerce", "name": "eBay Messaging APIs", "notes": "Pulls seller messages/inbox"},
            ],
            "tables": [
                {"table": "ebay_messages", "writes": True},
                {"table": "emails_messages", "writes": True},
            ],
            "entrypoints": [
                {"type": "endpoint", "method": "POST", "path": "/ebay/workers/run?api=messages", "notes": "Manual worker run"},
                {"type": "loop", "name": "app.workers.ebay_workers_loop", "notes": "Automatic 5-min scheduler"},
            ],
        },
        "active_inventory": {
            "title": "Active inventory snapshot (eBay ActiveInventoryReport → ebay_active_inventory / inventory)",
            "category": "inventory",
            "keywords": ["active_inventory", "inventory", "ebay_active_inventory", "snapshot"],
            "ebay_calls": [
                {"type": "rest", "family": "sell", "name": "Active inventory report", "notes": "Snapshot report"},
            ],
            "tables": [
                {"table": "ebay_active_inventory", "writes": True},
                {"table": "inventory", "writes": True},
            ],
            "entrypoints": [
                {"type": "endpoint", "method": "POST", "path": "/ebay/workers/run?api=active_inventory", "notes": "Manual worker run"},
                {"type": "loop", "name": "app.workers.ebay_workers_loop", "notes": "Automatic 5-min scheduler"},
            ],
        },
        "finances": {
            "title": "Finances sync (Finances API → ebay_finances_transactions / ebay_finances_fees)",
            "category": "finances",
            "keywords": ["finances", "fees", "ebay_finances_transactions", "ebay_finances_fees", "sync"],
            "ebay_calls": [
                {"type": "rest", "family": "finances", "name": "Finances API", "notes": "Transactions + fees"},
            ],
            "tables": [
                {"table": "ebay_finances_transactions", "writes": True},
                {"table": "ebay_finances_fees", "writes": True},
            ],
            "entrypoints": [
                {"type": "endpoint", "method": "POST", "path": "/ebay/workers/run?api=finances", "notes": "Manual worker run"},
                {"type": "loop", "name": "app.workers.ebay_workers_loop", "notes": "Automatic 5-min scheduler"},
            ],
        },
        "cases": {
            "title": "Cases sync (Sell:Cases → ebay_cases)",
            "category": "cases",
            "keywords": ["cases", "ebay_cases", "sync"],
            "ebay_calls": [
                {"type": "rest", "family": "cases", "name": "Cases API", "notes": "Disputes/cases"},
            ],
            "tables": [
                {"table": "ebay_cases", "writes": True},
            ],
            "entrypoints": [
                {"type": "endpoint", "method": "POST", "path": "/ebay/workers/run?api=cases", "notes": "Manual worker run"},
                {"type": "loop", "name": "app.workers.ebay_workers_loop", "notes": "Automatic 5-min scheduler"},
            ],
        },
        "buyer": {
            "title": "Buying purchases sync (Buy API → ebay_buyer)",
            "category": "buying",
            "keywords": ["buyer", "buying", "purchases", "ebay_buyer", "sync"],
            "ebay_calls": [
                {"type": "trading", "call_name": "GetMyeBayBuying", "notes": "Legacy-style Buying feed"},
            ],
            "tables": [
                {"table": "ebay_buyer", "writes": True},
                {"table": "tbl_ebay_buyer", "writes": False, "notes": "Legacy mirror table exists separately"},
            ],
            "entrypoints": [
                {"type": "endpoint", "method": "POST", "path": "/ebay/workers/run?api=buyer", "notes": "Manual worker run"},
                {"type": "loop", "name": "app.workers.ebay_workers_loop", "notes": "Automatic 5-min scheduler"},
            ],
        },
    }


def build_flow_graph(*, api_family: str, worker: DiscoveredWorker, spec: Dict[str, Any]) -> Dict[str, Any]:
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []

    ebay_node_key = f"ebay:{api_family}"
    worker_node_key = f"app:worker:{worker.class_name}"

    nodes[ebay_node_key] = {
        "type": "ebay_api",
        "label": f"eBay ({api_family})",
        "calls": spec.get("ebay_calls", []),
    }
    nodes[worker_node_key] = {
        "type": "worker",
        "label": worker.class_name,
        "api_family": api_family,
        "file": worker.file_path,
        "entrypoints": spec.get("entrypoints", []),
    }
    edges.append({"from": ebay_node_key, "to": worker_node_key, "label": "fetch"})

    for t in spec.get("tables", []):
        tbl = t.get("table")
        if not tbl:
            continue
        db_node_key = f"db:public.{tbl}"
        nodes[db_node_key] = {
            "type": "db_table",
            "label": tbl,
            "table": tbl,
            "keys": t.get("keys"),
            "writes": bool(t.get("writes")),
            "notes": t.get("notes"),
        }
        edges.append({"from": worker_node_key, "to": db_node_key, "label": "upsert/write" if t.get("writes") else "read"})

    return {"nodes": nodes, "edges": edges}


def generate_auto_flows() -> List[Dict[str, Any]]:
    workers = _discover_workers()
    specs = _worker_specs()

    flows: List[Dict[str, Any]] = []

    for w in sorted(workers, key=lambda x: x.api_family):
        spec = specs.get(w.api_family)
        if not spec:
            # Unknown worker family – still create a minimal entry so it's visible.
            spec = {
                "title": f"{w.api_family} sync ({w.class_name})",
                "category": "other",
                "keywords": [w.api_family, "sync"],
                "ebay_calls": [],
                "tables": [],
                "entrypoints": [{"type": "endpoint", "method": "POST", "path": f"/ebay/workers/run?api={w.api_family}"}],
            }

        flow_key = f"worker_{w.api_family}"
        flows.append(
            {
                "flow_key": flow_key,
                "title": spec.get("title") or flow_key,
                "summary": spec.get("summary"),
                "category": spec.get("category"),
                "keywords": list(dict.fromkeys([str(k).lower() for k in (spec.get("keywords") or []) if k])),
                "graph": build_flow_graph(api_family=w.api_family, worker=w, spec=spec),
                "source": {
                    "mode": "auto",
                    "discovered": {
                        "api_family": w.api_family,
                        "class_name": w.class_name,
                        "file": w.file_path,
                    },
                },
            }
        )

    # AssignStoragesForSoldItems worker (NEW implementation, 1-в-1 with legacy logic)
    flows.append(
        {
            "flow_key": "worker_assign_storages_for_sold_items",
            "title": "Assign storages for sold items (tbl_ebay_seller_info_detail → tbl_parts_inventory SOLD)",
            "summary": "Matches sold ItemID rows to oldest available inventory rows using ROW_NUMBER() and marks inventory as SOLD (StatusSKU=5, JustSoldFlag=1). Legacy-compatible process.",
            "category": "sold",
            "keywords": [
                "sold",
                "assign_storages",
                "tbl_ebay_seller_info_detail",
                "tbl_parts_inventory",
                "tbl_parts_inventory_detail",
                "statussku",
                "justsoldflag",
                "oldest",
                "row_number",
                "storageid",
                "storagealiasid",
                "partsinvdetail_id",
            ],
            "graph": {
                "nodes": {
                    "db:public.tbl_ebay_seller_info_detail": {
                        "type": "db_table",
                        "label": "tbl_ebay_seller_info_detail",
                        "table": "tbl_ebay_seller_info_detail",
                        "reads": True,
                        "writes": True,
                        "notes": "Queue of sold items awaiting storage assignment (StorageID IS NULL, ItemID exists in tbl_parts_inventory, PartsInvDetail_ID <> -1).",
                    },
                    "db:public.tbl_ebay_seller_info": {
                        "type": "db_table",
                        "label": "tbl_ebay_seller_info",
                        "table": "tbl_ebay_seller_info",
                        "reads": True,
                        "notes": "Source for EbayID (SellerID) via SellerInfo_ID.",
                    },
                    "app:worker:AssignStoragesForSoldItemsWorker": {
                        "type": "worker",
                        "label": "AssignStoragesForSoldItemsWorker",
                        "api_family": "assign_storages_for_sold_items",
                        "file": "backend/app/services/ebay_workers/assign_storages_for_sold_items_worker.py",
                        "entrypoints": [
                            {"type": "endpoint", "method": "POST", "path": "/ebay/workers/run?api=assign_storages_for_sold_items", "notes": "Manual worker run"},
                        ],
                    },
                    "db:public.tbl_parts_inventory": {
                        "type": "db_table",
                        "label": "tbl_parts_inventory",
                        "table": "tbl_parts_inventory",
                        "reads": True,
                        "writes": True,
                        "notes": "Sets StatusSKU=5, JustSoldFlag=1, StatusUpdated=NOW(), StatusUpdatedBy='system', JustSoldFlag_created/updated=NOW().",
                    },
                    "db:public.tbl_parts_inventory_detail": {
                        "type": "db_table",
                        "label": "tbl_parts_inventory_detail",
                        "table": "tbl_parts_inventory_detail",
                        "reads": True,
                        "notes": "Oldest rule uses ID ASC for pairing duplicates (ROW_NUMBER() PARTITION BY ItemID ORDER BY ID ASC).",
                    },
                },
                "edges": [
                    {"from": "db:public.tbl_ebay_seller_info_detail", "to": "app:worker:AssignStoragesForSoldItemsWorker", "label": "select sold items (StorageID IS NULL)"},
                    {"from": "db:public.tbl_ebay_seller_info", "to": "app:worker:AssignStoragesForSoldItemsWorker", "label": "read EbayID via SellerInfo_ID"},
                    {"from": "app:worker:AssignStoragesForSoldItemsWorker", "to": "db:public.tbl_parts_inventory_detail", "label": "match oldest inventory rows (ROW_NUMBER by ItemID, ID ASC)"},
                    {"from": "app:worker:AssignStoragesForSoldItemsWorker", "to": "db:public.tbl_ebay_seller_info_detail", "label": "update StorageID/StorageAliasID/PartsInvDetail_ID"},
                    {"from": "app:worker:AssignStoragesForSoldItemsWorker", "to": "db:public.tbl_parts_inventory", "label": "mark SOLD (StatusSKU=5, JustSoldFlag=1)"},
                ],
            },
            "source": {
                "mode": "auto",
                "notes": "New implementation matching legacy jobAssignStoragesForSoldItems.php logic exactly (ROW_NUMBER oldest-first matching).",
            },
        }
    )

    # Admin: BIN Trading debug flow (VerifyAddFixedPriceItem / AddFixedPriceItem)
    flows.append(
        {
            "flow_key": "admin_bin_trading_debug",
            "title": "Admin: BIN Listing Debug (Trading API Verify/AddFixedPriceItem)",
            "summary": "Admin-only tools to verify/list fixed-price items via Trading API; persists full request/response and hard ItemID mapping.",
            "category": "listing",
            "keywords": [
                "bin",
                "listing",
                "trading",
                "verifyaddfixedpriceitem",
                "addfixedpriceitem",
                "itemid",
                "ebay_bin_test_runs",
                "ebay_bin_listings_map",
                "tbl_parts_inventory",
                "tbl_parts_detail",
                "sellerprofiles",
                "business_policies",
            ],
            "graph": {
                "nodes": {
                    "ui:admin:bin-listing": {
                        "type": "admin_ui",
                        "label": "AdminBinListingPage",
                        "path": "/admin/bin-listing",
                    },
                    "api:POST:/api/admin/ebay/bin/source": {
                        "type": "endpoint",
                        "label": "GET source payload (no eBay call)",
                        "method": "GET",
                        "path": "/api/admin/ebay/bin/source?legacy_inventory_id=...",
                    },
                    "api:POST:/api/admin/ebay/bin/verify": {
                        "type": "endpoint",
                        "label": "VerifyAddFixedPriceItem (Trading)",
                        "method": "POST",
                        "path": "/api/admin/ebay/bin/verify",
                    },
                    "api:POST:/api/admin/ebay/bin/list": {
                        "type": "endpoint",
                        "label": "AddFixedPriceItem (Trading)",
                        "method": "POST",
                        "path": "/api/admin/ebay/bin/list",
                    },
                    "api:GET:/api/admin/ebay/bin/site-ids": {
                        "type": "endpoint",
                        "label": "Trading SiteID list",
                        "method": "GET",
                        "path": "/api/admin/ebay/bin/site-ids?active_only=true",
                    },
                    "ebay:trading:AddFixedPriceItem": {
                        "type": "ebay_api",
                        "label": "eBay Trading API (ws/api.dll)",
                        "calls": [
                            {"type": "trading", "call_name": "VerifyAddFixedPriceItem"},
                            {"type": "trading", "call_name": "AddFixedPriceItem"},
                        ],
                    },
                    "db:public.tbl_parts_inventory": {
                        "type": "db_table",
                        "label": "tbl_parts_inventory",
                        "table": "tbl_parts_inventory",
                        "reads": True,
                        "notes": "Source for override fields (title/price/condition/pics).",
                    },
                    "db:public.tbl_parts_detail": {
                        "type": "db_table",
                        "label": "tbl_parts_detail",
                        "table": "tbl_parts_detail",
                        "reads": True,
                        "writes": True,
                        "notes": "Best-effort persist ItemID into parts_detail.item_id (if enabled).",
                    },
                    "db:public.ebay_bin_test_runs": {
                        "type": "db_table",
                        "label": "ebay_bin_test_runs",
                        "table": "ebay_bin_test_runs",
                        "writes": True,
                        "notes": "Stores full request/response XML + parsed Ack/errors/warnings + ItemID.",
                    },
                    "db:public.ebay_bin_listings_map": {
                        "type": "db_table",
                        "label": "ebay_bin_listings_map",
                        "table": "ebay_bin_listings_map",
                        "writes": True,
                        "notes": "Hard mapping: legacy_inventory_id/SKU → ItemID (lossless).",
                    },
                    "db:public.tbl_globalsiteid": {
                        "type": "db_table",
                        "label": "tbl_globalsiteid",
                        "table": "tbl_globalsiteid",
                        "reads": True,
                        "notes": "Source of truth for Trading SiteID selection (X-EBAY-API-SITEID).",
                    },
                },
                "edges": [
                    {"from": "ui:admin:bin-listing", "to": "api:POST:/api/admin/ebay/bin/source", "label": "load DB payload"},
                    {"from": "api:POST:/api/admin/ebay/bin/source", "to": "db:public.tbl_parts_inventory", "label": "read overrides"},
                    {"from": "api:POST:/api/admin/ebay/bin/source", "to": "db:public.tbl_parts_detail", "label": "read base SKU fields"},
                    {"from": "ui:admin:bin-listing", "to": "api:GET:/api/admin/ebay/bin/site-ids", "label": "load SiteIDs"},
                    {"from": "api:GET:/api/admin/ebay/bin/site-ids", "to": "db:public.tbl_globalsiteid", "label": "read"},
                    {"from": "ui:admin:bin-listing", "to": "api:POST:/api/admin/ebay/bin/verify", "label": "VERIFY"},
                    {"from": "api:POST:/api/admin/ebay/bin/verify", "to": "ebay:trading:AddFixedPriceItem", "label": "call VerifyAddFixedPriceItem"},
                    {"from": "api:POST:/api/admin/ebay/bin/verify", "to": "db:public.ebay_bin_test_runs", "label": "write run log"},
                    {"from": "ui:admin:bin-listing", "to": "api:POST:/api/admin/ebay/bin/list", "label": "LIST"},
                    {"from": "api:POST:/api/admin/ebay/bin/list", "to": "ebay:trading:AddFixedPriceItem", "label": "call AddFixedPriceItem"},
                    {"from": "api:POST:/api/admin/ebay/bin/list", "to": "db:public.ebay_bin_test_runs", "label": "write run log"},
                    {"from": "api:POST:/api/admin/ebay/bin/list", "to": "db:public.ebay_bin_listings_map", "label": "write hard mapping"},
                    {"from": "api:POST:/api/admin/ebay/bin/list", "to": "db:public.tbl_parts_detail", "label": "best-effort persist ItemID"},
                ],
            },
            "source": {"mode": "auto_seed", "docs": ["docs/2025-12-12-ebay-bin-trading-debug-flow.md"]},
        }
    )

    # Admin: Business Policies Center (SellerProfiles dictionary + per-SKU mapping)
    flows.append(
        {
            "flow_key": "admin_business_policies_center",
            "title": "Admin: Business Policies Center (SellerProfiles IDs + per-SKU mapping)",
            "summary": "CRUD dictionary of Shipping/Payment/Return policy IDs and map policies per SKU for Trading SellerProfiles.",
            "category": "listing",
            "keywords": [
                "business_policies",
                "sellerprofiles",
                "shipping_policy_id",
                "payment_policy_id",
                "return_policy_id",
                "ebay_business_policies",
                "ebay_sku_business_policies",
                "sku",
                "admin",
            ],
            "graph": {
                "nodes": {
                    "ui:admin:business-policies-center": {
                        "type": "admin_ui",
                        "label": "AdminEbayBusinessPoliciesCenterPage",
                        "path": "/admin/ebay-business-policies-center",
                    },
                    "api:/api/admin/ebay/business-policies": {
                        "type": "endpoint",
                        "label": "Business policies CRUD",
                        "method": "GET/POST/PATCH/DELETE",
                        "path": "/api/admin/ebay/business-policies",
                    },
                    "db:public.ebay_business_policies": {
                        "type": "db_table",
                        "label": "ebay_business_policies",
                        "table": "ebay_business_policies",
                        "writes": True,
                    },
                    "db:public.ebay_business_policies_defaults": {
                        "type": "db_table",
                        "label": "ebay_business_policies_defaults",
                        "table": "ebay_business_policies_defaults",
                        "writes": True,
                    },
                    "db:public.ebay_sku_business_policies": {
                        "type": "db_table",
                        "label": "ebay_sku_business_policies",
                        "table": "ebay_sku_business_policies",
                        "writes": True,
                        "notes": "Per-SKU selected policy IDs (SellerProfiles).",
                    },
                    "ui:sku:edit": {
                        "type": "ui",
                        "label": "SKU edit/create form",
                        "notes": "Loads dictionary + stores per-SKU mapping.",
                    },
                },
                "edges": [
                    {"from": "ui:admin:business-policies-center", "to": "api:/api/admin/ebay/business-policies", "label": "CRUD"},
                    {"from": "api:/api/admin/ebay/business-policies", "to": "db:public.ebay_business_policies", "label": "read/write"},
                    {"from": "api:/api/admin/ebay/business-policies", "to": "db:public.ebay_business_policies_defaults", "label": "read/write defaults"},
                    {"from": "ui:sku:edit", "to": "db:public.ebay_sku_business_policies", "label": "read/write per-SKU mapping"},
                ],
            },
            "source": {"mode": "auto_seed", "docs": ["docs/2025-12-12-ebay-business-policies-table.md"]},
        }
    )

    # Admin: ShippingGroup→Policies mapping bridge
    flows.append(
        {
            "flow_key": "admin_shipping_group_policy_mappings",
            "title": "Admin: ShippingGroup → BusinessPolicy mapping (legacy bridge)",
            "summary": "Maps legacy ShippingGroup/ShippingType/DomesticOnly to SellerProfiles IDs to auto-apply policies on SKU forms and listing payloads.",
            "category": "listing",
            "keywords": [
                "shippinggroup",
                "shipping_type",
                "domestic_only",
                "mapping",
                "ebay_shipping_group_policy_mappings",
                "sellerprofiles",
                "policy",
                "admin",
            ],
            "graph": {
                "nodes": {
                    "ui:admin:policy-mappings": {
                        "type": "admin_ui",
                        "label": "AdminEbayPolicyMappingsPage",
                        "path": "/admin/ebay-policy-mappings",
                    },
                    "api:/api/admin/ebay/policy-mappings/shipping-groups": {
                        "type": "endpoint",
                        "label": "CRUD shipping-group policy mappings",
                        "method": "GET/POST/DELETE",
                        "path": "/api/admin/ebay/policy-mappings/shipping-groups",
                    },
                    "db:public.ebay_shipping_group_policy_mappings": {
                        "type": "db_table",
                        "label": "ebay_shipping_group_policy_mappings",
                        "table": "ebay_shipping_group_policy_mappings",
                        "writes": True,
                    },
                    "ui:sku:edit": {
                        "type": "ui",
                        "label": "SKU edit/create form",
                        "notes": "Auto-applies policy IDs based on mapping when possible.",
                    },
                },
                "edges": [
                    {"from": "ui:admin:policy-mappings", "to": "api:/api/admin/ebay/policy-mappings/shipping-groups", "label": "list/upsert/delete"},
                    {"from": "api:/api/admin/ebay/policy-mappings/shipping-groups", "to": "db:public.ebay_shipping_group_policy_mappings", "label": "read/write"},
                    {"from": "ui:sku:edit", "to": "db:public.ebay_shipping_group_policy_mappings", "label": "lookup mapping"},
                ],
            },
            "source": {"mode": "auto_seed", "migration": "supabase/migrations/20251213132000_ebay_shipping_group_policy_mappings.sql"},
        }
    )

    return flows
