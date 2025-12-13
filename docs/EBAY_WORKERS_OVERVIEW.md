# eBay Workers Overview

Документ описывает инфраструктуру eBay‑воркеров в текущем проекте: какие воркеры уже реализованы, какие eBay API они вызывают, какие данные забирают и в какие таблицы пишут, а также какие воркеры логически напрашиваются, но ещё не реализованы.

## 1. Общая архитектура воркеров

**Основные сущности в БД (Postgres):
- `ebay_sync_state` – состояние синхронизации по аккаунту + api_family (какой воркер, включён/выключен, курсор, последняя ошибка и т.п.).
- `ebay_worker_run` – отдельный запуск воркера (статус, время старта/финиша, summary_json).
- `ebay_api_worker_log` – покадровые логи воркера (start/page/done/error) для UI‑терминала.
- `ebay_worker_global_config` – глобальный kill‑switch (`workers_enabled`) и дефолтные настройки.

**Где лежит код инфраструктуры**
- Модели: `backend/app/models_sqlalchemy/ebay_workers.py`
- Alembic‑миграция: `backend/alembic/versions/20251115_add_ebay_workers.py`
- Логика состояния/курсора/kill‑switch:
  - `backend/app/services/ebay_workers/state.py`
  - `backend/app/services/ebay_workers/runs.py`
  - `backend/app/services/ebay_workers/logger.py`
- Планировщик по аккаунтам: `backend/app/services/ebay_workers/scheduler.py`
- HTTP‑роутер (UI + API для запуска воркеров): `backend/app/routers/ebay_workers.py`

**Общий паттерн воркера (per‑account):**
1. Получаем `EbayAccount` и `EbayToken` для `ebay_account_id`.
2. Через `get_or_create_sync_state` берём/создаём `EbaySyncState` с нужным `api_family`.
3. Проверяем `state.enabled` и глобальный флаг `workers_enabled`.
4. Через `start_run` создаём запись в `ebay_worker_run` (с защитой от дублей по аккаунту+api_family).
5. Через `compute_sync_window` получаем окно дат (`window_from` / `window_to`) с overlap и initial backfill.
6. Логируем `start` в `ebay_api_worker_log`.
7. Вызываем соответствующий метод `EbayService` (ниже по каждому воркеру).
8. Обновляем счётчики `total_fetched` / `total_stored`, логируем `page` и `done`.
9. Через `mark_sync_run_result` двигаем курсор (cursor_value = конец окна) или сохраняем ошибку.
10. Через `complete_run` / `fail_run` закрываем `ebay_worker_run`.

**Как запускаются воркеры**
- Ручной запуск по аккаунту: `POST /ebay/workers/run?account_id=...&api=orders|transactions|...`
- Планировщик для всех аккаунтов:
  - `backend/app/workers/ebay_workers_loop.py` → вызывает
  - `app.services.ebay_workers.scheduler.run_cycle_for_all_accounts()` → внутри по каждому аккаунту `run_cycle_for_account(ebay_account_id)`.

## 2. Существующие api_family и воркеры

Ниже перечислены воркеры из `backend/app/services/ebay_workers`, их API, таблицы и особенности.

### 2.1 `orders` – Orders worker

**Код**
- Воркеры: `backend/app/services/ebay_workers/orders_worker.py`
- Точка входа: `async def run_orders_worker_for_account(ebay_account_id: str) -> Optional[str]`
- Вызывается из:
  - `scheduler.run_cycle_for_account` (если `EbaySyncState.api_family="orders"` включён)
  - `POST /ebay/workers/run?api=orders`

**EbayService / eBay API**
- Метод: `EbayService.sync_all_orders(...)` в `backend/app/services/ebay.py`
- Внутри использует Sell Fulfillment API:
  - `GET /sell/fulfillment/v1/order?filter=orderStatus:COMPLETED&limit=200&offset=...`
- Получает заказы с 90‑дневным окном (логическое окно дополнительно логируется воркером).

**Куда пишет данные** (Postgres, через `PostgresEbayDatabase`):
- Основная таблица заказов: `ebay_orders`
- Позиции заказа: `order_line_items`

**Окно и курсор**
- Воркер сам считает окно через `compute_sync_window` (`overlap_minutes=60`, `initial_backfill_days=90`).
- В `sync_all_orders` сейчас окно в основном для логов; фактический фильтр – 90 дней назад до сейчас.
- `cursor_value` – ISO8601 до конца окна (worker window_to).

