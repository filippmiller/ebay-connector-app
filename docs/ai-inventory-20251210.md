# AI Infrastructure Inventory - eBay Connector App

**Date**: 2025-12-10  
**Purpose**: Document existing AI-related code before implementing AI Assistant subsystem

---

## Backend AI Modules

### Core AI Services

#### 1. [`ai_providers.py`](file:///c:/dev/ebay-connector-app/backend/app/services/ai_providers.py)
**Purpose**: OpenAI API configuration management

**Key Functions**:
- `get_openai_api_config(db)` - Resolves OpenAI API key, model, base URL
  - Precedence: 1) `ai_providers` table, 2) `settings.OPENAI_API_KEY`
  - Returns: `(api_key, model, base_url)`

**Used by**: All OpenAI integrations

---

#### 2. [`ai_query_engine.py`](file:///c:/dev/ebay-connector-app/backend/app/services/ai_query_engine.py)  
**Purpose**: Natural language → SQL conversion for analytics

**Key Functions**:
- `build_sql_from_prompt(prompt, allowed_tables, db)` - Generates SQL from natural language
  - Calls OpenAI Chat Completions
  - Returns: `(sql, columns)`
  - Validates: read-only, whitelisted tables only
  - Enforces: no INSERT/UPDATE/DELETE/DDL

**Safety Features**:
- `_validate_sql(sql, allowed_tables)` - Read-only enforcement
- `_extract_table_identifiers(sql)` - Table whitelist validation

**Status**: ✅ Already implements most Phase 1 functionality!

---

#### 3. [`ai_rules_engine.py`](file:///c:/dev/ebay-connector-app/backend/app/services/ai_rules_engine.py)
**Purpose**: AI rules management

**Functions**:
- Uses OpenAI for generating rules
- Integrates with `ai_rules` table

---

### AI-Powered Features

#### 4. [Accounting Parsers](file:///c:/dev/ebay-connector-app/backend/app/services/accounting_parsers/)
**Purpose**: Parse bank statements via OpenAI

**Files**:
- `pdf_parser.py` - OpenAI Assistants API for PDF parsing
- `td_bank_parser.py` - Deterministic parser (NO OpenAI)
- `csv_parser.py`, `xlsx_parser.py` - Legacy OpenAI-based parsers

**Key Function**:
- `parse_pdf_statement_v2(file_path)` - Uses OpenAI Assistants API

---

#### 5. [CV Brain](file:///c:/dev/ebay-connector-app/backend/app/cv/brain/)
**Purpose**: Computer Vision AI for eBay listings

**Modules**:
- `vision_brain_orchestrator.py` - Orchestrates CV tasks
- `llm_brain.py` - LLM integration for CV
- `brain_repository.py` - Data access
- `brain_models.py` - Data models

---

## Backend API Routes

### AI Endpoints

