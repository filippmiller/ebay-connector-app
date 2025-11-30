# eBay Analytics Schema Report

## Overview
Цель: зафиксировать реальную структуру таблиц в Supabase (Postgres) и описать, как связаны:

- Buying (покупка ноутбука / StorageID)
- Inventory (физические детали на складе)
- Transactions / Orders (продажи)
- eBay Fees (комиссии, финансы, рефанды)
- Inventory / Parts logs (история статусов и привязок)

Основной аналитический путь: `StorageID → Inventory / parts_detail → Transactions / Orders → Fees / Refunds → Logs`.

Все выводы ниже основаны на реальном introspection `information_schema` в схеме `public` Supabase.

## DB Connection

### Как подключается backend

Backend использует SQLAlchemy и переменную окружения `DATABASE_URL` (без .env, только через окружение/ Railway):

- `backend/app/config.py`:
  - `DATABASE_URL: str = os.getenv("DATABASE_URL", "")`
  - Жёсткая проверка при импорте:
    - если `DATABASE_URL` не задан → `RuntimeError("DATABASE_URL is required (Supabase/Postgres). No SQLite fallback.")`
    - если URL начинается с `sqlite` → `RuntimeError("SQLite is not allowed in this project.")`

- `backend/app/database.py`:
  - `SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL`
  - `engine = create_engine(SQLALCHEMY_DATABASE_URL, ...)`
  - Используются `connect_args` с `statement_timeout=30000` для PostgreSQL.
  - `SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)`
  - `Base = declarative_base()`

- `backend/app/models_sqlalchemy/__init__.py` (импортируется из `models.py`) использует тот же `engine` и `Base`.
- Схема БД: по умолчанию `public` (явных ссылок на другие схемы нет, таблицы созданы в `public`).
- Драйвер: SQLAlchemy (с postgres-драйвером, например `psycopg2` или совместимым).

### Фактический DATABASE_URL (production / Supabase)

На момент introspection в локальной среде был выставлен:

```text
postgresql://postgres:2ma5C7qZHXFJJGOG@db.nrpfahjygulsfxmbmfzv.supabase.co:5432/postgres?sslmode=require
```

## Tables & Columns

Ниже — ключевые таблицы, полученные из `information_schema.tables` и `information_schema.columns`.
Явно перечисляю только аналитически важные поля (полный список есть в выводе introspection-скрипта).

### 1. Buying (источник StorageID и цены покупки)

**Таблица:** `buying`

**Ключевые поля:**

| Column        | Type                       | Nullable | Comment                               |
|---------------|----------------------------|----------|----------------------------------------|
| `id`          | integer (PK, serial)       | NO       | Внутренний ID покупки                  |
| `item_id`     | character varying          | NO       | eBay ItemID (legacy)                   |
| `tracking_number` | character varying      | YES      | Трек-номер посылки                     |
| `buyer_id`    | character varying          | YES      | legacy buyer id                        |
| `buyer_username` | character varying       | YES      | ник покупателя (legacy)                |
| `seller_id`   | character varying          | YES      | продавец                               |
| `seller_username` | character varying      | YES      | логин продавца                         |
| `title`       | text                       | NO       | Заголовок покупки                      |
| `paid_date`   | timestamp without time zone| YES      | Дата оплаты                            |
| `amount_paid` | double precision           | YES      | Сумма, уплаченная за товар            |
| `sale_price`  | double precision           | YES      | Цена продажи (если была перепродажа)   |
| `ebay_fee`    | double precision           | YES      | Комиссия eBay (legacy)                 |
| `shipping_cost` | double precision         | YES      | Затраты на доставку                    |
| `refund`      | double precision           | YES      | Рефанд по покупке                      |
| `profit`      | double precision           | YES      | Маржа (legacy расчёт)                  |
| `status`      | character varying          | YES      | Статус покупки                         |
| `storage`     | character varying          | YES      | **StorageID (legacy)**                 |
| `comment`     | text                       | YES      | Комментарий                            |
| `author`      | character varying          | YES      | Автор записи                           |
| `rec_created` | timestamp                  | NO (now) | Создана                                |
| `rec_updated` | timestamp                  | NO (now) | Обновлена                              |

