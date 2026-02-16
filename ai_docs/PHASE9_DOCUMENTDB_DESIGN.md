# Phase 9 — Azure DocumentDB Vector Store Adapter

## Design Document

### Problem

mem0's built-in MongoDB vector store (`mem0.vector_stores.mongodb.MongoDB`) uses Atlas-specific APIs:
- `SearchIndexModel` + `collection.create_search_index()` for index creation
- `$vectorSearch` aggregation stage for similarity search
- `$meta: "vectorSearchScore"` for scoring

Azure Cosmos DB for MongoDB (DocumentDB) is wire-protocol compatible with MongoDB but uses a **different vector search API**:
- `db.command("createIndexes", ...)` with `cosmosSearch` key type
- `$search` with `cosmosSearch` operator
- `$meta: "searchScore"` for scoring

Standard CRUD operations (insert, find, update, delete) work identically.

### Solution

Create a custom `VectorStoreBase` subclass (`AzureDocumentDB`) that implements all 11 abstract methods using DocumentDB-compatible APIs. Register it with mem0's `VectorStoreFactory` so it can be selected via configuration.

### Approach Selected

**Option A: Full custom `VectorStoreBase` subclass** (user-approved)

Alternatives considered:
- **Option B: Monkey-patch Atlas adapter** — Fragile, breaks on mem0 updates
- **Option C: Fork mem0 MongoDB adapter** — Maintenance burden, version drift

### Implementation

#### Class Hierarchy

```
mem0.vector_stores.base.VectorStoreBase (ABC)
├── mem0.vector_stores.mongodb.MongoDB        # Atlas — built-in
└── maas.vector_stores.documentdb.AzureDocumentDB  # DocumentDB — custom
```

#### Abstract Methods Implemented

| Method | Atlas Approach | DocumentDB Approach |
|---|---|---|
| `create_col()` | `SearchIndexModel` + `create_search_index()` | Insert/delete placeholder + `db.command("createIndexes")` with `cosmosSearch` |
| `insert()` | `insert_many()` | `insert_many()` (identical) |
| `search()` | `$vectorSearch` pipeline | `$search` + `cosmosSearch` + `$meta: "searchScore"` |
| `delete()` | `delete_one()` | `delete_one()` (identical) |
| `update()` | `update_one()` | `update_one()` (identical) |
| `get()` | `find_one()` | `find_one()` (identical) |
| `list()` | `find()` with payload filters | `find()` with payload filters (identical) |
| `list_cols()` | `list_collection_names()` | `list_collection_names()` (identical) |
| `delete_col()` | `drop()` | `drop()` (identical) |
| `col_info()` | `collstats` command | `collstats` command (identical) |
| `reset()` | drop + recreate | drop + recreate (identical) |

#### Index Creation

```python
def _ensure_vector_index(self, database):
    # Check if index already exists
    result = database.command("listIndexes", self.collection_name)
    existing = [idx["name"] for idx in result["cursor"]["firstBatch"]]

    if self.index_name in existing:
        return  # Already created

    # Create HNSW cosmosSearch index
    index_def = {
        "name": f"{collection_name}_vector_index",
        "key": {"embedding": "cosmosSearch"},
        "cosmosSearchOptions": {
            "kind": "vector-hnsw",
            "m": 16,
            "efConstruction": 64,
            "similarity": "COS",
            "dimensions": embedding_model_dims,
        },
    }
    database.command("createIndexes", collection_name, indexes=[index_def])
```

#### Vector Search Pipeline

```python
pipeline = [
    {
        "$search": {
            "cosmosSearch": {
                "vector": query_vector,
                "path": "embedding",
                "k": limit,
                "efSearch": 40,
            },
            "returnStoredSource": True,
        },
    },
    {"$project": {"score": {"$meta": "searchScore"}, "document": "$$ROOT"}},
]

# Optional post-filter on payload fields
if filters:
    conditions = [{"document.payload." + key: value} for key, value in filters.items()]
    pipeline.append({"$match": {"$and": conditions}})
```

#### Factory Registration

```python
def register_documentdb_vector_store():
    from mem0.utils.factory import VectorStoreFactory
    VectorStoreFactory.provider_to_class["azure_documentdb"] = \
        "maas.vector_stores.documentdb.AzureDocumentDB"
```

Called during application startup in `LifespanResources.startup()`.

#### Configuration Integration

New enum value in `config.py`:
```python
class VectorStoreProvider(StrEnum):
    MONGODB = "mongodb"
    AZURE_DOCUMENTDB = "azure_documentdb"
```

`build_mem0_config()` passes `settings.vector_store_provider` as the provider name:
```python
"vector_store": {
    "provider": settings.vector_store_provider,  # "mongodb" or "azure_documentdb"
    "config": {
        "mongo_uri": settings.mongodb_uri,
        "db_name": settings.mongodb_db_name,
        "collection_name": settings.mongodb_collection_name,
        "embedding_model_dims": settings.embedding_dims,
    },
}
```

### Document Structure

Both providers use the same document structure:
```json
{
  "_id": "vector-uuid",
  "embedding": [0.1, 0.2, ...],
  "payload": {
    "category": "semantic",
    "data": "...",
    "user_id": "user-42"
  }
}
```

### HNSW Index Parameters

| Parameter | Value | Description |
|---|---|---|
| `kind` | `vector-hnsw` | HNSW graph index (recommended for DocumentDB) |
| `m` | 16 | Max bi-directional links per layer |
| `efConstruction` | 64 | Size of dynamic candidate list during construction |
| `efSearch` | 40 | Size of dynamic candidate list during search |
| `similarity` | `COS` | Cosine similarity metric |
| `dimensions` | From `EMBEDDING_DIMS` | Must match embedding model output |

### DiskANN Index Parameters

| Parameter | DiskANN Default | Range | Description |
|-----------|----------------|-------|-------------|
| `maxDegree` | 32 | 20-2048 | Graph degree |
| `lBuild` | 50 | 10-500 | Build quality |
| `lSearch` | 40 | 10-1000 | Search quality |

### Test Coverage

20 unit tests across 5 test classes:

| Test Class | Tests | Coverage |
|---|---|---|
| `TestAzureDocumentDBInit` | 3 | Constructor, collection creation, index creation/skipping |
| `TestAzureDocumentDBCRUD` | 8 | Insert, delete, update, get, list (with/without filters) |
| `TestAzureDocumentDBSearch` | 4 | Search output, pipeline structure, filters, error handling |
| `TestAzureDocumentDBCollections` | 3 | list_cols, delete_col, col_info |
| `TestAzureDocumentDBReset` | 1 | Drop and recreate |
| `test_register_documentdb_vector_store` | 1 | Factory registration |

### Files Changed in Phase 9

| File | Change |
|---|---|
| `src/maas/vector_stores/__init__.py` | **New** — Package init |
| `src/maas/vector_stores/documentdb.py` | **New** — Full adapter (347 lines) |
| `src/maas/config.py` | **Modified** — Added `VectorStoreProvider` enum + `vector_store_provider` setting |
| `src/maas/dependencies.py` | **Modified** — Added `register_documentdb_vector_store()` call |
| `src/maas/ltm/config.py` | **Modified** — Dynamic `vector_store_provider` in mem0 config |
| `.env.example` | **Modified** — Added `VECTOR_STORE_PROVIDER` variable |
| `tests/unit/test_documentdb.py` | **New** — 20 tests (334 lines) |
| `tests/unit/test_ltm_service.py` | **Modified** — Added `test_build_mem0_config_azure_documentdb_provider` |