### 2.2 `transactions` – Transactions worker (legacy Finances sync)

**Код**
- Воркеры: `backend/app/services/ebay_workers/transactions_worker.py`
- Точка входа: `async def run_transactions_worker_for_account(ebay_account_id: str)`

**EbayService / eBay API**
- Метод: `EbayService.sync_all_transactions(...)`
- Использует Sell Finances API `GET /sell/finances/v1/transaction` с фильтрацией по `transactionDate`.

**Куда пишет данные**
- Таблица транзакций: `ebay_transactions`

**Окно и курсор**
- `OVERLAP_MINUTES_DEFAULT = 60`, `INITIAL_BACKFILL_DAYS_DEFAULT = 90`.
- `compute_sync_window` возвращает (from,to); воркер передаёт их в `sync_all_transactions`, которая реально фильтрует транзакции по датам.
- `cursor_value` = `window_to`.

### 2.3 `finances` – Finances worker (новый путь в специализированные таблицы)

**Код**
- Воркеры: `backend/app/services/ebay_workers/finances_worker.py`
- Точка входа: `async def run_finances_worker_for_account(ebay_account_id: str)`
- Пока **не подключён** в `scheduler.API_FAMILIES` (запуск через `/ebay/workers/run?api=finances` или через UI).

**EbayService / eBay API**
- Метод: `EbayService.sync_finances_transactions(...)`
- Также опирается на Sell Finances API `GET /sell/finances/v1/transaction`.

**Куда пишет данные** (через `PostgresEbayDatabase.upsert_finances_transaction`):
- Основная таблица: `ebay_finances_transactions`
- Детализация комиссий: `ebay_finances_fees`

**Особенности**
- Более «правильный» путь для финансов: транзакции + fees в отдельных таблицах.
- Логика похожа на `sync_all_transactions`, но запись в другие таблицы и отдельные эвенты для Notification Center.

### 2.4 `offers` – Offers worker

**Код**
- `backend/app/services/ebay_workers/offers_worker.py`
- Точка входа: `async def run_offers_worker_for_account(ebay_account_id: str)`
- Входит в `scheduler.API_FAMILIES` и автоматически вызывается при цикле.

**EbayService / eBay API**
- Метод: `EbayService.sync_all_offers(...)`
- API последовательность (см. докстринг в `ebay.py`):
  1. `GET /sell/inventory/v1/inventory_item?limit=200&offset=...` – получить список SKU.
  2. Для каждого SKU: `GET /sell/inventory/v1/offer?sku={sku}&limit=200&offset=...`.

**Куда пишет данные** (через `PostgresEbayDatabase.upsert_offer` + частично `upsert_inventory_item`):
- Офферы: `ebay_offers`
- Связанные inventory‑item’ы – таблица инвентаря (см. `upsert_inventory_item`), используется для listing‑грида.

**Окно и курсор**
- `OVERLAP_MINUTES_DEFAULT = 360` (6 часов), `INITIAL_BACKFILL_DAYS_DEFAULT = 90`.
- Фактически Inventory/Offers API не принимают полноценный date‑filter; окно используется в основном для логирования и для более агрессивного отсечения старых офферов на уровне записи.

### 2.5 `messages` – Messages worker

**Код**
- `backend/app/services/ebay_workers/messages_worker.py`
- Точка входа: `async def run_messages_worker_for_account(ebay_account_id: str)`
- Вызывается планировщиком и через `/ebay/workers/run?api=messages`.

**EbayService / eBay API**
- Метод: `EbayService.sync_all_messages(...)`
- Trading API `GetMyMessages` (XML):
  - сначала заголовки (ReturnSummary/ReturnHeaders) по папкам и окну дат,
  - потом батчами `GetMyMessages` c `ReturnMessages` для получения тел сообщений.

**Куда пишет данные**
- Основная таблица: `ebay_messages` (см. схему и `DATABASE_SCHEMA.md`; в Postgres путь идёт через SQLAlchemy‑модель `Message`).

**Окно и курсор**
- `OVERLAP_MINUTES_DEFAULT = 60`, backfill 90 дней.
- `window_from` / `window_to` передаются в `GetMyMessages` как `StartTimeFrom` / `StartTimeTo`, то есть это полноценный инкрементальный sync по времени.

### 2.6 `active_inventory` – Active Inventory snapshot worker

