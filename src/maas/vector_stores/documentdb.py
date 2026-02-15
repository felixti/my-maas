"""Azure DocumentDB (MongoDB-compatible) vector store adapter for mem0.

Replaces Atlas-specific ``$vectorSearch`` / ``SearchIndexModel`` APIs
with the ``cosmosSearch`` syntax supported by Azure Cosmos DB for MongoDB
(vCore).
"""

from __future__ import annotations

import logging
from typing import Any

from mem0.vector_stores.base import VectorStoreBase
from pydantic import BaseModel
from pymongo import MongoClient
from pymongo.errors import PyMongoError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared output model - identical to mem0's ``OutputData`` so the rest of the
# framework can consume results without conversion.
# ---------------------------------------------------------------------------


class OutputData(BaseModel):
    id: str | None
    score: float | None
    payload: dict | None


# ---------------------------------------------------------------------------
# DocumentDB vector store
# ---------------------------------------------------------------------------

_DEFAULT_HNSW_M = 16
_DEFAULT_HNSW_EF_CONSTRUCTION = 64
_DEFAULT_HNSW_EF_SEARCH = 40


class AzureDocumentDB(VectorStoreBase):
    """mem0-compatible vector store backed by Azure Cosmos DB for MongoDB.

    Uses the ``cosmosSearch`` aggregation operator for vector similarity
    search and ``db.command("createIndexes", …)`` for HNSW index creation.
    All standard CRUD operations use plain pymongo calls which are fully
    compatible with the MongoDB wire protocol exposed by DocumentDB.
    """

    SIMILARITY_METRIC = "COS"
    INDEX_KIND = "vector-hnsw"

    def __init__(
        self,
        db_name: str,
        collection_name: str,
        embedding_model_dims: int,
        mongo_uri: str,
    ) -> None:
        self.db_name = db_name
        self.collection_name = collection_name
        self.embedding_model_dims = embedding_model_dims

        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.collection = self.create_col()

    # ------------------------------------------------------------------
    # Collection / index management
    # ------------------------------------------------------------------

    def create_col(self) -> Any:
        """Create the collection and ensure the HNSW vector index exists."""
        try:
            database = self.client[self.db_name]
            collection_names = database.list_collection_names()

            if self.collection_name not in collection_names:
                logger.info("Collection '%s' does not exist. Creating it now.", self.collection_name)
                collection = database[self.collection_name]
                # Insert + remove placeholder to materialise the collection.
                collection.insert_one({"_id": 0, "placeholder": True})
                collection.delete_one({"_id": 0})
                logger.info("Collection '%s' created.", self.collection_name)
            else:
                collection = database[self.collection_name]

            self.index_name = f"{self.collection_name}_vector_index"
            self._ensure_vector_index(database)
            return collection

        except PyMongoError:
            logger.exception("Error creating collection / vector index")
            return None

    def _ensure_vector_index(self, database: Any) -> None:
        """Create the HNSW cosmosSearch index if it doesn't already exist."""
        try:
            result = database.command("listIndexes", self.collection_name)
            existing = [idx["name"] for idx in result["cursor"]["firstBatch"]]
        except PyMongoError:
            # Collection may have just been created; no indexes yet.
            existing = []

        if self.index_name in existing:
            logger.info(
                "Vector index '%s' already exists on '%s'.",
                self.index_name,
                self.collection_name,
            )
            return

        index_def = {
            "name": self.index_name,
            "key": {"embedding": "cosmosSearch"},
            "cosmosSearchOptions": {
                "kind": self.INDEX_KIND,
                "m": _DEFAULT_HNSW_M,
                "efConstruction": _DEFAULT_HNSW_EF_CONSTRUCTION,
                "similarity": self.SIMILARITY_METRIC,
                "dimensions": self.embedding_model_dims,
            },
        }
        database.command(
            "createIndexes",
            self.collection_name,
            indexes=[index_def],
        )
        logger.info(
            "Vector index '%s' created on '%s'.",
            self.index_name,
            self.collection_name,
        )

    # ------------------------------------------------------------------
    # Insert
    # ------------------------------------------------------------------

    def insert(
        self,
        vectors: list[list[float]],
        payloads: list[dict] | None = None,
        ids: list[str] | None = None,
    ) -> None:
        """Insert vectors with optional payloads and IDs."""
        logger.info("Inserting %d vectors into '%s'.", len(vectors), self.collection_name)

        safe_payloads = payloads or [{}] * len(vectors)
        safe_ids = ids or [None] * len(vectors)  # type: ignore[list-item]

        data = [
            {"_id": _id, "embedding": vector, "payload": payload}
            for vector, payload, _id in zip(vectors, safe_payloads, safe_ids, strict=True)
        ]
        try:
            self.collection.insert_many(data)
            logger.info("Inserted %d documents into '%s'.", len(data), self.collection_name)
        except PyMongoError:
            logger.exception("Error inserting data")

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        vectors: list[float],
        limit: int = 5,
        filters: dict | None = None,
    ) -> list[OutputData]:
        """Semantic similarity search using ``cosmosSearch``."""
        pipeline: list[dict[str, Any]] = [
            {
                "$search": {
                    "cosmosSearch": {
                        "vector": vectors,
                        "path": "embedding",
                        "k": limit,
                        "efSearch": _DEFAULT_HNSW_EF_SEARCH,
                    },
                    "returnStoredSource": True,
                },
            },
            {"$project": {"score": {"$meta": "searchScore"}, "document": "$$ROOT"}},
        ]

        # Post-filter on payload fields (same approach as Atlas adapter).
        if filters:
            conditions = [{"document.payload." + key: value} for key, value in filters.items()]
            if conditions:
                pipeline.append({"$match": {"$and": conditions}})

        try:
            raw = list(self.collection.aggregate(pipeline))
            logger.info("Vector search completed. Found %d documents.", len(raw))
        except Exception:
            logger.exception("Error during vector search for query '%s'", query)
            return []

        return [
            OutputData(
                id=str(doc["document"]["_id"]),
                score=doc.get("score"),
                payload=doc["document"].get("payload"),
            )
            for doc in raw
        ]

    # ------------------------------------------------------------------
    # CRUD (standard pymongo - fully compatible with DocumentDB)
    # ------------------------------------------------------------------

    def delete(self, vector_id: str) -> None:
        """Delete a vector by ID."""
        try:
            result = self.collection.delete_one({"_id": vector_id})
            if result.deleted_count > 0:
                logger.info("Deleted document '%s'.", vector_id)
            else:
                logger.warning("No document found with ID '%s' to delete.", vector_id)
        except PyMongoError:
            logger.exception("Error deleting document")

    def update(
        self,
        vector_id: str,
        vector: list[float] | None = None,
        payload: dict | None = None,
    ) -> None:
        """Update a vector and/or its payload."""
        update_fields: dict[str, Any] = {}
        if vector is not None:
            update_fields["embedding"] = vector
        if payload is not None:
            update_fields["payload"] = payload

        if not update_fields:
            return

        try:
            result = self.collection.update_one({"_id": vector_id}, {"$set": update_fields})
            if result.matched_count > 0:
                logger.info("Updated document '%s'.", vector_id)
            else:
                logger.warning("No document found with ID '%s' to update.", vector_id)
        except PyMongoError:
            logger.exception("Error updating document")

    def get(self, vector_id: str) -> OutputData | None:
        """Retrieve a single vector by ID."""
        try:
            doc = self.collection.find_one({"_id": vector_id})
            if doc:
                logger.info("Retrieved document '%s'.", vector_id)
                return OutputData(id=str(doc["_id"]), score=None, payload=doc.get("payload"))
            logger.warning("Document '%s' not found.", vector_id)
            return None
        except PyMongoError:
            logger.exception("Error retrieving document")
            return None

    def list(self, filters: dict | None = None, limit: int = 100) -> list[OutputData]:
        """List vectors, optionally filtered on payload fields."""
        try:
            query: dict[str, Any] = {}
            if filters:
                conditions = [{"payload." + key: value} for key, value in filters.items()]
                if conditions:
                    query = {"$and": conditions}

            cursor = self.collection.find(query).limit(limit)
            results = [OutputData(id=str(doc["_id"]), score=None, payload=doc.get("payload")) for doc in cursor]
            logger.info("Retrieved %d documents from '%s'.", len(results), self.collection_name)
            return results
        except PyMongoError:
            logger.exception("Error listing documents")
            return []

    # ------------------------------------------------------------------
    # Collection-level operations
    # ------------------------------------------------------------------

    def list_cols(self) -> list[str]:
        """List all collection names in the database."""
        try:
            collections = self.db.list_collection_names()
            logger.info("Collections in '%s': %s", self.db_name, collections)
            return collections
        except PyMongoError:
            logger.exception("Error listing collections")
            return []

    def delete_col(self) -> None:
        """Drop the collection."""
        try:
            self.collection.drop()
            logger.info("Dropped collection '%s'.", self.collection_name)
        except PyMongoError:
            logger.exception("Error dropping collection")

    def col_info(self) -> dict[str, Any]:
        """Return basic stats for the collection."""
        try:
            stats = self.db.command("collstats", self.collection_name)
            info: dict[str, Any] = {
                "name": self.collection_name,
                "count": stats.get("count"),
                "size": stats.get("size"),
            }
            logger.info("Collection info: %s", info)
            return info
        except PyMongoError:
            logger.exception("Error getting collection info")
            return {}

    def reset(self) -> None:
        """Drop the collection and recreate it with a fresh index."""
        logger.warning("Resetting collection '%s'…", self.collection_name)
        self.delete_col()
        self.collection = self.create_col()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def __del__(self) -> None:
        if hasattr(self, "client"):
            self.client.close()
            logger.info("MongoClient connection closed.")


# ---------------------------------------------------------------------------
# Factory registration helper
# ---------------------------------------------------------------------------


def register_documentdb_vector_store() -> None:
    """Register ``AzureDocumentDB`` with mem0's ``VectorStoreFactory``.

    Must be called **before** any ``mem0.AsyncMemory.from_config()`` that
    uses the ``azure_documentdb`` provider.
    """
    from mem0.utils.factory import VectorStoreFactory

    VectorStoreFactory.provider_to_class["azure_documentdb"] = "maas.vector_stores.documentdb.AzureDocumentDB"
