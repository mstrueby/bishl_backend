"""Unit tests for AuthHandler"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
import jwt
from authentication import AuthHandler, AuthenticationException


@pytest.fixture
def auth_handler():
    """AuthHandler instance with test settings"""
    # Patch settings before creating AuthHandler and keep it active
    patcher = patch('authentication.settings')
    mock_settings = patcher.start()
    
    mock_settings.SECRET_KEY = "test-secret-key"
    mock_settings.JWT_SECRET_KEY = "test-secret-key"
    mock_settings.JWT_REFRESH_SECRET_KEY = "test-refresh-secret"
    mock_settings.JWT_ALGORITHM = "HS256"
    mock_settings.ACCESS_TOKEN_EXPIRE_MINUTES = 30
    mock_settings.REFRESH_TOKEN_EXPIRE_DAYS = 7
    
    handler = AuthHandler()
    yield handler
    
    # Clean up the patch after test completes
    patcher.stop()


@pytest.fixture
def mock_user():
    """Mock user object"""
    return {
        "_id": "test-user-id",
        "email": "test@example.com",
        "roles": ["USER"],
        "firstName": "Test",
        "lastName": "User",
        "club": {
            "clubId": "test-club-id",
            "clubName": "Test Club"
        }
    }


class TestEncodeToken:
    """Test JWT token encoding"""

    def test_encode_access_token_success(self, auth_handler, mock_user):
        """Test successful access token encoding"""
        token = auth_handler.encode_token(mock_user)

        assert isinstance(token, str)
        assert len(token) > 0

        # Decode to verify structure using auth_handler's decode method
        payload = auth_handler.decode_token(token)
        assert payload.sub == mock_user["_id"]
        assert payload.roles == mock_user["roles"]

    def test_encode_token_includes_expiration(self, auth_handler, mock_user):
        """Test token includes expiration time"""
        token = auth_handler.encode_token(mock_user)

        # Decode the raw JWT to check expiration (TokenPayload doesn't expose exp)
        import jwt
        raw_payload = jwt.decode(token, auth_handler.secret, algorithms=["HS256"])
        
        assert "exp" in raw_payload
        exp_time = datetime.fromtimestamp(raw_payload["exp"])
        now = datetime.utcnow()
        assert exp_time > now

    def test_encode_refresh_token_success(self, auth_handler, mock_user):
        """Test successful refresh token encoding"""
        token = auth_handler.encode_refresh_token(mock_user)

        assert isinstance(token, str)
        assert len(token) > 0

        # Decode refresh token returns just the user ID (string), not TokenPayload
        user_id = auth_handler.decode_refresh_token(token)
        assert user_id == mock_user["_id"]
        
        # Verify token type by decoding raw JWT
        import jwt
        raw_payload = jwt.decode(token, auth_handler.refresh_secret, algorithms=["HS256"])
        assert raw_payload["type"] == "refresh"


class TestDecodeToken:
    """Test JWT token decoding"""

    def test_decode_valid_token_success(self, auth_handler, mock_user):
        """Test decoding valid token"""
        token = auth_handler.encode_token(mock_user)
        payload = auth_handler.decode_token(token)

        assert payload.sub == mock_user["_id"]
        assert payload.firstName == mock_user["firstName"]
        assert payload.lastName == mock_user["lastName"]

    def test_decode_expired_token_raises_exception(self, auth_handler):
        """Test decoding expired token raises exception"""
        # Create expired token using the same secret as auth_handler
        payload = {
            "sub": "test-user",
            "exp": datetime.now() - timedelta(hours=1),
            "type": "access"
        }
        expired_token = jwt.encode(payload, auth_handler.secret, algorithm="HS256")

        with pytest.raises(AuthenticationException) as exc_info:
            auth_handler.decode_token(expired_token)

        assert "expired" in str(exc_info.value).lower()

    def test_decode_invalid_token_raises_exception(self, auth_handler):
        """Test decoding invalid token raises exception"""
        invalid_token = "invalid.token.here"

        with pytest.raises(AuthenticationException):
            auth_handler.decode_token(invalid_token)

    def test_decode_token_wrong_secret(self, auth_handler):
        """Test decoding token with wrong secret fails"""
        # Create token with different secret
        payload = {"sub": "test-user"}
        wrong_token = jwt.encode(payload, "wrong-secret", algorithm="HS256")

        with pytest.raises(AuthenticationException):
            auth_handler.decode_token(wrong_token)


class TestPasswordHashing:
    """Test password hashing and verification"""

    def test_hash_password_returns_hash(self, auth_handler):
        """Test password hashing"""
        password = "test-password-123"
        hashed = auth_handler.hash_password(password)

        assert isinstance(hashed, str)
        assert hashed != password
        assert len(hashed) > 0

    def test_verify_password_correct(self, auth_handler):
        """Test password verification with correct password"""
        password = "test-password-123"
        hashed = auth_handler.hash_password(password)

        assert auth_handler.verify_password(password, hashed) is True

    def test_verify_password_incorrect(self, auth_handler):
        """Test password verification with incorrect password"""
        password = "test-password-123"
        hashed = auth_handler.hash_password(password)

        assert auth_handler.verify_password("wrong-password", hashed) is False

    def test_different_hashes_for_same_password(self, auth_handler):
        """Test that same password produces different hashes (salt)"""
        password = "test-password-123"
        hash1 = auth_handler.hash_password(password)
        hash2 = auth_handler.hash_password(password)

        assert hash1 != hash2
        assert auth_handler.verify_password(password, hash1) is True
        assert auth_handler.verify_password(password, hash2) is True


class TestRoleValidation:
    """Test role-based access control"""

    def test_user_has_role_single_role(self, auth_handler):
        """Test user has specific role"""
        roles = ["USER"]
        assert auth_handler.has_role(roles, "USER") is True
        assert auth_handler.has_role(roles, "ADMIN") is False

    def test_user_has_role_multiple_roles(self, auth_handler):
        """Test user with multiple roles"""
        roles = ["USER", "ADMIN", "REF_ADMIN"]
        assert auth_handler.has_role(roles, "ADMIN") is True
        assert auth_handler.has_role(roles, "USER") is True
        assert auth_handler.has_role(roles, "REF_ADMIN") is True

    def test_user_has_any_role(self, auth_handler):
        """Test user has any of required roles"""
        roles = ["USER", "MODERATOR"]
        required = ["ADMIN", "MODERATOR", "SUPER_ADMIN"]

        assert auth_handler.has_any_role(roles, required) is True

    def test_user_has_no_required_roles(self, auth_handler):
        """Test user has none of required roles"""
        roles = ["USER"]
        required = ["ADMIN", "MODERATOR"]

        assert auth_handler.has_any_role(roles, required) is False