**Вывод:**

- StorageID для buying — поле `buying.storage` (строковое).
- `buying.item_id` даёт legacy ItemID.

### 2. Inventory (текущие детали на складе)

**Таблица:** `inventory`

**Ключевые поля:**

| Column           | Type                        | Nullable | Comment                                       |
|------------------|-----------------------------|----------|----------------------------------------------|
| `id`             | integer (PK, serial)        | NO       | Уникальный идентификатор записи инвентаря    |
| `sku_id`         | integer                     | NO       | Связь со справочником SKU                    |
| `storage`        | character varying           | YES      | Строковый storage (человекочитаемый)        |
| `storage_id`     | character varying           | YES      | **StorageID (нормализованный)**              |
| `status`         | character varying           | YES      | Статус (legacy строка)                       |
| `category`       | character varying           | YES      | Категория                                    |
| `price`          | double precision            | YES      | Цена (legacy)                                |
| `warehouse_id`   | integer                     | YES      | Склады                                       |
| `quantity`       | integer                     | YES      | Кол-во                                       |
| `rec_created`    | timestamp                   | NO (now) | Время создания                               |
| `rec_updated`    | timestamp                   | NO (now) | Время обновления                             |
| `model`          | text                        | YES      | Модель                                       |
| `part_number`    | character varying           | YES      | Part number                                  |
| `price_value`    | numeric                     | YES      | Нормализованная цена                         |
| `price_currency` | character                   | YES      | Валюта                                        |
| `ebay_listing_id`| character varying           | YES      | eBay listing ID (ItemID/ListingID)          |
| `ebay_status`    | USER-DEFINED (Enum)        | YES      | Статус листинга                              |
| `photo_count`    | integer                     | YES (0)  | Кол-во фото                                  |
| `author`         | character varying           | YES      | Автор                                         |
| `buyer_info`     | text                        | YES      | Свободный текст о покупателе                 |
| `tracking_number`| character varying           | YES      | Трек номер                                   |
| `raw_payload`    | jsonb                       | YES      | Raw данные                                   |
| `sku_code`       | character varying           | YES      | SKU строковый                                |
| `title`          | text                        | YES      | Заголовок                                    |
| `condition`      | character varying           | YES      | Состояние (строковое)                        |
| `cost`           | numeric                     | YES      | Себестоимость                                |
| `expected_price` | numeric                     | YES      | Ожидаемая цена                               |
| `image_url`      | text                        | YES      | Картинка                                     |
| `notes`          | text                        | YES      | Заметки                                      |
| `ebay_account_id`| character varying           | YES      | Аккаунт eBay                                 |
| `ebay_user_id`   | character varying           | YES      | userId eBay                                  |
| `parts_detail_id`| integer                     | YES      | FK → `parts_detail.id`                       |

**Выводы:**

- `inventory.id` — уникальный ID записи в нормализованной inventory. В проекте он трактуется как отдельный физический объект (деталь).
- Прямая связка с eBay продажами по TransactionID/OrderID **в таблице `inventory` отсутствует**.
- Связь с legacy-миром осуществляется через:
  - `inventory.storage_id` / `inventory.storage` ↔ StorageID
  - `inventory.ebay_listing_id` ↔ eBay Listing / ItemID
  - `inventory.parts_detail_id` ↔ `parts_detail` (подробная legacy-таблица по SKU/Storage/ItemID).

### 3. Parts Detail (legacy inventory-detail; мост к legacy MSSQL)

**Таблица:** `parts_detail`

Это большая таблица-«универсальный контроллер» legacy-листингов, статусов, флагов и цен.
Для нашей цепочки важны:

