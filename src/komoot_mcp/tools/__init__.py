"""MCP tool registration helpers for Komoot."""

from .tours import register as register_tours
from .exports import register as register_exports
from .uploads import register as register_uploads
from .highlights import register as register_highlights
from .routing import register as register_routing
from .streams import register as register_streams
from .profile import register as register_profile
from .discover import register as register_discover
from .sharing import register as register_sharing

__all__ = [
    "register_tours",
    "register_exports",
    "register_uploads",
    "register_highlights",
    "register_routing",
    "register_streams",
    "register_profile",
    "register_discover",
    "register_sharing",
]
