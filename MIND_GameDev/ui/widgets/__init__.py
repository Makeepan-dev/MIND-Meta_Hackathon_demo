"""
MIND Universal Development Studio Widgets Package.
"""

from .live_website_preview import LiveWebsitePreviewWidget, HAS_WEBENGINE
from .design_preview_window import (
    DesignPreviewManager,
    DesignPreviewRecord,
    DesignPreviewWindow,
)

__all__ = [
    "LiveWebsitePreviewWidget",
    "HAS_WEBENGINE",
    "DesignPreviewManager",
    "DesignPreviewRecord",
    "DesignPreviewWindow",
]
