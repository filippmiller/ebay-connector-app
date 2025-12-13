from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models_sqlalchemy.models import EbayAccount, EbayToken
from app.utils.logger import logger
from .base_worker import BaseWorker


class AssignStoragesForSoldItemsWorker(BaseWorker):
    """
    Worker that matches sold items (tbl_ebay_seller_info_detail) to oldest available
    inventory rows (tbl_parts_inventory) and marks inventory as SOLD.

    This is a legacy-compatible process that:
    1. Finds sold items where StorageID IS NULL
    2. Matches them to available inventory (StatusSKU=3) using ROW_NUMBER() oldest-first
    3. Updates tbl_ebay_seller_info_detail with StorageID/StorageAliasID/PartsInvDetail_ID
    4. Marks tbl_parts_inventory as SOLD (StatusSKU=5, JustSoldFlag=1)

    Note: This worker does NOT call eBay API; it's a pure database matching process.
    We inherit from BaseWorker for consistency with other workers, but we don't use
    the window/cursor logic (overlap_minutes=None means no window).
    """

    def __init__(self):
        super().__init__(
            api_family="assign_storages_for_sold_items",
            overlap_minutes=None,  # No time window needed for this process
            initial_backfill_days=0,
            limit=100,  # Process up to 100 matches per run
        )

    async def execute_sync(
        self,
        db: Session,
        account: EbayAccount,
        token: EbayToken,  # Not used, but required by BaseWorker signature
        run_id: str,
        sync_run_id: str,
        window_from: Optional[str],  # Not used
        window_to: Optional[str],  # Not used
    ) -> Dict[str, Any]:
        """
        Execute the storage assignment logic (1-в-1 with legacy jobAssignStoragesForSoldItems.php).

        Returns:
            Dict with total_fetched (matched pairs found) and total_stored (successfully updated).
        """

        # Get EbayID from account (this is the seller username like "mil_243", "betterplanetcomputers")
        ebay_id = account.ebay_user_id or account.username
        if not ebay_id:
            logger.warning(
                f"[assign_storages_worker] No ebay_user_id/username for account {account.id}, skipping"
            )
            return {
                "total_fetched": 0,
                "total_stored": 0,
                "error_message": "No ebay_user_id/username available",
            }

        limit = self.limit

        # Main matching query (1-в-1 with legacy SQL, adapted for Postgres)
        # Legacy uses ROW_NUMBER() partitioned by ItemID, ordered by ID ASC for oldest-first matching
        query = text("""
            SELECT
                T1."ID" AS seller_info_detail_id,
                T1."SellerInfo_ID",
                T1."ItemID",
                T1.nom,
                T1."StorageID",
                T1."StorageAliasID",
                T1."PartsInvDetail_ID",
                T1.ebay_id AS sold_ebay_id,

                T2.nom AS inventory_nom,
                T2."SKU" AS inventory_sku,
                T2."PartsInvDetail_ID" AS inventory_parts_inv_detail_id,
                T2."Storage" AS inventory_storage_id,
                T2."StorageAlias" AS inventory_storage_alias_id,
                T2."InventoryID",
                T2."EbayID" AS inventory_ebay_id
            FROM
            (
                SELECT
                    T1."ID",
                    T1."ItemID",
                    T1."SKU",
                    T1."StorageID",
                    T1."StorageAliasID",
                    T1."SellerInfo_ID",
                    T1."PartsInvDetail_ID",
                    ROW_NUMBER() OVER (PARTITION BY T1."ItemID" ORDER BY T1."ID" ASC) AS nom,
                    (
                        SELECT T2."SellerID"
                        FROM "tbl_ebay_seller_info" T2
                        WHERE T1."SellerInfo_ID" = T2."ID"
                    ) AS ebay_id
                FROM "tbl_ebay_seller_info_detail" T1
                WHERE 1 = 1
                    AND COALESCE(T1."ItemID", '') <> ''
                    AND T1."ItemID" IN (
                        SELECT DISTINCT "ItemID"
                        FROM "tbl_parts_inventory"
                        WHERE "ItemID" IS NOT NULL
                    )
                    AND COALESCE(T1."PartsInvDetail_ID", 0) <> -1
                    AND T1."StorageID" IS NULL
            ) T1
            INNER JOIN
            (
                SELECT
                    T1."ID" AS "PartsInvDetail_ID",
                    ROW_NUMBER() OVER (PARTITION BY T2."ItemID" ORDER BY T1."ID" ASC) AS nom,
                    T1."Inv_ID",
                    T1."record_created",
                    T2."ItemID",
                    T2."StatusSKU",
                    T2."SKU",
                    T2."Storage",
                    T2."StorageAlias",
                    T2."ID" AS "InventoryID",
                    T2."EbayID"
                FROM "tbl_parts_inventory_detail" T1
                INNER JOIN "tbl_parts_inventory" T2
                    ON T1."Inv_ID" = T2."ID"
                WHERE T2."StatusSKU" IN (3)
            ) T2
            ON T1."ItemID" = T2."ItemID"
                AND T1.nom = T2.nom
                AND COALESCE(T1.ebay_id, '') = COALESCE(T2."EbayID", '')
            LIMIT :limit
        """)

        try:
            rows = db.execute(query, {"limit": limit}).mappings().all()
            matched_pairs = list(rows)
            total_fetched = len(matched_pairs)

            logger.info(
                f"[assign_storages_worker] Found {total_fetched} matched pairs for account {account.id} (ebay_id={ebay_id})"
            )

            total_stored = 0
            errors: list[str] = []

            for pair in matched_pairs:
                seller_info_detail_id = pair.get("seller_info_detail_id")
                inventory_storage_id = pair.get("inventory_storage_id")
                inventory_storage_alias_id = pair.get("inventory_storage_alias_id")
                inventory_parts_inv_detail_id = pair.get("inventory_parts_inv_detail_id")
                inventory_id = pair.get("InventoryID")
                item_id = pair.get("ItemID")

                if not all(
                    [
                        seller_info_detail_id,
                        inventory_storage_id,
                        inventory_parts_inv_detail_id,
                        inventory_id,
                    ]
                ):
                    errors.append(
                        f"Missing required fields for ItemID={item_id}: "
                        f"seller_info_detail_id={seller_info_detail_id}, "
                        f"inventory_id={inventory_id}, "
                        f"storage_id={inventory_storage_id}, "
                        f"parts_inv_detail_id={inventory_parts_inv_detail_id}"
                    )
                    continue

                # Step 1: Update tbl_ebay_seller_info_detail (assign storage to sold item)
                update_seller_detail = text("""
                    UPDATE "tbl_ebay_seller_info_detail"
                    SET
                        "StorageID" = :storage_id,
                        "StorageAliasID" = :storage_alias_id,
                        "PartsInvDetail_ID" = :parts_inv_detail_id
                    WHERE "ID" = :seller_info_detail_id
                """)

                try:
                    result1 = db.execute(
                        update_seller_detail,
                        {
                            "storage_id": inventory_storage_id,
                            "storage_alias_id": inventory_storage_alias_id,
                            "parts_inv_detail_id": int(inventory_parts_inv_detail_id),
                            "seller_info_detail_id": int(seller_info_detail_id),
                        },
                    )
                    if result1.rowcount == 0:
                        errors.append(
                            f"Failed to update tbl_ebay_seller_info_detail.ID={seller_info_detail_id}"
                        )
                        continue
                except Exception as exc:
                    errors.append(
                        f"Error updating seller_info_detail {seller_info_detail_id}: {exc}"
                    )
                    continue

                # Step 2: Mark inventory as SOLD (StatusSKU=5, JustSoldFlag=1)
                update_inventory = text("""
                    UPDATE "tbl_parts_inventory"
                    SET
                        "StatusSKU" = 5,
                        "StatusUpdated" = NOW(),
                        "StatusUpdatedBy" = 'system',
                        "JustSoldFlag" = 1,
                        "JustSoldFlag_created" = NOW(),
                        "JustSoldFlag_updated" = NOW()
                    WHERE "ID" = :inventory_id
                """)

                try:
                    result2 = db.execute(
                        update_inventory,
                        {"inventory_id": int(inventory_id)},
                    )
                    if result2.rowcount == 0:
                        errors.append(
                            f"Failed to update tbl_parts_inventory.ID={inventory_id}"
                        )
                        db.rollback()  # Rollback seller_detail update too
                        continue
                except Exception as exc:
                    errors.append(f"Error updating inventory {inventory_id}: {exc}")
                    db.rollback()  # Rollback seller_detail update too
                    continue

                # Commit both updates together
                db.commit()
                total_stored += 1

                logger.debug(
                    f"[assign_storages_worker] Assigned ItemID={item_id} to inventory_id={inventory_id} "
                    f"(storage={inventory_storage_id})"
                )

            if errors:
                logger.warning(
                    f"[assign_storages_worker] Completed with {len(errors)} errors: {errors[:5]}"
                )

            logger.info(
                f"[assign_storages_worker] Completed: matched={total_fetched}, updated={total_stored}, errors={len(errors)}"
            )

            return {
                "total_fetched": total_fetched,
                "total_stored": total_stored,
                "errors": errors[:10] if errors else None,  # Return first 10 errors
            }

        except Exception as exc:
            db.rollback()
            logger.error(
                f"[assign_storages_worker] Failed for account {account.id}: {exc}",
                exc_info=True,
            )
            return {
                "total_fetched": 0,
                "total_stored": 0,
                "error_message": str(exc),
            }


async def run_assign_storages_worker_for_account(
    ebay_account_id: str,
    triggered_by: str = "unknown",
) -> Optional[str]:
    """Run AssignStoragesForSoldItems worker for a specific eBay account."""
    worker = AssignStoragesForSoldItemsWorker()
    return await worker.run_for_account(ebay_account_id, triggered_by=triggered_by)