#### Admin AI Routes
- [`admin_ai.py`](file:///c:/dev/ebay-connector-app/backend/app/routers/admin_ai.py)
- [`admin_ai_overview.py`](file:///c:/dev/ebay-connector-app/backend/app/routers/admin_ai_overview.py)
- [`admin_ai_rules_ext.py`](file:///c:/dev/ebay-connector-app/backend/app/routers/admin_ai_rules_ext.py)
- [`admin_ai_integrations.py`](file:///c:/dev/ebay-connector-app/backend/app/routers/admin_ai_integrations.py)

#### Other AI Routes
- [`cv_brain.py`](file:///c:/dev/ebay-connector-app/backend/app/routers/cv_brain.py) - CV operations
- [`ai_messages.py`](file:///c:/dev/ebay-connector-app/backend/app/routers/ai_messages.py) - AI messages
- [`ai_speech.py`](file:///c:/dev/ebay-connector-app/backend/app/routers/ai_speech.py) - Speech processing

---

## Supabase Schema (Existing AI Tables)

### 1. `ai_providers`
**Migration**: [`ai_providers_openai_20251126.py`](file:///c:/dev/ebay-connector-app/backend/alembic/versions/ai_providers_openai_20251126.py)

**Schema**:
```sql
CREATE TABLE ai_providers (
    id VARCHAR(36) PRIMARY KEY,
    provider_code TEXT UNIQUE NOT NULL,  -- e.g. "openai"
    name TEXT NOT NULL,
    owner_user_id VARCHAR(36) REFERENCES users(id),
    api_key TEXT,  -- Encrypted at rest
    model_default TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Purpose**: Store encrypted OpenAI API keys per user/org

---

### 2. `ai_rules`
**Migration**: [`ai_analytics_20251125.py`](file:///c:/dev/ebay-connector-app/backend/alembic/versions/ai_analytics_20251125.py)

**Schema**:
```sql
CREATE TABLE ai_rules (
    id VARCHAR(36) PRIMARY KEY,
    name TEXT NOT NULL,
    rule_sql TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by_user_id VARCHAR(36) REFERENCES users(id)
);
```

**Purpose**: Reusable SQL rule fragments (e.g. profitability conditions)

---

### 3. `ai_query_log`
**Migration**: [`ai_analytics_20251125.py`](file:///c:/dev/ebay-connector-app/backend/alembic/versions/ai_analytics_20251125.py)

**Schema**:
```sql
CREATE TABLE ai_query_log (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) REFERENCES users(id),
    prompt TEXT NOT NULL,
    sql TEXT NOT NULL,
    row_count INTEGER,
    executed_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Purpose**: Append-only log of AI-generated SQL queries

---

### 4. Other AI-related migrations
- [`ai_ebay_actions_20251125.py`](file:///c:/dev/ebay-connector-app/backend/alembic/versions/ai_ebay_actions_20251125.py)
- [`ai_ebay_candidates_20251125.py`](file:///c:/dev/ebay-connector-app/backend/alembic/versions/ai_ebay_candidates_20251125.py)
- [`20251206_120000_add_raw_openai_response.py`](file:///c:/dev/ebay-connector-app/backend/alembic/versions/20251206_120000_add_raw_openai_response.py)

---

## Frontend AI Components

### 1. Chat Widget Loader
**File**: [`frontend/src/main.tsx`](file:///c:/dev/ebay-connector-app/frontend/src/main.tsx)

**Function**: `loadChatWidget()`
**Purpose**: Dynamically loads external AI chat widget from Railway

**Configuration**:
- URL: `VITE_CHAT_WIDGET_BASE_URL`
- Attributes: `data-api`, `data-title`, `data-greeting`

**Status**: ✅ Active (connects to external widget backend)

---

## External Dependencies

### AI Chat Widget (Railway Service)
**Location**: `external/ai-chat-widget/`

**Backend**: FastAPI
- Routes: `/api/chat/message`, `/api/stt/transcribe`
- Features: Text chat + Russian voice input (OpenAI Whisper)

**Frontend**: `widget.js`
- Floating chat button (bottom-right)
- Voice recording with MediaRecorder
- Russian STT via OpenAI

**Deployment**: Separate Railway service (`aiwidget.up.railway.app`)

---

## Configuration

### Environment Variables (Backend)
```bash
# From config.py
OPENAI_API_KEY=<key>
OPENAI_API_BASE_URL=https://api.openai.com
OPENAI_MODEL=gpt-4o
```

### Environment Variables (Frontend)
```bash
# Chat widget
VITE_CHAT_WIDGET_BASE_URL=https://aiwidget.up.railway.app
```

---

## Key Insights for Phase 1 & 2

### ✅ What Already Exists

1. **OpenAI Integration** - `ai_providers.py` handles API keys
2. **SQL Generation** - `ai_query_engine.py` converts NL → SQL
3. **SQL Validation** - Read-only enforcement, table whitelisting
4. **Query Logging** - `ai_query_log` table
5. **Chat Widget** - External floating widget with voice input

### ❌ What Needs to Be Built

#### Phase 1 (Analytics Assistant)
- [ ] `ai_schema_tables` - Schema catalog
- [ ] `ai_schema_columns` - Column metadata  
- [ ] `ai_semantic_rules` - User intent → SQL patterns
- [ ] Schema discovery endpoint (`POST /api/ai/schema-refresh`)
- [ ] Unified assistant endpoint (`POST /api/ai-assistant/query`)
- [ ] Wire widget to use new endpoint

#### Phase 2 (Training Center)
- [ ] `ai_training_sessions` - Training sessions
- [ ] `ai_training_examples` - Training examples
- [ ] Training Center UI (`/admin/ai-training`)
- [ ] Voice-based training workflow
- [ ] Semantic rule promotion

---

## Recommendations

1. **Reuse `ai_query_engine.py`** - Most Phase 1 SQL logic already exists
2. **Extend `ai_providers.py`** - Already handles OpenAI config
3. **Reuse existing STT** - Chat widget already has `/api/stt/transcribe`
4. **Leverage existing tables** - `ai_rules` can be adapted for semantic rules
5. **Build on top** - Don't duplicate, extend existing infrastructure

---

## Next Steps

1. Create Phase 1 schema (4 new tables)
2. Add schema discovery module
3. Create unified `/api/ai-assistant/query` endpoint
4. Wire widget to new endpoint
5. Test analytics queries
6. Move to Phase 2
