
"""Unit tests for utility functions"""
import pytest
from datetime import datetime
from utils import format_datetime, validate_email, sanitize_string, parse_match_time


class TestFormatDateTime:
    """Test datetime formatting utilities"""

    def test_format_datetime_iso(self):
        """Test ISO datetime formatting"""
        dt = datetime(2024, 1, 15, 14, 30, 0)
        result = format_datetime(dt, format="iso")
        assert result == "2024-01-15T14:30:00"

    def test_format_datetime_readable(self):
        """Test readable datetime formatting"""
        dt = datetime(2024, 1, 15, 14, 30, 0)
        result = format_datetime(dt, format="readable")
        assert "2024" in result
        assert "14:30" in result


class TestValidateEmail:
    """Test email validation"""

    def test_valid_email_returns_true(self):
        """Test validation of valid email"""
        assert validate_email("test@example.com") is True
        assert validate_email("user.name+tag@example.co.uk") is True

    def test_invalid_email_returns_false(self):
        """Test validation of invalid email"""
        assert validate_email("notanemail") is False
        assert validate_email("missing@domain") is False
        assert validate_email("@example.com") is False
        assert validate_email("test@") is False


class TestSanitizeString:
    """Test string sanitization"""

    def test_remove_special_characters(self):
        """Test removal of special characters"""
        result = sanitize_string("Hello<script>World</script>")
        assert "<script>" not in result
        assert "Hello" in result
        assert "World" in result

    def test_trim_whitespace(self):
        """Test trimming of whitespace"""
        result = sanitize_string("  Hello World  ")
        assert result == "Hello World"

    def test_empty_string(self):
        """Test handling of empty string"""
        result = sanitize_string("")
        assert result == ""


class TestParseMatchTime:
    """Test match time parsing"""

    def test_parse_valid_time(self):
        """Test parsing valid match time"""
        result = parse_match_time("15:30")
        assert result["minutes"] == 15
        assert result["seconds"] == 30

    def test_parse_time_with_single_digits(self):
        """Test parsing time with single digits"""
        result = parse_match_time("5:03")
        assert result["minutes"] == 5
        assert result["seconds"] == 3

    def test_parse_invalid_time_format(self):
        """Test parsing invalid time format"""
        with pytest.raises(ValueError):
            parse_match_time("invalid")

    def test_parse_time_out_of_range(self):
        """Test parsing time with values out of range"""
        with pytest.raises(ValueError):
            parse_match_time("15:99")
