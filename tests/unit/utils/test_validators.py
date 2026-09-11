"""Tests for validators."""

import pytest
from app.utils.validators import validate_username, validate_dig_amount


class TestValidators:
    def test_validate_username_none(self):
        assert validate_username(None) is None

    def test_validate_username_empty(self):
        assert validate_username("") is None

    def test_validate_username_with_at(self):
        assert validate_username("@testuser") == "testuser"

    def test_validate_username_truncate(self):
        long_name = "a" * 40
        result = validate_username(long_name)
        assert len(result) == 32

    def test_validate_username_invalid_chars(self):
        assert validate_username("test user") is None
        assert validate_username("test-user") is None
        assert validate_username("test@user") is None

    def test_validate_username_valid(self):
        assert validate_username("testuser") == "testuser"
        assert validate_username("Test_User123") == "Test_User123"

    def test_validate_dig_amount_bounds(self):
        # Mock settings
        import app.utils.validators
        original_settings = app.utils.validators.get_settings
        
        class MockSettings:
            dig_min_kg = 1.0
            dig_max_kg = 7.0
            dig_precision = 1
        
        app.utils.validators.get_settings = lambda: MockSettings()
        
        try:
            assert validate_dig_amount(0.5) == 1.0
            assert validate_dig_amount(10.0) == 7.0
            assert validate_dig_amount(3.14159) == 3.1
            assert validate_dig_amount(5.0) == 5.0
        finally:
            app.utils.validators.get_settings = original_settings