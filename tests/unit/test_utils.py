
"""Unit tests for utility functions"""
import pytest
from datetime import datetime
from utils import (
    parse_datetime,
    parse_time_to_seconds,
    parse_time_from_seconds,
    validate_match_time,
    flatten_dict,
    to_camel
)


class TestParseDatetime:
    """Test datetime parsing utilities"""

    def test_parse_datetime_valid(self):
        """Test parsing valid datetime string"""
        result = parse_datetime("2024-01-15 14:30:00")
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 14
        assert result.minute == 30

    def test_parse_datetime_none(self):
        """Test parsing None returns None"""
        result = parse_datetime(None)
        assert result is None

    def test_parse_datetime_empty_string(self):
        """Test parsing empty string returns None"""
        result = parse_datetime("")
        assert result is None


class TestParseTime:
    """Test match time parsing"""

    def test_parse_time_to_seconds_valid(self):
        """Test converting time string to seconds"""
        result = parse_time_to_seconds("15:30")
        assert result == 930  # 15*60 + 30

    def test_parse_time_to_seconds_zero(self):
        """Test converting zero time"""
        result = parse_time_to_seconds("00:00")
        assert result == 0

    def test_parse_time_to_seconds_none(self):
        """Test handling None returns 0"""
        result = parse_time_to_seconds(None)
        assert result == 0

    def test_parse_time_from_seconds_valid(self):
        """Test converting seconds to time string"""
        result = parse_time_from_seconds(930)
        assert result == "15:30"

    def test_parse_time_from_seconds_zero(self):
        """Test converting zero seconds"""
        result = parse_time_from_seconds(0)
        assert result == "00:00"


class TestValidateMatchTime:
    """Test match time validation"""

    def test_validate_match_time_valid(self):
        """Test validation of valid match time"""
        result = validate_match_time("15:30", "matchTime")
        assert result == "15:30"

    def test_validate_match_time_single_digit_minutes(self):
        """Test validation with single digit minutes"""
        result = validate_match_time("5:30", "matchTime")
        assert result == "5:30"

    def test_validate_match_time_invalid_format(self):
        """Test validation fails for invalid format"""
        with pytest.raises(ValueError):
            validate_match_time("invalid", "matchTime")

    def test_validate_match_time_invalid_seconds(self):
        """Test validation fails for seconds >= 60"""
        with pytest.raises(ValueError):
            validate_match_time("15:99", "matchTime")


class TestFlattenDict:
    """Test dictionary flattening"""

    def test_flatten_dict_simple(self):
        """Test flattening simple nested dict"""
        input_dict = {
            "a": 1,
            "b": {
                "c": 2,
                "d": 3
            }
        }
        result = flatten_dict(input_dict)
        assert result == {"a": 1, "b.c": 2, "b.d": 3}

    def test_flatten_dict_deep_nesting(self):
        """Test flattening deeply nested dict"""
        input_dict = {
            "a": {
                "b": {
                    "c": 1
                }
            }
        }
        result = flatten_dict(input_dict)
        assert result == {"a.b.c": 1}

    def test_flatten_dict_empty(self):
        """Test flattening empty dict"""
        result = flatten_dict({})
        assert result == {}


class TestToCamel:
    """Test snake_case to camelCase conversion"""

    def test_to_camel_simple(self):
        """Test simple snake_case conversion"""
        result = to_camel("hello_world")
        assert result == "helloWorld"

    def test_to_camel_multiple_underscores(self):
        """Test multiple underscores"""
        result = to_camel("this_is_a_test")
        assert result == "thisIsATest"

    def test_to_camel_no_underscores(self):
        """Test string without underscores"""
        result = to_camel("hello")
        assert result == "hello"
