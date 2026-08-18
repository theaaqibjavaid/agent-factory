"""Legacy compatibility adapters.

Compatibility code may depend on NeuraHive, but NeuraHive core must never
import this package.
"""

from .legacy_agent import LegacyAgentAdapter

__all__ = ["LegacyAgentAdapter"]
