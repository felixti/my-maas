# DiskANN Vector Index for Azure DocumentDB

## TL;DR

> **Quick Summary**: Replace hardcoded HNSW vector index with configurable DiskANN/HNSW support in the custom Azure DocumentDB adapter. New `VECTOR_INDEX_TYPE` env var (default: `diskann`) controls index type. DiskANN scales to 500K+ vectors vs HNSW's 50K limit.
> 
> **Deliverables**:
> - Configurable vector index type via `VECTOR_INDEX_TYPE` env var (`diskann` | `hnsw`)
> - Updated `AzureDocumentDB` adapter with dual index type support
> - Index-kind mismatch detection with warning log
> - Parameterized unit tests covering both index types
> - Updated documentation (AGENTS.md, .env.example, README, PHASE9 design doc, CONFIGURATION)
> 
> **Estimated Effort**: Medium
> **Parallel Execution**: YES — 3 waves
> **Critical Path**: Task 1 → Task 2 → Task 4 → Task 6 → F1-F4

---

## Context

### Original Request
User wants to replace HNSW vector index implementation with DiskANN in the Azure DocumentDB vector store adapter, making the index type configurable.

### Interview Summary
**Key Discussions**:
- **Configurability**: User chose configurable approach (env var) over hard-switch, to allow HNSW fallback for local dev if DocumentDB Local doesn't support DiskANN
- **Test strategy**: Tests-after (update existing tests post-implementation, not TDD)
- **Index type default**: `diskann` for production, `hnsw` available as fallback

**Research Findings**:
- Microsoft docs confirm DiskANN uses `vector-diskann` kind, `maxDegree`/`lBuild` build params, optional `lSearch` search param
- Both HNSW and DiskANN use the same `cosmosSearch` operator in `$search` aggregation pipeline
- Both require M30+ cluster tier — no tier difference between them
- DiskANN scales to 500K+ vectors vs HNSW's 50K limit
- mem0's built-in MongoDB adapter is irrelevant — MaaS uses fully custom `AzureDocumentDB` class
- `documentdb.py` has zero imports from `maas.config` — must stay decoupled

### Metis Review
**Identified Gaps** (addressed):
- **Index migration on existing deployments**: Existing index name check would silently keep HNSW when switching to DiskANN → Added mismatch detection with warning log
- **`returnStoredSource` compatibility**: Not shown in DiskANN docs examples → Kept as-is (standard MongoDB feature, index-agnostic), added QA verification
- **Pre-filtering vs post-filtering**: DiskANN supports native pre-filtering → Explicitly excluded from scope (behavioral change)
- **Default parameter values**: Using DocumentDB defaults for DiskANN (`maxDegree=32`, `lBuild=50`, `lSearch=40`)
- **Tests don't assert on index payload**: Current tests only check `createIndexes` was called → New tests must assert exact `cosmosSearchOptions` contents

---

## Work Objectives

### Core Objective
Make the vector index type configurable between DiskANN and HNSW in the Azure DocumentDB adapter, defaulting to DiskANN for better scalability.

### Concrete Deliverables
- `VectorIndexType` StrEnum in `src/maas/config.py`
- `vector_index_type` setting in `Settings` class
- Updated `AzureDocumentDB.__init__()` accepting `index_type` parameter
- Updated `_ensure_vector_index()` building correct params per index type
- Updated `search()` using correct search param per index type
- Index-kind mismatch detection in `_ensure_vector_index()`
- Updated `AzureDocumentDBConfig` with `index_type` field
- Updated `build_mem0_config()` passing index type through
- Parameterized unit tests for both index types
- Updated `.env.example`, `AGENTS.md`, `README.md`, `PHASE9_DOCUMENTDB_DESIGN.md`, `CONFIGURATION.md`

### Definition of Done
- [ ] `uv run pytest tests/unit/ -v` → ALL pass, 0 failures, count ≥ 92 (85 existing + 7+ new)
- [ ] `uv run ruff check src/ tests/` → exit code 0
- [ ] `uv run ruff format --check src/ tests/` → exit code 0
- [ ] `VECTOR_INDEX_TYPE=diskann` creates DiskANN index with correct params
- [ ] `VECTOR_INDEX_TYPE=hnsw` creates HNSW index with correct params (backward compatible)
- [ ] Index-kind mismatch logs warning when configured type ≠ existing index type

### Must Have
- `VECTOR_INDEX_TYPE` env var with `diskann` and `hnsw` options
- Default to `diskann`
- Both index types use correct build params and search params
- Index-kind mismatch detection (warning log, not error/crash)
- Backward compatibility — existing HNSW deployments work with `VECTOR_INDEX_TYPE=hnsw`
- `from __future__ import annotations` on all modified files
- All existing tests continue to pass

### Must NOT Have (Guardrails)
- **No pre-filtering conversion** — Keep post-filtering via `$match` stage. Pre-filtering is a separate optimization.
- **No quantization config** — DiskANN `quantizationByteSize` is out of scope
- **No individual param env vars** — `maxDegree`, `lBuild`, `lSearch`, `m`, `efConstruction`, `efSearch` stay as constants, not configurable
- **No IVF index type** — Only `hnsw` and `diskann`
- **No CRUD method changes** — `insert`, `delete`, `update`, `get`, `list` are index-agnostic
- **No auto-migration** — Don't auto-drop and recreate indexes. Detect mismatch, warn, that's it.
- **No integration test changes** — Integration tests use MongoDB 7 container, not DocumentDB
- **No changes to `dependencies.py`** — Registration logic unchanged
- **No import from `maas.config` in `documentdb.py`** — Keep adapter decoupled; pass `index_type` as `str`
- **No `as any` / `@ts-ignore` / empty catch / bare except** — Follow existing strict patterns
- **No excessive comments or docstring bloat** — Match existing comment density

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (pytest + pytest-asyncio)
- **Automated tests**: Tests-after (update existing + add new, post-implementation)
- **Framework**: pytest via `uv run pytest`
- **Pattern**: Parameterize with `@pytest.mark.parametrize` for both index types

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