| Column               | Type                         | Nullable | Comment                                         |
|----------------------|------------------------------|----------|------------------------------------------------|
| `id`                 | integer (PK, serial)         | NO       | Уникальный ID parts_detail                      |
| `sku`                | character varying            | YES      | SKU                                            |
| `sku2`               | character varying            | YES      | Альтернативный SKU                             |
| `override_sku`       | character varying            | YES      | Override SKU                                   |
| `storage`            | character varying            | YES      | Storage (legacy)                               |
| `alt_storage`        | character varying            | YES      | Альтернативный storage                         |
| `storage_alias`      | character varying            | YES      | Alias для storage                              |
| `warehouse_id`       | integer                      | YES      | Склады                                         |
| `item_id`            | character varying            | YES      | **eBay ItemID**                                |
| `ebay_id`            | character varying            | YES      | Legacy eBay ID                                 |
| `username`           | character varying            | YES      | eBay username                                  |
| `status_sku`         | character varying            | YES      | Legacy-статус детали                           |
| `listing_status`     | character varying            | YES      | Статус листинга                                |
| `listing_start_time` | timestamptz                  | YES      | Старт листинга                                 |
| `listing_end_time`   | timestamptz                  | YES      | Окончание листинга                             |
| ... множество override_* и *flag полей (best offer, relist, cancel и т.д.) |
| `record_created_at`  | timestamptz                  | NO       | Создана                                        |
| `record_updated_at`  | timestamptz                  | YES      | Обновлена                                      |

**Связь с Inventory:**

- `inventory.parts_detail_id` → `parts_detail.id`
- `parts_detail.storage` ↔ legacy Storage
- `parts_detail.item_id` ↔ eBay ItemID

### 4. Parts Detail Log (история изменений по деталям)

**Таблица:** `parts_detail_log`

Это логовая таблица для `parts_detail`.

| Column            | Type                        | Nullable | Comment                              |
|-------------------|-----------------------------|----------|--------------------------------------|
| `id`              | integer (PK, serial)        | NO       | Лог-запись                           |
| `part_detail_id`  | integer                     | NO       | FK → `parts_detail.id`               |
| `sku`             | character varying           | YES      | SKU снимка                           |
| `model_id`        | integer                     | YES      |                                      |
| `part`            | text                        | YES      |                                      |
| ... множество полей-слепков цен, описаний, статусов |
| `record_created_at` | timestamptz               | YES      |                                      |
| `record_updated_at` | timestamptz               | YES      |                                      |
| `log_created_at`  | timestamptz (now)           | NO       | Время создания лог-записи            |
| `log_created_by`  | character varying           | YES      | Кто внёс изменения                   |

**Вывод:**

- Это основной источник истории для `parts_detail`.
- Через связку `inventory.parts_detail_id → parts_detail.id → parts_detail_log.part_detail_id` можно восстанавливать историю статусов, цен и list/relist/return событий по конкретной детали/StorageID.

### 5. Modern Transactions (нормализованные eBay продажи)

**Таблица:** `transactions`

| Column            | Type                        | Nullable | Comment                                       |
|-------------------|-----------------------------|----------|-----------------------------------------------|
| `transaction_id`  | character varying (PK логический) | NO | eBay TransactionID                            |
| `user_id`         | character varying           | NO       | Внутренний пользователь                       |
| `order_id`        | character varying           | YES      | eBay OrderID                                  |
| `line_item_id`    | character varying           | YES      | eBay OrderLineItemID                          |
| `sku`             | character varying           | YES      | SKU проданной позиции                         |
| `buyer_username`  | character varying           | YES      | Покупатель                                     |
| `sale_value`      | numeric                     | YES      | Сумма продажи                                 |
| `currency`        | character                   | YES      | Валюта                                        |
| `sale_date`       | timestamptz                 | YES      | Дата продажи                                  |
| `quantity`        | integer                     | YES      | Кол-во единиц                                 |
| `shipping_charged`| numeric                     | YES      | Взятая доставка                               |
| `tax_collected`   | numeric                     | YES      | Налог                                         |
| `fulfillment_status` | USER-DEFINED (Enum)      | YES      | Статус исполнения                             |
| `payment_status`  | USER-DEFINED (Enum)         | YES      | Статус оплаты                                 |
| `profit`          | numeric                     | YES      | Прибыль по транзакции                         |
| `profit_status`   | USER-DEFINED                | YES      | Статус прибыли (OK/NEGATIVE/INCOMPLETE)       |
| `raw_payload`     | jsonb                       | YES      | Raw JSON от eBay                              |
| `created_at`      | timestamptz                 | NO       | Вставка                                       |
| `updated_at`      | timestamptz                 | NO       | Обновление                                    |
| `ebay_account_id` | character varying           | YES      | Связь с eBay аккаунтом                        |
| `ebay_user_id`    | character varying           | YES      | eBay userId                                   |

