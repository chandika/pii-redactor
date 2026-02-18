"""PII Redactor — fast, layered PII anonymization for LLM pipelines."""

from .redactor import Redactor
from .vault import Vault
from .types import RedactedMessage, EntityMatch

__all__ = ["Redactor", "Vault", "RedactedMessage", "EntityMatch"]
__version__ = "0.1.0"