| Deliverable Type | Verification Tool | Method |
|------------------|-------------------|--------|
| Python source | Bash (uv run ruff) | Lint + format check |
| Config/Settings | Bash (uv run pytest) | Unit tests with assertions |
| DocumentDB adapter | Bash (uv run pytest) | Parameterized tests, mock pymongo |
| Documentation | Bash (grep) | Verify key terms present in docs |

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — config layer + docs research):
├── Task 1: Config layer — VectorIndexType enum + Settings + build_mem0_config [quick]
├── Task 3: Documentation updates (AGENTS.md, .env.example, README, PHASE9, CONFIGURATION) [writing]

Wave 2 (After Task 1 — core adapter changes):
├── Task 2: DocumentDB adapter — dual index support + mismatch detection [deep]

Wave 3 (After Task 2 — tests):
├── Task 4: Unit tests — parameterize existing + add new assertions [unspecified-high]

Wave 4 (After Task 4 — full regression):
├── Task 5: Full regression + lint [quick]

Wave FINAL (After ALL tasks — independent review, 4 parallel):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real manual QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)

Critical Path: Task 1 → Task 2 → Task 4 → Task 5 → F1-F4
Parallel Speedup: ~30% faster (Wave 1 parallelism)
Max Concurrent: 2 (Wave 1)
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|------------|--------|------|
| 1 | — | 2, 4 | 1 |
| 2 | 1 | 4, 5 | 2 |
| 3 | — | F1 | 1 |
| 4 | 1, 2 | 5 | 3 |
| 5 | 2, 4 | F1-F4 | 4 |
| F1-F4 | 5 | — | FINAL |

### Agent Dispatch Summary