**Вывод:**

- `transactions` — нормализованный слой, агрегирующий продажу по SKU/TransactionID/OrderID.
- Прямой FK на `inventory` отсутствует; связка идёт по SKU и/или ItemID через `parts_detail`.

### 6. Order Line Items (декомпозиция заказов)

**Таблица:** `order_line_items`

| Column            | Type                        | Nullable | Comment                        |
|-------------------|-----------------------------|----------|--------------------------------|
| `id`              | bigint (PK, serial)         | NO       | Внутренний ID строки          |
| `order_id`        | character varying           | NO       | eBay OrderID                  |
| `line_item_id`    | character varying           | NO       | eBay OrderLineItemID          |
| `sku`             | character varying           | YES      | SKU                           |
| `title`           | text                        | YES      | Заголовок позиции             |
| `quantity`        | integer (default 0)         | YES      | Кол-во                        |
| `total_value`     | numeric                     | YES      | Цена за строку               |
| `currency`        | character                   | YES      | Валюта                        |
| `raw_payload`     | text                        | YES      | Raw данные                    |
| `created_at`      | timestamptz (now)           | YES      |                               |
| `ebay_account_id` | character varying           | YES      |                               |
| `ebay_user_id`    | character varying           | YES      |                               |

**Связь с transactions:** по `order_id`+`line_item_id`/`sku`.

### 7. Legacy eBay Buyer / Fees / Transactions (старые MSSQL-таблицы)

**Таблица:** `tbl_ebay_buyer`

Содержит подробные legacy-данные по покупателям и продажам.

Ключевые поля:

- `ID` — numeric (PK legacy)
- `ItemID` — text (eBay ItemID)
- `Title` — text
- `TransactionID` — text
- `OrderLineItemID` — text
- `ShippingCarrier`, `TrackingNumber` — доставка
- `BuyerID`, `SellerID`, `SellerLocation` и т.д.
- `Storage` — text (legacy StorageID)
- `Profit`, `Refund`, кучи флагов и комментариев.

**Таблица:** `tbl_ebay_fees`

Ключевые поля:

- `ID` — numeric (PK legacy)
- `AccountDetailsEntryType` — тип записи (комиссия/возврат/налог)
- `Description`, `Date`
- `GrossDetailAmount`, `NetDetailAmount`, `VATPercent`, `DiscountAmount`
- `ItemID`, `OrderLineItemID`, `TransactionID`, `OrderID`
- `EbayID`, `ErrorMessage`, `record_created`, `record_updated`

**Таблица:** `ebay_transactions`

- `transaction_id`, `order_id`, `amount`, `currency`, `transaction_type`, `transaction_status`, `transaction_data`, `ebay_account_id`, `ebay_user_id` — legacy-normalизованный слой.

### 8. Modern Finances: Fees & Transactions (Supabase-слой)

**Таблица:** `ebay_finances_transactions`

