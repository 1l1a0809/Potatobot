"""Tests for dig service."""

import pytest
import time
from unittest.mock import AsyncMock
from app.services.dig_service import DigService
from app.exceptions import CooldownError
from app.database import User


class TestDigService:
    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db):
        return DigService(mock_db)

    @pytest.mark.asyncio
    async def test_dig_first_time(self, service, mock_db):
        """Test dig for new user."""
        # Setup
        mock_db.get_or_create_user.return_value = User(
            user_id=1,
            tg_id=12345,
            username="testuser",
            total_kg=0.0,
            last_dig_time=None,
            created_at=time.time(),
        )
        mock_db.add_dig_record.return_value = 1
        mock_db.update_user_dig.return_value = User(
            user_id=1,
            tg_id=12345,
            username="testuser",
            total_kg=5.0,
            last_dig_time=time.time(),
            created_at=time.time(),
        )

        # Execute
        result = await service.perform_dig(12345, "testuser")

        # Assert
        assert result["kg"] >= 1.0
        assert result["kg"] <= 7.0
        assert result["total_kg"] == result["kg"]
        assert "dig_id" in result
        assert "remaining_cooldown" in result
        mock_db.add_dig_record.assert_called_once()
        mock_db.update_user_dig.assert_called_once()

    @pytest.mark.asyncio
    async def test_dig_on_cooldown(self, service, mock_db):
        """Test dig when user is on cooldown."""
        # Setup: user dug 30 minutes ago
        mock_db.get_or_create_user.return_value = User(
            user_id=1,
            tg_id=12345,
            username="testuser",
            total_kg=10.0,
            last_dig_time=time.time() - 1800,  # 30 min ago
            created_at=time.time(),
        )

        # Execute & Assert
        with pytest.raises(CooldownError) as exc:
            await service.perform_dig(12345, "testuser")
        
        assert exc.value.remaining == 1800  # 30 min left
        mock_db.add_dig_record.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_user_history(self, service, mock_db):
        """Test getting user history."""
        from app.database import DigRecord
        
        mock_db.get_user_by_tg_id.return_value = User(
            user_id=1, tg_id=12345, username="test",
            total_kg=10.0, last_dig_time=time.time(), created_at=time.time()
        )
        mock_db.get_user_history.return_value = [
            DigRecord(dig_id=1, user_id=1, kg=3.5, timestamp=time.time()),
            DigRecord(dig_id=2, user_id=1, kg=2.1, timestamp=time.time() - 3600),
        ]

        history = await service.get_user_history(12345, 10)
        
        assert len(history) == 2
        assert history[0].kg == 3.5
        mock_db.get_user_history.assert_called_once_with(1, 10)

    @pytest.mark.asyncio
    async def test_leaderboard_cache(self, service, mock_db):
        """Test leaderboard caching."""
        from app.database import LeaderboardEntry
        
        mock_db.get_top_day.return_value = [
            LeaderboardEntry(rank=1, username="user1", total_kg=10.0, digs_count=3),
        ]

        # First call - hits DB
        result1 = await service.get_top_day(10)
        # Second call - hits cache
        result2 = await service.get_top_day(10)
        
        assert result1 == result2
        assert mock_db.get_top_day.call_count == 1  # Only called once due to cache

    @pytest.mark.asyncio
    async def test_invalidate_leaderboard_cache(self, service, mock_db):
        """Test cache invalidation."""
        from app.database import LeaderboardEntry
        
        mock_db.get_top_day.return_value = [
            LeaderboardEntry(rank=1, username="user1", total_kg=10.0, digs_count=3),
        ]

        await service.get_top_day(10)
        service.invalidate_leaderboard_cache()
        
        # Should hit DB again after invalidation
        await service.get_top_day(10)
        assert mock_db.get_top_day.call_count == 2