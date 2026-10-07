"""Colour tokens and the application stylesheet.

Everything visual is derived from one palette dict, so the whole product can
be rethemed by swapping tokens rather than hunting through widgets.
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

BASE_FONT = "Segoe UI"

DARK = {
    "window": "#0A0C11",
    "sidebar": "#0D1017",
    "panel": "#12161F",
    "panel_alt": "#161B25",
    "hover": "#1A2130",
    "pressed": "#202839",
    "border": "#1E2431",
    "border_soft": "#181D28",
    "text": "#E8ECF4",
    "text_dim": "#9AA4B8",
    "text_mute": "#6B7488",
    "accent": "#4FD1FF",
    "accent_2": "#5B8CFF",
    "accent_3": "#7C6CFF",
    # Qt reads an 8-digit hex as #AARRGGBB, so the translucent variants are
    # written alpha-first: accent/danger with a low alpha, not alpha tacked
    # on the end (which would be read as RRGGBBAA and come out yellow-green).
    "accent_soft": "#224FD1FF",
    "danger": "#FF6B7A",
    "danger_soft": "#1FFF6B7A",
    "success": "#4ADE80",
    "warning": "#FBBF24",
    "on_accent": "#04121B",
    "titlebar": "#0B0E14",
    "bubble_user": "#1B2636",
    "scroll": "#2A3345",
}

LIGHT = {
    "window": "#F4F6FA",
    "sidebar": "#FFFFFF",
    "panel": "#FFFFFF",
    "panel_alt": "#F7F9FC",
    "hover": "#EDF1F7",
    "pressed": "#E3E9F2",
    "border": "#DCE2EC",
    "border_soft": "#E6EAF2",
    "text": "#11151D",
    "text_dim": "#4C576B",
    "text_mute": "#7C869B",
    "accent": "#0A7EA4",
    "accent_2": "#3457D5",
    "accent_3": "#5B45D6",
    "accent_soft": "#1F0A7EA4",
    "danger": "#D93A4B",
    "danger_soft": "#1AD93A4B",
    "success": "#158A45",
    "warning": "#B57500",
    "on_accent": "#FFFFFF",
    "titlebar": "#FFFFFF",
    "bubble_user": "#E8EEF8",
    "scroll": "#C3CBD9",
}

PALETTES = {"dark": DARK, "light": LIGHT}
DEFAULT_THEME = "dark"


def font(size: int = 13, weight: int = QFont.Weight.Normal) -> QFont:
    f = QFont(BASE_FONT)
    f.setPixelSize(size)
    f.setWeight(weight)
    return f


def prefers_reduced_motion() -> bool:
    """Honour the Windows "show animations" accessibility setting."""
    try:
        hints = QApplication.styleHints()
        getter = getattr(hints, "reduceAnimation", None)
        if callable(getter):
            return bool(getter())
    except Exception:
        pass
    return False


def stylesheet(colors: dict[str, str]) -> str:
    """Build the QSS from the token set."""
    c = colors
    return f"""
/* ---- base ---- */
QWidget {{
    background: transparent;
    color: {c['text']};
    font-family: "{BASE_FONT}";
    font-size: 13px;
}}
QToolTip {{
    background: {c['panel_alt']};
    color: {c['text']};
    border: 1px solid {c['border']};
    padding: 6px 8px;
    border-radius: 6px;
    font-size: 12px;
}}

/* ---- scrollbars ---- */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 4px 2px 4px 4px;
}}
QScrollBar::handle:vertical {{
    background: {c['scroll']};
    min-height: 32px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical:hover {{ background: {c['text_mute']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    height: 0; width: 0; background: transparent;
}}
QScrollBar:horizontal {{
    background: transparent; height: 10px; margin: 2px 4px;
}}
QScrollBar::handle:horizontal {{
    background: {c['scroll']}; min-width: 32px; border-radius: 5px;
}}

/* ---- panels / cards ---- */
#Card {{
    background: {c['panel']};
    border: 1px solid {c['border']};
    border-radius: 12px;
}}
#CardFlat {{
    background: {c['panel_alt']};
    border: 1px solid {c['border_soft']};
    border-radius: 10px;
}}
#Separator {{ background: {c['border_soft']}; max-height: 1px; }}