| Column                      | Type        | Nullable |
|-----------------------------|-------------|----------|
| `id`                        | bigint (PK) | NO       |
| `ebay_account_id`           | varchar     | NO       |
| `ebay_user_id`              | varchar     | NO       |
| `transaction_id`            | varchar     | NO       |
| `transaction_type`          | varchar     | NO       |
| `transaction_status`        | varchar     | YES      |
| `booking_date`              | timestamptz | YES      |
| `transaction_amount_value`  | numeric     | YES      |
| `transaction_amount_currency`| char       | YES      |
| `order_id`                  | varchar     | YES      |
| `order_line_item_id`        | varchar     | YES      |
| `payout_id`                 | varchar     | YES      |
| `seller_reference`          | varchar     | YES      |
| `transaction_memo`          | text        | YES      |
| `raw_payload`               | jsonb       | YES      |
| `created_at`                | timestamptz | NO       |
| `updated_at`                | timestamptz | NO       |

**Таблица:** `ebay_finances_fees`

| Column           | Type        | Nullable |
|------------------|-------------|----------|
| `id`             | bigint (PK) | NO       |
| `ebay_account_id`| varchar     | NO       |
| `transaction_id` | varchar     | NO       | Связь с finances_transactions.transaction_id |
| `fee_type`       | varchar     | YES      |
| `amount_value`   | numeric     | YES      |
| `amount_currency`| char        | YES      |
| `raw_payload`    | jsonb       | YES      |
| `created_at`     | timestamptz | NO       |
| `updated_at`     | timestamptz | NO       |

**Вывод по Fees:**

- Современный слой комиссий/финансов:
  - Группировка по `transaction_id`: все комиссии по конкретной eBay финансовой транзакции.
  - Через `ebay_finances_transactions.order_id` и `order_line_item_id` можно выйти на конкретный заказ.

### 9. Inventory / Buyer Logs (legacy)

**Таблицы:** `tbl_ebay_buyer_log`, `tbl_parts_inventory`, `tbl_parts_inventorystatus`, `tbl_ebay_buyer`.

Для нашей цели важнее modern-лог `parts_detail_log` и связки через `parts_detail_id`, поэтому `tbl_*` таблицы рассматриваются как read-only legacy-источник, уже частично агрегированный в `parts_detail` / `parts_detail_log`.

## Relationship Map

Текстовое описание ключевых связей.

### Buying ↔ Inventory / Parts

- Legacy buying:
  - `buying.storage` хранит StorageID покупки.
  - Legacy ebay buyer таблица `tbl_ebay_buyer` тоже имеет `Storage` и `ItemID`.
- Нормализованный слой:
  - `inventory.storage_id` хранит нормализованный StorageID для текущей детали.
  - `inventory.parts_detail_id` → `parts_detail.id`, где `parts_detail.storage` и `parts_detail.item_id` повторяют legacy Storage и ItemID.

**Логическая цепочка:**

1. `StorageID` из Buying → поиск по:
   - `buying.storage = :storage_id` (legacy факт покупки ноутбука),
   - `parts_detail.storage = :storage_id`,
   - `inventory.storage_id = :storage_id`.
2. `inventory` связывается с `parts_detail` через FK `parts_detail_id`.

### Inventory ↔ Transactions / Orders

- Прямая колонка `transaction_id` / `order_id` в `inventory` **отсутствует**.
- Связь идёт через SKU / ItemID / parts_detail:
  - `inventory.sku_id` → SKU справочник (`SKU_catalog` / `sku`),
  - `parts_detail.item_id` ↔ eBay ItemID,
  - `order_line_items.sku` и/или `transactions.sku` ↔ тот же SKU,
  - `ebay_finances_transactions.order_id` / `order_line_item_id` ↔ `order_line_items`.

Типичный путь:

1. `inventory.id` → `inventory.parts_detail_id` → `parts_detail.item_id`.
2. `parts_detail.item_id` используется для поиска продаж:
   - В modern слое через `transactions.raw_payload` / `order_line_items.raw_payload` (по ItemID) или напрямую по SKU, если SKU однозначен.
   - В legacy через `tbl_ebay_buyer.ItemID` / `TransactionID`.

### Transactions ↔ Fees / Refunds

- Legacy:
  - `tbl_ebay_fees.TransactionID`, `OrderID`, `ItemID`, `OrderLineItemID` → группировка всех комиссий и корректировок по конкретной продаже.