| Wave | # Parallel | Tasks → Agent Category |
|------|------------|----------------------|
| 1 | **2** | T1 → `quick`, T3 → `writing` |
| 2 | **1** | T2 → `deep` |
| 3 | **1** | T4 → `unspecified-high` |
| 4 | **1** | T5 → `quick` |
| FINAL | **4** | F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep` |

---

## TODOs

- [x] 1. Config Layer — Add VectorIndexType enum, Settings field, and config plumbing

  **What to do**:
  - Add `VectorIndexType(StrEnum)` to `src/maas/config.py` with values `hnsw = "hnsw"` and `diskann = "diskann"`, following the exact pattern of `VectorStoreProvider` (lines 37-39)
  - Add `vector_index_type: VectorIndexType = VectorIndexType.DISKANN` to the `Settings` class, with `Field(description="Vector index type for DocumentDB: diskann or hnsw")`
  - In `src/maas/ltm/config.py` `build_mem0_config()`, add `"index_type": settings.vector_index_type.value` to the vector store config dict (the dict at the path `config["vector_store"]["config"]`)
  - In `src/maas/vector_stores/documentdb.py`, add `index_type: str = "diskann"` to `AzureDocumentDBConfig` model fields (after `mongo_uri`)
  - Ensure `from __future__ import annotations` is present at top of all modified files

  **Must NOT do**:
  - Do NOT import `VectorIndexType` or anything from `maas.config` in `documentdb.py` — pass as plain `str`
  - Do NOT make individual DiskANN/HNSW params (maxDegree, lBuild, etc.) configurable via env vars
  - Do NOT add `index_type` to `MongoDBConfig` or any non-DocumentDB config

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Small, well-defined changes across 3 files with clear patterns to follow
  - **Skills**: []
    - No special skills needed — standard Python edits
  - **Skills Evaluated but Omitted**:
    - `playwright`: No browser interaction
    - `git-master`: Commit handled separately

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 3)
  - **Parallel Group**: Wave 1 (with Task 3)
  - **Blocks**: Task 2, Task 4
  - **Blocked By**: None (can start immediately)

  **References** (CRITICAL):

  **Pattern References** (existing code to follow):
  - `src/maas/config.py:37-39` — `VectorStoreProvider(StrEnum)` definition pattern. Copy this exact pattern for `VectorIndexType`.
  - `src/maas/config.py:55-120` — `Settings` class fields. Add `vector_index_type` following the same `Field()` pattern used by other settings like `vector_store_provider` (line 80).
  - `src/maas/ltm/config.py:78-86` — `build_mem0_config()` vector store config dict construction. Add `"index_type"` key here alongside `"db_name"`, `"collection_name"`, etc.
  - `src/maas/vector_stores/documentdb.py:383-394` — `AzureDocumentDBConfig(BaseModel)` with its 4 existing fields. Add `index_type: str = "diskann"` following the same `Field()` pattern.

  **API/Type References**:
  - `src/maas/config.py:37-39` — Existing `StrEnum` pattern: `class VectorStoreProvider(StrEnum): mongodb = "mongodb" ...`

  **WHY Each Reference Matters**:
  - `config.py:37-39`: The new enum MUST follow the identical pattern (StrEnum, lowercase values) for consistency with the codebase
  - `config.py:55-120`: Settings field must use the same `Field(description=...)` pattern and be positioned logically near `vector_store_provider`
  - `ltm/config.py:78-86`: This is the ONLY place where Settings values flow into the vector store config — missing this means the adapter never receives the setting
  - `documentdb.py:383-394`: The config model is what mem0's factory uses to instantiate the adapter — adding the field here ensures it's passed to `__init__`

  **Acceptance Criteria**:

  - [ ] `VectorIndexType` enum exists in `config.py` with `hnsw` and `diskann` values
  - [ ] `Settings.vector_index_type` defaults to `VectorIndexType.DISKANN`
  - [ ] `build_mem0_config()` output includes `index_type` in vector store config
  - [ ] `AzureDocumentDBConfig` accepts `index_type` field
  - [ ] `uv run ruff check src/maas/config.py src/maas/ltm/config.py src/maas/vector_stores/documentdb.py` → exit 0
  - [ ] `uv run ruff format --check src/maas/config.py src/maas/ltm/config.py src/maas/vector_stores/documentdb.py` → exit 0

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: VectorIndexType enum validates correctly
    Tool: Bash (uv run python)
    Preconditions: Config changes applied
    Steps:
      1. Run: uv run python -c "from maas.config import VectorIndexType; print(VectorIndexType.DISKANN.value, VectorIndexType.HNSW.value)"
      2. Assert output: "diskann hnsw"
      3. Run: uv run python -c "from maas.config import VectorIndexType; VectorIndexType('invalid')"
      4. Assert: raises ValueError
    Expected Result: Enum works for valid values, raises for invalid
    Failure Indicators: ImportError, wrong values, no ValueError for invalid input
    Evidence: .sisyphus/evidence/task-1-enum-validation.txt

  Scenario: Settings defaults to diskann
    Tool: Bash (uv run python)
    Preconditions: No VECTOR_INDEX_TYPE env var set
    Steps:
      1. Run: uv run python -c "from maas.config import get_settings; s = get_settings(); print(s.vector_index_type.value)"
      2. Assert output contains: "diskann"
    Expected Result: Default is "diskann"
    Failure Indicators: Output is "hnsw" or error
    Evidence: .sisyphus/evidence/task-1-settings-default.txt

  Scenario: build_mem0_config includes index_type
    Tool: Bash (uv run python)
    Preconditions: Config changes applied
    Steps:
      1. Run: uv run python -c "
         from maas.config import Settings
         from maas.ltm.config import build_mem0_config
         s = Settings(llm_api_key='test', llm_model='test', embedding_api_key='test', embedding_model='test', mongodb_uri='mongodb://localhost:10260', redis_url='redis://localhost:6379')
         c = build_mem0_config(s)
         print(c['vector_store']['config'].get('index_type'))
         "
      2. Assert output: "diskann"
    Expected Result: index_type is present in vector store config
    Failure Indicators: KeyError, None, or wrong value
    Evidence: .sisyphus/evidence/task-1-config-plumbing.txt
  ```

  **Evidence to Capture:**
  - [ ] task-1-enum-validation.txt — Enum valid/invalid test output
  - [ ] task-1-settings-default.txt — Settings default value
  - [ ] task-1-config-plumbing.txt — Config dict contents

  **Commit**: YES
  - Message: `feat(config): add VectorIndexType enum and VECTOR_INDEX_TYPE setting`
  - Files: `src/maas/config.py`, `src/maas/ltm/config.py`, `src/maas/vector_stores/documentdb.py`
  - Pre-commit: `uv run ruff check src/maas/config.py src/maas/ltm/config.py src/maas/vector_stores/documentdb.py`

---