/* ---- typography ---- */
#H1 {{ font-size: 30px; font-weight: 600; color: {c['text']}; }}
#H2 {{ font-size: 20px; font-weight: 600; color: {c['text']}; }}
#H3 {{ font-size: 15px; font-weight: 600; color: {c['text']}; }}
#Sub {{ font-size: 14px; color: {c['text_dim']}; }}
#Muted {{ font-size: 12px; color: {c['text_mute']}; }}
#Eyebrow {{
    font-size: 11px; font-weight: 600; color: {c['text_mute']};
    letter-spacing: 1.4px;
}}
#AccentText {{ color: {c['accent']}; font-size: 13px; }}
#DangerText {{ color: {c['danger']}; font-size: 13px; }}
#SuccessText {{ color: {c['success']}; font-size: 13px; }}

/* ---- buttons ---- */
QPushButton {{
    background: {c['panel_alt']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 8px 14px;
    color: {c['text']};
    font-size: 13px;
}}
QPushButton:hover {{ background: {c['hover']}; border-color: {c['border']}; }}
QPushButton:pressed {{ background: {c['pressed']}; }}
QPushButton:disabled {{
    background: {c['panel']}; color: {c['text_mute']};
    border-color: {c['border_soft']};
}}
#PrimaryButton {{
    background: {c['accent']};
    color: {c['on_accent']};
    border: 1px solid {c['accent']};
    font-weight: 600;
}}
#PrimaryButton:hover {{ background: {c['accent_2']}; border-color: {c['accent_2']}; }}
#PrimaryButton:pressed {{ background: {c['accent_3']}; border-color: {c['accent_3']}; }}
#PrimaryButton:disabled {{
    background: {c['panel_alt']}; color: {c['text_mute']};
    border: 1px solid {c['border']};
}}
#DangerButton {{
    background: transparent; color: {c['danger']};
    border: 1px solid {c['danger']};
}}
#DangerButton:hover {{ background: {c['danger_soft']}; }}
#GhostButton {{
    background: transparent; border: 1px solid transparent;
    color: {c['text_dim']};
}}
#GhostButton:hover {{ background: {c['hover']}; color: {c['text']}; }}
#IconButton {{
    background: transparent; border: 1px solid transparent;
    border-radius: 7px; padding: 6px;
    min-width: 30px; min-height: 30px;
}}
#IconButton:hover {{ background: {c['hover']}; border-color: {c['border']}; }}
#IconButton:pressed {{ background: {c['pressed']}; }}
#TitleButton {{
    background: transparent; border: none; border-radius: 0;
    min-width: 44px; max-width: 44px; min-height: 32px;
    color: {c['text_dim']};
}}
#TitleButton:hover {{ background: {c['hover']}; color: {c['text']}; }}
#TitleClose:hover {{ background: #E81123; color: #FFFFFF; }}

/* ---- sidebar ---- */
#NavButton {{
    background: transparent; border: none; border-radius: 9px;
    padding: 10px 12px 10px 18px; text-align: left;
    color: {c['text_dim']}; font-size: 13px;
}}
#NavButton:hover {{ background: {c['hover']}; color: {c['text']}; }}
#NavButton:checked {{
    background: {c['accent_soft']}; color: {c['text']}; font-weight: 600;
}}