- Modern finances:
  - `ebay_finances_transactions.transaction_id` ↔ `ebay_finances_fees.transaction_id`.
  - Через `ebay_finances_transactions.order_id` / `order_line_item_id` можно связаться с `order_line_items` и далее с конкретной продажей.

### Inventory ↔ Logs

- Modern лог:
  - `inventory.parts_detail_id` → `parts_detail.id` → `parts_detail_log.part_detail_id`.
  - История цен, статусов, флагов list/relist/return хранится в `parts_detail_log`.
- Legacy buyer logs:
  - `tbl_ebay_buyer_log` фиксирует изменения по покупателям, storage и т.п., но находится в legacy-слое.

## Legacy Algorithm Reconstruction

Ниже — реконструкция алгоритма привязки eBay-продажи к уникальной детали (InventoryID), основанная на текущей схеме.

### Цель

Вход: `(item_id, transaction_id, order_id)`

Выход: уникальный `inventory.id` (физическая деталь) + запись в логе.

### Шаги (концептуально)

1. **Найти кандидатные parts_detail по ItemID:**
   - `SELECT id FROM parts_detail WHERE item_id = :item_id`.
2. **Найти связанные записи inventory:**
   - `SELECT * FROM inventory WHERE parts_detail_id IN (:parts_detail_ids)`.
3. **Отфильтровать по статусу:**
   - Учитывать только детали со статусами, позволяющими продажу (`AVAILABLE` / `LISTED` / `PENDING_LISTING` и т.п.; сейчас статус текстовый, но может быть сопоставлен с enum `InventoryStatus`).
4. **Проверить, не была ли деталь уже продана:**
   - По текущей схеме это делается не через поле `transaction_id` в `inventory`, а через:
     - `parts_detail.listing_status`,
     - историю в `parts_detail_log` (флаги `just_sold_flag`, `return_flag`, `loss_flag` и т.п.),
     - modern слой `transactions` (по SKU/ItemID).
5. **Выбор кандидата по FIFO:**
   - Отсортировать кандидатов по `rec_created` или `parts_detail.record_created_at` (старейшая деталь первая):

   ```sql
   SELECT i.id
   FROM inventory i
   JOIN parts_detail p ON i.parts_detail_id = p.id
   WHERE p.item_id = :item_id
     AND /* статус i/p допускает продажу */
   ORDER BY i.rec_created ASC
   LIMIT 1;
   ```

6. **Обновление статуса (концептуально):**
   - Обновить `parts_detail.status_sku`, `parts_detail.listing_status` и, возможно, `inventory.status` на SOLD.
   - Зафиксировать `transaction_id`/`order_id` в связанной таблице (modern-подход — в `transactions` + маппинг через SKU/ItemID).

7. **Запись в лог:**
   - Создать запись в `parts_detail_log` или отдельной лог-таблице, содержащей:
     - `part_detail_id` / `inventory_id`,
     - `item_id`, `transaction_id`, `order_id`,
     - старый и новый статус,
     - `log_created_at`, `log_created_by`.

### Псевдокод (на уровне репозитория)

```python
path=null start=null
from datetime import datetime
from sqlalchemy.orm import Session


def assign_transaction_to_inventory(db: Session, item_id: str, transaction_id: str | None, order_id: str | None) -> int | None:
    # 1. parts_detail-кандидаты по ItemID
    parts = (
        db.query(PartsDetail)
        .filter(PartsDetail.item_id == item_id)
        .all()
    )
    if not parts:
        return None

    part_ids = [p.id for p in parts]

    # 2. inventory по parts_detail_id
    candidates = (
        db.query(Inventory)
        .filter(Inventory.parts_detail_id.in_(part_ids))
        .order_by(Inventory.rec_created.asc())
        .all()
    )

    # 3. отфильтровать по статусу/уже проданным (условие зависит от бизнес-логики)
    eligible = [i for i in candidates if is_inventory_sellable(i)]
    if not eligible:
        return None

    chosen = eligible[0]

    # 4. обновить статус (концептуально)
    old_status = chosen.status
    chosen.status = "SOLD"
    # parts_detail.status_sku / listing_status также могут быть обновлены

    # 5. записать лог
    log = PartsDetailLog(
        part_detail_id=chosen.parts_detail_id,
        # ... копируем интересующие поля снапшота ...
        log_created_at=datetime.utcnow(),
        log_created_by="system-ebay-sync",
    )

    db.add(log)
    db.commit()

    return chosen.id
```