- [x] 2. DocumentDB Adapter — Dual index type support + mismatch detection

  **What to do**:
  - In `src/maas/vector_stores/documentdb.py`:
    1. **Replace module-level HNSW constants** (lines 36-38) with two sets of defaults:
       ```python
       # DiskANN defaults (Azure DocumentDB recommended)
       _DEFAULT_DISKANN_MAX_DEGREE = 32
       _DEFAULT_DISKANN_L_BUILD = 50
       _DEFAULT_DISKANN_L_SEARCH = 40
       # HNSW defaults (legacy/fallback)
       _DEFAULT_HNSW_M = 16
       _DEFAULT_HNSW_EF_CONSTRUCTION = 64
       _DEFAULT_HNSW_EF_SEARCH = 40
       ```
    2. **Update class-level `INDEX_KIND`** (line 51): Remove the hardcoded `INDEX_KIND = "vector-hnsw"` class variable. Instead, derive it from `self.index_type` in `__init__`.
    3. **Update `__init__`** to accept `index_type: str = "diskann"` parameter, store as `self.index_type`, and set `self.index_kind` to `f"vector-{self.index_type}"`. Validate that `index_type` is one of `("diskann", "hnsw")`, raising `ValueError` if not.
    4. **Update `_ensure_vector_index()`** (lines 143-177):
       - Build `cosmosSearchOptions` conditionally based on `self.index_type`:
         - For `"diskann"`: use `kind: "vector-diskann"`, `maxDegree`, `lBuild`, `similarity`, `dimensions`
         - For `"hnsw"`: use `kind: "vector-hnsw"`, `m`, `efConstruction`, `similarity`, `dimensions`
       - **Add mismatch detection**: After checking if the index already exists (line 147-150), if the index exists, read its `cosmosSearchOptions.kind` from the existing index definition. If it doesn't match `self.index_kind`, log a WARNING: `f"Existing vector index '{self.index_name}' has kind '{existing_kind}' but configured index type is '{self.index_kind}'. Drop and recreate the index to switch types."`
       - The existing index information is available from the `getIndexes` command response that is already executed at line 147. Extract `kind` from the matching index's `cosmosSearch` options.
    5. **Update `search()`** (lines 215-228):
       - For `"diskann"`: use `"lSearch": _DEFAULT_DISKANN_L_SEARCH` instead of `"efSearch": _DEFAULT_HNSW_EF_SEARCH`
       - For `"hnsw"`: keep `"efSearch": _DEFAULT_HNSW_EF_SEARCH`
       - Keep `"returnStoredSource": True` for both — it's a standard MongoDB aggregation feature, not index-specific
    6. **Keep `SIMILARITY_METRIC = "COS"` unchanged** — both index types use cosine similarity

  **Must NOT do**:
  - Do NOT import anything from `maas.config` — keep adapter self-contained
  - Do NOT change post-filtering (`$match` stage) to pre-filtering
  - Do NOT add quantization configuration
  - Do NOT modify any CRUD methods (`insert`, `delete`, `update`, `get`, `list`)
  - Do NOT auto-drop and recreate indexes on mismatch — only warn
  - Do NOT change the `$project` stage structure
  - Do NOT make build/search params configurable — they are constants

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Core logic changes requiring careful understanding of index creation, search pipeline, and mismatch detection. Multiple interrelated changes within one file that must be consistent.
  - **Skills**: []
    - No special skills needed — standard Python/pymongo changes
  - **Skills Evaluated but Omitted**:
    - `playwright`: No browser interaction
    - `git-master`: Commit handled separately

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2 (sequential after Task 1)
  - **Blocks**: Task 4, Task 5
  - **Blocked By**: Task 1

  **References** (CRITICAL):

  **Pattern References** (existing code to follow):
  - `src/maas/vector_stores/documentdb.py:36-38` — Current HNSW constants to replace/extend. Keep HNSW constants and add DiskANN constants alongside.
  - `src/maas/vector_stores/documentdb.py:49-51` — Current class variables including `INDEX_KIND = "vector-hnsw"`. Remove `INDEX_KIND` class var, derive from `self.index_type` in `__init__`.
  - `src/maas/vector_stores/documentdb.py:53-93` — Current `__init__` method. Add `index_type: str = "diskann"` parameter after existing params. Store `self.index_type` and `self.index_kind`.
  - `src/maas/vector_stores/documentdb.py:143-177` — Current `_ensure_vector_index()` with HNSW-only index creation. This is the PRIMARY change target — conditionally build `cosmosSearchOptions` dict.
  - `src/maas/vector_stores/documentdb.py:147-150` — Existing index existence check via `getIndexes` command. Extract `kind` from response for mismatch detection.
  - `src/maas/vector_stores/documentdb.py:155-165` — Current HNSW `index_def` construction. Replace with conditional construction.
  - `src/maas/vector_stores/documentdb.py:215-228` — Current search pipeline with `efSearch`. Replace search param conditionally.

  **External References** (DiskANN syntax from Microsoft docs):
  - Index creation `cosmosSearchOptions`: `{"kind": "vector-diskann", "dimensions": <int>, "similarity": "COS", "maxDegree": 32, "lBuild": 50}`
  - Search `cosmosSearch`: `{"vector": [...], "path": "embedding", "k": <int>, "lSearch": 40}` (lSearch is optional, defaults to 40)
  - HNSW index creation: `{"kind": "vector-hnsw", "dimensions": <int>, "similarity": "COS", "m": 16, "efConstruction": 64}`
  - HNSW search: `{"vector": [...], "path": "embedding", "k": <int>, "efSearch": 40}`

  **WHY Each Reference Matters**:
  - Lines 36-38: These constants are used in `_ensure_vector_index()` and `search()` — must add DiskANN equivalents
  - Lines 49-51: `INDEX_KIND` class var is used in `_ensure_vector_index()` — must become instance-level
  - Lines 53-93: Constructor signature is called by mem0's factory via `AzureDocumentDBConfig` fields — new param must match config field name
  - Lines 143-177: This is the core index creation logic — the main change target
  - Lines 215-228: This is the search pipeline — must use correct search param per index type

  **Acceptance Criteria**:

  - [ ] `AzureDocumentDB(index_type="diskann", ...)` creates instance with `self.index_kind == "vector-diskann"`
  - [ ] `AzureDocumentDB(index_type="hnsw", ...)` creates instance with `self.index_kind == "vector-hnsw"`
  - [ ] `AzureDocumentDB(index_type="invalid", ...)` raises `ValueError`
  - [ ] Default `AzureDocumentDB(...)` (no `index_type`) uses DiskANN
  - [ ] `_ensure_vector_index()` for DiskANN calls `createIndexes` with `maxDegree`, `lBuild`, NOT `m`, `efConstruction`
  - [ ] `_ensure_vector_index()` for HNSW calls `createIndexes` with `m`, `efConstruction`, NOT `maxDegree`, `lBuild`
  - [ ] Index mismatch logs WARNING when existing index kind ≠ configured kind
  - [ ] `search()` for DiskANN uses `lSearch` in pipeline, NOT `efSearch`
  - [ ] `search()` for HNSW uses `efSearch` in pipeline, NOT `lSearch`
  - [ ] `uv run ruff check src/maas/vector_stores/documentdb.py` → exit 0
  - [ ] `uv run ruff format --check src/maas/vector_stores/documentdb.py` → exit 0
  - [ ] No imports from `maas.config` in `documentdb.py`

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: DiskANN index creation uses correct params
    Tool: Bash (uv run pytest)
    Preconditions: Task 1 config changes applied, Task 2 adapter changes applied
    Steps:
      1. Run: uv run pytest tests/unit/test_documentdb.py -v -k "diskann and index" --tb=short 2>&1
      2. Verify test passes and asserts `cosmosSearchOptions` contains:
         - "kind": "vector-diskann"
         - "maxDegree": 32
         - "lBuild": 50
         - "similarity": "COS"
      3. Verify `cosmosSearchOptions` does NOT contain "m" or "efConstruction"
    Expected Result: Test PASSED
    Failure Indicators: Test FAILED, AssertionError, KeyError
    Evidence: .sisyphus/evidence/task-2-diskann-index-creation.txt

  Scenario: HNSW index creation preserved (backward compat)
    Tool: Bash (uv run pytest)
    Preconditions: Adapter changes applied
    Steps:
      1. Run: uv run pytest tests/unit/test_documentdb.py -v -k "hnsw and index" --tb=short 2>&1
      2. Verify test passes and asserts `cosmosSearchOptions` contains:
         - "kind": "vector-hnsw"
         - "m": 16
         - "efConstruction": 64
      3. Verify `cosmosSearchOptions` does NOT contain "maxDegree" or "lBuild"
    Expected Result: Test PASSED
    Failure Indicators: Test FAILED
    Evidence: .sisyphus/evidence/task-2-hnsw-backward-compat.txt

  Scenario: Index mismatch detection logs warning
    Tool: Bash (uv run pytest)
    Preconditions: Adapter changes applied
    Steps:
      1. Run: uv run pytest tests/unit/test_documentdb.py -v -k "mismatch" --tb=short 2>&1
      2. Verify test creates adapter with index_type="diskann" but mocks getIndexes to return existing "vector-hnsw" index
      3. Verify WARNING log message is emitted containing "Drop and recreate"
    Expected Result: Test PASSED, warning logged
    Failure Indicators: No warning logged, test FAILED
    Evidence: .sisyphus/evidence/task-2-mismatch-detection.txt

  Scenario: DiskANN search uses lSearch param
    Tool: Bash (uv run pytest)
    Preconditions: Adapter changes applied
    Steps:
      1. Run: uv run pytest tests/unit/test_documentdb.py -v -k "diskann and search" --tb=short 2>&1
      2. Verify test asserts search pipeline `cosmosSearch` dict contains "lSearch": 40
      3. Verify `cosmosSearch` dict does NOT contain "efSearch"
    Expected Result: Test PASSED
    Failure Indicators: Test FAILED, wrong param key
    Evidence: .sisyphus/evidence/task-2-diskann-search-param.txt

  Scenario: Invalid index_type raises ValueError
    Tool: Bash (uv run python)
    Preconditions: Adapter changes applied
    Steps:
      1. Run: uv run python -c "
         from maas.vector_stores.documentdb import AzureDocumentDB
         try:
             AzureDocumentDB(db_name='test', collection_name='test', embedding_model_dims=1536, mongo_uri='mongodb://localhost:10260', index_type='ivf')
         except ValueError as e:
             print(f'PASS: {e}')
         else:
             print('FAIL: No ValueError raised')
         "
      2. Assert output starts with "PASS:"
    Expected Result: ValueError raised with descriptive message
    Failure Indicators: Output starts with "FAIL:" or other error
    Evidence: .sisyphus/evidence/task-2-invalid-index-type.txt

  Scenario: No maas.config imports in documentdb.py
    Tool: Bash (grep)
    Preconditions: All adapter changes applied
    Steps:
      1. Run: grep -n "from maas.config" src/maas/vector_stores/documentdb.py || echo "PASS: No maas.config imports"
      2. Run: grep -n "import maas.config" src/maas/vector_stores/documentdb.py || echo "PASS: No maas.config imports"
      3. Assert both outputs contain "PASS"
    Expected Result: No imports from maas.config
    Failure Indicators: grep finds matches
    Evidence: .sisyphus/evidence/task-2-no-config-imports.txt
  ```

  **Evidence to Capture:**
  - [ ] task-2-diskann-index-creation.txt
  - [ ] task-2-hnsw-backward-compat.txt
  - [ ] task-2-mismatch-detection.txt
  - [ ] task-2-diskann-search-param.txt
  - [ ] task-2-invalid-index-type.txt
  - [ ] task-2-no-config-imports.txt

  **Commit**: YES
  - Message: `feat(documentdb): add configurable DiskANN/HNSW vector index support`
  - Files: `src/maas/vector_stores/documentdb.py`
  - Pre-commit: `uv run ruff check src/maas/vector_stores/documentdb.py && uv run ruff format --check src/maas/vector_stores/documentdb.py`

---

- [x] 3. Documentation Updates

  **What to do**:
  - Update `AGENTS.md`:
    - Add `VECTOR_INDEX_TYPE` to the "Environment Variables" table with purpose "Vector index type for DocumentDB: diskann (default) or hnsw"
    - Add to "Known Gotchas" section: "**Switching `VECTOR_INDEX_TYPE`** on existing deployment requires dropping and recreating the vector index — the adapter logs a warning if mismatch detected"
    - Update "Architecture Overview" or "Quick Facts" if HNSW is mentioned specifically
  - Update `.env.example`:
    - Add `VECTOR_INDEX_TYPE=diskann` with comment `# Vector index type: diskann (default, scales to 500K+) or hnsw (legacy, up to 50K)`
  - Update `README.md`:
    - Add `VECTOR_INDEX_TYPE` to any environment variable table in the LTM/DocumentDB section
  - Update `ai_docs/PHASE9_DOCUMENTDB_DESIGN.md`:
    - Add DiskANN parameters table alongside existing HNSW table
    - Add note about configurable index type
    - Update any HNSW-specific language to acknowledge both types
  - Update `ai_docs/CONFIGURATION.md`:
    - Add `VECTOR_INDEX_TYPE` documentation
    - Document the index type switching warning behavior

  **Must NOT do**:
  - Do NOT create new documentation files — only update existing ones
  - Do NOT add excessive documentation — keep changes proportional to code changes
  - Do NOT change any code in documentation task

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: Pure documentation updates across 5 files — writing-focused task
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `playwright`: No browser interaction
    - `git-master`: Commit handled separately

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 1)
  - **Parallel Group**: Wave 1 (with Task 1)
  - **Blocks**: F1 (plan compliance audit)
  - **Blocked By**: None (can start immediately — docs describe the design, not the code)

  **References** (CRITICAL):

  **Pattern References**:
  - `AGENTS.md` — "Environment Variables" table around line with `VECTOR_STORE_PROVIDER`. Add `VECTOR_INDEX_TYPE` in same format.
  - `AGENTS.md` — "Known Gotchas" section. Add new bullet following existing format.
  - `.env.example` — Look for existing vector/DocumentDB vars. Add new var nearby.
  - `ai_docs/PHASE9_DOCUMENTDB_DESIGN.md` — Find HNSW params table (lines ~155-164). Add DiskANN equivalent table.
  - `ai_docs/CONFIGURATION.md` — Find vector store configuration section. Add index type documentation.

  **External References**:
  - DiskANN params: `maxDegree` (20-2048, default 32), `lBuild` (10-500, default 50), `lSearch` (10-1000, default 40)
  - HNSW params: `m` (2-100, default 16), `efConstruction` (4-1000, default 64), `efSearch` (default 40)
  - DiskANN scales to 500K+ vectors; HNSW up to 50K

  **WHY Each Reference Matters**:
  - `AGENTS.md` env var table: This is the primary reference for all env vars — missing it means users won't know the setting exists
  - `.env.example`: Template for new deployments — must include all configurable vars
  - `PHASE9_DOCUMENTDB_DESIGN.md`: Design doc should reflect the actual implementation including both index types

  **Acceptance Criteria**:

  - [ ] `AGENTS.md` contains `VECTOR_INDEX_TYPE` in env vars table
  - [ ] `AGENTS.md` "Known Gotchas" mentions index type switching warning
  - [ ] `.env.example` contains `VECTOR_INDEX_TYPE=diskann` with comment
  - [ ] `README.md` mentions `VECTOR_INDEX_TYPE`
  - [ ] `PHASE9_DOCUMENTDB_DESIGN.md` documents both DiskANN and HNSW params
  - [ ] `CONFIGURATION.md` documents `VECTOR_INDEX_TYPE`

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: AGENTS.md contains VECTOR_INDEX_TYPE
    Tool: Bash (grep)
    Preconditions: Documentation updates applied
    Steps:
      1. Run: grep -c "VECTOR_INDEX_TYPE" AGENTS.md
      2. Assert count >= 2 (env table + gotchas)
    Expected Result: At least 2 mentions
    Failure Indicators: Count is 0 or 1
    Evidence: .sisyphus/evidence/task-3-agents-md.txt

  Scenario: .env.example has new variable
    Tool: Bash (grep)
    Preconditions: Documentation updates applied
    Steps:
      1. Run: grep "VECTOR_INDEX_TYPE" .env.example
      2. Assert output contains "diskann"
    Expected Result: Variable present with diskann value
    Failure Indicators: grep returns no results
    Evidence: .sisyphus/evidence/task-3-env-example.txt

  Scenario: PHASE9 design doc has DiskANN params
    Tool: Bash (grep)
    Preconditions: Documentation updates applied
    Steps:
      1. Run: grep -c "diskann\|DiskANN\|maxDegree\|lBuild" ai_docs/PHASE9_DOCUMENTDB_DESIGN.md
      2. Assert count >= 4
    Expected Result: DiskANN terminology present in design doc
    Failure Indicators: Count < 4
    Evidence: .sisyphus/evidence/task-3-phase9-doc.txt
  ```

  **Evidence to Capture:**
  - [ ] task-3-agents-md.txt
  - [ ] task-3-env-example.txt
  - [ ] task-3-phase9-doc.txt

  **Commit**: YES
  - Message: `docs: add DiskANN vector index configuration documentation`
  - Files: `AGENTS.md`, `.env.example`, `README.md`, `ai_docs/PHASE9_DOCUMENTDB_DESIGN.md`, `ai_docs/CONFIGURATION.md`
  - Pre-commit: none (docs only)

---

- [x] 4. Unit Tests — Parameterize for both index types + new assertions

  **What to do**:
  - In `tests/unit/test_documentdb.py`:
    1. **Update existing test fixtures**: The `store` fixture (and any fixture creating `AzureDocumentDB` instances) should be parameterized or have variants for both index types. Consider creating `diskann_store` and `hnsw_store` fixtures, or parameterizing with `@pytest.fixture(params=["diskann", "hnsw"])`.
    2. **Add index creation payload assertion tests** (NEW — currently missing):
       - `test_ensure_vector_index_diskann_params`: Assert `createIndexes` command is called with `cosmosSearchOptions` containing `kind: "vector-diskann"`, `maxDegree: 32`, `lBuild: 50`, `similarity: "COS"`, `dimensions: <expected>`. Assert NO `m` or `efConstruction` keys.
       - `test_ensure_vector_index_hnsw_params`: Same pattern but with `kind: "vector-hnsw"`, `m: 16`, `efConstruction: 64`. Assert NO `maxDegree` or `lBuild` keys.
    3. **Add search param assertion tests** (NEW):
       - `test_search_diskann_uses_l_search`: Mock the aggregate pipeline, assert `cosmosSearch` dict contains `"lSearch": 40` and NOT `"efSearch"`.
       - `test_search_hnsw_uses_ef_search`: Assert `cosmosSearch` dict contains `"efSearch": 40` and NOT `"lSearch"`.
    4. **Add mismatch detection test** (NEW):
       - `test_index_mismatch_logs_warning`: Create store with `index_type="diskann"`, mock `getIndexes` to return an index with `kind: "vector-hnsw"`. Assert `logger.warning` is called with message containing "Drop and recreate".
    5. **Add invalid index type test** (NEW):
       - `test_invalid_index_type_raises_value_error`: Assert `AzureDocumentDB(index_type="ivf", ...)` raises `ValueError`.
    6. **Add default index type test** (NEW):
       - `test_default_index_type_is_diskann`: Create `AzureDocumentDB(...)` without `index_type` param, assert `self.index_type == "diskann"`.
    7. **Update existing tests**: Ensure all existing tests that create `AzureDocumentDB` instances still work — they should use default `index_type="diskann"` or explicitly pass `index_type="hnsw"` for backward-compatibility tests.
  - In `tests/unit/test_ltm_service.py`:
    8. **Add config flow test**: Assert `build_mem0_config(settings)["vector_store"]["config"]["index_type"]` equals `settings.vector_index_type.value`.

  **Must NOT do**:
  - Do NOT modify integration tests (`tests/integration/`)
  - Do NOT require Docker services for any test
  - Do NOT test against real DocumentDB
  - Do NOT create separate test files — all DocumentDB tests go in `test_documentdb.py`
  - Do NOT break existing test patterns — follow `@pytest.mark.asyncio`, `unittest.mock.patch`, `MagicMock` patterns already used

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Multiple test cases across two files, requires understanding mock setup, pytest parametrize, and the adapter internals
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `playwright`: No browser testing

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 (after Tasks 1 and 2)
  - **Blocks**: Task 5
  - **Blocked By**: Task 1, Task 2

  **References** (CRITICAL):

  **Pattern References**:
  - `tests/unit/test_documentdb.py:1-30` — Imports and test setup. Follow existing import pattern.
  - `tests/unit/test_documentdb.py:32-60` — Existing fixtures (`store`, `mock_client`, etc.). Create new fixtures or parameterize existing ones for index type.
  - `tests/unit/test_documentdb.py:60-62` — Current index creation test. This is the test that only checks `createIndexes` was called — enhance it to check payload.
  - `tests/unit/test_documentdb.py` — Search tests (find existing search tests for pipeline assertion patterns).
  - `tests/unit/test_ltm_service.py:126-146` — `test_build_mem0_config` — add `index_type` assertion here.

  **Test References**:
  - `tests/unit/test_documentdb.py` — All existing test patterns: how `AzureDocumentDB` is instantiated with mocks, how `command()` calls are asserted, how search pipeline is tested.

  **WHY Each Reference Matters**:
  - Lines 32-60: Fixtures define how the store is created with mocks — must understand this to add index_type param correctly
  - Lines 60-62: The current "test" for index creation is too weak — this is what needs strengthening
  - `test_ltm_service.py:126-146`: This tests config flow — must verify index_type propagates

  **Acceptance Criteria**:

  - [ ] `uv run pytest tests/unit/test_documentdb.py -v --tb=short` → ALL pass
  - [ ] New tests exist for: DiskANN index params, HNSW index params, DiskANN search param, HNSW search param, mismatch detection, invalid index type, default index type
  - [ ] At least 7 NEW test functions added
  - [ ] `uv run pytest tests/unit/test_ltm_service.py -v --tb=short` → ALL pass (including new config flow test)
  - [ ] `uv run ruff check tests/unit/test_documentdb.py tests/unit/test_ltm_service.py` → exit 0
  - [ ] `uv run ruff format --check tests/unit/test_documentdb.py tests/unit/test_ltm_service.py` → exit 0

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: All DocumentDB tests pass
    Tool: Bash (uv run pytest)
    Preconditions: Tasks 1-2 applied, test changes applied
    Steps:
      1. Run: uv run pytest tests/unit/test_documentdb.py -v --tb=short 2>&1
      2. Count PASSED vs FAILED in output
      3. Assert 0 FAILED, 0 ERROR
      4. Assert total >= existing count + 7 new tests
    Expected Result: All tests pass
    Failure Indicators: Any FAILED or ERROR
    Evidence: .sisyphus/evidence/task-4-documentdb-tests.txt

  Scenario: LTM service config test passes
    Tool: Bash (uv run pytest)
    Preconditions: Tasks 1-2 applied, test changes applied
    Steps:
      1. Run: uv run pytest tests/unit/test_ltm_service.py -v -k "build_mem0_config" --tb=short 2>&1
      2. Assert PASSED
    Expected Result: Config flow test passes
    Failure Indicators: FAILED or ERROR
    Evidence: .sisyphus/evidence/task-4-ltm-config-test.txt

  Scenario: Parametrized tests cover both index types
    Tool: Bash (uv run pytest)
    Preconditions: Test changes applied
    Steps:
      1. Run: uv run pytest tests/unit/test_documentdb.py -v --tb=short 2>&1 | grep -E "diskann|hnsw"
      2. Assert output contains tests for BOTH "diskann" AND "hnsw"
    Expected Result: Both index types appear in test names/output
    Failure Indicators: Only one index type tested
    Evidence: .sisyphus/evidence/task-4-parametrized-coverage.txt
  ```

  **Evidence to Capture:**
  - [ ] task-4-documentdb-tests.txt — Full test output
  - [ ] task-4-ltm-config-test.txt — Config flow test output
  - [ ] task-4-parametrized-coverage.txt — Both index types in test names

  **Commit**: YES
  - Message: `test(documentdb): add parameterized tests for DiskANN and HNSW index types`
  - Files: `tests/unit/test_documentdb.py`, `tests/unit/test_ltm_service.py`
  - Pre-commit: `uv run pytest tests/unit/test_documentdb.py tests/unit/test_ltm_service.py -v --tb=short`

