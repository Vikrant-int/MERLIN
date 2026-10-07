"""One module per page, exported for the window to assemble."""
from .chat import ChatView
from .dashboard import DashboardView
from .music import MusicView
from .news import NewsView
from .settings import SettingsView
from .voice import VoiceView

__all__ = [
    "ChatView",
    "DashboardView",
    "MusicView",
    "NewsView",
    "SettingsView",
    "VoiceView",
]
