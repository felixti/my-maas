from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.integration
async def test_health_endpoint(integration_client: AsyncClient) -> None:
    """Integration test: health endpoint returns ok."""
    response = await integration_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
