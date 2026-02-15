# MaaS — API Reference

Base URL: `http://localhost:8000`

---

## Health

### `GET /health`

Health check endpoint.

**Response** `200 OK`:
```json
{"status": "ok"}
```

---

## STM (Short-Term Memory)

Session-scoped message buffers backed by Redis sorted sets.

### `POST /stm/{session_id}/messages`

Add messages to a session's buffer.

**Path Parameters:**
| Parameter | Type | Description |
|---|---|---|
| `session_id` | `string` | Unique session identifier |

**Request Body:**
```json
{
  "messages": [
    {
      "role": "user",
      "content": "Hello, how are you?",
      "metadata": {"source": "chat-ui"}
    },
    {
      "role": "assistant",
      "content": "I'm doing well, thanks!"
    }
  ]
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `messages` | `Message[]` | Yes | Array of messages to add |
| `messages[].role` | `string` | Yes | One of: `user`, `assistant`, `system`, `summary` |
| `messages[].content` | `string` | Yes | Message text content |
| `messages[].metadata` | `object` | No | Arbitrary key-value metadata |

**Response** `200 OK`:
```json
{
  "session_id": "abc123",
  "added": 2,
  "messages": [
    {
      "id": "uuid-1",
      "role": "user",
      "content": "Hello, how are you?",
      "metadata": {"source": "chat-ui"},
      "timestamp": 1707900000.123,
      "token_count": 6
    }
  ]
}
```

---

### `GET /stm/{session_id}/messages`

Retrieve messages from a session.

**Path Parameters:**
| Parameter | Type | Description |
|---|---|---|
| `session_id` | `string` | Unique session identifier |

**Query Parameters:**
| Parameter | Type | Default | Description |
|---|---|---|---|
| `limit` | `int` | `null` (all) | Maximum number of most recent messages to return |

**Response** `200 OK`:
```json
{
  "session_id": "abc123",
  "messages": [
    {
      "id": "uuid-1",
      "role": "user",
      "content": "Hello",
      "metadata": null,
      "timestamp": 1707900000.0,
      "token_count": 1
    }
  ]
}
```

---

### `GET /stm/{session_id}/context`

Get the context window for a session. Applies the active strategy (sliding window or token threshold with summarization).

**Path Parameters:**
| Parameter | Type | Description |
|---|---|---|
| `session_id` | `string` | Unique session identifier |

**Response** `200 OK`:
```json
{
  "session_id": "abc123",
  "messages": [...],
  "strategy": "sliding_window",
  "total_tokens": 1234
}
```

**Behavior by strategy:**
- **`sliding_window`**: Returns last N messages (N = per-session `max_messages` or global `STM_MAX_MESSAGES`)
- **`token_threshold`**: If total tokens exceed threshold, summarizes older 60% of messages via LLM, replaces them in Redis with a summary message, returns the compacted buffer

---

### `DELETE /stm/{session_id}`

Delete a session and all its messages.

**Path Parameters:**
| Parameter | Type | Description |
|---|---|---|
| `session_id` | `string` | Unique session identifier |

**Response** `200 OK`:
```json
{
  "session_id": "abc123",
  "deleted": true
}
```

---

### `PUT /stm/{session_id}/config`

Set per-session strategy configuration. Overrides global defaults for this session.

**Path Parameters:**
| Parameter | Type | Description |
|---|---|---|
| `session_id` | `string` | Unique session identifier |

**Request Body:**
```json
{
  "strategy": "token_threshold",
  "max_messages": 100,
  "max_tokens": 4000
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `strategy` | `string` | No | `sliding_window` or `token_threshold` |
| `max_messages` | `int` | No | Override max messages for sliding window |
| `max_tokens` | `int` | No | Override token threshold |

**Response** `200 OK`:
```json
{
  "session_id": "abc123",
  "config": {
    "strategy": "token_threshold",
    "max_messages": 100,
    "max_tokens": 4000
  }
}
```

---

## LTM (Long-Term Memory)

Persistent semantic memory backed by mem0 + MongoDB vector store.

### `POST /ltm/memories`

Add a memory to long-term storage.

**Request Body:**
```json
{
  "messages": "The user prefers dark mode and uses Vim.",
  "category": "preference",
  "user_id": "user-42",
  "metadata": {"source": "settings-page"}
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `messages` | `string` or `list[dict]` | Yes | Memory content — plain string or chat message format |
| `category` | `string` | Yes | One of: `semantic`, `episodic`, `fact`, `preference` |
| `user_id` | `string` | Conditional | User scope (at least one scope required) |
| `agent_id` | `string` | Conditional | Agent scope |
| `session_id` | `string` | Conditional | Session scope |
| `metadata` | `object` | No | Additional metadata |

**Scope requirement**: At least one of `user_id`, `agent_id`, or `session_id` must be provided.

**Response** `200 OK`:
```json
{
  "id": "mem-uuid",
  "memory": "User prefers dark mode and uses Vim",
  "metadata": {"category": "preference", "source": "settings-page"},
  "created_at": "2025-02-14T12:00:00Z",
  "updated_at": null,
  "score": null
}
```

---

### `POST /ltm/memories/search`

Search memories by semantic similarity.

**Request Body:**
```json
{
  "query": "What editor does the user prefer?",
  "user_id": "user-42",
  "categories": ["preference", "fact"],
  "limit": 10
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `query` | `string` | Yes | Natural language search query |
| `user_id` | `string` | Conditional | User scope filter |
| `agent_id` | `string` | Conditional | Agent scope filter |
| `session_id` | `string` | Conditional | Session scope filter |
| `categories` | `string[]` | No | Filter by memory categories |
| `limit` | `int` | No (default: 100) | Maximum results |

**Response** `200 OK`:
```json
{
  "results": [
    {
      "id": "mem-uuid",
      "memory": "User prefers dark mode and uses Vim",
      "metadata": {"category": "preference"},
      "score": 0.92
    }
  ]
}
```

---

### `GET /ltm/memories`

List all memories with optional filters.

**Query Parameters:**
| Parameter | Type | Description |
|---|---|---|
| `user_id` | `string` | Filter by user |
| `agent_id` | `string` | Filter by agent |
| `session_id` | `string` | Filter by session |
| `limit` | `int` | Max results (default: 100) |

**Response** `200 OK`:
```json
{
  "results": [...]
}
```

---

### `GET /ltm/memories/{memory_id}`

Get a specific memory by ID.

**Response** `200 OK`:
```json
{
  "id": "mem-uuid",
  "memory": "...",
  "metadata": {...},
  "created_at": "...",
  "updated_at": "..."
}
```

---

### `PUT /ltm/memories/{memory_id}`

Update a memory's content.

**Request Body:**
```json
{
  "data": "Updated memory content"
}
```

**Response** `200 OK`: Updated `MemoryResponse`

---

### `DELETE /ltm/memories/{memory_id}`

Delete a memory.

**Response** `200 OK`:
```json
{
  "id": "mem-uuid",
  "deleted": true
}
```

---

### `GET /ltm/memories/{memory_id}/history`

Get the change history for a memory.

**Response** `200 OK`:
```json
{
  "entries": [
    {
      "id": "hist-uuid",
      "memory_id": "mem-uuid",
      "old_memory": "...",
      "new_memory": "...",
      "event": "update",
      "timestamp": "..."
    }
  ]
}
```

---

## Error Responses

### `503 Service Unavailable`

Returned when a backing service (Redis, LLM) is not initialized:
```json
{
  "detail": "Redis not initialized"
}
```

### `422 Unprocessable Entity`

Returned when request validation fails (e.g., missing required scope):
```json
{
  "detail": [
    {
      "type": "value_error",
      "msg": "Value error, At least one of user_id, agent_id, or session_id must be provided"
    }
  ]
}
```
