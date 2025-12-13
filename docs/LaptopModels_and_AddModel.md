# LaptopModels and AddModel

This document describes how the **Laptop Models** catalog is stored in the production Supabase/Postgres database and how the **Add Model** flow works end-to-end in the eBay Connector App.

## 1. Database: `tbl_parts_models`

The laptop models dictionary lives in the legacy Postgres table `tbl_parts_models` in the `public` schema. This table is treated as the single source of truth for laptop models that are reused across SKUs.

Key columns (based on the current production schema):

- `ID` (numeric, NOT NULL) – primary numeric identifier for each model row.
- `Model_ID` (numeric, NULL) – legacy model ID used by the old system; defaults to `0` when missing.
- `Brand_ID` (integer, NULL) – identifier of the brand (e.g. Apple, Dell).
- `Model` (text, NULL) – human-readable laptop model name, e.g. `Apple MacBook Pro 14" A2442 2021`. This is the only *required* input in the Add Model form.
- `oc_filter_Model_ID`, `oc_filter_Model_ID2` (numeric, NULL) – OpenCart filter IDs used by the previous store.
- Condition score columns (all numeric, NOT NULL in practice, defaulting to `0` in the app):
  - `BuyingPrice`
  - `working`
  - `motherboard`
  - `battery`
  - `hdd`
  - `keyboard`
  - `memory`
  - `screen`
  - `casing`
  - `drive`
  - `damage`
  - `cd`
  - `adapter`
- Metadata:
  - `record_created` (timestamp without time zone, NOT NULL, default `NOW()` in DB).
  - `do_not_buy` (boolean, NULL/false by default) – flag marking models that should not be purchased.

The app does **not** create or manage this table via Alembic. Instead, it reflects the existing structure at runtime and issues raw SQL/SQLAlchemy Core statements directly against it.

## 2. Backend model reflection

The table is reflected in `backend/app/models_sqlalchemy/models.py`:

- `tbl_parts_models_table` is created with:
  - `Table("tbl_parts_models", Base.metadata, autoload_with=engine)`
- If the table does not exist or cannot be reflected, a warning is logged and `tbl_parts_models_table` is set to `None`.
- All routes that depend on this table first check whether `tbl_parts_models_table` is not `None` and either return an empty result set or raise `503` if the table is unavailable in the current environment.

This reflection uses the same SQLAlchemy engine as the rest of the Postgres-backed models, so it always targets the production Supabase/Postgres configured via `DATABASE_URL`.

## 3. API layer: `/api/sq/parts-models` and `/api/sq/models/search`

The API for laptop models is defined in `backend/app/routers/sq_catalog.py` and exposes two main endpoints.

### 3.1 `GET /api/sq/models/search`

Purpose:

- Lightweight typeahead for the **Model** field in the SKU Create/Edit form.

Behaviour:

1. Uses the reflected `tbl_parts_models_table` to detect a numeric ID column and a text label column (preferring names that contain `model`, `name`, `title`, or `part`).
2. Runs a `SELECT id_col, label_col FROM tbl_parts_models WHERE label_col ILIKE '%q%' LIMIT :limit` query.
3. Returns `{ items: [{ id, label }], total }`, where `label` is the chosen text column converted to string.
4. If `tbl_parts_models_table` is missing or has no usable text columns, returns an empty list rather than failing.

The SKU form uses this endpoint when the user types in the Model input and presses **Enter**.

### 3.2 `GET /api/sq/parts-models`

Purpose:

- Load the paginated **Models** grid inside the Models modal.

Behaviour:

- Accepts `search`, `brand_id`, `limit`, and `offset` query parameters.
- Builds a dynamic WHERE clause and executes a raw SQL query that:
  - Filters `LOWER("Model") LIKE :search` when a search term is provided.
  - Optionally filters by `"Brand_ID"`.
  - Orders by `"Model" ASC`.
  - Limits and offsets for pagination.
- Returns a full representation of each row, mapped to the `PartsModel` TypeScript type used by the frontend (`id`, `model_id`, `brand_id`, condition scores, `record_created`, `do_not_buy`).

### 3.3 `POST /api/sq/parts-models` (Add Model)

Purpose:

- Create a new laptop model row in `tbl_parts_models` for use in SKU creation.

Implementation details (after the current fix):