> Важно: В текущей Supabase-схеме нет явного поля `transaction_id` в `inventory`, поэтому для будущей реализации рекомендуется добавить либо связь `inventory_id` в `transactions`, либо отдельную таблицу маппинга `inventory_sales`.

## Analytics Path for StorageID

Ниже — практический путь аналитики «от StorageID до прибыли и комиссий».

### 1. Найти все Inventory по StorageID

Поисковые варианты:

- **Нормализованный слой:**

  ```sql
  SELECT *
  FROM inventory
  WHERE storage_id = :storage_id;
  ```

- **Legacy слой (parts_detail):**

  ```sql
  SELECT p.*
  FROM parts_detail p
  WHERE p.storage = :storage_id
     OR p.alt_storage = :storage_id
     OR p.storage_alias = :storage_id;
  ```

### 2. Связать Inventory → Parts Detail → ItemID/SKU

```sql
SELECT i.id AS inventory_id,
       i.storage_id,
       i.sku_id,
       i.sku_code,
       p.id AS parts_detail_id,
       p.item_id,
       p.status_sku,
       p.listing_status
FROM inventory i
LEFT JOIN parts_detail p ON i.parts_detail_id = p.id
WHERE i.storage_id = :storage_id;
```

### 3. Найти все транзакции по ItemID / SKU

Modern путь через `transactions` / `order_line_items`:

```sql
-- через SKU
SELECT t.*
FROM transactions t
WHERE t.sku = :sku_code;

-- через order_line_items (если SKU там точнее)
SELECT oli.*, t.*
FROM order_line_items oli
LEFT JOIN transactions t
  ON t.order_id = oli.order_id
 AND (t.line_item_id = oli.line_item_id OR t.sku = oli.sku)
WHERE oli.sku = :sku_code;
```

Legacy путь (для валидации):

```sql
SELECT b.*
FROM tbl_ebay_buyer b
WHERE b.ItemID = :item_id
   OR b.Storage = :storage_id;
```

### 4. Найти все Fees / Refunds по TransactionID / OrderID

Legacy fees:

```sql
SELECT f.*
FROM tbl_ebay_fees f
WHERE f.TransactionID = :transaction_id
   OR f.OrderID = :order_id
   OR f.ItemID = :item_id
   OR f.OrderLineItemID = :order_line_item_id;
```

Modern finances:

```sql
-- Все финансы по TransactionID
SELECT ft.*, ff.*
FROM ebay_finances_transactions ft
LEFT JOIN ebay_finances_fees ff
  ON ff.transaction_id = ft.transaction_id
WHERE ft.transaction_id = :transaction_id;

-- Все финансы по OrderID
SELECT ft.*, ff.*
FROM ebay_finances_transactions ft
LEFT JOIN ebay_finances_fees ff
  ON ff.transaction_id = ft.transaction_id
WHERE ft.order_id = :order_id;
```

### 5. Посчитать выручку и комиссии по StorageID

Идея: собрать `StorageID` → список `transaction_id` → агрегировать `sale_value` и комиссии.

**Примерное view (концепция):**