---

- [x] 5. Full Regression + Lint Check

  **What to do**:
  - Run the complete unit test suite to ensure no regressions
  - Run full ruff lint check on all source and test files
  - Run full ruff format check
  - Fix any failures found

  **Must NOT do**:
  - Do NOT run integration tests (require Docker)
  - Do NOT modify code unless fixing a regression

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple verification task — run commands, report results, fix if needed
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 4 (after all implementation)
  - **Blocks**: F1-F4
  - **Blocked By**: Task 2, Task 4

  **References**:
  - `AGENTS.md` — Testing section: `uv run pytest tests/unit/ -v`, `uv run ruff check src/ tests/`, `uv run ruff format --check src/ tests/`

  **Acceptance Criteria**:

  - [ ] `uv run pytest tests/unit/ -v --tb=short` → ALL pass, 0 failures, count ≥ 92
  - [ ] `uv run ruff check src/ tests/` → exit 0
  - [ ] `uv run ruff format --check src/ tests/` → exit 0

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Full unit test suite passes
    Tool: Bash (uv run pytest)
    Preconditions: All implementation tasks complete
    Steps:
      1. Run: uv run pytest tests/unit/ -v --tb=short 2>&1
      2. Parse last line for "X passed"
      3. Assert 0 failed, 0 errors
      4. Assert X >= 92
    Expected Result: All tests pass, count >= 92
    Failure Indicators: Any failures, count < 92
    Evidence: .sisyphus/evidence/task-5-full-regression.txt

  Scenario: Lint passes
    Tool: Bash (uv run ruff)
    Preconditions: All implementation tasks complete
    Steps:
      1. Run: uv run ruff check src/ tests/ 2>&1
      2. Assert exit code 0
      3. Run: uv run ruff format --check src/ tests/ 2>&1
      4. Assert exit code 0
    Expected Result: Zero lint/format issues
    Failure Indicators: Non-zero exit code, any warnings
    Evidence: .sisyphus/evidence/task-5-lint-format.txt
  ```

  **Evidence to Capture:**
  - [ ] task-5-full-regression.txt — Full pytest output
  - [ ] task-5-lint-format.txt — Ruff check + format output

  **Commit**: NO (only fix commits if regressions found)

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Rejection → fix → re-run.

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run `uv run ruff check src/ tests/` + `uv run ruff format --check src/ tests/` + `uv run pytest tests/unit/ -v`. Review all changed files for: empty catches, `logger.exception()` usage, `from __future__ import annotations` on every file, `TYPE_CHECKING` blocks for type-only imports, consistent `StrEnum` pattern. Check AI slop: excessive comments, over-abstraction, generic variable names.
  Output: `Lint [PASS/FAIL] | Format [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high`
  Start from clean state. Execute EVERY QA scenario from EVERY task — follow exact steps, capture evidence. Test cross-task integration: config setting flows through build_mem0_config to adapter. Test edge cases: invalid index type, mismatch detection. Save to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff (git log/diff). Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT do" compliance: no pre-filtering, no quantization, no individual param env vars, no CRUD changes, no maas.config import in documentdb.py. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

| After Task | Message | Files | Verification |
|------------|---------|-------|--------------|
| 1 | `feat(config): add VectorIndexType enum and VECTOR_INDEX_TYPE setting` | config.py, ltm/config.py, documentdb.py | ruff check |
| 2 | `feat(documentdb): add configurable DiskANN/HNSW vector index support` | documentdb.py | ruff check + format |
| 3 | `docs: add DiskANN vector index configuration documentation` | AGENTS.md, .env.example, README.md, PHASE9, CONFIGURATION.md | — |
| 4 | `test(documentdb): add parameterized tests for DiskANN and HNSW index types` | test_documentdb.py, test_ltm_service.py | pytest |
| 5 | (fix commits only if needed) | — | full regression |

---

## Success Criteria

### Verification Commands
```bash
uv run pytest tests/unit/ -v --tb=short  # Expected: ≥92 passed, 0 failed
uv run ruff check src/ tests/            # Expected: exit 0
uv run ruff format --check src/ tests/   # Expected: exit 0
```

### Final Checklist
- [ ] All "Must Have" present (configurable index type, DiskANN default, HNSW fallback, mismatch warning, tests, docs)
- [ ] All "Must NOT Have" absent (no pre-filtering, no quantization, no individual param env vars, no CRUD changes, no maas.config import in documentdb.py)
- [ ] All tests pass (≥92 unit tests)
- [ ] Lint clean (ruff check + format)
- [ ] Evidence files captured for all QA scenarios
