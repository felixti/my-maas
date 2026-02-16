from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from maas.vector_stores.documentdb import (
    AzureDocumentDB,
    OutputData,
    register_documentdb_vector_store,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_mongo_client():
    """Patch MongoClient so no real connection is made."""
    with patch("maas.vector_stores.documentdb.MongoClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        # Set up the database and collection chain.
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_client.__getitem__ = MagicMock(return_value=mock_db)
        mock_db.list_collection_names.return_value = []
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_db.command.return_value = {"cursor": {"firstBatch": []}}

        yield mock_client, mock_db, mock_collection


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAzureDocumentDBInit:
    def test_creates_collection_and_index(self, mock_mongo_client: tuple) -> None:
        _client, mock_db, mock_collection = mock_mongo_client

        store = AzureDocumentDB(
            db_name="testdb",
            collection_name="vecs",
            embedding_model_dims=1536,
            mongo_uri="mongodb://localhost:27017",
        )

        assert store.collection_name == "vecs"
        assert store.embedding_model_dims == 1536
        assert store.index_name == "vecs_vector_index"
        # Collection created via insert + delete placeholder
        mock_collection.insert_one.assert_called_once()
        mock_collection.delete_one.assert_called_once()
        # Index created via db.command
        calls = mock_db.command.call_args_list
        # First call: listIndexes, second: createIndexes
        assert any(c.args[0] == "createIndexes" for c in calls)

    def test_skips_collection_creation_if_exists(self, mock_mongo_client: tuple) -> None:
        _client, mock_db, mock_collection = mock_mongo_client
        mock_db.list_collection_names.return_value = ["vecs"]

        AzureDocumentDB(
            db_name="testdb",
            collection_name="vecs",
            embedding_model_dims=1536,
            mongo_uri="mongodb://localhost:27017",
        )

        mock_collection.insert_one.assert_not_called()

    def test_skips_index_creation_if_exists(self, mock_mongo_client: tuple) -> None:
        _client, mock_db, _collection = mock_mongo_client
        mock_db.list_collection_names.return_value = ["vecs"]
        mock_db.command.return_value = {
            "cursor": {"firstBatch": [{"name": "vecs_vector_index"}]},
        }

        AzureDocumentDB(
            db_name="testdb",
            collection_name="vecs",
            embedding_model_dims=1536,
            mongo_uri="mongodb://localhost:27017",
        )

        # Only listIndexes called, not createIndexes
        create_calls = [c for c in mock_db.command.call_args_list if c.args[0] == "createIndexes"]
        assert len(create_calls) == 0


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.usefixtures("mock_mongo_client")
class TestAzureDocumentDBCRUD:
    @staticmethod
    def _make_store() -> AzureDocumentDB:
        return AzureDocumentDB(
            db_name="testdb",
            collection_name="vecs",
            embedding_model_dims=3,
            mongo_uri="mongodb://localhost:27017",
        )

    def test_insert(self) -> None:
        store = self._make_store()
        store.insert(
            vectors=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
            payloads=[{"a": 1}, {"b": 2}],
            ids=["id1", "id2"],
        )
        store.collection.insert_many.assert_called_once()
        docs = store.collection.insert_many.call_args.args[0]
        assert len(docs) == 2
        assert docs[0]["_id"] == "id1"
        assert docs[0]["embedding"] == [0.1, 0.2, 0.3]
        assert docs[0]["payload"] == {"a": 1}

    def test_delete(self) -> None:
        store = self._make_store()
        store.collection.delete_one.return_value = MagicMock(deleted_count=1)
        store.delete("id1")
        store.collection.delete_one.assert_called_with({"_id": "id1"})

    def test_update_vector_and_payload(self) -> None:
        store = self._make_store()
        store.collection.update_one.return_value = MagicMock(matched_count=1)
        store.update("id1", vector=[0.9, 0.8, 0.7], payload={"x": 42})
        store.collection.update_one.assert_called_once_with(
            {"_id": "id1"},
            {"$set": {"embedding": [0.9, 0.8, 0.7], "payload": {"x": 42}}},
        )

    def test_update_noop_when_no_fields(self) -> None:
        store = self._make_store()
        store.update("id1")
        store.collection.update_one.assert_not_called()

    def test_get_found(self) -> None:
        store = self._make_store()
        store.collection.find_one.return_value = {
            "_id": "id1",
            "embedding": [0.1, 0.2, 0.3],
            "payload": {"key": "val"},
        }
        result = store.get("id1")
        assert result is not None
        assert result.id == "id1"
        assert result.payload == {"key": "val"}
        assert result.score is None

    def test_get_not_found(self) -> None:
        store = self._make_store()
        store.collection.find_one.return_value = None
        result = store.get("missing")
        assert result is None

    def test_list_with_filters(self) -> None:
        store = self._make_store()
        cursor_mock = MagicMock()
        cursor_mock.limit.return_value = [
            {"_id": "id1", "payload": {"category": "semantic"}},
        ]
        store.collection.find.return_value = cursor_mock

        results = store.list(filters={"category": "semantic"}, limit=10)

        store.collection.find.assert_called_once_with(
            {"$and": [{"payload.category": "semantic"}]},
        )
        assert len(results) == 1
        assert results[0].id == "id1"

    def test_list_no_filters(self) -> None:
        store = self._make_store()
        cursor_mock = MagicMock()
        cursor_mock.limit.return_value = []
        store.collection.find.return_value = cursor_mock

        store.list()

        store.collection.find.assert_called_once_with({})


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.usefixtures("mock_mongo_client")
class TestAzureDocumentDBSearch:
    @staticmethod
    def _make_store() -> AzureDocumentDB:
        return AzureDocumentDB(
            db_name="testdb",
            collection_name="vecs",
            embedding_model_dims=3,
            mongo_uri="mongodb://localhost:27017",
        )

    def test_search_returns_output_data(self) -> None:
        store = self._make_store()
        store.collection.aggregate.return_value = [
            {
                "score": 0.95,
                "document": {"_id": "id1", "payload": {"text": "hello"}, "embedding": [0.1, 0.2, 0.3]},
            },
        ]

        results = store.search(query="hi", vectors=[0.1, 0.2, 0.3], limit=5)

        assert len(results) == 1
        assert isinstance(results[0], OutputData)
        assert results[0].id == "id1"
        assert results[0].score == 0.95
        assert results[0].payload == {"text": "hello"}

    def test_search_pipeline_uses_cosmos_search(self) -> None:
        store = self._make_store()
        store.collection.aggregate.return_value = []

        store.search(query="test", vectors=[0.1, 0.2, 0.3], limit=3)

        pipeline = store.collection.aggregate.call_args.args[0]
        # First stage must be $search with cosmosSearch
        assert "$search" in pipeline[0]
        assert "cosmosSearch" in pipeline[0]["$search"]
        cosmos = pipeline[0]["$search"]["cosmosSearch"]
        assert cosmos["vector"] == [0.1, 0.2, 0.3]
        assert cosmos["path"] == "embedding"
        assert cosmos["k"] == 3

    def test_search_with_filters_adds_match_stage(self) -> None:
        store = self._make_store()
        store.collection.aggregate.return_value = []

        store.search(query="test", vectors=[0.1, 0.2, 0.3], filters={"category": "semantic"})

        pipeline = store.collection.aggregate.call_args.args[0]
        # Should have 3 stages: $search, $project, $match
        assert len(pipeline) == 3
        match_stage = pipeline[2]
        assert "$match" in match_stage
        assert match_stage["$match"]["$and"] == [{"document.payload.category": "semantic"}]

    def test_search_handles_exception(self) -> None:
        store = self._make_store()
        store.collection.aggregate.side_effect = RuntimeError("connection lost")

        results = store.search(query="fail", vectors=[0.1, 0.2, 0.3])

        assert results == []


# ---------------------------------------------------------------------------
# Collection-level operations
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.usefixtures("mock_mongo_client")
class TestAzureDocumentDBCollections:
    @staticmethod
    def _make_store() -> AzureDocumentDB:
        return AzureDocumentDB(
            db_name="testdb",
            collection_name="vecs",
            embedding_model_dims=3,
            mongo_uri="mongodb://localhost:27017",
        )

    def test_list_cols(self, mock_mongo_client: tuple) -> None:
        _client, mock_db, _collection = mock_mongo_client
        store = self._make_store()
        mock_db.list_collection_names.return_value = ["vecs", "other"]

        result = store.list_cols()

        assert result == ["vecs", "other"]

    def test_delete_col(self) -> None:
        store = self._make_store()
        store.delete_col()
        store.collection.drop.assert_called_once()

    def test_col_info(self, mock_mongo_client: tuple) -> None:
        _client, mock_db, _collection = mock_mongo_client
        store = self._make_store()
        mock_db.command.return_value = {"count": 42, "size": 12345}

        info = store.col_info()

        assert info["name"] == "vecs"
        assert info["count"] == 42
        assert info["size"] == 12345


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.usefixtures("mock_mongo_client")
class TestAzureDocumentDBReset:
    def test_reset_drops_and_recreates(self) -> None:
        store = AzureDocumentDB(
            db_name="testdb",
            collection_name="vecs",
            embedding_model_dims=3,
            mongo_uri="mongodb://localhost:27017",
        )
        store.collection.drop = MagicMock()
        store.reset()
        store.collection.drop.assert_called()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_register_documentdb_vector_store() -> None:
    register_documentdb_vector_store()

    import sys

    from mem0.utils.factory import VectorStoreFactory
    from mem0.vector_stores.configs import VectorStoreConfig

    # Factory registration (runtime instantiation)
    assert "azure_documentdb" in VectorStoreFactory.provider_to_class
    assert VectorStoreFactory.provider_to_class["azure_documentdb"] == "maas.vector_stores.documentdb.AzureDocumentDB"

    # Config validation registration (pydantic model_validator)
    assert "azure_documentdb" in VectorStoreConfig._provider_configs.default
    assert VectorStoreConfig._provider_configs.default["azure_documentdb"] == "AzureDocumentDBConfig"

    # Synthetic module for dynamic __import__ in validator
    assert "mem0.configs.vector_stores.azure_documentdb" in sys.modules
    mod = sys.modules["mem0.configs.vector_stores.azure_documentdb"]
    assert hasattr(mod, "AzureDocumentDBConfig")


# ---------------------------------------------------------------------------
# Index Type Configuration
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.usefixtures("mock_mongo_client")
class TestAzureDocumentDBIndexType:
    def test_ensure_vector_index_diskann_params(self, mock_mongo_client: tuple) -> None:
        _client, mock_db, _collection = mock_mongo_client
        mock_db.command.return_value = {"cursor": {"firstBatch": []}}

        AzureDocumentDB(
            db_name="testdb",
            collection_name="vecs",
            embedding_model_dims=1536,
            mongo_uri="mongodb://localhost:27017",
            index_type="diskann",
        )

        # Find createIndexes call
        create_calls = [c for c in mock_db.command.call_args_list if c.args[0] == "createIndexes"]
        assert len(create_calls) == 1
        call_args = create_calls[0]
        indexes = call_args.kwargs["indexes"]
        assert len(indexes) == 1
        cosmos_opts = indexes[0]["cosmosSearchOptions"]

        # Assert DiskANN params present
        assert cosmos_opts["kind"] == "vector-diskann"
        assert cosmos_opts["maxDegree"] == 32
        assert cosmos_opts["lBuild"] == 50
        assert cosmos_opts["similarity"] == "COS"
        assert cosmos_opts["dimensions"] == 1536

        # Assert HNSW params NOT present
        assert "m" not in cosmos_opts
        assert "efConstruction" not in cosmos_opts

    def test_ensure_vector_index_hnsw_params(self, mock_mongo_client: tuple) -> None:
        _client, mock_db, _collection = mock_mongo_client
        mock_db.command.return_value = {"cursor": {"firstBatch": []}}

        AzureDocumentDB(
            db_name="testdb",
            collection_name="vecs",
            embedding_model_dims=1536,
            mongo_uri="mongodb://localhost:27017",
            index_type="hnsw",
        )

        # Find createIndexes call
        create_calls = [c for c in mock_db.command.call_args_list if c.args[0] == "createIndexes"]
        assert len(create_calls) == 1
        call_args = create_calls[0]
        indexes = call_args.kwargs["indexes"]
        assert len(indexes) == 1
        cosmos_opts = indexes[0]["cosmosSearchOptions"]

        # Assert HNSW params present
        assert cosmos_opts["kind"] == "vector-hnsw"
        assert cosmos_opts["m"] == 16
        assert cosmos_opts["efConstruction"] == 64
        assert cosmos_opts["similarity"] == "COS"
        assert cosmos_opts["dimensions"] == 1536

        # Assert DiskANN params NOT present
        assert "maxDegree" not in cosmos_opts
        assert "lBuild" not in cosmos_opts

    def test_search_diskann_uses_l_search(self, mock_mongo_client: tuple) -> None:
        _client, _db, _collection = mock_mongo_client
        store = AzureDocumentDB(
            db_name="testdb",
            collection_name="vecs",
            embedding_model_dims=3,
            mongo_uri="mongodb://localhost:27017",
            index_type="diskann",
        )
        store.collection.aggregate.return_value = []

        store.search(query="test", vectors=[0.1, 0.2, 0.3], limit=5)

        pipeline = store.collection.aggregate.call_args.args[0]
        cosmos_search = pipeline[0]["$search"]["cosmosSearch"]

        # Assert lSearch present, efSearch NOT present
        assert "lSearch" in cosmos_search
        assert cosmos_search["lSearch"] == 40
        assert "efSearch" not in cosmos_search

    def test_search_hnsw_uses_ef_search(self, mock_mongo_client: tuple) -> None:
        _client, _db, _collection = mock_mongo_client
        store = AzureDocumentDB(
            db_name="testdb",
            collection_name="vecs",
            embedding_model_dims=3,
            mongo_uri="mongodb://localhost:27017",
            index_type="hnsw",
        )
        store.collection.aggregate.return_value = []

        store.search(query="test", vectors=[0.1, 0.2, 0.3], limit=5)

        pipeline = store.collection.aggregate.call_args.args[0]
        cosmos_search = pipeline[0]["$search"]["cosmosSearch"]

        # Assert efSearch present, lSearch NOT present
        assert "efSearch" in cosmos_search
        assert cosmos_search["efSearch"] == 40
        assert "lSearch" not in cosmos_search

    def test_index_mismatch_logs_warning(self, mock_mongo_client: tuple) -> None:
        _client, mock_db, _collection = mock_mongo_client
        # Existing index with HNSW kind
        mock_db.command.return_value = {
            "cursor": {
                "firstBatch": [
                    {
                        "name": "vecs_vector_index",
                        "cosmosSearchOptions": {"kind": "vector-hnsw"},
                    },
                ],
            },
        }

        # Try to create with DiskANN
        with patch("maas.vector_stores.documentdb.logger") as mock_logger:
            AzureDocumentDB(
                db_name="testdb",
                collection_name="vecs",
                embedding_model_dims=1536,
                mongo_uri="mongodb://localhost:27017",
                index_type="diskann",
            )

            # Assert warning logged with correct message
            mock_logger.warning.assert_called_once()
            warning_call = mock_logger.warning.call_args
            assert "Drop and recreate" in warning_call.args[0]
            assert "vector-hnsw" in warning_call.args
            assert "vector-diskann" in warning_call.args

    def test_invalid_index_type_raises_value_error(self, mock_mongo_client: tuple) -> None:
        _client, _db, _collection = mock_mongo_client

        with pytest.raises(ValueError, match="index_type must be either 'diskann' or 'hnsw'"):
            AzureDocumentDB(
                db_name="testdb",
                collection_name="vecs",
                embedding_model_dims=1536,
                mongo_uri="mongodb://localhost:27017",
                index_type="ivf",
            )

    def test_default_index_type_is_diskann(self, mock_mongo_client: tuple) -> None:
        _client, mock_db, _collection = mock_mongo_client
        mock_db.command.return_value = {"cursor": {"firstBatch": []}}

        # Don't pass index_type, rely on default
        store = AzureDocumentDB(
            db_name="testdb",
            collection_name="vecs",
            embedding_model_dims=1536,
            mongo_uri="mongodb://localhost:27017",
        )

        assert store.index_type == "diskann"
        assert store.index_kind == "vector-diskann"

        # Verify createIndexes used DiskANN params
        create_calls = [c for c in mock_db.command.call_args_list if c.args[0] == "createIndexes"]
        assert len(create_calls) == 1
        cosmos_opts = create_calls[0].kwargs["indexes"][0]["cosmosSearchOptions"]
        assert cosmos_opts["kind"] == "vector-diskann"