```sql
-- 1) Связать inventory с parts_detail и transactions через SKU
CREATE VIEW v_inventory_sales AS
SELECT i.id AS inventory_id,
       i.storage_id,
       i.sku_code,
       p.item_id,
       t.transaction_id,
       t.order_id,
       t.sale_value,
       t.currency,
       t.profit,
       t.sale_date
FROM inventory i
LEFT JOIN parts_detail p ON i.parts_detail_id = p.id
LEFT JOIN transactions t ON t.sku = i.sku_code;

-- 2) Финансы по transaction_id
CREATE VIEW v_transaction_fees AS
SELECT ft.transaction_id,
       SUM(COALESCE(ff.amount_value, 0)) AS total_fees,
       MAX(ft.transaction_amount_currency) AS currency
FROM ebay_finances_transactions ft
LEFT JOIN ebay_finances_fees ff
  ON ff.transaction_id = ft.transaction_id
GROUP BY ft.transaction_id;

-- 3) Финальный Profit по StorageID
CREATE VIEW v_storage_profit AS
SELECT s.storage_id,
       SUM(s.sale_value) AS total_sales,
       SUM(COALESCE(f.total_fees, 0)) AS total_fees,
       SUM(COALESCE(s.profit, 0)) AS total_profit_from_transactions
FROM v_inventory_sales s
LEFT JOIN v_transaction_fees f
  ON f.transaction_id = s.transaction_id
GROUP BY s.storage_id;
```

> На практике для точной математики по StorageID нужно учесть себестоимость (`inventory.cost` / `buying.amount_paid`) и дополнительные расходы (`accounting_transaction` с `storage_id`).

## Next Steps

1. **Уточнение связей Inventory ↔ Transactions:**
   - Добавить явный FK или связь через маппинг-таблицу:
     - Вариант A: в `transactions` добавить `inventory_id` (nullable), обновлять при матчинге.
     - Вариант B: создать таблицу `inventory_sales (inventory_id, transaction_id, quantity, linked_at)`.

2. **Расширение логирования:**
   - Добавить специализированную лог-таблицу `inventory_log` (в Supabase), которая будет фиксировать:
     - `inventory_id`,
     - `item_id`, `transaction_id`, `order_id`,
     - старый/новый статус,
     - источник изменения (worker/API),
     - timestamp.
   - Связать её с уже существующим `parts_detail_log` для богатой истории.

3. **Новые представления (views) для аналитики:**
   - `v_inventory_sales` (описано выше): Inventory → Transactions.
   - `v_transaction_fees`: группировка eBay finances fees по `transaction_id`/`order_id`.
   - `v_storage_profit`: агрегация по StorageID (продажи, комиссии, прибыль).
   - Дополнительно: join с `accounting_transaction` по `storage_id` для учёта внешних расходов.

4. **Модель Profit(StorageID):**

   Концепция модели:

   ```text
   Profit(StorageID) =
       Σ Sales(StorageID)         -- из transactions/order_line_items
     - Σ eBayFees(StorageID)      -- из ebay_finances_*
     - Σ ShippingCosts(StorageID) -- из buying / accounting_transaction
     - Σ OtherCosts(StorageID)    -- расходные accounting_transaction
   ```

   Для этого потребуются:

   - Явные связи `StorageID` во всех слоях (сейчас есть в `inventory.storage_id`, `buying.storage`, `accounting_transaction.storage_id`).
   - Нормализованный маппинг `inventory_id` ↔ `transaction_id`.

5. **Документация и миграции:**
   - Формализовать в отдельной документации (например, `docs/analytics_profit_model.md`) точные формулы и SQL view.
   - Спроектировать Alembic-миграции для новых таблиц/полей:
     - `inventory_sales` или `inventory_id` в `transactions`.
     - `inventory_log` (Supabase-таблица).

6. **Проверка против legacy:**
   - Сравнить результаты по StorageID из modern слоёв (`transactions`, `ebay_finances_*`) с legacy-таблицами (`tbl_ebay_buyer`, `tbl_ebay_fees`) на ограниченном сэмпле StorageID, чтобы верифицировать корректность маппинга и расчётов.

---

Этот отчёт основан на реальной схеме Supabase (таблицы `inventory`, `buying`, `parts_detail`, `parts_detail_log`, `transactions`, `order_line_items`, `ebay_finances_transactions`, `ebay_finances_fees`, `tbl_ebay_*`) и может использоваться как база для дальнейших миграций и построения полноценной модели прибыли по StorageID.