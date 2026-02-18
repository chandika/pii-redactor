"""PII Redactor — fast, layered PII anonymization for LLM pipelines."""

from .redactor import Redactor, RedactorConfig
from .vault import Vault
from .vault_sqlite import SqliteVault
from .middleware import RedactMiddleware
from .streaming import StreamingRehydrator
from .config import create_middleware, load_config, load_from_yaml
from .types import RedactedMessage, EntityMatch

__all__ = [
    "Redactor", "RedactorConfig",
    "Vault", "SqliteVault",
    "RedactMiddleware",
    "StreamingRehydrator",
    "create_middleware", "load_config", "load_from_yaml",
    "RedactedMessage", "EntityMatch",
]
__version__ = "0.1.0"
