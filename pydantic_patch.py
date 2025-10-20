
"""
Monkey-patch for fastapi-mail compatibility with Pydantic v2.
This must be imported before any fastapi-mail imports.
"""
from pydantic import SecretStr
import pydantic

# Make SecretStr available at module level for fastapi-mail
pydantic.SecretStr = SecretStr

# Also patch pydantic.types if it exists
try:
    import pydantic.types
    pydantic.types.SecretStr = SecretStr
except (ImportError, AttributeError):
    # Create the types module if it doesn't exist
    import sys
    from types import ModuleType
    pydantic_types = ModuleType('pydantic.types')
    pydantic_types.SecretStr = SecretStr
    sys.modules['pydantic.types'] = pydantic_types