**Код**
- `backend/app/services/ebay_workers/active_inventory_worker.py`
- Точка входа: `async def run_active_inventory_worker_for_account(ebay_account_id: str)`
- Подключён в `scheduler.API_FAMILIES`.

**EbayService / eBay API**
- Метод: `EbayService.sync_active_inventory_report(...)`
- Trading API `GetMyeBaySelling` (ActiveList) через XML `POST https://api.ebay.com/ws/api.dll`.

**Куда пишет данные**
- Таблица снапшота активных листингов: `ebay_active_inventory` (SQLAlchemy‑модель `ActiveInventory`).

**Особенности**
- Это **snapshot**‑воркер без окна времени: каждый запуск строит полный снимок активных лотов.
- Воркер логирует «синтетическое» окно `from=to=now` только для observability; в `cursor_value` складывается время последнего успешного снапшота.

### 2.7 `buyer` – Purchases / Buyer worker

**Код**
- `backend/app/services/ebay_workers/purchases_worker.py`
- Точка входа: `async def run_purchases_worker_for_account(ebay_account_id: str)`
- Подключён в `scheduler.API_FAMILIES` как `api_family="buyer"`.

**EbayService / eBay API**
- Метод: `EbayService.get_purchases(access_token, since=None)`
- Trading API `GetMyeBayBuying` (XML) через `POST https://api.ebay.com/ws/api.dll`.

**Куда пишет данные**
- Таблица: `ebay_buyer` (SQLAlchemy‑модель `EbayBuyer`).
- Воркер явно upsert’ит записи в `ebay_buyer` через ORM.

**Окно и курсор**
- `OVERLAP_MINUTES_DEFAULT = 60`, `INITIAL_BACKFILL_DAYS_DEFAULT = 30`.
- Сейчас `since` в `get_purchases` фактически не используется (Trading возьмёт своё дефолтное окно), но курсор ведётся, чтобы в будущем можно было перейти на явный date‑filter.

### 2.8 `inquiries` – Post‑Order Inquiries worker

**Код**
- `backend/app/services/ebay_workers/inquiries_worker.py`
- Точка входа: `async def run_inquiries_worker_for_account(ebay_account_id: str)`
- **Не подключён в `scheduler.API_FAMILIES`**, но:
  - всегда показывается в UI через `/ebay/workers/config`,
  - может быть запущен через `/ebay/workers/run?api=inquiries`.

**EbayService / eBay API**
- Метод: `EbayService.sync_postorder_inquiries(...)`
- Post‑Order API: `GET /post-order/v2/inquiry/search` +, при необходимости, `GET /post-order/v2/inquiry/{inquiryId}` для детализации.

**Куда пишет данные** (через `PostgresEbayDatabase.upsert_inquiry`):
- Таблица: `ebay_inquiries`.

**Роль в продукте**
- Данные объединяются с `ebay_cases` + `ebay_disputes` в единую grid по проблемным заказам (INR/SNAD и др.).

### 2.9 `cases` – Post‑Order Cases worker

**Код**
- `backend/app/services/ebay_workers/cases_worker.py`
- Точка входа: `async def run_cases_worker_for_account(ebay_account_id: str)`
- Аналогично inquiries/finances – пока не в `scheduler.API_FAMILIES`, но доступен через API/UI.

**EbayService / eBay API**
- Метод: `EbayService.sync_postorder_cases(...)`
- Post‑Order API: `GET /post-order/v2/casemanagement/search` (+ возможные дополнительные detail‑вызовы).

**Куда пишет данные** (через `PostgresEbayDatabase.upsert_case`):
- Таблица: `ebay_cases`.

**Особенности**
- Нормализует itemId/transactionId, buyer/seller username, суммы claimAmount, respondBy, API‑timestamps.
- В summary воркер пишет дополнительную статистику:
  - `normalized_full`, `normalized_partial`, `normalization_errors`.

## 3. Таблицы, которые уже используются воркерами

Сводная карта «воркер → таблицы» (Postgres‑ветка проекта):

- `orders` → `ebay_orders`, `order_line_items`.
- `transactions` → `ebay_transactions`.
- `finances` → `ebay_finances_transactions`, `ebay_finances_fees`.
- `offers` → `ebay_offers` (+ inventory‑таблица через `upsert_inventory_item`).
- `messages` → `ebay_messages`.
- `active_inventory` → `ebay_active_inventory`.
- `buyer` (purchases) → `ebay_buyer`.
- `inquiries` → `ebay_inquiries`.
- `cases` → `ebay_cases`.