/* ---- inputs ---- */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background: {c['panel_alt']};
    border: 1px solid {c['border']};
    border-radius: 9px;
    padding: 9px 12px;
    color: {c['text']};
    selection-background-color: {c['accent_2']};
    selection-color: {c['on_accent']};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {c['accent']};
}}
QLineEdit:disabled, QTextEdit:disabled {{
    background: {c['panel']}; color: {c['text_mute']};
}}
QComboBox {{
    background: {c['panel_alt']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 7px 30px 7px 11px;
    color: {c['text']};
    min-height: 20px;
}}
QComboBox:hover {{ border-color: {c['text_mute']}; }}
QComboBox:focus {{ border-color: {c['accent']}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{
    image: none; border-left: 4px solid transparent;
    border-right: 4px solid transparent; border-top: 5px solid {c['text_dim']};
    margin-right: 10px;
}}
QComboBox QAbstractItemView {{
    background: {c['panel_alt']};
    border: 1px solid {c['border']};
    selection-background-color: {c['hover']};
    selection-color: {c['text']};
    outline: none; padding: 4px;
}}

/* ---- checkboxes / switches ---- */
QCheckBox {{ spacing: 9px; color: {c['text_dim']}; font-size: 13px; }}
QCheckBox:hover {{ color: {c['text']}; }}
QCheckBox::indicator {{
    width: 34px; height: 19px; border-radius: 10px;
    background: {c['pressed']}; border: 1px solid {c['border']};
}}
QCheckBox::indicator:checked {{
    background: {c['accent']}; border-color: {c['accent']};
}}
QCheckBox::indicator:hover {{ border-color: {c['text_mute']}; }}

/* ---- list / conversation ---- */
QListView, QListWidget {{
    background: transparent; border: none; outline: none;
}}
QListView::item, QListWidget::item {{
    padding: 9px 10px; border-radius: 8px;
}}
QListView::item:hover {{ background: {c['hover']}; }}
QListView::item:selected {{ background: {c['accent_soft']}; color: {c['text']}; }}

/* ---- slider ---- */
QSlider::groove:horizontal {{
    height: 4px; background: {c['pressed']}; border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {c['accent']}; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 14px; height: 14px; margin: -5px 0;
    border-radius: 7px; background: {c['text']};
    border: 2px solid {c['accent']};
}}
QSlider::handle:horizontal:hover {{ background: {c['accent']}; }}

/* ---- progress ---- */
QProgressBar {{
    background: {c['pressed']}; border: none; border-radius: 4px;
    height: 6px; text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background: {c['accent']}; border-radius: 4px; }}

/* ---- messages ---- */
#BannerError {{
    background: {c['danger_soft']};
    border: 1px solid {c['danger']};
    border-radius: 10px;
}}
#BannerInfo {{
    background: {c['accent_soft']};
    border: 1px solid {c['accent_2']};
    border-radius: 10px;
}}
#Pill {{
    background: {c['panel_alt']}; border: 1px solid {c['border']};
    border-radius: 11px; padding: 3px 10px;
    font-size: 11px; color: {c['text_dim']};
}}

/* ---- icon buttons that carry the primary action ---- */
#PrimaryIconButton {{
    background: {c['accent']};
    border: 1px solid {c['accent']};
    border-radius: 9px; padding: 6px;
    min-width: 30px; min-height: 30px;
}}
#PrimaryIconButton:hover {{ background: {c['accent_2']};
    border-color: {c['accent_2']}; }}
#PrimaryIconButton:pressed {{ background: {c['accent_3']};
    border-color: {c['accent_3']}; }}
#PrimaryIconButton:disabled {{
    background: {c['panel_alt']}; border-color: {c['border']};
}}

/* ---- chat transcript ---- */
#ChatBubbleUser {{
    background: {c['bubble_user']};
    border: 1px solid {c['border']};
    border-radius: 13px;
}}
#ChatBubbleAssistant {{
    background: {c['panel_alt']};
    border: 1px solid {c['border_soft']};
    border-radius: 13px;
}}
#ChatBubbleError {{
    background: {c['danger_soft']};
    border: 1px solid {c['danger']};
    border-radius: 13px;
}}
"""


def apply_theme(app: QApplication, name: str) -> dict[str, str]:
    """Apply a palette to the application and return the tokens used."""
    colors = PALETTES.get(name, DARK)
    app.setStyleSheet(stylesheet(colors))

    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(colors["window"]))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(colors["text"]))
    pal.setColor(QPalette.ColorRole.Base, QColor(colors["panel"]))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(colors["panel_alt"]))
    pal.setColor(QPalette.ColorRole.Text, QColor(colors["text"]))
    pal.setColor(QPalette.ColorRole.Button, QColor(colors["panel_alt"]))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(colors["text"]))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(colors["accent_2"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(colors["on_accent"]))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(colors["panel_alt"]))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(colors["text"]))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(colors["text_mute"]))
    app.setPalette(pal)
    return colors