- Location: `backend/app/routers/sq_catalog.py`, function `create_parts_model`.
- Input: `payload: dict` parsed from JSON. The frontend sends a `NewPartsModel` object with fields like `brand_id`, `model`, and integer scores.
- Validation:
  - Reads `model` from the payload, trims it, and requires it to be non-empty.
  - All other numeric fields are optional and default to `0` when missing or falsy.
- Insert logic:
  1. Builds an `insert_data` dict whose keys *exactly* match the real column names (`"Model_ID"`, `"Brand_ID"`, `"Model"`, etc.).
  2. Uses SQLAlchemy Core with the reflected table instead of hand-written SQL:
     - `insert_stmt = tbl_parts_models_table.insert().values(**insert_data)`
     - Adds a `.returning(...)` clause selecting all required columns.
  3. Executes `result = db.execute(insert_stmt)`.
  4. Calls `row = result.fetchone()` **before** committing.
  5. Commits the transaction with `db.commit()`.
  6. If `row` is `None`, raises a `500` error.
- Response:
  - Returns a JSON object shaped like `PartsModel`:
    - `id`, `model_id`, `brand_id`, `model`, all condition scores, `record_created` (ISO 8601 string or `null`), and `do_not_buy` as a boolean.
- Error handling:
  - If `tbl_parts_models_table` is `None`, responds with HTTP 503 and `"tbl_parts_models table not available in this environment"`.
  - If `model` is empty, responds with HTTP 400 and `"Model name is required"`.
  - Any unexpected database error is logged (with stack trace) and surfaced as HTTP 500 with `detail="Database error: ..."`.

This refactoring ensures that we rely on SQLAlchemy to generate the correct INSERT/RETURNING statement for Postgres and avoids subtle issues with manual quoting or result handling.

## 4. Frontend types and API client

The frontend API and types for laptop models live under `frontend/src`.

### 4.1 Types: `frontend/src/types/partsModel.ts`

Relevant TypeScript types:

- `PartsModel` – full representation of a row from `tbl_parts_models`:
  - `id: number` – primary key.
  - `model_id?: number | null` – legacy ID.
  - `brand_id?: number | null` – brand.
  - `model: string` – model name.
  - `oc_filter_model_id?: number | null`, `oc_filter_model_id2?: number | null`.
  - Numeric scores: `buying_price`, `working`, `motherboard`, `battery`, `hdd`, `keyboard`, `memory`, `screen`, `casing`, `drive`, `damage`, `cd`, `adapter`.
  - Metadata: `record_created?: string | null`, `do_not_buy?: boolean | null`.
- `NewPartsModel` – `Omit<PartsModel, "id" | "record_created">`. This is the payload type for creation.

### 4.2 API client: `frontend/src/api/partsModels.ts`

Two helper functions wrap the backend endpoints:

1. `listPartsModels(params?: ListPartsModelsParams): Promise<ListPartsModelsResponse>`
   - Performs `GET /api/sq/parts-models`.
   - Passes `search`, `brand_id`, `limit`, and `offset` as query parameters.
   - Returns `{ items: PartsModel[], total: number }`.

2. `createPartsModel(payload: NewPartsModel): Promise<PartsModel>`
   - Normalises the payload so all NOT NULL numeric fields and `do_not_buy` always have explicit values (default `0` or `false`).
   - Sends a `POST` request to `/api/sq/parts-models`.
   - Returns the created `PartsModel` from the backend.

These helpers are the only entry points the UI uses to talk to the laptop models API.

## 5. UI flow: Models modal and Add Model

The UI flow for selecting and creating laptop models on the SKU screen involves three components:

1. `SkuFormModal` – main SKU Create/Edit modal.
2. `ModelsModal` – modal showing the laptop models grid.
3. `AddModelModal` – nested modal used to create a new entry in `tbl_parts_models`.

### 5.1 `SkuFormModal` (Model field)

File: `frontend/src/components/SkuFormModal.tsx`

- The **Model** field is a controlled `Input` backed by `form.model`.
- Behaviours:
  - Typing in the field and pressing **Enter** triggers a search against `GET /api/sq/models/search` and renders a dropdown with `{ id, label }` items.
  - Selecting a suggestion sets `form.model` to the chosen label.
  - Clicking the **+** button next to the Model field opens `ModelsModal`.
- When a model is selected from `ModelsModal`, `handlePartsModelSelected(partsModel)` runs:
  - Updates the form with `form.model = partsModel.model`.
  - Closes the `ModelsModal`.

### 5.2 `ModelsModal` (models catalog browser)

File: `frontend/src/components/ModelsModal.tsx`

Purpose:

- Provide a paginated, searchable view of all laptop models and allow the user to pick one or create a new one.

Key behaviours:

- Local state:
  - `models: PartsModel[]`, `total`, `loading`, `searchTerm`, `page`, `showAddModal`.
- On open:
  - Calls `listPartsModels({ search: searchTerm, limit: 50, offset: (page - 1) * 50 })` to populate the grid.
- Search:
  - The search input triggers `handleSearch()` on Enter or when the **Find** button is clicked.
  - `handleClear()` resets the search term and reloads the first page.
- Selection:
  - Double-clicking a row calls `handleRowDoubleClick(model)` → `handleSelectModel(model)`.
  - `handleSelectModel(model)` calls the parent callback `onModelSelected(model)` and then `onClose()` to close the modal.
- Add Model:
  - Clicking **Add Model** sets `showAddModal = true` and renders `AddModelModal` as a nested dialog.
  - When a new model is created, `handleCreated(created)` is called:
    - Prepends the new model to the local `models` list.
    - Increments `total` by 1.
    - Closes `AddModelModal`.
    - Immediately calls `onModelSelected(created)` to update the SKU form.
    - Closes the `ModelsModal` itself.

### 5.3 `AddModelModal` (nested modal for creation)

File: `frontend/src/components/AddModelModal.tsx`

Behaviour:

- Controlled form state with fields:
  - `brand_id`, `model`, `buying_price`, and integer condition scores (`working`, `motherboard`, `keyboard`, `memory`, `battery`, `hdd`, `screen`, `casing`, `drive`, `cd`, `adapter`, `damage`), plus `do_not_buy`.
- Validation:
  - Only requires `model` to be non-empty.
  - All numeric fields default to string `'0'` and are converted to numbers on save.
- Save handler (`handleSave`):
  1. Validates the form.
  2. Builds a `NewPartsModel` payload with numeric types (using `Number(...) || 0`).
  3. Calls `createPartsModel(payload)`.
  4. On success:
     - Shows a toast: `Model "…" has been created successfully.`
     - Resets the local form to its initial state.
     - Calls `onCreated(created)` so that `ModelsModal` can:
       - Update its grid,
       - Auto-select the new model,
       - And close both modals.
  5. On error:
     - Reads `detail` from the backend HTTP error if available and shows a destructive toast.
- Cancel handler (`handleCancel`):
  - Resets the form and errors.
  - Calls `onClose()` to close the nested modal.

## 6. End-to-end Add Model flow

Putting all pieces together, the Add Model flow works as follows:

1. User opens the **SKU** tab and clicks **Add SKU**.
2. `SkuFormModal` opens. In the **Title & Model** section, user clicks the **+** button next to the Model field.
3. `ModelsModal` opens and loads models from `/api/sq/parts-models`.
4. User clicks **Add Model** in the Models modal.
5. `AddModelModal` opens. User fills out at least the **Model Name** field and optionally the brand and score fields, then clicks **Save**.
6. Frontend sends a `POST /api/sq/parts-models` with a `NewPartsModel` payload.
7. Backend:
   - Validates the model name.
   - Inserts a row into `tbl_parts_models` using SQLAlchemy Core and returns the full row data.
8. Frontend receives the created `PartsModel`:
   - `AddModelModal` calls `onCreated(created)`.
   - `ModelsModal` prepends the row, auto-selects it, and closes.
   - `SkuFormModal` receives the selected model in `handlePartsModelSelected` and updates its `model` field.
9. Back in the SKU form, the **Model** input now contains the newly created model name, and the user can proceed to fill the rest of the SKU and save it.

## 7. Notes and troubleshooting

- If the backend cannot connect to `tbl_parts_models` (for example, because the underlying table is missing or the database connection string points to the wrong database), `POST /api/sq/parts-models` will return HTTP 503 with a clear error message. In that case, the Add Model form will show a destructive toast and no data will be written.
- If the user submits the Add Model form without a model name, the backend responds with HTTP 400 `"Model name is required"` and the frontend displays the message.
- All numeric score fields are always normalised to integers in both the frontend payload and backend defaults, which matches the current `tbl_parts_models` schema where these columns are effectively NOT NULL and default to `0`.
- TypeScript compilation (`npm run build`) must pass for the Add Model flow to be considered safe to deploy. ESLint currently reports several pre-existing style issues (`no-explicit-any`, `react-hooks/exhaustive-deps`, etc.), but these do not block the build and are independent from the Add Model implementation.
