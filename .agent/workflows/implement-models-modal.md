---
description: Implement triple-modal flow for Models selection and creation
---

# Implementation Plan: Models Modal Flow

## Objective
Add a triple-modal cascade in the SKU form:
1. Create SKU → Model field with "+" button
2. "+" opens "Models" modal (searchable grid from `tbl_parts_models`)
3. "Models" modal has "Add Model" button
4. "Add Model" opens form modal to create new model
5. On save: INSERT into `tbl_parts_models`, refresh grid, auto-select, return to Create SKU

## Database Schema
Table: `public.tbl_parts_models`

Columns (from DB Explorer screenshot):
- `ID` (numeric, PK, not null)
- `Model_ID` (numeric, nullable)
- `Brand_ID` (integer, nullable)
- `Model` (text, nullable)
- `oc_filter_Model_ID` (numeric)
- `oc_filter_Model_ID2` (numeric)
- `BuyingPrice` (integer, NOT NULL)
- `working` (integer, NOT NULL)
- `motherboard` (integer, NOT NULL)
- `battery` (integer, NOT NULL)
- `hdd` (integer, NOT NULL)
- `keyboard` (integer, NOT NULL)
- `memory` (integer, NOT NULL)
- `screen` (integer, NOT NULL)
- `casing` (integer, NOT NULL)
- `drive` (integer, NOT NULL)
- `damage` (integer, NOT NULL)
- `cd` (integer, NOT NULL)
- `adapter` (integer, NOT NULL)
- `record_created` (timestamp without time zone, nullable)
- `do_not_buy` (boolean, nullable)

## Implementation Steps

### 1. Create TypeScript Types
**File**: `frontend/src/types/partsModel.ts`

```typescript
export interface PartsModel {
  id: number;
  model_id?: number | null;
  brand_id?: number | null;
  model: string;
  oc_filter_model_id?: number | null;
  oc_filter_model_id2?: number | null;
  buying_price: number;
  working: number;
  motherboard: number;
  battery: number;
  hdd: number;
  keyboard: number;
  memory: number;
  screen: number;
  casing: number;
  drive: number;
  damage: number;
  cd: number;
  adapter: number;
  record_created?: string | null;
  do_not_buy?: boolean | null;
}

export type NewPartsModel = Omit<PartsModel, "id" | "record_created">;
```

### 2. Create API Helper
**File**: `frontend/src/api/partsModels.ts`

Functions:
- `listPartsModels(params)` - search/filter models
- `createPartsModel(payload)` - insert new model

### 3. Backend API Endpoints
**File**: `backend/app/routers/sq_catalog.py`

Add routes:
- `GET /api/sq/parts-models` - list/search models with pagination
- `POST /api/sq/parts-models` - create new model

### 4. Create AddModelModal Component
**File**: `frontend/src/components/AddModelModal.tsx`

Props:
- `isOpen: boolean`
- `onClose: () => void`
- `onCreated: (model: PartsModel) => void`

Form fields:
- Brand (dropdown - reuse existing brands)
- Model (text, required)
- BuyingPrice (number, default 0)
- Working, Motherboard, Keyboard, Memory ,Battery, HDD, Screen, Casing, Drive, CD, Adapter, Damage (all number, default 0)
- Do Not Buy (checkbox, default false)

### 5. Create ModelsModal Component
**File**: `frontend/src/components/ModelsModal.tsx`

Props:
- `isOpen: boolean`
- `onClose: () => void`
- `onModelSelected: (model: PartsModel) => void`

Features:
- Search input (debounced)
- Data grid with columns (ID, Brand, Model, BuyingPrice, etc.)
- "Add Model" button
- Double-click or Select button to choose model
- Integrates AddModelModal

### 6. Modify SkuFormModal
**File**: `frontend/src/components/SkuFormModal.tsx`

Changes:
- Add "+" button next to Model field (line ~557-602)
- Add state: `const [showModelsModal, setShowModelsModal] = useState(false)`
- Add state: `const [selectedModel, setSelectedModel] = useState<PartsModel | null>(null)`
- Render ModelsModal component
- Update model field to show selected model

### 7. Wiring Data Flow

```
User clicks "+" 
  → setShowModelsModal(true)
  → ModelsModal opens
  → User searches/browses
  
Option A: User clicks "Add Model"
  → ModelsModal opens AddModelModal
  → User fills form, clicks Save
  → createPartsModel() API call
  → onCreated(newModel) callback
  → ModelsModal adds to grid
  → Auto-selects new model
  → onModelSelected(newModel)
  → SkuFormModal.setSelectedModel(newModel)
  → Both modals close

Option B: User selects existing model
  → onModelSelected(model)
  → SkuFormModal.setSelectedModel(model)
  → Modal closes
```

## Testing Checklist
- [ ] Connect to Railway/Supabase
- [ ] Verify `tbl_parts_models` structure
- [ ] Test model search API
- [ ] Test model create API
- [ ] Verify brand dropdown loads correctly
- [ ] Test full flow: Create SKU → + → Search → Select
- [ ] Test full flow: Create SKU → + → Add Model → Save → Auto-select
- [ ] Verify model FK saved correctly in SKU

## Notes
- All NOT NULL integer fields default to 0
- `record_created` should be set by DB (NOW()) or backend
- `do_not_buy` defaults to false
- Brand dropdown should reuse existing brand dictionary (check dictionaries endpoint)