Отдельно, без воркера, но уже есть полный ingestion‑путь:

- Disputes (payment disputes) → `ebay_disputes` (см. `PostgresEbayDatabase.upsert_dispute`). Сейчас вызывается из методов `EbayService.sync_all_disputes` (poll‑синхронизация, не интегрированная в `ebay_workers`).

Также в `DATABASE_SCHEMA.md` описаны проектные таблицы `ebay_refunds`, `ebay_fees`, но под них ещё нет полноценного ingestion через воркеры.

## 4. Legacy / вспомогательные воркеры вокруг eBay

Помимо нового `ebay_workers`‑слоя есть и другие фоновые задачи, связанные с eBay:

- `backend/app/workers/ebay_listing_worker.py`
  - Оркестрирует синхронизацию листингов (inventory + offers) для одного пользователя/аккаунта.
  - Использует те же методы `EbayService` и `PostgresEbayDatabase`, но не завязан на `ebay_sync_state` / `ebay_worker_run`.

- `backend/app/workers/ebay_monitor_worker.py`
  - Мониторинг / health‑check интеграции (состояние токенов, базовые вызовы API).

- `backend/app/workers/token_refresh_worker.py`
  - Фоновое обновление OAuth‑токенов eBay (не относится к domain‑воркерам, но критично для их работы).

Эти воркеры стоит воспринимать как «околосервисные»; основная модель для описания бизнес‑данных – это именно `app/services/ebay_workers/*` + `ebay_sync_state`.

## 5. Планируемые / отсутствующие воркеры и предложения по реализации

Ниже – воркеры, которые логически напрашиваются исходя из уже существующих сервисов и схемы БД, но полного `ebay_workers`‑варианта пока нет.

### 5.1 `disputes` – Payment Disputes worker

**Почему нужен**
- Есть:
  - Метод `EbayService.sync_all_disputes(...)` (см. фрагменты с логами "Disputes sync ...").
  - `PostgresEbayDatabase.upsert_dispute(...)`, пишущий в таблицу `ebay_disputes`.
  - `API_FAMILIES` в `state.py` уже содержит строку `"disputes"`.
- Нет:
  - `disputes_worker.py` в `app/services/ebay_workers`.
  - интеграции этого api_family в `scheduler` и `/ebay/workers/run`.

**Предлагаемый воркер**
- Файл: `backend/app/services/ebay_workers/disputes_worker.py`.
- Сигнатура: `async def run_disputes_worker_for_account(ebay_account_id: str) -> Optional[str]`.
- Паттерн копируем с `cases_worker` / `inquiries_worker`:
  1. Берём `EbayAccount` + `EbayToken` по `ebay_account_id`.
  2. `state = get_or_create_sync_state(..., api_family="disputes")`.
  3. `run = start_run(..., api_family="disputes")`.
  4. Окно – либо как у transactions/finances (по `transactionDate`), либо (если API не поддерживает фильтр) treat window как метаданные, как это сделано для `cases`/`inquiries`.
  5. Вызываем `await ebay_service.sync_all_disputes(...)`, передаём `window_from/window_to` для логов.
  6. Собираем `total_fetched/total_stored` из результата, пишем `log_page`, `log_done`, обновляем курсор.
  7. В случае ошибки – `log_error`, `mark_sync_run_result(..., error=msg)`, `fail_run`.

**Интеграция**
- В `backend/app/routers/ebay_workers.py`:
  - импортировать `run_disputes_worker_for_account`.
  - Добавить `"disputes"` в множество допустимых api в `/run` и в `ensured_families` для `/config` и `/schedule`.
- В `scheduler.API_FAMILIES` – по желанию включить `"disputes"`, если хотим периодический автозапуск.

### 5.2 `refunds` – Refunds worker (таблица `ebay_refunds`)

**Текущая ситуация**
- В схеме (`DATABASE_SCHEMA.md`) есть:
  - Таблица `ebay_refunds` с полями `refund_id`, `refund_amount`, `refund_status`, `refund_reason`, ссылкой на заказ, и т.п.
- В коде нет:
  - `PostgresEbayDatabase.upsert_refund`.
  - Метода `EbayService.sync_refunds`.
  - Самого воркера на базе `ebay_workers`.

**Предлагаемый ingestion‑путь**

_Вариант A – через Finances API (рекомендуется как минимум базовый шаг):_
- В `EbayService.sync_finances_transactions` уже приходят Finances‑транзакции с типами, включая REFUND / NON_SALE_CHARGE и т.п.
- Можно:
  - в `PostgresEbayDatabase.upsert_finances_transaction` дополнительно маппить транзакции с типом `REFUND` в таблицу `ebay_refunds` (через новый helper `upsert_refund_from_finances(...)`).
  - Или сделать отдельный проход по финтранзакциям в новом методе `sync_refunds`, который будет вызывать новый helper в Postgres‑слое.

_Вариант B – через Post‑Order Returns / Refunds API:_
- Добавить в `EbayService` метод `sync_postorder_refunds(...)`, который будет:
  - дергать Post‑Order endpoint’ы для возвратов/рефандов (например, `GET /post-order/v2/return/search`, далее detail по каждому return/refund),
  - собирать нормализованный DTO под `ebay_refunds`.
- В `PostgresEbayDatabase` реализовать `upsert_refund(user_id, refund_data, ebay_account_id, ebay_user_id)` c INSERT/ON CONFLICT в `ebay_refunds`.

**Предлагаемый воркер**
- Файл: `backend/app/services/ebay_workers/refunds_worker.py`.
- Сигнатура: `async def run_refunds_worker_for_account(ebay_account_id: str) -> Optional[str]`.
- Паттерн как у `finances_worker`:
  - api_family = `"refunds"`.
  - Окно по дате рефанда (либо через Finances transactionDate, либо через Post‑Order даты).
  - Логика overlap/backfill – по аналогии: `OVERLAP_MINUTES_DEFAULT = 60`, `INITIAL_BACKFILL_DAYS_DEFAULT = 90`.

**Интеграция**
- Добавить `"refunds"` в:
  - `API_FAMILIES` в `state.py`.
  - `ensured_families` в `/ebay/workers/config` и `/ebay/workers/schedule`.
  - Множество поддерживаемых API в `/ebay/workers/run`.
- По желанию – добавить в `scheduler.API_FAMILIES`, если нужен регулярный опрос.

### 5.3 Inventory core worker (SKU‑inventory, не только active snapshot)

Сейчас:
- `EbayService.sync_all_offers` уже опрашивает `getInventoryItems` и складывает данные через `PostgresEbayDatabase.upsert_inventory_item`.
- Есть активный снапшот по Trading (`active_inventory_worker` → `ebay_active_inventory`).

Чего нет:
- Отдельного воркера api_family, явно отвечающего за «core inventory» (`inventory_core` или `inventory_sku`), который бы:
  - регулярно обновлял таблицу инвентаря (по SKU) независимо от Offers.
  - позволял управлять этим потоком отдельно (включать/отключать, смотреть курсор, лог и т.п.).

**Предлагаемый воркер**
- Файл: `backend/app/services/ebay_workers/inventory_worker.py`.
- api_family, например, `"inventory"`.
- Точка входа: `run_inventory_worker_for_account(ebay_account_id: str)`.
- Внутри – тонкий адаптер к существующей логике `sync_inventory_items` (или части `sync_all_offers`, если хотим вынести inventory в отдельный helper).

Интеграция аналогична другим воркерам:
- Добавить api_family в `state.API_FAMILIES`, config/schedule/router `/run` и (при необходимости) scheduler.

## 6. Итоговое состояние и приоритеты

На текущий момент `ebay_workers` покрывают:
- Продажи и заказы: `orders`, `transactions`, `finances`, `offers`, `active_inventory`.
- Коммуникацию и поддержка: `messages`, `inquiries`, `cases`.
- Покупки (buyer‑сторона): `buyer`.

Логически ближайшие шаги по развитию:
1. **Disputes worker (`disputes`)** – минимальный треугольник `inquiries + cases + disputes` для единой матрицы проблемных заказов.
2. **Refunds ingestion (`refunds`)** – заполнить `ebay_refunds` и связать её с заказами / cases / disputes.
3. **Явный inventory‑воркер** – чтобы синхронизация SKU‑инвентаря была прозрачной и управляемой так же, как `offers` и `active_inventory`.

Этот документ можно расширять по мере появления новых api_family (shipping, metrics, traffic и т.п.), добавляя секции с тем же шаблоном: `api_family → worker → EbayService → eBay endpoints → таблицы`.