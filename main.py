import sys
import os
import winreg 
import json
import shutil
import re
import tempfile
import time
import base64
import locale 
try:
    import requests
except ImportError:
    requests = None
try:
    import patoolib
except ImportError:
    patoolib = None
try:
    import win32gui
    import win32api
    import win32con
    import win32gui
    import win32event
    import winerror
except ImportError:
    win32api = None
    win32gui = None
    win32con = None
    win32event = None
    winerror = None
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QListWidget, QPushButton, QStackedWidget, QLabel,
    QTabWidget, QFileDialog, QInputDialog, QMessageBox, QListWidgetItem,
    QDialog, QButtonGroup, QLineEdit, QListView, QStyle, QFrame, QSpacerItem, QSizePolicy, QStackedLayout, QSystemTrayIcon, QMenu
)
from PyQt6.QtCore import Qt, QSize, QRectF, QByteArray, pyqtSignal, QTimer, QPointF, QUrl, QEventLoop
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QBrush, QColor, QPalette, QPainterPath, QDesktopServices, QCursor, QPen, QFontMetrics, QAction
from PyQt6.QtSvg import QSvgRenderer
from lib.ui_dialogs import ProfileItemWidget, ProfileDialog, ApiSelectionDialog, ModInfoDialog
from lib.overlay import OverlayController
from lib.translation import Translator
import tempfile
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from lib.download_tab import FileSelectionDialog, DownloadProgressDialog
import re
from lib.one_click_dialog import OneClickInstallDialog

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

if sys.platform == "win32":
    import subprocess
    if patoolib: 
        original_run = patoolib.util.run

        def run_silently(*args, **kwargs):
            creationflags = subprocess.CREATE_NO_WINDOW
            if 'creationflags' not in kwargs:
                kwargs['creationflags'] = creationflags
            return original_run(*args, **kwargs)
        patoolib.util.run = run_silently

class SingleInstance:
    def __init__(self, name):
        self.mutex = None
        self.mutex_name = name
        self.is_running = False
        self.mutex = win32event.CreateMutex(None, 1, self.mutex_name)
        last_error = win32api.GetLastError()
        if last_error == winerror.ERROR_ALREADY_EXISTS:
            self.is_running = True

    def __del__(self):
        if self.mutex:
            win32api.CloseHandle(self.mutex)

class MarqueeLabel(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.offset = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._scroll)
        self.padding = 30

    def is_overflowing(self):
        return len(self.text()) > 20

    def start_marquee(self):
        if self.is_overflowing():
            self.offset = 0
            self.timer.start(30)

    def stop_marquee(self):
        self.timer.stop()
        self.offset = 0
        self.update()

    def _scroll(self):
        self.offset += 1
        text_width = QFontMetrics(self.font()).horizontalAdvance(self.text())
        if self.offset > text_width + self.padding:
            self.offset = 0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.is_overflowing() and self.timer.isActive():
            fm = QFontMetrics(self.font())
            text_width = fm.horizontalAdvance(self.text())
            y_pos = (self.height() - fm.height()) / 2 + fm.ascent()

            painter.drawText(QPointF(0 - self.offset, y_pos), self.text())
            if self.offset > 0:
                 painter.drawText(QPointF(0 - self.offset + text_width + self.padding, y_pos), self.text())
        else:
            text_to_draw = self.text()
            alignment = self.alignment() 
            if self.is_overflowing():
                text_to_draw = self.text()[:20] + "..."
                alignment = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            painter.drawText(self.rect(), alignment, text_to_draw)

    def setText(self, text):
        super().setText(text)
        self.stop_marquee()

class ModCardWidget(QWidget):
    edit_requested = pyqtSignal()
    delete_requested = pyqtSignal()
    url_requested = pyqtSignal(str)
    update_requested = pyqtSignal()

    def __init__(self, mod_info, parent=None):
        super().__init__(parent)
        self.mod_manager = parent
        self.translator = self.mod_manager.translator
        self.mod_info = mod_info
        self.is_active = False
        self.is_hovered = False

        self.setFixedSize(280, 220)
        self.setMouseTracking(True) 

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(5)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(215, 120)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet("border: 1px solid #ddd; border-radius: 4px; background-color: rgba(0,0,0,0.05);")
        icon_path = self.mod_info.get("icon")
        if icon_path and os.path.exists(icon_path):
            pixmap = QPixmap(icon_path)
            self.icon_label.setPixmap(pixmap.scaled(220, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            self.icon_label.setText(self.translator.translate("text_no_icon"))
        main_layout.addWidget(self.icon_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        display_name = self.mod_info.get("display_name") or self.mod_info.get("name", self.translator.translate("text_unknown_name"))
        self.name_label = MarqueeLabel(display_name, self)
        self.name_label.setStyleSheet("font-size: 11pt; font-weight: bold;")
        self.name_label.setWordWrap(False)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        font_metrics = QFontMetrics(self.name_label.font())
        max_width = font_metrics.horizontalAdvance("W" * 15) + 5 
        self.name_label.setMaximumWidth(max_width)

        creator = self.mod_info.get("creator")
        creator_text = f"<i>{self.translator.translate('text_creator_prefix', creator=creator)}</i>" if creator else f"<i>{self.translator.translate('text_unknown_creator')}</i>"
        creator_label = QLabel(creator_text)
        creator_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        creator_label.setWordWrap(True)
        
        name_layout = QHBoxLayout()
        name_layout.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        name_layout.addWidget(self.name_label)
        name_layout.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))

        main_layout.addLayout(name_layout)
        main_layout.addWidget(creator_label)
        main_layout.addStretch()

        button_layout = QHBoxLayout()
        button_layout.setSpacing(4)
        highlight_color = self.palette().color(QPalette.ColorRole.Highlight)
        btn_size, icon_size = 32, 18
        stylesheet = f"QPushButton {{ background-color: transparent; border-radius: {btn_size//2}px; }} QPushButton:hover {{ background-color: rgba({highlight_color.red()}, {highlight_color.green()}, {highlight_color.blue()}, 40); }} QPushButton:pressed {{ background-color: rgba({highlight_color.red()}, {highlight_color.green()}, {highlight_color.blue()}, 80); }}"

        edit_button = QPushButton()
        edit_button.setIcon(self.mod_manager._create_colored_icon(self.mod_manager.ICON_EDIT, highlight_color))
        edit_button.setToolTip(self.translator.translate("tooltip_edit_mod_info")) 
        edit_button.clicked.connect(self.edit_requested.emit)

        url_button = QPushButton()
        url_button.setIcon(self.mod_manager._create_colored_icon(self.mod_manager.ICON_URL, highlight_color))
        url_button.setToolTip(self.translator.translate("tooltip_open_mod_page")) 
        url_button.clicked.connect(lambda: self.url_requested.emit(self.mod_info.get("url", "")))
        if not self.mod_info.get("url"): url_button.setEnabled(False)

        update_button = QPushButton()
        update_button.setIcon(self.mod_manager._create_colored_icon(self.mod_manager.ICON_UPDATE, highlight_color))
        update_button.setToolTip(self.translator.translate("tooltip_check_for_updates"))
        update_button.clicked.connect(self.update_requested.emit)
        is_api_mod = bool(self.mod_info.get("profile_url"))
        update_button.setEnabled(is_api_mod)

        delete_button = QPushButton()
        delete_button.setIcon(self.mod_manager._create_colored_icon(self.mod_manager.ICON_REMOVE, highlight_color))
        delete_button.setToolTip(self.translator.translate("tooltip_delete_this_mod")) 
        delete_button.clicked.connect(self.delete_requested.emit)
    
        for btn in [edit_button, url_button, update_button, delete_button]:
            btn.setFixedSize(btn_size, btn_size); btn.setIconSize(QSize(icon_size, icon_size)); btn.setStyleSheet(stylesheet); btn.setCursor(Qt.CursorShape.PointingHandCursor)
            button_layout.addWidget(btn)

        main_layout.addLayout(button_layout)

    def set_active(self, active):
        if self.is_active != active:
            self.is_active = active
            self.update_text_color()
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.is_hovered and not self.is_active:
            highlight_color = self.palette().color(QPalette.ColorRole.Highlight)
            highlight_color.setAlpha(40)
            brush_to_use = QBrush(highlight_color)
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()), 8, 8)
            painter.fillPath(path, brush_to_use)
        if self.is_active:
            highlight_color = self.palette().color(QPalette.ColorRole.Highlight)
            pen = QPen(highlight_color)
            pen.setWidth(3)
            painter.setPen(pen)
            rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
            painter.drawRoundedRect(rect, 8, 8)
    
    def enterEvent(self, event):
        self.is_hovered = True
        self.update()
        self.name_label.start_marquee()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.is_hovered = False
        self.update()
        self.name_label.stop_marquee()
        super().leaveEvent(event)
        
    def update_text_color(self):
        text_widgets = self.findChildren(QLabel)
        if self.is_active:
            highlight_color = self.palette().color(QPalette.ColorRole.Highlight)
            text_color_name = highlight_color.name()
            for widget in text_widgets:
                if not widget.pixmap(): widget.setStyleSheet(f"color: {text_color_name}; background-color: transparent;")
        else:
            for widget in text_widgets:
                if not widget.pixmap():
                    current_style = widget.styleSheet()
                    new_style = re.sub(r'color:\s*#[0-9a-fA-F]+;', '', current_style)
                    widget.setStyleSheet(new_style)

class NoneModCardWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.mod_manager = parent
        self.translator = self.mod_manager.translator 
        self.is_active = False
        self.is_hovered = False

        self.setFixedSize(280, 220)
        self.setMouseTracking(True)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8); main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addSpacing(20)

        icon_display_size = 80
        base64_svg = self.mod_manager.ICON_NONE; svg_data = base64.b64decode(base64_svg); svg_str = svg_data.decode('utf-8')
        highlight_color = self.palette().color(QPalette.ColorRole.Highlight); color_to_use = highlight_color.darker(120)
        colored_svg_str = svg_str.replace('currentColor', color_to_use.name()); qt_svg_data = QByteArray(colored_svg_str.encode('utf-8'))
        renderer = QSvgRenderer(qt_svg_data)
        target_pixmap = QPixmap(icon_display_size, icon_display_size); target_pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(target_pixmap); renderer.render(painter); painter.end()
        icon_label = QLabel(); icon_label.setFixedSize(icon_display_size, icon_display_size); icon_label.setPixmap(target_pixmap)
        main_layout.addWidget(icon_label); main_layout.addStretch()

        self.name_label = QLabel(self.translator.translate("text_none"))
        self.name_label.setStyleSheet("font-size: 11pt; font-weight: bold;"); self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label = QLabel(f"<i>({self.translator.translate('text_deactivated')})</i>") 
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.name_label); main_layout.addWidget(self.status_label); main_layout.addSpacing(40)
    
    def set_active(self, active):
        if self.is_active != active:
            self.is_active = active
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.is_hovered and not self.is_active:
            highlight_color = self.palette().color(QPalette.ColorRole.Highlight)
            highlight_color.setAlpha(40) 
            brush_to_use = QBrush(highlight_color)
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()), 8, 8)
            painter.fillPath(path, brush_to_use)
        if self.is_active:
            highlight_color = self.palette().color(QPalette.ColorRole.Highlight)
            pen = QPen(highlight_color)
            pen.setWidth(3)
            painter.setPen(pen)
            
            rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
            painter.drawRoundedRect(rect, 8, 8)

    def enterEvent(self, event):
        self.is_hovered = True; self.update(); super().enterEvent(event)

    def leaveEvent(self, event):
        self.is_hovered = False; self.update(); super().leaveEvent(event)
        
    def update_text_color(self):
        text_widgets = self.findChildren(QLabel)
        if self.is_active:
            highlight_color = self.palette().color(QPalette.ColorRole.Highlight)
            text_color_name = highlight_color.name()
            for widget in text_widgets: widget.setStyleSheet(f"color: {text_color_name}; background-color: transparent;")
        else:
            for widget in text_widgets:
                current_style = widget.styleSheet()
                new_style = re.sub(r'color:\s*#[0-9a-fA-F]+;', '', current_style)
                widget.setStyleSheet(new_style)

class ModManager(QMainWindow):
    ICON_ADD = "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxsaW5lIHgxPSIxMiIgeTE9IjUiIHgyPSIxMiIgeTI9IjE5Ii8+PGxpbmUgeDE9IjUiIHkxPSIxMiIgeDI9IjE5IiB5Mj0iMTIiLz48L3N2Zz4="
    ICON_EDIT = "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxwYXRoIGQ9Ik0xMiAzSDVhMiAyIDAgMCAwLTIgMnYxNGEyIDIgMCAwIDAgMiAyaDE0YTIgMiAwIDAgMCAyLTJ2LTciLz48cGF0aCBkPSJNMTguMzcgMi42M2EyLjEyMSAyLjEyMSAwIDAgMSAzIDNMMTIgMTVsLTQgMSAxLTQgOS4zNy05LjM3eiIvPjwvc3ZnPg=="
    ICON_REMOVE = "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxwYXRoIGQ9Ik0zIDZoMTgiLz48cGF0aCBkPSJNMTkgNnYxNGEyIDIgMCAwIDEtMiAySDdhMiAyIDAgMCAxLTItMlY2aDE0WiIvPjxwYXRoIGQ9Ik0xMCAxMXY2Ii8+PHBhdGggZD0iTTE0IDExdjYiLz48L3N2Zz4="
    ICON_URL = "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxjaXJjbGUgY3g9IjEyIiBjeT0iMTIiIHI9IjEwIj48L2NpcmNsZT48bGluZSB4MT0iMiIgeTE9IjEyIiB4Mj0iMjIiIHkyPSIxMiI+PC9saW5lPjxwYXRoIGQ9Ik0xMiAyYTE1LjMgMTUuMyAwIDAgMSA0IDEwIDE1LjMgMTUuMyAwIDAgMS00IDEwIDE1LjMgMTUuMyAwIDAgMS00LTEwIDE1LjMgMTUuMyAwIDAgMSA0LTEweiI+PC9wYXRoPjwvc3ZnPg=="
    ICON_UPDATE = "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxwb2x5bGluZSBwb2ludHM9IjIzIDQgMjMgMTAgMTcgMTAiPjwvcG9seWxpbmU+PHBvbHlsaW5lIHBvaW50cz0iMSAyMCAxIDE0IDcgMTQiPjwvcG9seWxpbmU+PHBhdGggZD0iTTMuNTEgOWE5IDkgMCAwIDEgMTQuODUtMy4zNkwyMyAxME0xIDE0bDQuNjQgNC4zNkE5IDkgMCAwIDAgMjAuNDkgMTUiPjwvcGF0aD48L3N2Zz4="
    ICON_NONE = "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxjaXJjbGUgY3g9IjEyIiBjeT0iMTIiIHI9IjEwIj48L2NpcmNsZT48bGluZSB4MT0iMTUiIHkxPSI5IiB4Mj0iOSIgeTI9IjE1Ij48L2xpbmU+PGxpbmUgeDE9IjkiIHkxPSI5IiB4Mj0iMTUiIHkyPSIxNSI+PC9saW5lPjwvc3ZnPg=="
    ICON_SEARCH = "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxjaXJjbGUgY3g9IjExIiBjeT0iMTEiIHI9IjgiPjwvY2lyY2xlPjxsaW5lIHgxPSIyMSIgeTE9IjIxIiB4Mj0iMTYuNjUiIHkyPSIxNi42NSI+PC9saW5lPjwvc3ZnPg=="
    ICON_LIKE = "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZHRoPSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxwYXRoIGQ9Ik0xNCA5VjVhMyAzIDAgMCAwLTMtM2wtNCA5djExaDExLjI4YTIgMiAwIDAgMCAyLTEuN2wxLjM4LTlhMiAyIDAgMCAwLTItMi4zeiI+PC9wYXRoPjxwYXRoIGQ9Ik03IDIyaC0zYTIgMiAwIDAgMS0yLTJ2LTdhMiAyIDAgMCAxIDItMmgzIj48L3BhdGg+PC9zdmc+"
    ICON_DOWNLOAD = "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZHRoPSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxwYXRoIGQ9Ik0yMSAxNXY0YTIgMiAwIDAgMS0yIDJINWEyIDIgMCAwIDEtMi0ydi00Ij48L3BhdGg+PHBvbHlsaW5lIHBvaW50cz0iNyAxMCAxMiAxNSAxNyAxMCI+PC9wb2x5bGluZT48bGluZSB4MT0iMTIiIHkxPSIxNSIgeDI9IjEyIiB5Mj0iMyI+PC9saW5lPjwvc3ZnPg=="
    ICON_VIEWS = "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZHRoPSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxwYXRoIGQ9Ik0xIDEycy41LTggMTEtOCAxMSA4IDExIDgtLjUtOC0xMS04LTExIDgtMTEgOHoiPjwvcGF0aD48Y2lyY2xlIGN4PSIxMiIgY3k9IjEyIiByPSIzIj48L2NpcmNsZT48L3N2Zz4="

    def __init__(self,  startup_url=None):
        super().__init__()
        self._ensure_protocol_is_registered()
        self.app_root_path = os.path.dirname(os.path.abspath(sys.argv[0]))
        translations_path = resource_path(os.path.join("lib", "lang"))
        self.user_icons_path = resource_path("icons") 
        self.app_data_path = os.path.join(os.getenv('APPDATA'), "MIMM")
        os.makedirs(self.app_data_path, exist_ok=True)
        self.icons_cache_path = os.path.join(self.app_data_path, "icons_cache")
        os.makedirs(self.icons_cache_path, exist_ok=True)
        self.translator = Translator(translations_path)
        self.config = self.load_config()
        if "language" not in self.config:
            try:
                system_lang, _ = locale.getdefaultlocale()
                lang_code = system_lang.split('_')[0].lower() 
                
                supported_languages = ['es', 'en', 'pt', 'zh']
                if lang_code in supported_languages:
                    initial_lang = lang_code
                    print(f"Idioma del sistema detectado y soportado: '{initial_lang}'")
                else:
                    initial_lang = 'en' 
                    print(f"Idioma del sistema '{lang_code}' no soportado. Usando 'en' por defecto.")

            except Exception as e:
                print(f"No se pudo detectar el idioma del sistema: {e}. Usando 'en' por defecto.")
                initial_lang = 'en'
            
            self.config['language'] = initial_lang
            self.save_config()
        
        else:
            initial_lang = self.config.get("language")

        self.translator.set_language(initial_lang)
        self.translator.language_changed.connect(self.retranslate_ui)
        self.setWindowTitle(self.translator.translate("window_title"))
        self.setGeometry(100, 100, 1335, 700)
        self.default_icon_path = os.path.join(self.user_icons_path, "Others", "default.png")
        self.xxmi_path = self.find_xxmi_path()
        self.management_folder_name = ".MIMM"
        self.root_namespace = "MIMM"
        self.game_data = {
            "Genshin Impact": { "folder": "GIMI", "short_name": "GI", "game_id": 8552, "categories": {
                "Personajes": {"t_key": "category_characters", "type": "api", "id": 18140},
                "Armas": {"t_key": "category_weapons", "type": "manual_icon", "api_id": 18137},
                "Otros": {"t_key": "category_others", "type": "direct_management", "api_id": 12526, "sub_categories": [
                    {"name": "UI", "t_key": "category_sub_ui", "id": 22474},
                    {"name": "Objetos", "t_key": "category_sub_objects", "id": 18310},
                    {"name": "Entidades", "t_key": "category_sub_entities", "id": 22725},
                    {"name": "Gadget", "t_key": "category_sub_gadget", "id": 23574},
                    {"name": "Waverider", "t_key": "category_sub_waverider", "id": 24279}
                ]}
            }},
            "Honkai: Star Rail": { "folder": "SRMI", "short_name": "HSR", "game_id": 18366, "categories": {
                "Personajes": {"t_key": "category_characters", "type": "api", "id": 22832},
                "Armas": {"t_key": "category_weapons", "type": "manual_icon", "api_id": 22833},
                "Otros": {"t_key": "category_others", "type": "direct_management", "api_id": 22628, "sub_categories": [
                    {"name": "UI", "t_key": "category_sub_ui", "id": 22830},
                    {"name": "Objetos", "t_key": "category_sub_objects", "id": 22829}
                ]}
            }},
            "Wuthering Waves": { "folder": "WWMI", "short_name": "WW", "game_id": 20357, "categories": {
                "Personajes": {"t_key": "category_characters", "type": "api", "id": 29524},
                "Otros": {"t_key": "category_others", "type": "direct_management", "api_id": 29493, "sub_categories": [
                    {"name": "UI", "t_key": "category_sub_ui", "id": 29496}
                ]}
            }},
            "Zenless Zone Zero": { "folder": "ZZMI", "short_name": "ZZZ", "game_id": 19567, "categories": {
                "Personajes": {"t_key": "category_characters", "type": "api", "id": 30305},
                "Bangboos": {"t_key": "category_bangboos", "type": "api", "id": 30702},
                "Otros": {"t_key": "category_others", "type": "direct_management", "api_id": 29874, "sub_categories": [
                    {"name": "UI", "t_key": "category_sub_ui", "id": 30395}
                ]}
            }}
        }
        for game in self.game_data.values():
            os.makedirs(os.path.join(self.user_icons_path, game['short_name']), exist_ok=True)
        os.makedirs(os.path.join(self.user_icons_path, "Others"), exist_ok=True)
        os.makedirs(os.path.join(self.user_icons_path, "Games"), exist_ok=True)
        self.profiles = self.load_profiles()
        self.current_game = ""
        self.current_category = None
        self.category_widgets = {}
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QHBoxLayout(self.central_widget)
        self.setup_ui()
        self.overlay_controller = OverlayController(self, self.translator)
        self.overlay_controller.mod_state_changed_from_overlay.connect(self.on_mod_state_changed_from_overlay)
        self.is_quitting = False
        self._setup_tray_icon()
        self.command_file_path = os.path.join(self.app_data_path, "mimm_command.lock")
        self.command_check_timer = QTimer(self)
        self.command_check_timer.timeout.connect(self._check_for_command_file)
        self.command_check_timer.start(1500) 
        if not self.xxmi_path: self.show_path_error()
        else:
            first_game_button = self.game_button_group.buttons()[0]
            first_game_button.setChecked(True)
            self.on_game_button_clicked(first_game_button)
        if startup_url:
            print(f"ModManager inicializado con una URL: {startup_url}. Esperando para procesar...")
            QTimer.singleShot(250, lambda: self.process_startup_url(startup_url))

    def _sanitize_filename(self, name): return re.sub(r'[\\/*?:"<>|]', "", name)

    def _create_colored_icon(self, base64_svg, color):
        svg_data = base64.b64decode(base64_svg)
        svg_str = svg_data.decode('utf-8')
        
        colored_svg_str = svg_str.replace('currentColor', color.name())
        
        qt_svg_data = QByteArray(colored_svg_str.encode('utf-8'))
        pixmap = QPixmap()
        pixmap.loadFromData(qt_svg_data, 'svg')
        
        return QIcon(pixmap)
    
    def update_xxmi_path(self, new_path):
        if os.path.isdir(new_path):
            self.config["xxmi_path"] = new_path
            self.save_config()
            self.xxmi_path = new_path
            QMessageBox.information(self, "Ruta Actualizada", "La ruta de XXMI Launcher ha sido actualizada.")
        else:
            QMessageBox.warning(self, "Ruta Inválida", "La ruta seleccionada no es un directorio válido.")

    def _check_for_one_click_command(self):
        if not os.path.exists(self.command_file_path):
            return
        try:
            with open(self.command_file_path, 'r') as f:
                url = f.read().strip()
            os.remove(self.command_file_path)

            if not url.startswith("MIMM:"):
                return
            
            print(f"Comando 1-Click detectado: {url}")

            match = re.search(r'mmdl/(\d+),Mod,(\d+)', url)
            if match:
                file_id, mod_id = match.groups()
                self.showNormal()
                self.activateWindow()
                
                dialog = OneClickInstallDialog(mod_id, file_id, self)
                dialog.exec()

        except Exception as e:
            print(f"Error procesando el archivo de comando 1-Click: {e}")
            if os.path.exists(self.command_file_path):
                os.remove(self.command_file_path) 

    def retranslate_ui(self):
        self.setWindowTitle(self.translator.translate("window_title"))
        self.game_title_label.setText(self.translator.translate("select_game_title"))
        self.category_title_label.setText(self.translator.translate("categories_title"))
        self.add_profile_button.setToolTip(self.translator.translate("add_profile_tooltip"))
        self.edit_profile_button.setToolTip(self.translator.translate("edit_profile_tooltip"))
        self.remove_profile_button.setToolTip(self.translator.translate("remove_profile_tooltip"))
        if self.current_game:
            self.update_category_ui(self.current_game)
        if hasattr(self, 'tray_menu_actions'):
            for key, action in self.tray_menu_actions.items():
                action.setText(self.translator.translate(key))
        if self.right_panel.currentWidget():
            list_widget = self.profile_list_stack.currentWidget()
            if list_widget and list_widget.currentItem():
                self.display_profile_mods(list_widget.currentItem())

    def setup_ui(self):
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_panel.setFixedWidth(371)
        self.game_title_label = QLabel(self.translator.translate("select_game_title"))
        self.game_title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        left_layout.addWidget(self.game_title_label)
        self.game_buttons_widget = QWidget()
        game_buttons_layout = QHBoxLayout(self.game_buttons_widget)
        game_buttons_layout.setContentsMargins(0,0,0,0)
        self.game_button_group = QButtonGroup(self)
        self.game_button_group.setExclusive(True)
        self.game_button_group.buttonClicked.connect(self.on_game_button_clicked)
        game_icons_path = os.path.join(self.user_icons_path, "Games")
        highlight_color = self.palette().color(QPalette.ColorRole.Highlight)
        luminance = 0.2126 * highlight_color.redF() + 0.7152 * highlight_color.greenF() + 0.0722 * highlight_color.blueF()
        text_color_on_highlight = "#000000" if luminance > 0.5 else "#FFFFFF"
        game_button_style = f"""
            QPushButton {{
                background-color: transparent; border-radius: 8px; outline: none;
            }}
            QPushButton:hover {{
                background-color: rgba({highlight_color.red()}, {highlight_color.green()}, {highlight_color.blue()}, 40);
                border: 2px solid {highlight_color.name()};
            }}
            QPushButton:checked {{
                background-color: {highlight_color.name()}; border: 1px solid {highlight_color.name()};
                color: {text_color_on_highlight};
            }}
            QPushButton:pressed {{
                background-color: rgba({highlight_color.red()}, {highlight_color.green()}, {highlight_color.blue()}, 80);
            }}
        """
        for name, data in self.game_data.items():
            button = QPushButton()
            button.setCheckable(True)
            button.setProperty("game_name", name)
            button.setToolTip(name)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(game_button_style)
            icon_path = next((os.path.join(game_icons_path, f"{data['short_name']}{ext}") for ext in ['.png', '.jpg', '.jpeg'] if os.path.exists(os.path.join(game_icons_path, f"{data['short_name']}{ext}"))), None)
            if icon_path:
                button.setIcon(QIcon(icon_path)); button.setIconSize(QSize(50, 50)); button.setFixedSize(QSize(83, 65))
            else:
                button.setText(data['short_name']); button.setFixedSize(QSize(83, 65))
            self.game_button_group.addButton(button)
            game_buttons_layout.addWidget(button)
        game_buttons_layout.addStretch()
        left_layout.addWidget(self.game_buttons_widget)
        separator = QFrame(); separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet(f"border: 1px solid {highlight_color.name()}; background-color: {highlight_color.name()};")
        separator.setFixedHeight(1); separator.setContentsMargins(0, 10, 0, 10)
        left_layout.addWidget(separator)
        self.category_title_label = QLabel(self.translator.translate("categories_title"))
        self.category_title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        left_layout.addWidget(self.category_title_label)
        self.category_buttons_widget = QWidget()
        self.category_buttons_layout = QHBoxLayout(self.category_buttons_widget)
        self.category_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.category_button_group = QButtonGroup(self)
        self.category_button_group.setExclusive(True)
        self.category_button_group.buttonClicked.connect(self.on_category_button_clicked)
        self.profile_list_stack = QStackedWidget()
        button_size, icon_size = 50, 34
        hover_color = highlight_color.lighter(130)
        button_stylesheet = f"""
            QPushButton {{ outline: none; background-color: transparent; border-radius: {button_size // 2}px; }}
            QPushButton:hover {{ border: 2px solid; border-color: {hover_color.name(QColor.NameFormat.HexArgb)}; }}
            QPushButton:pressed {{ border-color: {highlight_color.name(QColor.NameFormat.HexArgb)}; }}
        """
        self.add_profile_button = QPushButton()
        self.add_profile_button.setToolTip(self.translator.translate("add_profile_tooltip"))
        self.add_profile_button.setIcon(self._create_colored_icon(self.ICON_ADD, highlight_color))
        self.add_profile_button.clicked.connect(self.add_profile)
        self.edit_profile_button = QPushButton()
        self.edit_profile_button.setToolTip(self.translator.translate("edit_profile_tooltip"))
        self.edit_profile_button.setIcon(self._create_colored_icon(self.ICON_EDIT, highlight_color))
        self.edit_profile_button.clicked.connect(self.edit_profile)
        self.remove_profile_button = QPushButton()
        self.remove_profile_button.setToolTip(self.translator.translate("remove_profile_tooltip"))
        self.remove_profile_button.setIcon(self._create_colored_icon(self.ICON_REMOVE, highlight_color))
        self.remove_profile_button.clicked.connect(self.remove_profile)
        for btn in [self.add_profile_button, self.edit_profile_button, self.remove_profile_button]:
            btn.setFixedSize(button_size, button_size)
            btn.setIconSize(QSize(icon_size, icon_size))
            btn.setStyleSheet(button_stylesheet)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
        left_layout.addWidget(self.category_buttons_widget)
        left_layout.addWidget(self.profile_list_stack)
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.add_profile_button)
        buttons_layout.addWidget(self.edit_profile_button)
        buttons_layout.addWidget(self.remove_profile_button)
        buttons_layout.addStretch()
        left_layout.addLayout(buttons_layout)
        self.right_panel = QStackedWidget()
        self.layout.addWidget(left_panel)
        self.layout.addWidget(self.right_panel)

    def find_xxmi_path(self):
        saved_path = self.config.get("xxmi_path")
        if saved_path and os.path.isdir(saved_path): return saved_path
        auto_path = self.scan_common_locations()
        if auto_path: self.config["xxmi_path"] = auto_path; self.save_config(); return auto_path
        reply = QMessageBox.information(self, self.translator.translate("title_initial_setup"), self.translator.translate("msg_xxmi_not_found"), QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        if reply == QMessageBox.StandardButton.Ok:
            user_path = QFileDialog.getExistingDirectory(self, self.translator.translate("title_select_xxmi_folder"))
            if user_path and os.path.isdir(user_path): self.config["xxmi_path"] = user_path; self.save_config(); return user_path
        return None
        
    def scan_common_locations(self):
        target_folder = "XXMI Launcher"
        path_vars = ['LOCALAPPDATA', 'APPDATA', 'ProgramFiles', 'ProgramFiles(x86)']
        for var in path_vars:
            path = os.getenv(var)
            if path and os.path.isdir(path):
                full_path = os.path.join(path, target_folder)
                if os.path.isdir(full_path) and os.path.isdir(os.path.join(full_path, "GIMI")): return full_path
        return None

    def show_path_error(self):
        QMessageBox.critical(self, self.translator.translate("title_error"), self.translator.translate("msg_invalid_xxmi_path"))
        sys.exit()
    
    def on_game_button_clicked(self, button):
        game_name = button.property("game_name")
        if game_name and game_name != self.current_game: self.on_game_changed(game_name)
    
    def on_game_changed(self, game_name):
        self.current_game = game_name; self.setup_nrmm_structure(game_name); self.update_category_ui(game_name)

    def on_category_button_clicked(self, button):
        category_key = button.property("category_key")
        if category_key == self.current_category: return
        self.current_category = category_key
        list_widget = self.category_widgets[category_key]['list']
        self.profile_list_stack.setCurrentWidget(list_widget)
        self.update_profile_list()

    def edit_direct_mod_info(self, profile_name, mod_info):
        dialog = ModInfoDialog(mod_info, self)
        if dialog.exec():
            details = dialog.get_details()
            profile = self.profiles[self.current_game][self.current_category][profile_name]
            for i, mod in enumerate(profile["mods"]):
                if mod["folder_name"] == mod_info["folder_name"]:
                    profile["mods"][i]["display_name"] = details["display_name"] or mod_info["name"]
                    profile["mods"][i]["creator"] = details["creator"]
                    profile["mods"][i]["url"] = details["url"]
                    if details["icon_source_path"] and details["icon_source_path"] != mod_info.get("icon"):
                        new_icon_path = self._copy_icon_to_cache(details["icon_source_path"], f"mod_{profile_name}_{mod_info['folder_name']}")
                        old_icon = mod_info.get('icon')
                        if old_icon and os.path.exists(old_icon) and self.icons_cache_path in old_icon:
                            os.remove(old_icon)
                        profile["mods"][i]["icon"] = new_icon_path
                    break
            self.save_profiles()
            self.update_direct_mods_list_cards(profile_name)

    def update_category_ui(self, game_name):
        previously_selected_key = self.current_category
        for button in self.category_button_group.buttons():
            self.category_button_group.removeButton(button)
            button.deleteLater()
        while self.profile_list_stack.count() > 0:
            widget = self.profile_list_stack.widget(0)
            self.profile_list_stack.removeWidget(widget)
            widget.deleteLater()
        self.category_widgets.clear()
        highlight_color = self.palette().color(QPalette.ColorRole.Highlight)
        luminance = 0.2126 * highlight_color.redF() + 0.7152 * highlight_color.greenF() + 0.0722 * highlight_color.blueF()
        text_color_on_highlight = "#000000" if luminance > 0.5 else "#FFFFFF"
        category_button_style = f"""
            QPushButton {{ background-color: transparent; color: {highlight_color.darker(120).name()}; border-radius: 8px; padding: 6px 16px; font-size: 10pt; outline: none; font-weight: bold; }}
            QPushButton:hover {{ border: 2px solid {highlight_color.name()}; }}
            QPushButton:checked {{ background-color: {highlight_color.name()}; color: {text_color_on_highlight}; border-color: {highlight_color.name()}; font-weight: bold; }}
        """
        categories = self.game_data[game_name]["categories"]
        button_to_select = None
        for original_name, data in categories.items():
            translated_name = self.translator.translate(data['t_key'])
            button = QPushButton(translated_name)
            button.setProperty("category_key", original_name)
            button.setCheckable(True)
            button.setFixedHeight(35)
            button.setStyleSheet(category_button_style)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            if original_name == previously_selected_key:
                button_to_select = button
            self.category_buttons_layout.addWidget(button)
            self.category_button_group.addButton(button)
            list_widget = QListWidget()
            list_widget.setSpacing(15); list_widget.setViewMode(QListView.ViewMode.IconMode); list_widget.setMovement(QListView.Movement.Static)
            list_widget.setResizeMode(QListView.ResizeMode.Adjust); list_widget.setUniformItemSizes(True); list_widget.currentItemChanged.connect(self.display_profile_mods)
            self.profile_list_stack.addWidget(list_widget)
            self.category_widgets[original_name] = {"list": list_widget, "type": data["type"]} 
        self.current_category = None
        if not button_to_select and self.category_button_group.buttons():
            button_to_select = self.category_button_group.buttons()[0]
        if button_to_select:
            button_to_select.setChecked(True)
            self.on_category_button_clicked(button_to_select)

    def update_profile_list(self, select_profile_name=None):
        if not self.current_game or not self.current_category: return
        list_widget = self.category_widgets[self.current_category]['list']
        list_widget.blockSignals(True)
        name_to_select = select_profile_name
        if not name_to_select and list_widget.currentItem():
            name_to_select = list_widget.currentItem().data(Qt.ItemDataRole.UserRole)
        list_widget.clear()
        while self.right_panel.count() > 0:
            widget = self.right_panel.widget(0)
            self.right_panel.removeWidget(widget)
            widget.deleteLater()
        game_profiles = self.profiles.setdefault(self.current_game, {})
        category_profiles = game_profiles.setdefault(self.current_category, {})
        category_type = self.category_widgets[self.current_category]['type']
        sorted_profiles = sorted(category_profiles.items())
        item_to_select = None
        for name, profile_data in sorted_profiles:
            icon_path = profile_data.get('icon') or self.default_icon_path
            if not (icon_path and os.path.exists(icon_path)):
                icon_path = self.default_icon_path
            profile_widget = ProfileItemWidget(icon_path, name)
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, name) 
            item.setSizeHint(QSize(92, 120)) 
            list_widget.addItem(item)
            list_widget.setItemWidget(item, profile_widget)
            if name == name_to_select:
                item_to_select = item
        list_widget.blockSignals(False)
        if item_to_select:
            list_widget.setCurrentItem(item_to_select)
        elif list_widget.count() > 0:
            list_widget.setCurrentRow(0)
        else:
            self.display_profile_mods(None)

    def fetch_gamebanana_data(self, category_id):
        if not requests:
            self.show_message(self.translator.translate("title_error"), self.translator.translate("msg_requests_required"), "critical")
            return None
        url = f"https://gamebanana.com/apiv11/Mod/Categories?&_idCategoryRow={category_id}&_sSort=a_to_z"
        headers = {'User-Agent': 'MIMM/1.0'}
        try:
            response = requests.get(url, timeout=15, headers=headers); response.raise_for_status()
            items, data = [], response.json()
            game_short_name = self.game_data[self.current_game]['short_name']
            game_icon_folder = os.path.join(self.user_icons_path, game_short_name)
            name_to_exclude = "NPCs & Entities"
            for item in data:
                name = item.get('_sName')
                if not name: continue
                if name.strip() == name_to_exclude:
                    continue
                local_icon_path = next((os.path.join(game_icon_folder, f"{name}{ext}") for ext in ['.png', '.jpg', '.jpeg', '.webp'] if os.path.exists(os.path.join(game_icon_folder, f"{name}{ext}"))), None)
                items.append({ "name": name, "icon_path": local_icon_path, "id": item.get('_idRow') })
            return items
        except json.JSONDecodeError:
            self.show_message(self.translator.translate("title_api_error"), self.translator.translate("msg_api_invalid_json"), "critical")
            return None
        except requests.RequestException as e:
            self.show_message(self.translator.translate("title_network_error"), self.translator.translate("msg_api_fetch_list_failed", e=e), "critical")
            return None

    def add_profile(self):
        category_type = self.category_widgets[self.current_category]['type']
        category_profiles = self.profiles.setdefault(self.current_game, {}).setdefault(self.current_category, {})
        newly_created_profile_name = None
        if category_type == 'api':
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                api_id = self.game_data[self.current_game]['categories'][self.current_category]['id']
                items = self.fetch_gamebanana_data(api_id)
                if not items: return
            finally: QApplication.restoreOverrideCursor()

            api_dialog = ApiSelectionDialog(items, self.default_icon_path, self)
            if api_dialog.exec():
                selected = api_dialog.get_selected_item()
                if selected and selected['name'] not in category_profiles:
                    source_icon_path = selected.get('icon_path')
                    final_icon_path = None 
                    should_create = True
                    if not source_icon_path:
                        reply = QMessageBox.question(self, self.translator.translate("title_no_local_icon"), self.translator.translate("msg_no_icon_found_prompt", name=selected['name']), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                        if reply == QMessageBox.StandardButton.Yes:
                            dialog = ProfileDialog(profile_name=selected['name'], is_name_editable=False, parent=self)
                            if dialog.exec():
                                details = dialog.get_details()
                                final_icon_path = self._copy_icon_to_cache(details['icon_source_path'], details['name'])
                            else:
                                should_create = False
                    else:
                        final_icon_path = self._copy_icon_to_cache(source_icon_path, selected['name'])
                    
                    if should_create:
                        self.create_managed_profile(selected['name'], final_icon_path, category_id=selected.get('id'))
                        newly_created_profile_name = selected['name']

        elif category_type in ['manual_icon', 'direct_management']:
            dialog = ProfileDialog(is_name_editable=True, parent=self)
            if dialog.exec():
                details = dialog.get_details()
                name = details['name']
                if not name: self.show_message(self.translator.translate("title_empty_name"), self.translator.translate("msg_name_cannot_be_empty"), "warning"); return
                if name in category_profiles: self.show_message(self.translator.translate("title_duplicate_name"), self.translator.translate("msg_profile_name_exists", name=name), "warning"); return
                icon_path = self._copy_icon_to_cache(details['icon_source_path'], name)
                if category_type == 'manual_icon': 
                    self.create_managed_profile(name, icon_path)
                else:
                    category_profiles[name] = {"mods": [], "icon": icon_path}
                    self.save_profiles()
                newly_created_profile_name = name
        if newly_created_profile_name:
            self.update_profile_list(select_profile_name=newly_created_profile_name)

    def edit_profile(self):
        list_widget = self.profile_list_stack.currentWidget()
        current_item = list_widget.currentItem()
        if not list_widget or not current_item:
            self.show_message(self.translator.translate("title_no_selection"), self.translator.translate("msg_select_profile_to_edit"))
            return
        name = current_item.data(Qt.ItemDataRole.UserRole)
        if not name: return
        category_type = self.category_widgets[self.current_category]['type']
        is_name_editable = category_type in ['manual_icon', 'direct_management']

        profile_data = self.profiles[self.current_game][self.current_category][name]
        
        dialog = ProfileDialog(
            profile_name=name, 
            is_name_editable=is_name_editable, 
            current_icon_path=profile_data.get('icon'), 
            parent=self
        )

        if dialog.exec():
            details = dialog.get_details()
            new_name = details['name']
            
            category_profiles = self.profiles[self.current_game][self.current_category]

            if is_name_editable and new_name != name:
                if not new_name:
                    self.show_message(self.translator.translate("title_empty_name"), self.translator.translate("msg_name_cannot_be_empty"), "warning")
                    return
                if new_name in category_profiles:
                    self.show_message(self.translator.translate("title_duplicate_name"), self.translator.translate("msg_profile_name_exists", name=new_name), "warning")
                    return
                if category_type == 'manual_icon':
                    try:
                        management_path = self.get_management_path(self.current_game)
                        old_folder_path = os.path.join(management_path, profile_data['folder_name'])
                        
                        new_folder_name = self._sanitize_filename(new_name)
                        new_folder_path = os.path.join(management_path, new_folder_name)

                        if os.path.exists(old_folder_path):
                            os.rename(old_folder_path, new_folder_path)
                            profile_data['folder_name'] = new_folder_name
                            for mod_info in profile_data.get('mods', []):
                                mod_folder_name = os.path.basename(mod_info['path'])
                                for root, _, files in os.walk(os.path.join(new_folder_path, mod_folder_name)):
                                    for file in files:
                                        if file.lower().endswith('.ini'):
                                            self._rewrite_ini_file(os.path.join(root, file), mod_info['slot_id'], new_folder_name, mod_folder_name)
                        
                    except OSError as e:
                        self.show_message(self.translator.translate("title_file_error"), self.translator.translate("msg_rename_folder_failed", e=e), "critical")
                        return
                category_profiles[new_name] = profile_data
                del category_profiles[name]
                name = new_name 

            if details['icon_source_path']:
                new_icon_path = self._copy_icon_to_cache(details['icon_source_path'], name) 
                if new_icon_path and new_icon_path != profile_data.get('icon'):
                    old_icon = profile_data.get('icon')
                    if old_icon and os.path.exists(old_icon) and self.icons_cache_path in old_icon:
                        os.remove(old_icon)
                    profile_data['icon'] = new_icon_path
            self.save_profiles()
            self.update_profile_list(select_profile_name=name)

    def _save_image_content_to_cache(self, image_content, profile_name, mod_name):
        if not image_content:
            return None
        try:
            ext = ".png" 
            final_name = self._sanitize_filename(f"mod_{profile_name}_{mod_name}_{int(time.time())}{ext}")
            final_path = os.path.join(self.icons_cache_path, final_name)
            with open(final_path, 'wb') as f:
                f.write(image_content)
            return final_path
        except Exception as e:
            print(f"No se pudo guardar el contenido del icono en la caché: {e}")
            return None

    def create_managed_profile(self, name, icon_path=None, category_id=None, update_ui=True):
        management_path = self.get_management_path(self.current_game)
        if not management_path:
            return False
            
        folder_name = self._sanitize_filename(name)
        character_path = os.path.join(management_path, folder_name)

        if os.path.exists(character_path):
            self.show_message(self.translator.translate("title_error"), self.translator.translate("msg_profile_folder_exists"))
            return False

        try:
            profile_id = self._get_next_available_profile_id(self.current_game)
            os.makedirs(character_path, exist_ok=True)
            ini_content = (f"; MIMM Config for: {name}\n" f"namespace = {self.root_namespace}\\{folder_name}\n\n" "[Constants]\n" "persist global $active_slot = 0\n" f"global $profile_id = {profile_id}\n\n" "[KeyMod]\n" f"condition = $profile_id == $\\{self.root_namespace}\\profile_manager\\active_profile_id\n" "key = VK_CLEAR VK_RETURN\n" "run = CommandListMod\n\n" "[CommandListMod]\n" "$active_slot = cursor_screen_x\n")
            with open(os.path.join(character_path, "MIMM_Profile.ini"), "w") as f: f.write(ini_content)
            
            self.profiles[self.current_game][self.current_category][name] = { "mods": [], "active_mod": None, "profile_id": profile_id, "folder_name": folder_name, "icon": icon_path, "category_id": category_id }
            
            self.save_profiles()
            if update_ui:
                self.update_profile_list()
                
            return True
        except Exception as e:
            print(f"Error al crear perfil gestionado '{name}': {e}")
            return False

    def create_direct_profile(self, name, icon_path=None, update_ui=True):
        try:
            if not self.current_game or not self.current_category:
                print("ERROR: No se puede crear un perfil directo sin un juego/categoría actual.")
                return False

            category_profiles = self.profiles.setdefault(self.current_game, {}).setdefault(self.current_category, {})

            if name in category_profiles:
                print(f"Advertencia: El perfil directo '{name}' ya existe.")
                return True

            category_profiles[name] = {"mods": [], "icon": icon_path}
            self.save_profiles()
            
            if update_ui:
                self.update_profile_list()
            
            return True
        except Exception as e:
            print(f"ERROR al crear perfil directo '{name}': {e}")
            return False
        
    def focus_on_profile(self, game_name, category_key, profile_name):

        print(f"Enfocando UI en: {game_name} -> {category_key} -> {profile_name}")

        game_button_to_select = next((b for b in self.game_button_group.buttons() if b.property("game_name") == game_name), None)
        if not game_button_to_select:
            print(f"Error de enfoque: No se encontró el botón para el juego '{game_name}'.")
            return
        if not game_button_to_select.isChecked():
            game_button_to_select.setChecked(True)

        def force_correct_category_and_profiles():
            category_button_to_select = next((b for b in self.category_button_group.buttons() if b.property("category_key") == category_key), None)
            if not category_button_to_select:
                print(f"Error de enfoque: No se encontró el botón para la categoría '{category_key}'.")
                return
            
            self.current_category = category_key

            category_button_to_select.blockSignals(True)
            category_button_to_select.setChecked(True)
            category_button_to_select.blockSignals(False)

            correct_list_widget = self.category_widgets[category_key]['list']
            self.profile_list_stack.setCurrentWidget(correct_list_widget)

            self.update_profile_list(select_profile_name=profile_name)

        QTimer.singleShot(50, force_correct_category_and_profiles)

    def _rewrite_ini_file(self, ini_path, slot_id, character_folder_name, mod_folder_name):
        try:
            with open(ini_path, 'r', encoding='utf-8', errors='ignore') as f: content = f.read()
        except FileNotFoundError: return
        state_vars = set(re.findall(r'\[Key.*?^\s*(\$[a-zA-Z0-9_]+)\s*=', content, re.MULTILINE | re.IGNORECASE))
        default_values = { match.group(1): match.group(0) for var in state_vars for match in re.finditer(r'^\s*(?:persist\s+global|global|persist)\s+(' + re.escape(var) + r')\s*=\s*.*?$', content, re.MULTILINE | re.IGNORECASE) }
        mod_prefix = self._sanitize_filename(mod_folder_name) + '_'
        for var in state_vars: content = re.sub(r'\b' + re.escape(var) + r'\b', f"${mod_prefix}{var[1:]}", content)
        lines = content.splitlines(True)
        sections, original_order, current_section = {}, [], 'global'
        sections.setdefault('global', []); original_order.append('global')
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('[') and stripped.endswith(']'):
                current_section = stripped
                if current_section not in sections: sections[current_section] = []; original_order.append(current_section)
            else: sections.setdefault(current_section, []).append(line)
        constants_section = '[Constants]'
        if constants_section not in sections: sections[constants_section] = []; original_order.insert(0, constants_section)
        sections[constants_section].insert(0, f"global $managed_slot_id = {slot_id}\n")
        for var, declaration in default_values.items():
            new_var = f"${mod_prefix}{var[1:]}"; new_declaration = declaration.replace(var, new_var)
            sections[constants_section].append(new_declaration + "\n")
        output = []
        for section_name in original_order:
            section_lines = sections[section_name]
            if section_name != 'global': output.append(section_name + '\n')
            s_lower = section_name.lower()
            handling_line = None
            new_section_lines = []
            for line in section_lines:
                if line.strip().lower() == 'handling = skip':
                    handling_line = line  
                else:
                    new_section_lines.append(line) 
            section_lines = new_section_lines 
            if s_lower.startswith('[key'):
                condition = f"condition = $managed_slot_id == $\\{self.root_namespace}\\{character_folder_name}\\active_slot\n"
                if any(l.strip().lower().startswith('condition') for l in section_lines):
                    section_lines = [l.strip() + f" && ($managed_slot_id == $\\{self.root_namespace}\\{character_folder_name}\\active_slot)\n" if l.strip().lower().startswith('condition') else l for l in section_lines]
                else: section_lines.insert(0, condition)
            excluded = s_lower.startswith(('[constants]', '[resource', '[customshader', '[commandlist', '[key'))
            if not excluded:
                output.append(f"if $managed_slot_id == $\\{self.root_namespace}\\{character_folder_name}\\active_slot\n")
                if handling_line:
                    output.append(handling_line)
                if "match_priority" not in ''.join(section_lines).lower(): output.append("match_priority = 0\n")
            output.extend(section_lines)
            if not excluded: output.append("endif\n")
            output.append('\n')
        with open(ini_path, 'w', encoding='utf-8', errors='ignore') as f: f.writelines(output)
            
    def remove_profile(self):
        list_widget = self.profile_list_stack.currentWidget(); current_item = list_widget.currentItem()
        if not list_widget or not current_item: return
        name = current_item.data(Qt.ItemDataRole.UserRole)
        if not name: return
        category_type = self.category_widgets[self.current_category]['type']
        
        question_text = self.translator.translate("msg_confirm_delete_profile", name=name)
        reply = QMessageBox.question(self, self.translator.translate("title_confirm"), question_text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes: return

        profile = self.profiles[self.current_game][self.current_category].get(name)
        if profile:
            try:
                os.chdir(self.app_root_path)
                print(f"DEBUG: Se ha restablecido el directorio de trabajo a: {os.getcwd()}")
            except Exception as e:
                print(f"ADVERTENCIA: No se pudo cambiar el directorio de trabajo: {e}")
            old_icon = profile.get('icon')
            if old_icon and os.path.exists(old_icon) and self.icons_cache_path in old_icon: os.remove(old_icon)
            if category_type != 'direct_management':
                management_path = self.get_management_path(self.current_game)
                profile_path = os.path.join(management_path, profile['folder_name'])
                
                if not self._safe_remove_directory(profile_path):
                    return
            else:
                mods_path = self.get_game_mods_path(self.current_game)
                for mod in profile.get("mods", []):
                    mod_path = os.path.join(mods_path, mod['folder_name'])
                    self._safe_remove_directory(mod_path)

        del self.profiles[self.current_game][self.current_category][name]
        self._simulate_f10_press()
        self.save_profiles(); self.update_profile_list()

    def _get_next_available_profile_id(self, game):
        used_ids = set()
        valid_categories = self.game_data.get(game, {}).get("categories", {})
        for category_name, profiles in self.profiles.get(game, {}).items():
            category_data = valid_categories.get(category_name)

            if not category_data or category_data.get('type') == 'direct_management':
                continue
            for profile in profiles.values():
                used_ids.add(profile.get('profile_id', 0))
        i = 1
        while i in used_ids:
            i += 1
        return i

    def display_profile_mods(self, current_item):
        list_widget = self.profile_list_stack.currentWidget()
        if not list_widget: return

        for i in range(list_widget.count()):
            item = list_widget.item(i)
            widget = list_widget.itemWidget(item)
            if widget:
                widget.set_selected(item == current_item)

        while self.right_panel.count() > 0:
            widget = self.right_panel.widget(0)
            self.right_panel.removeWidget(widget)
            widget.deleteLater()

        if not current_item:
            return

        profile_name = current_item.data(Qt.ItemDataRole.UserRole)
        if not profile_name:
            return
        
        main_tabs = QTabWidget()
        main_tabs.setMovable(True)

        highlight_color = self.palette().color(QPalette.ColorRole.Highlight)
        luminance = 0.2126 * highlight_color.redF() + 0.7152 * highlight_color.greenF() + 0.0722 * highlight_color.blueF()
        text_color_on_highlight = "#000000" if luminance > 0.5 else "#FFFFFF"
        
        tab_stylesheet = f"""
            QTabWidget::pane {{ border: 1px solid {highlight_color.name()}; border-radius: 8px; }}
            QTabWidget::tab-bar {{ alignment: left; bottom: -1px; outline: none; }}
            QTabBar::tab {{
                background-color: transparent; border: 1px solid #d0d0d0;
                border-bottom-color: {highlight_color.name()}; padding: 8px 20px;
                border-top-left-radius: 8px; border-top-right-radius: 8px;
                color: #555555; margin-left: 5px; font-weight: bold;
                outline: none;
            }}
            QTabBar::tab:!selected:hover {{ background-color: rgba({highlight_color.red()}, {highlight_color.green()}, {highlight_color.blue()}, 40); }}
            QTabBar::tab:selected {{
                background-color: {highlight_color.name()}; color: {text_color_on_highlight};
                border-color: {highlight_color.name()}; border-bottom-color: {highlight_color.name()};
                font-weight: bold;
            }}
        """
        main_tabs.setStyleSheet(tab_stylesheet)
        self.right_panel.addWidget(main_tabs)
        profile_mods_widget = QWidget()
        self.setup_profile_mods_tab(profile_mods_widget, profile_name)
        main_tabs.addTab(profile_mods_widget, self.translator.translate("profile_mods_tab")) 
        main_tabs.currentChanged.connect(self._reposition_floating_buttons)
        profile_data = self.profiles[self.current_game][self.current_category].get(profile_name, {})
        category_data = self.game_data[self.current_game]['categories'][self.current_category]
        api_category_id = profile_data.get('category_id') or category_data.get('api_id')
        
        if api_category_id:
            try:
                from lib.download_tab import DownloadTab
                download_widget = DownloadTab(profile_name, api_category_id, self)
                main_tabs.addTab(download_widget, self.translator.translate("download_tab")) 
            except ImportError:
                print("Advertencia: No se pudo cargar el módulo download_tab.py")
        try:
            from lib.settings_tab import SettingsTab
            from lib.info_tab import InfoTab
            main_tabs.addTab(SettingsTab(profile_name, self), self.translator.translate("settings_tab")) 
            main_tabs.addTab(InfoTab(profile_name, self), self.translator.translate("info_tab"))       
        except ImportError:
            print("Advertencia: No se pudieron cargar los módulos de pestañas adicionales.")

    def setup_direct_management_ui_cards(self, profile_name):
        highlight_color = self.palette().color(QPalette.ColorRole.Highlight)
        search_bar_stylesheet = f"""
            QLineEdit {{
                border: 1px solid #cccccc; border-radius: 15px; padding-left: 10px; outline: none;
                padding-right: 10px; height: 30px;
            }}
            QLineEdit:focus {{ border: 1px solid {highlight_color.name()}; }}
        """
        self.mod_search_bar = QLineEdit()
        self.mod_search_bar.setPlaceholderText("Buscar por nombre de mod...")
        self.mod_search_bar.setStyleSheet(search_bar_stylesheet)
        self.mod_search_bar.textChanged.connect(self.filter_mods_list)
        
        search_icon = self._create_colored_icon(self.ICON_SEARCH, self.palette().color(QPalette.ColorRole.Text))
        self.mod_search_bar.addAction(QAction(search_icon, "", self.mod_search_bar), QLineEdit.ActionPosition.LeadingPosition)
        self.mod_search_bar.setClearButtonEnabled(True)

        self.mods_list_widget = QListWidget()
        self.mods_list_widget.itemClicked.connect(lambda i: self.on_direct_mod_clicked(profile_name, i))
        self.mods_list_widget.setViewMode(QListView.ViewMode.IconMode)
        self.mods_list_widget.setResizeMode(QListView.ResizeMode.Adjust)
        self.mods_list_widget.setMovement(QListView.Movement.Static)
        self.mods_list_widget.setUniformItemSizes(True)
        self.mods_list_widget.setGridSize(QSize(290, 245))
        self.mods_list_widget.setStyleSheet("""
            QListWidget { padding: 5px; border: none; outline: none; }
            QListWidget::item { outline: none; margin-top: 25px; margin-left: -4px;}
            QListWidget::item:hover { background-color: transparent; border: none; }
            QListWidget::item:selected { background-color: transparent; }
        """)
        self._setup_add_mod_button(self.mods_list_widget, lambda: self.import_direct_mod(profile_name))
        self.update_direct_mods_list_cards(profile_name)
        return self.mod_search_bar, self.mods_list_widget

    def update_direct_mods_list_cards(self, profile_name):
        if not hasattr(self, 'mods_list_widget'): return
        
        self.mods_list_widget.blockSignals(True)
        self.mods_list_widget.clear()
        
        profile = self.profiles[self.current_game][self.current_category].get(profile_name, {})
        mods_path = self.get_game_mods_path(self.current_game)
        synced_mods = []
        for mod_info in profile.get("mods", []):
            mod_path = os.path.join(mods_path, mod_info['folder_name'])
            if not os.path.isdir(mod_path): continue 
            is_active = any(f.lower().endswith('.ini') for _, _, files in os.walk(mod_path) for f in files)
            mod_info['active'] = is_active
            synced_mods.append(mod_info)
        profile['mods'] = synced_mods
        self.save_profiles() 
        for mod_info in sorted(profile.get("mods", []), key=lambda m: m.get('display_name', m.get('name', '')).lower()):
            item = QListWidgetItem()
            mod_data_for_card = {
                "name": mod_info.get("name"),
                "display_name": mod_info.get("display_name", mod_info.get("name")),
                "creator": mod_info.get("creator"),
                "url": mod_info.get("url"),
                "icon": mod_info.get("icon"),
                "profile_url": mod_info.get("profile_url") 
            }
            item.setData(Qt.ItemDataRole.UserRole, mod_info) 
            card = ModCardWidget(mod_data_for_card, self)
            card.set_active(mod_info.get("active", False))
            card.delete_requested.connect(lambda mod=mod_info: self.remove_direct_mod(profile_name, mod))
            card.edit_requested.connect(lambda mod=mod_info: self.edit_direct_mod_info(profile_name, mod))
            card.url_requested.connect(self.open_mod_url)
            card.update_requested.connect(lambda mod=mod_info: self.update_mod(profile_name, mod))
            item.setSizeHint(card.sizeHint())
            self.mods_list_widget.addItem(item)
            self.mods_list_widget.setItemWidget(item, card)
        self.mods_list_widget.blockSignals(False)
        self.filter_mods_list()

    def on_direct_mod_clicked(self, profile_name, item):
        mod_info = item.data(Qt.ItemDataRole.UserRole)
        card_widget = self.mods_list_widget.itemWidget(item)
        if not mod_info or not card_widget: return
        mod_path = os.path.join(self.get_game_mods_path(self.current_game), mod_info['folder_name'])
        if not os.path.isdir(mod_path):
            QMessageBox.warning(self, "Error", f"La carpeta del mod '{mod_info['name']}' no fue encontrada.")
            self.update_direct_mods_list_cards(profile_name)
            return
        is_currently_active = mod_info.get('active', False)
        try:
            if is_currently_active: 
                for root, _, files in os.walk(mod_path):
                    for file_name in files:
                        if file_name.lower().endswith('.ini'):
                            os.rename(os.path.join(root, file_name), os.path.join(root, file_name + '.disabled'))
            else: 
                for root, _, files in os.walk(mod_path):
                    for file_name in files:
                        if file_name.lower().endswith('.ini.disabled'):
                            os.rename(os.path.join(root, file_name), os.path.join(root, file_name[:-9]))
            new_active_state = not is_currently_active
            mod_info['active'] = new_active_state
            card_widget.set_active(new_active_state)
            item.setData(Qt.ItemDataRole.UserRole, mod_info)
            self._simulate_f10_press()
            self.save_profiles()

        except OSError as e:
            QMessageBox.critical(self, "Error de Archivo", f"No se pudo renombrar los archivos del mod:\n{e}")
            self.update_direct_mods_list_cards(profile_name)

    def setup_managed_mod_ui(self, profile_name):
        highlight_color = self.palette().color(QPalette.ColorRole.Highlight)
        search_bar_stylesheet = f"QLineEdit {{ outline: none; border: 1px solid #cccccc; border-radius: 15px; padding-left: 10px; padding-right: 10px; height: 30px; }} QLineEdit:focus {{ border: 1px solid {highlight_color.name()}; }}"
        self.mod_search_bar = QLineEdit()
        self.mod_search_bar.setPlaceholderText(self.translator.translate("placeholder_search_mod_name")) 
        self.mod_search_bar.setStyleSheet(search_bar_stylesheet)
        self.mod_search_bar.textChanged.connect(self.filter_mods_list)
        search_icon = self._create_colored_icon(self.ICON_SEARCH, self.palette().color(QPalette.ColorRole.Text))
        self.mod_search_bar.addAction(QAction(search_icon, "", self.mod_search_bar), QLineEdit.ActionPosition.LeadingPosition)
        self.mod_search_bar.setClearButtonEnabled(True)
        self.mods_list_widget = QListWidget()
        self.mods_list_widget.itemClicked.connect(lambda i: self.on_managed_mod_clicked(profile_name, i))
        self.mods_list_widget.setViewMode(QListView.ViewMode.IconMode); self.mods_list_widget.setResizeMode(QListView.ResizeMode.Adjust); self.mods_list_widget.setMovement(QListView.Movement.Static); self.mods_list_widget.setUniformItemSizes(False); self.mods_list_widget.setGridSize(QSize(290, 245))
        self.mods_list_widget.setStyleSheet("QListWidget { padding: 5px; border: none; outline: none; } QListWidget::item { outline: none; margin-top: 25px; margin-left: -4px;} QListWidget::item:hover { background-color: transparent; border: none; } QListWidget::item:selected { background-color: transparent; }")
        self.update_managed_mods_list(profile_name)
        return self.mod_search_bar, self.mods_list_widget

    def setup_direct_management_ui_cards(self, profile_name):
        highlight_color = self.palette().color(QPalette.ColorRole.Highlight)
        search_bar_stylesheet = f"QLineEdit {{ outline: none; border: 1px solid #cccccc; border-radius: 15px; padding-left: 10px; padding-right: 10px; height: 30px; }} QLineEdit:focus {{ border: 1px solid {highlight_color.name()}; }}"
        self.mod_search_bar = QLineEdit()
        self.mod_search_bar.setPlaceholderText(self.translator.translate("placeholder_search_mod_name")) 
        self.mod_search_bar.setStyleSheet(search_bar_stylesheet)
        self.mod_search_bar.textChanged.connect(self.filter_mods_list)
        search_icon = self._create_colored_icon(self.ICON_SEARCH, self.palette().color(QPalette.ColorRole.Text))
        self.mod_search_bar.addAction(QAction(search_icon, "", self.mod_search_bar), QLineEdit.ActionPosition.LeadingPosition)
        self.mod_search_bar.setClearButtonEnabled(True)
        self.mods_list_widget = QListWidget()
        self.mods_list_widget.itemClicked.connect(lambda i: self.on_direct_mod_clicked(profile_name, i))
        self.mods_list_widget.setViewMode(QListView.ViewMode.IconMode); self.mods_list_widget.setResizeMode(QListView.ResizeMode.Adjust); self.mods_list_widget.setMovement(QListView.Movement.Static); self.mods_list_widget.setUniformItemSizes(True); self.mods_list_widget.setGridSize(QSize(290, 245))
        self.mods_list_widget.setStyleSheet("QListWidget { padding: 5px; border: none; outline: none; } QListWidget::item { outline: none; margin-top: 25px; margin-left: -4px;} QListWidget::item:hover { background-color: transparent; border: none; } QListWidget::item:selected { background-color: transparent; }")
        self.update_direct_mods_list_cards(profile_name)
        return self.mod_search_bar, self.mods_list_widget
    
    def _reposition_floating_buttons(self):
        if not hasattr(self, 'add_mod_button') or not self.add_mod_button.parentWidget(): return
        
        parent_widget = self.add_mod_button.parentWidget()
        list_widget_size = parent_widget.size()
        button_size = self.add_mod_button.size()
        margin_right = 20
        margin_bottom = 10
        
        scrollbar = parent_widget.verticalScrollBar()
        if scrollbar and scrollbar.isVisible():
            margin_right += scrollbar.width()
            
        add_btn_x = list_widget_size.width() - button_size.width() - margin_right
        add_btn_y = list_widget_size.height() - button_size.height() - margin_bottom
        self.add_mod_button.move(add_btn_x, add_btn_y)
        
        if hasattr(self, 'scan_mods_button') and self.scan_mods_button.isVisible():
            scan_button_size = self.scan_mods_button.size()
            spacing = 15
            scan_btn_y = add_btn_y + (button_size.height() - scan_button_size.height()) // 2
            scan_btn_x = add_btn_x - scan_button_size.width() - spacing
            self.scan_mods_button.move(scan_btn_x, scan_btn_y)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_floating_buttons()

    def filter_mods_list(self):
        if not hasattr(self, 'mods_list_widget') or not hasattr(self, 'mod_search_bar'):
            return
        filter_text = self.mod_search_bar.text().lower()
        for i in range(self.mods_list_widget.count()):
            item = self.mods_list_widget.item(i)
            mod_info = item.data(Qt.ItemDataRole.UserRole)
            if mod_info.get("slot_id") == 0:
                item.setHidden(False)
                continue 
            searchable_name = (mod_info.get("display_name") or mod_info.get("name", "")).lower()
            if filter_text in searchable_name:
                item.setHidden(False)
            else:
                item.setHidden(True)

    def import_managed_mod(self, profile_name):
        if not patoolib: 
            QMessageBox.critical(self, "Error", "'patool' es necesario para esta función.")
            return

        archive_path, _ = QFileDialog.getOpenFileName(self, "Seleccionar Archivo de Mod", "", "Archivos Comprimidos (*.zip *.rar *.7z)")
        if not archive_path: 
            return

        mod_name = self._sanitize_filename(os.path.splitext(os.path.basename(archive_path))[0])
        profile = self.profiles[self.current_game][self.current_category][profile_name]
        
        if any(m.get('name') == mod_name for m in profile.get("mods", [])):
             QMessageBox.warning(self, "Conflicto", f"Un mod con el nombre de archivo '{mod_name}' ya existe en este perfil.")
             return

        info_dialog = ModInfoDialog(mod_info={"display_name": mod_name.replace("_", " ")}, parent=self)
        if not info_dialog.exec():
            return 

        details = info_dialog.get_details()
        if not details["display_name"]:
            details["display_name"] = mod_name 

        profile_folder_name = profile['folder_name']
        slot_id = len(profile.get("mods", [])) + 1
        management_path = self.get_management_path(self.current_game)
        profile_path = os.path.join(management_path, profile_folder_name)
        mod_dest_path = os.path.join(profile_path, mod_name)

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                patoolib.extract_archive(archive_path, outdir=temp_dir)
                extracted_contents = os.listdir(temp_dir)
                source_mod_folder = temp_dir
                if len(extracted_contents) == 1 and os.path.isdir(os.path.join(temp_dir, extracted_contents[0])):
                    source_mod_folder = os.path.join(temp_dir, extracted_contents[0])
                shutil.copytree(source_mod_folder, mod_dest_path)
                for root, _, files in os.walk(mod_dest_path):
                    for file in files:
                        if file.lower().endswith('.ini'):
                            self._rewrite_ini_file(os.path.join(root, file), slot_id, profile_folder_name, mod_name)
            icon_path = self._copy_icon_to_cache(details['icon_source_path'], f"mod_{profile_name}_{mod_name}")
            new_mod_info = {
                "name": mod_name,
                "path": mod_dest_path,
                "slot_id": slot_id,
                "display_name": details["display_name"],
                "creator": details["creator"],
                "url": details["url"],
                "icon": icon_path
            }
            profile["mods"].append(new_mod_info)
            self.save_profiles()
            self.update_managed_mods_list(profile_name)
            self._simulate_f10_press() 

        except Exception as e:
            QMessageBox.critical(self, "Error de Importación", f"No se pudo importar el archivo:\n{e}")
            if os.path.exists(mod_dest_path):
                shutil.rmtree(mod_dest_path)

    def update_managed_mods_list(self, profile_name):
        if not hasattr(self, 'mods_list_widget'): return
        self.mods_list_widget.blockSignals(True)
        self.mods_list_widget.clear()
        profile = self.profiles[self.current_game][self.current_category].get(profile_name, {})
        active_mod_path = profile.get("active_mod")
        item_none = QListWidgetItem()
        item_none.setData(Qt.ItemDataRole.UserRole, {"path": None, "slot_id": 0})
        card_none = NoneModCardWidget(self)
        card_none.set_active(not active_mod_path)
        item_none.setSizeHint(QSize(232, 220)) 
        self.mods_list_widget.addItem(item_none)
        self.mods_list_widget.setItemWidget(item_none, card_none)
        sorted_mods = sorted(profile.get("mods", []), key=lambda m: m.get('display_name', m.get('name', '')).lower())
        for mod_info in sorted_mods:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, mod_info)
            card = ModCardWidget(mod_info, self)
            card.set_active(active_mod_path == mod_info.get("path"))
            card.delete_requested.connect(lambda mod=mod_info: self.remove_managed_mod(profile_name, mod))
            card.edit_requested.connect(lambda mod=mod_info: self.edit_managed_mod_info(profile_name, mod))
            card.url_requested.connect(self.open_mod_url)
            card.update_requested.connect(lambda mod=mod_info: self.update_mod(profile_name, mod))
            item.setSizeHint(QSize(232, 220))
            self.mods_list_widget.addItem(item)
            self.mods_list_widget.setItemWidget(item, card)
        self.mods_list_widget.blockSignals(False)
        self.filter_mods_list()

    def _simulate_f10_press(self):
        if not win32api:
            print("Librería 'pywin32' no disponible, no se puede simular F10.")
            return
        try:
            VK_F10 = 0x79  
            win32api.keybd_event(VK_F10, 0, 0, 0) 
            time.sleep(0.05) 
            win32api.keybd_event(VK_F10, 0, win32con.KEYEVENTF_KEYUP, 0) 
            print("Simulada pulsación de F10.")
        except Exception as e:
            print(f"No se pudo simular la pulsación de F10: {e}")

    def _safe_remove_directory(self, path, max_retries=5, delay=0.2):
        if not os.path.exists(path):
            return True 

        def onerror(func, path, exc_info):
            exc_instance = exc_info[1]
            if isinstance(exc_instance, PermissionError):
                print(f"Error de permiso en: {path}. Intentando cambiar permisos y reintentar.")
                try:
                    os.chmod(path, 0o777) 
                    func(path)
                except Exception as e:
                    print(f"Falló el reintento de eliminar {path}: {e}")
            
        for i in range(max_retries):
            try:
                shutil.rmtree(path, onerror=onerror)
                print(f"Carpeta {path} eliminada con éxito.")
                return True
            except Exception as e:
                print(f"Intento {i+1}/{max_retries} de rmtree falló para {path}: {e}")
                time.sleep(delay * (i + 1)) 

        self.show_message(
            self.translator.translate("title_file_error"),
            self.translator.translate("msg_could_not_delete_folder", path=path) + "\n\nAsegúrese de que el juego, el launcher y el Explorador de Archivos no estén usando esta carpeta.",
            "critical"
        )
        return False

    def remove_managed_mod(self, profile_name, mod_info_to_delete, confirm=True):
        if not mod_info_to_delete: return

        if confirm:
            question_text = self.translator.translate("msg_confirm_delete_mod", name=mod_info_to_delete.get('display_name', mod_info_to_delete['name']))
            reply = QMessageBox.question(self, self.translator.translate("title_confirm"), question_text, 
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes: return

        profile = self.profiles[self.current_game][self.current_category][profile_name]

        if profile.get("active_mod") == mod_info_to_delete['path']:
            profile["active_mod"] = None
            self._activate_mod_via_keypress(profile['profile_id'], 0)
        
        old_icon = mod_info_to_delete.get('icon')
        if old_icon and os.path.exists(old_icon) and self.icons_cache_path in old_icon:
            os.remove(old_icon)

        if not self._safe_remove_directory(mod_info_to_delete['path']):
            self.update_managed_mods_list(profile_name) 
            return

        profile["mods"] = [m for m in profile["mods"] if m['path'] != mod_info_to_delete['path']]
        profile['mods'].sort(key=lambda m: m.get('slot_id', 999))
        new_slot_id = 1
        for mod_to_update in profile['mods']:
            mod_to_update['slot_id'] = new_slot_id
            mod_folder_name = os.path.basename(mod_to_update['path'])
            for root, _, files in os.walk(mod_to_update['path']):
                for file in files:
                    if file.lower().endswith('.ini'):
                        self._rewrite_ini_file(os.path.join(root, file), new_slot_id, profile['folder_name'], mod_folder_name)
            new_slot_id += 1

        self.save_profiles()
        self.update_managed_mods_list(profile_name)
        self._simulate_f10_press()
        

    def on_managed_mod_clicked(self, profile_name, item):
        mod_info = item.data(Qt.ItemDataRole.UserRole)
        if not mod_info: return
        profile = self.profiles[self.current_game][self.current_category][profile_name]
        if mod_info.get("path") == profile.get("active_mod"):
            return
        profile["active_mod"] = mod_info.get("path")
        self.save_profiles()
        self._activate_mod_via_keypress(profile['profile_id'], mod_info['slot_id'])
        for i in range(self.mods_list_widget.count()):
            current_item = self.mods_list_widget.item(i)
            widget = self.mods_list_widget.itemWidget(current_item)
            if widget and hasattr(widget, 'set_active'):
                item_data = current_item.data(Qt.ItemDataRole.UserRole)
                is_this_one_active = (item_data.get("path") == profile["active_mod"])
                widget.set_active(is_this_one_active)

    def edit_managed_mod_info(self, profile_name, mod_info):
        dialog = ModInfoDialog(mod_info, self)
        if dialog.exec():
            details = dialog.get_details()
            profile = self.profiles[self.current_game][self.current_category][profile_name]
            for i, mod in enumerate(profile["mods"]):
                if mod["path"] == mod_info["path"]:
                    profile["mods"][i]["display_name"] = details["display_name"] or mod_info["name"]
                    profile["mods"][i]["creator"] = details["creator"]
                    profile["mods"][i]["url"] = details["url"]
                    if details["icon_source_path"] and details["icon_source_path"] != mod_info.get("icon"):
                        new_icon_path = self._copy_icon_to_cache(details["icon_source_path"], f"mod_{profile_name}_{mod_info['name']}")
                        old_icon = mod_info.get('icon')
                        if old_icon and os.path.exists(old_icon) and self.icons_cache_path in old_icon:
                            os.remove(old_icon)
                        
                        profile["mods"][i]["icon"] = new_icon_path
                    break
            
            self.save_profiles()
            self.update_managed_mods_list(profile_name)

    def open_mod_url(self, url):
        if url:
            if not url.startswith(('http://', 'https://')):
                url = 'http://' + url
            QDesktopServices.openUrl(QUrl(url))
            
        else:
            QMessageBox.information(self, "Sin URL", "Este mod no tiene una URL configurada.")
        
    def _activate_mod_via_keypress(self, profile_id, slot_id):
        if not win32api: QMessageBox.critical(self, "Error", "La librería 'pywin32' no está disponible para activar mods."); return
        original_pos = win32gui.GetCursorPos()
        win32api.SetCursorPos((slot_id, profile_id))
        time.sleep(0.05)
        VK_CLEAR, VK_SPACE, VK_RETURN = 0x0C, 0x20, 0x0D
        win32api.keybd_event(VK_CLEAR, 0, 0, 0); win32api.keybd_event(VK_SPACE, 0, 0, 0); time.sleep(0.05)
        win32api.keybd_event(VK_SPACE, 0, win32con.KEYEVENTF_KEYUP, 0); win32api.keybd_event(VK_CLEAR, 0, win32con.KEYEVENTF_KEYUP, 0); time.sleep(0.05)
        win32api.keybd_event(VK_CLEAR, 0, 0, 0); win32api.keybd_event(VK_RETURN, 0, 0, 0); time.sleep(0.05)
        win32api.keybd_event(VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0); win32api.keybd_event(VK_CLEAR, 0, win32con.KEYEVENTF_KEYUP, 0); time.sleep(0.05)
        win32api.SetCursorPos(original_pos)
        print(f"Activado Grupo {profile_id}, Slot {slot_id}")
        
    def get_game_mods_path(self, game): return os.path.join(self.xxmi_path, self.game_data[game]["folder"], "Mods")
    
    def import_direct_mod(self, profile_name):
        if not patoolib: 
            QMessageBox.critical(self, "Error", "'patool' es necesario para esta función.")
            return
        
        archive_path, _ = QFileDialog.getOpenFileName(self, "Seleccionar Archivo de Mod", "", "Archivos Comprimidos (*.zip *.rar *.7z)")
        if not archive_path: return
        
        mods_path = self.get_game_mods_path(self.current_game)
        mod_folder_name = self._sanitize_filename(os.path.splitext(os.path.basename(archive_path))[0])
        mod_dest_path = os.path.join(mods_path, mod_folder_name)
        
        if os.path.exists(mod_dest_path):
            QMessageBox.warning(self, "Conflicto", f"Un mod con el nombre '{mod_folder_name}' ya existe.")
            return

        info_dialog = ModInfoDialog(mod_info={"display_name": mod_folder_name.replace("_", " ")}, parent=self)
        if not info_dialog.exec(): return

        details = info_dialog.get_details()
        if not details["display_name"]:
            details["display_name"] = mod_folder_name

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                patoolib.extract_archive(archive_path, outdir=temp_dir)
                extracted_contents = os.listdir(temp_dir)
                source_mod_folder = temp_dir
                if len(extracted_contents) == 1 and os.path.isdir(os.path.join(temp_dir, extracted_contents[0])):
                    source_mod_folder = os.path.join(temp_dir, extracted_contents[0])
                shutil.copytree(source_mod_folder, mod_dest_path)

            profile = self.profiles[self.current_game][self.current_category][profile_name]
            icon_path = self._copy_icon_to_cache(details['icon_source_path'], f"mod_{profile_name}_{mod_folder_name}")

            new_mod_info = {
                "name": mod_folder_name,
                "folder_name": mod_folder_name,
                "display_name": details["display_name"],
                "creator": details["creator"],
                "url": details["url"],
                "icon": icon_path
            }
            profile["mods"].append(new_mod_info)
            self.save_profiles()
            self.update_direct_mods_list_cards(profile_name) 
            self._simulate_f10_press() 

        except Exception as e:
            QMessageBox.critical(self, "Error de Importación", f"No se pudo importar el archivo:\n{e}")
            if os.path.exists(mod_dest_path):
                shutil.rmtree(mod_dest_path)
            
    def update_direct_mods_list(self, profile_name):
        if not hasattr(self, 'other_mods_list_widget'): return
        self.other_mods_list_widget.clear()
        profile = self.profiles[self.current_game][self.current_category][profile_name]
        mods_path = self.get_game_mods_path(self.current_game)
        synced_mods = []
        for mod_info in profile.get("mods", []):
            mod_path = os.path.join(mods_path, mod_info['folder_name'])
            if not os.path.isdir(mod_path): continue 
            is_active = any(f.lower().endswith('.ini') for _, _, files in os.walk(mod_path) for f in files)
            mod_info['active'] = is_active; synced_mods.append(mod_info)
        profile['mods'] = synced_mods; self.save_profiles()
        for mod_info in profile.get("mods", []):
            status = " [ACTIVO]" if mod_info['active'] else " [INACTIVO]"
            item = QListWidgetItem(mod_info['name'] + status); item.setData(Qt.ItemDataRole.UserRole, mod_info); self.other_mods_list_widget.addItem(item)
            
    def toggle_direct_mod(self, profile_name):
        if not self.other_mods_list_widget.currentItem(): return
        mod_info = self.other_mods_list_widget.currentItem().data(Qt.ItemDataRole.UserRole)
        mod_path = os.path.join(self.get_game_mods_path(self.current_game), mod_info['folder_name'])
        if not os.path.isdir(mod_path): QMessageBox.warning(self, "Error", f"La carpeta del mod '{mod_info['name']}' no fue encontrada."); self.update_direct_mods_list(profile_name); return
        try:
            if mod_info['active']:
                renamed_count = 0
                for root, _, files in os.walk(mod_path):
                    for file_name in files:
                        if file_name.lower().endswith('.ini'): os.rename(os.path.join(root, file_name), os.path.join(root, file_name + '.disabled')); renamed_count += 1
                if renamed_count == 0: QMessageBox.information(self, "Información", "No se encontraron archivos .ini para desactivar.")
            else:
                for root, _, files in os.walk(mod_path):
                    for file_name in files:
                        if file_name.lower().endswith('.ini.disabled'): os.rename(os.path.join(root, file_name), os.path.join(root, file_name[:-9]))
        except OSError as e: QMessageBox.critical(self, "Error de Archivo", f"No se pudo renombrar los archivos del mod:\n{e}")
        self.update_direct_mods_list(profile_name)

    def remove_direct_mod(self, profile_name, mod_info_to_delete, confirm=True):
        if not mod_info_to_delete: return

        if confirm:
            question_text = self.translator.translate("msg_confirm_delete_mod_permanent", name=mod_info_to_delete.get('display_name', mod_info_to_delete['name']))
            reply = QMessageBox.question(self, self.translator.translate("title_confirm"), question_text,
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes: return
        mod_path = os.path.join(self.get_game_mods_path(self.current_game), mod_info_to_delete['folder_name'])
        if not self._safe_remove_directory(mod_path):
            self.update_direct_mods_list_cards(profile_name) 
            return

        old_icon = mod_info_to_delete.get('icon')
        if old_icon and os.path.exists(old_icon) and self.icons_cache_path in old_icon:
            os.remove(old_icon)
        
        profile = self.profiles[self.current_game][self.current_category][profile_name]
        profile['mods'] = [m for m in profile['mods'] if m['folder_name'] != mod_info_to_delete['folder_name']]
        self.save_profiles()
        self.update_direct_mods_list_cards(profile_name)

    def _check_for_command_file(self):
        if not os.path.exists(self.command_file_path):
            return
        print(f"[{time.time()}] DETECTADO el archivo de comando: {self.command_file_path}")
        try:
            with open(self.command_file_path, 'r') as f:
                url = f.read().strip()
            os.remove(self.command_file_path)
            print(f"Archivo de comando leído y borrado. Contenido: '{url}'")
            if url:
                self.process_startup_url(url)
        except Exception as e:
            print(f"Error procesando el archivo de comando: {e}")
            if os.path.exists(self.command_file_path):
                os.remove(self.command_file_path)

    def process_startup_url(self, url):
        if not url.startswith("mimm:"):
            return
        print(f"Procesando URL de 1-Click: {url}")

        match = re.search(r'mmdl/(\d+),Mod,(\d+)', url)
        if match:
            file_id, mod_id = match.groups()
            self.showNormal()  
            self.activateWindow() 
            self.raise_()         
            dialog = OneClickInstallDialog(mod_id, file_id, self)
            dialog.exec()
        else:
            print(f"La URL '{url}' no tiene el formato esperado.")

    def _ensure_protocol_is_registered(self):
        app_name = "MIMM"
        try:
            if getattr(sys, 'frozen', False):
                exe_path = sys.executable
                expected_command = f'"{exe_path}" "%1"'
            else:
                python_exe_path = sys.executable
                script_path = os.path.abspath(sys.argv[0])
                expected_command = f'"{python_exe_path}" "{script_path}" "%1"'

            key_path = rf'Software\Classes\{app_name}\shell\open\command'
            needs_registration = False
            
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                    current_command, _ = winreg.QueryValueEx(key, None)
                    if current_command != expected_command:
                        print("Comando de protocolo incorrecto. Actualizando...")
                        needs_registration = True
            except FileNotFoundError:
                print("Protocolo no registrado. Registrando...")
                needs_registration = True

            if needs_registration:
                print(f"Registrando comando: {expected_command}")
                main_key_path = rf'Software\Classes\{app_name}'
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, main_key_path) as key:
                    winreg.SetValue(key, '', winreg.REG_SZ, f'URL:{app_name} Protocol')
                    winreg.SetValueEx(key, 'URL Protocol', 0, winreg.REG_SZ, '')

                    with winreg.CreateKey(key, r'shell\open\command') as cmd_key:
                        winreg.SetValue(cmd_key, '', winreg.REG_SZ, expected_command)
                
                print("Protocolo registrado/actualizado con éxito.")

        except Exception as e:
            print(f"ADVERTENCIA: No se pudo verificar/registrar el protocolo. Error: {e}")

    def show_message(self, title, message, level="info"):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        if level == "critical":
            msg_box.setIcon(QMessageBox.Icon.Critical)
        elif level == "warning":
            msg_box.setIcon(QMessageBox.Icon.Warning)
        else:
            msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.exec()

    def setup_profile_mods_tab(self, parent_widget, profile_name):
        layout = QVBoxLayout(parent_widget)
        layout.setContentsMargins(5, 5, 5, 5) 
        
        category_type = self.category_widgets[self.current_category]['type']
        is_managed_profile = category_type != 'direct_management'
        
        scan_callback = None
        if is_managed_profile:
            search_bar, mods_list = self.setup_managed_mod_ui(profile_name)
            add_callback = lambda: self.import_managed_mod(profile_name)
            scan_callback = lambda: self.scan_and_register_untracked_mods(profile_name)
        else:
            search_bar, mods_list = self.setup_direct_management_ui_cards(profile_name)
            add_callback = lambda: self.import_direct_mod(profile_name)
            
        search_layout = QHBoxLayout()
        search_layout.addWidget(search_bar)
        layout.addLayout(search_layout)
        layout.addWidget(mods_list)
        
        self._setup_floating_buttons(mods_list, add_callback, scan_callback)

    def _install_direct_mod_from_api(self, profile_name, mod_data, archive_path):
        mod_folder_name = self._sanitize_filename(mod_data.get('_sName'))
        mods_path = self.get_game_mods_path(self.current_game)
        mod_dest_path = os.path.join(mods_path, mod_folder_name)

        if os.path.exists(mod_dest_path):
            self.show_message(
                self.translator.translate("title_conflict"), 
                self.translator.translate("msg_mod_exists", name=mod_folder_name), 
                "warning"
            )
            return

        self._extract_and_copy_mod(archive_path, mod_dest_path)
        
        profile = self.profiles[self.current_game][self.current_category][profile_name]
        
        icon_path = self._download_and_save_mod_icon(mod_data, profile_name, mod_folder_name)

        new_mod_info = {
            "name": mod_folder_name, "folder_name": mod_folder_name,
            "display_name": mod_data.get('_sName'),
            "creator": mod_data.get('_aSubmitter', {}).get('_sName'),
            "url": mod_data.get('_sProfileUrl'),
            "profile_url": mod_data.get('_sProfileUrl'),
            "icon": icon_path
        }
        profile["mods"].append(new_mod_info)
        self.save_profiles()
        self.update_direct_mods_list_cards(profile_name)
        self._simulate_f10_press() 
        self.show_message(
            self.translator.translate("success_title"), 
            self.translator.translate("success_mod_installed", name=mod_folder_name)
        )

    def _copy_icon_to_cache(self, source_path, base_filename):
        if not source_path or not os.path.exists(source_path):
            return None
        try:
            if self.icons_cache_path in os.path.normpath(source_path):
                return source_path
            ext = os.path.splitext(source_path)[1] or ".png"
            final_name = self._sanitize_filename(f"{base_filename}_{int(time.time())}{ext}")
            final_path = os.path.join(self.icons_cache_path, final_name)
            shutil.copy(source_path, final_path)
            return final_path
        except Exception as e:
            print(f"No se pudo copiar el icono a la caché: {e}")
            return None

    def _install_managed_mod_from_api(self, profile_name, mod_data, archive_path, forced_slot_id=None):
        mod_name = self._sanitize_filename(mod_data.get('_sName'))
        profile = self.profiles[self.current_game][self.current_category][profile_name]

        profile_folder_name = profile['folder_name']
        if forced_slot_id is not None:
            slot_id = forced_slot_id
        else:
            slot_id = len(profile.get("mods", [])) + 1
            
        mod_dest_path = os.path.join(self.get_management_path(self.current_game), profile_folder_name, mod_name)

        self._extract_and_copy_mod(archive_path, mod_dest_path)
        for root, _, files in os.walk(mod_dest_path):
            for file in files:
                if file.lower().endswith('.ini'):
                    self._rewrite_ini_file(os.path.join(root, file), slot_id, profile_folder_name, mod_name)
        
        icon_path = self._download_and_save_mod_icon(mod_data, profile_name, mod_name)
        
        new_mod_info = {
            "name": mod_name, "path": mod_dest_path, "slot_id": slot_id,
            "display_name": mod_data.get('_sName'),
            "creator": mod_data.get('_aSubmitter', {}).get('_sName'),
            "url": mod_data.get('_sProfileUrl'),
            "profile_url": mod_data.get('_sProfileUrl'),
            "icon": icon_path
        }
        
        profile["mods"].append(new_mod_info)
        self.save_profiles()
        self.update_managed_mods_list(profile_name)
        self._simulate_f10_press()
        self.show_message(
            self.translator.translate("success_title"), 
            self.translator.translate("success_mod_installed", name=mod_name)
        )
        
    def _download_and_save_mod_icon(self, mod_data, profile_name, mod_name):
        previews_data = mod_data.get('_aPreviewMedia')
        images_list = []
        if isinstance(previews_data, dict):
            images_list = previews_data.get('_aImages', [])
        elif isinstance(previews_data, list):
            images_list = previews_data
        
        if not images_list:
            print(f"No se encontró lista de imágenes para el mod '{mod_name}'")
            return None

        valid_image_info = None
        for img in images_list:
            if isinstance(img, dict) and img.get('_sBaseUrl') and (img.get('_sFile') or img.get('_sFile670')):
                valid_image_info = img
                break

        if not valid_image_info:
            print(f"No se encontró una imagen con URL descargable para el mod '{mod_name}'")
            return None
        
        file_key = '_sFile670' if '_sFile670' in valid_image_info else '_sFile'
        img_url = valid_image_info['_sBaseUrl'] + '/' + valid_image_info[file_key]
        
        try:
            response = requests.get(img_url, timeout=15, headers={'User-Agent': 'MIMM/1.0'})
            response.raise_for_status()
            image_content = response.content

            pixmap_validator = QPixmap()
            if not pixmap_validator.loadFromData(image_content):
                print(f"Error: Los datos de {img_url} no son una imagen válida.")
                return None

            ext = os.path.splitext(img_url)[1] or ".jpg" 
            if '?' in ext: ext = ext.split('?')[0] 
            
            final_name = self._sanitize_filename(f"mod_{profile_name}_{mod_name}_{int(time.time())}{ext}")
            final_path = os.path.join(self.icons_cache_path, final_name)
            
            with open(final_path, 'wb') as f:
                f.write(image_content)

            if os.path.exists(final_path) and os.path.getsize(final_path) > 0:
                return final_path
            else:
                print(f"Error: El guardado del icono falló para {final_path}")
                return None

        except requests.RequestException as e:
            print(f"No se pudo descargar el icono del mod: {e}")
            return None
        except Exception as e:
            print(f"Error inesperado al procesar el icono: {e}")
            return None

    def install_mod_from_api(self, profile_name, mod_data, file_data, forced_slot_id=None):
        if not patoolib:
            self.show_message(self.translator.translate("title_error"), self.translator.translate("msg_patool_required"), "critical")
            return
        download_url = file_data.get('_sDownloadUrl')
        if not download_url:
            self.show_message(self.translator.translate("title_error"), self.translator.translate("error_no_download_url"), "critical")
            return
        progress_dialog = DownloadProgressDialog(self.translator, self)
        progress_dialog.show()
        archive_path = None
        download_successful = False
        
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_file:
                archive_path = tmp_file.name
                
                qnam = QNetworkAccessManager()
                reply = qnam.get(QNetworkRequest(QUrl(download_url)))
                
                loop = QEventLoop()
                reply.finished.connect(loop.quit)
                reply.downloadProgress.connect(
                    lambda r, t: progress_dialog.update_progress(int(r / t * 100)) if t > 0 else None
                )
                loop.exec()

                if reply.error() == reply.NetworkError.NoError:
                    tmp_file.write(reply.readAll().data())
                    download_successful = True
                else:
                    raise requests.RequestException(f"Error de red: {reply.errorString()}")
                
                reply.deleteLater()
                progress_dialog.close()

            if download_successful:
                category_type = self.category_widgets[self.current_category]['type']
                installer_func = self._install_direct_mod_from_api if category_type == 'direct_management' else self._install_managed_mod_from_api

                if category_type == 'direct_management':
                    installer_func(profile_name, mod_data, archive_path)
                else:
                    installer_func(profile_name, mod_data, archive_path, forced_slot_id=forced_slot_id)
            
        except requests.RequestException as e:
            self.show_message(self.translator.translate("title_download_error"), self.translator.translate("msg_download_failed", e=e), "critical")
            raise
        except Exception as e:
            error_msg = self.translator.translate("msg_install_error_generic", e=e)
            if archive_path:
                error_msg += self.translator.translate("msg_install_error_temp_path", path=archive_path)
            self.show_message(self.translator.translate("title_install_error"), error_msg, "critical")
            raise 
        finally:
            if progress_dialog.isVisible():
                progress_dialog.close()
            if archive_path and os.path.exists(archive_path):
                os.remove(archive_path)
        
    def _extract_and_copy_mod(self, archive_path, dest_path):
        with tempfile.TemporaryDirectory() as temp_dir:
            patoolib.extract_archive(archive_path, outdir=temp_dir)
            extracted_contents = os.listdir(temp_dir)
            source_folder = temp_dir
            if len(extracted_contents) == 1 and os.path.isdir(os.path.join(temp_dir, extracted_contents[0])):
                source_folder = os.path.join(temp_dir, extracted_contents[0])
            shutil.copytree(source_folder, dest_path)

    def _download_mod_icon(self, mod_data, profile_name, mod_name):
        previews = mod_data.get('_aPreviewMedia', [])
        if not (isinstance(previews, list) and previews):
            return None

        img_info = previews[0]
        file_key = '_sFile670'
        if not (isinstance(img_info, dict) and img_info.get('_sBaseUrl') and img_info.get(file_key)):
            return None

        img_url = img_info['_sBaseUrl'] + '/' + img_info[file_key]
        
        try:
            response = requests.get(img_url, timeout=15, headers={'User-Agent': 'MIMM/1.0'})
            response.raise_for_status()
            image_content = response.content
            pixmap_validator = QPixmap()
            if not pixmap_validator.loadFromData(image_content):
                print(f"Error: Los datos de {img_url} no son una imagen válida.")
                return None
            return self._save_image_content_to_cache(image_content, profile_name, mod_name)

        except requests.RequestException as e:
            print(f"No se pudo descargar el icono del mod: {e}")
            return None

    def _get_contrasting_icon_color(self, color):
        luminance = (0.2126 * color.redF() + 0.7152 * color.greenF() + 0.0722 * color.blueF())
        if luminance > 0.5:
            return QColor(Qt.GlobalColor.black)
        else:
            return QColor(Qt.GlobalColor.white)

    def _setup_floating_buttons(self, parent_widget, add_callback, scan_callback=None):
        highlight_color = self.palette().color(QPalette.ColorRole.Highlight)
        icon_color = self._get_contrasting_icon_color(highlight_color)
        btn_size, icon_size = 75, 42
        scan_btn_size, scan_icon_size = 55, 30

        stylesheet = f"""
            QPushButton {{
                background-color: {highlight_color.name()}; border: none;
                border-radius: {btn_size // 2}px; outline: none;
            }}
            QPushButton:hover {{ background-color: {highlight_color.lighter(115).name()}; }}
            QPushButton:pressed {{ background-color: {highlight_color.darker(115).name()}; }}
        """
        scan_stylesheet = f"""
            QPushButton {{
                background-color: {highlight_color.name()}; border: none;
                border-radius: {scan_btn_size // 2}px; outline: none;
            }}
            QPushButton:hover {{ background-color: {highlight_color.lighter(115).name()}; }}
            QPushButton:pressed {{ background-color: {highlight_color.darker(115).name()}; }}
        """
        
        self.add_mod_button = QPushButton(parent=parent_widget)
        self.add_mod_button.setToolTip(self.translator.translate("tooltip_import_new_mod"))
        self.add_mod_button.setFixedSize(btn_size, btn_size)
        self.add_mod_button.setIcon(self._create_colored_icon(self.ICON_ADD, icon_color))
        self.add_mod_button.setIconSize(QSize(icon_size, icon_size))
        self.add_mod_button.setStyleSheet(stylesheet)
        self.add_mod_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_mod_button.clicked.connect(add_callback)
        self.add_mod_button.show()
        
        if hasattr(self, 'scan_mods_button'):
            delattr(self, 'scan_mods_button')

        if scan_callback:
            self.scan_mods_button = QPushButton(parent=parent_widget)
            self.scan_mods_button.setToolTip(self.translator.translate("tooltip_scan_unregistered_mods"))
            self.scan_mods_button.setFixedSize(scan_btn_size, scan_btn_size)
            self.scan_mods_button.setIcon(self._create_colored_icon(self.ICON_UPDATE, icon_color))
            self.scan_mods_button.setIconSize(QSize(scan_icon_size, scan_icon_size))
            self.scan_mods_button.setStyleSheet(scan_stylesheet)
            self.scan_mods_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.scan_mods_button.clicked.connect(scan_callback)
            self.scan_mods_button.show()

        QTimer.singleShot(5, self._reposition_floating_buttons)

    def update_mod(self, profile_name, mod_info):
        original_mod_name = mod_info.get("name")
        if not original_mod_name:
            self.show_message(self.translator.translate("title_error"), self.translator.translate("msg_update_no_original_name"), "critical")
            return

        game_id = self.game_data[self.current_game].get("game_id")
        if not game_id:
            self.show_message(self.translator.translate("title_error"), self.translator.translate("msg_update_no_api_search"), "critical")
            return

        existing_icon_path = mod_info.get("icon")
        old_mod_path = mod_info.get("path")
        old_folder_name = mod_info.get("folder_name")

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        
        API_BYTE_MAX_LENGTH = 50
        search_name = original_mod_name
        
        if len(original_mod_name.encode('utf-8')) > API_BYTE_MAX_LENGTH:
            truncated_chars = []
            current_byte_length = 0
            for char in original_mod_name:
                char_bytes = char.encode('utf-8')
                if current_byte_length + len(char_bytes) > API_BYTE_MAX_LENGTH:
                    break
                truncated_chars.append(char)
                current_byte_length += len(char_bytes)
            search_name = "".join(truncated_chars)
        
        try:
            search_url = f"https://gamebanana.com/apiv11/Game/{game_id}/Subfeed"
            params = {"_nPage": 1, "_sSort": "new", "_sName": search_name}
            response = requests.get(search_url, params=params, timeout=20, headers={'User-Agent': 'MIMM/1.0'})
            response.raise_for_status()
            search_data = response.json()

            mod_id, remote_mod_data = None, None
            for record in search_data.get("_aRecords", []):
                if record.get("_sModelName") == "Mod" and record.get("_sName") == original_mod_name:
                    mod_id, remote_mod_data = record.get("_idRow"), record
                    break

            if not mod_id:
                self.show_message(self.translator.translate("title_not_found"), self.translator.translate("msg_update_no_exact_match", name=original_mod_name))
                return

            files_url = f"https://gamebanana.com/apiv11/Mod/{mod_id}"
            params = {"_csvProperties": "_aFiles"}
            response = requests.get(files_url, params=params, timeout=20, headers={'User-Agent': 'MIMM/1.0'})
            response.raise_for_status()
            files_list = response.json().get("_aFiles", [])

            if not files_list:
                self.show_message(self.translator.translate("title_no_files"), self.translator.translate("msg_update_no_downloadable_files"))
                return

        except requests.RequestException as e:
            self.show_message(self.translator.translate("title_network_error"), self.translator.translate("msg_update_search_failed", e=e), "critical")
            return
        finally:
            if QApplication.overrideCursor():
                QApplication.restoreOverrideCursor()

        file_to_install = files_list[0]
        if len(files_list) > 1:
            dialog = FileSelectionDialog(files_list, self)
            if dialog.exec(): file_to_install = dialog.selected_file
            else: return
        if not file_to_install: return

        question_text = self.translator.translate("msg_confirm_update_replace",
                                                display_name=mod_info.get('display_name'),
                                                file_name=file_to_install.get('_sFile'))
        reply = QMessageBox.question(self, self.translator.translate("title_confirm_update"),
                                    question_text,
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            profile = self.profiles[self.current_game][self.current_category][profile_name]
            category_type = self.category_widgets[self.current_category]['type']
            slot_to_preserve = mod_info.get("slot_id") if category_type != 'direct_management' else None

            if category_type == 'direct_management':
                full_old_path = os.path.join(self.get_game_mods_path(self.current_game), old_folder_name)
                if not self._safe_remove_directory(full_old_path): return
                profile['mods'] = [m for m in profile['mods'] if m.get('folder_name') != old_folder_name]
            else:
                if not self._safe_remove_directory(old_mod_path): return
                profile['mods'] = [m for m in profile['mods'] if m.get('path') != old_mod_path]

            download_url = file_to_install.get('_sDownloadUrl')
            if not download_url:
                self.show_message(self.translator.translate("title_error"), self.translator.translate("error_no_download_url"), "critical")
                return

            progress_dialog = DownloadProgressDialog(self.translator, self)
            progress_dialog.show()

            archive_path = None
            download_successful = False
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_file:
                    archive_path = tmp_file.name
                    qnam = QNetworkAccessManager()
                    reply = qnam.get(QNetworkRequest(QUrl(download_url)))
                    
                    loop = QEventLoop()
                    reply.finished.connect(loop.quit)
                    reply.downloadProgress.connect(lambda r, t: progress_dialog.update_progress(int(r/t*100)) if t > 0 else None)
                    loop.exec()

                    if reply.error() == reply.NetworkError.NoError:
                        tmp_file.write(reply.readAll().data())
                        download_successful = True
                    else:
                        self.show_message(self.translator.translate("title_download_error"), self.translator.translate("msg_download_failed", e=reply.errorString()), "critical")
                    reply.deleteLater()
            finally:
                progress_dialog.close()

            if not download_successful:
                if archive_path and os.path.exists(archive_path): os.remove(archive_path)
                return
            try:
                sanitized_mod_name = self._sanitize_filename(remote_mod_data.get('_sName'))
                
                if category_type == 'direct_management':
                    mod_dest_path = os.path.join(self.get_game_mods_path(self.current_game), sanitized_mod_name)
                    self._extract_and_copy_mod(archive_path, mod_dest_path)
                    new_mod_info = {
                        "name": original_mod_name, "folder_name": sanitized_mod_name,
                        "display_name": remote_mod_data.get('_sName'),
                        "creator": remote_mod_data.get('_aSubmitter', {}).get('_sName'),
                        "url": remote_mod_data.get('_sProfileUrl'),
                        "profile_url": remote_mod_data.get('_sProfileUrl'),
                        "icon": existing_icon_path
                    }
                    profile["mods"].append(new_mod_info)
                else: 
                    profile_folder_name = profile['folder_name']
                    mod_dest_path = os.path.join(self.get_management_path(self.current_game), profile_folder_name, sanitized_mod_name)
                    self._extract_and_copy_mod(archive_path, mod_dest_path)
                    for root, _, files in os.walk(mod_dest_path):
                        for file in files:
                            if file.lower().endswith('.ini'):
                                self._rewrite_ini_file(os.path.join(root, file), slot_to_preserve, profile_folder_name, sanitized_mod_name)
                    new_mod_info = {
                        "name": original_mod_name, "path": mod_dest_path, "slot_id": slot_to_preserve,
                        "display_name": remote_mod_data.get('_sName'),
                        "creator": remote_mod_data.get('_aSubmitter', {}).get('_sName'),
                        "url": remote_mod_data.get('_sProfileUrl'),
                        "profile_url": remote_mod_data.get('_sProfileUrl'),
                        "icon": existing_icon_path
                    }
                    profile["mods"].append(new_mod_info)
                    profile['mods'].sort(key=lambda m: m.get('slot_id', 999))
                self.save_profiles()
                
                if category_type == 'direct_management':
                    self.update_direct_mods_list_cards(profile_name)
                else:
                    self.update_managed_mods_list(profile_name)
                    
                self._simulate_f10_press()
                self.show_message(self.translator.translate("success_title"), self.translator.translate("msg_mod_updated_successfully"))

            except Exception as e:
                self.show_message(self.translator.translate("title_install_error"), self.translator.translate("msg_install_error_generic", e=e), "critical")
            finally:
                if archive_path and os.path.exists(archive_path):
                    os.remove(archive_path)

    def scan_and_register_untracked_mods(self, profile_name):
        profile = self.profiles[self.current_game][self.current_category][profile_name]
        category_type = self.category_widgets[self.current_category]['type']

        if category_type == 'direct_management':
            self.show_message("Función no aplicable", "Esta función solo está disponible para perfiles de gestión de mods (no gestión directa).")
            return

        profile_folder_name = profile['folder_name']
        management_path = self.get_management_path(self.current_game)
        scan_path = os.path.join(management_path, profile_folder_name)
        
        registered_folders = {mod.get('name') for mod in profile.get("mods", [])}

        if not os.path.isdir(scan_path):
            return
            
        untracked_folders = []
        for item in os.listdir(scan_path):
            item_path = os.path.join(scan_path, item)
            if os.path.isdir(item_path) and item not in registered_folders:
                untracked_folders.append(item)

        if not untracked_folders:
            self.show_message(self.translator.translate("sync_title"), self.translator.translate("sync_no_unregistered_mods"))
            return

        added_mods_count = 0
        for mod_folder in untracked_folders:
            info_dialog = ModInfoDialog(mod_info={"display_name": mod_folder.replace("_", " ")}, parent=self)
            if not info_dialog.exec():
                continue

            details = info_dialog.get_details()
            if not details["display_name"]:
                details["display_name"] = mod_folder
                
            slot_id = len(profile.get("mods", [])) + 1
            mod_dest_path = os.path.join(scan_path, mod_folder)
            
            for root, _, files in os.walk(mod_dest_path):
                for file in files:
                    if file.lower().endswith('.ini'):
                        self._rewrite_ini_file(os.path.join(root, file), slot_id, profile_folder_name, mod_folder)

            icon_path = self._copy_icon_to_cache(details['icon_source_path'], f"mod_{profile_name}_{mod_folder}")
            
            new_mod_info = {
                "name": mod_folder,
                "path": mod_dest_path,
                "slot_id": slot_id,
                "display_name": details["display_name"],
                "creator": details["creator"],
                "url": details["url"],
                "icon": icon_path
            }
            profile["mods"].append(new_mod_info)
            added_mods_count += 1
            
        if added_mods_count > 0:
            self.save_profiles()
            self.update_managed_mods_list(profile_name)
            self._simulate_f10_press()
            self.show_message(self.translator.translate("success_title"), self.translator.translate("sync_success_message", count=added_mods_count))
        
    def on_mod_state_changed_from_overlay(self, game, category, profile_name, mod_data):
        print(f"ModManager: Recibida señal de actualización desde el overlay para {profile_name}")
        self.profiles = self.load_profiles()
        
        if (self.current_game == game and
            self.current_category == category and
            self.profile_list_stack.currentWidget().currentItem() and
            self.profile_list_stack.currentWidget().currentItem().data(Qt.ItemDataRole.UserRole) == profile_name):
            print("La vista actual coincide. Refrescando la lista de mods...")
            category_type = self.category_widgets[self.current_category]['type']
            if category_type == 'direct_management':
                self.update_direct_mods_list_cards(profile_name)
            else:
                self.update_managed_mods_list(profile_name)
        else:
            print("La vista actual no coincide, no se requiere refresco de UI.")

    def get_management_path(self, game):
        if not self.xxmi_path or game not in self.game_data: return None
        return os.path.join(self.get_game_mods_path(game), self.management_folder_name)
        
    def setup_nrmm_structure(self, game):
        management_path = self.get_management_path(game)
        if not management_path: return
        os.makedirs(management_path, exist_ok=True)
        global_config_path = os.path.join(management_path, "MIMM_Global.ini")
        if not os.path.exists(global_config_path):
            content = (f"; MIMM Global Config\n" f"namespace = {self.root_namespace}\\profile_manager\n\n" "[System]\n" "check_foreground_window = 0\n\n" "[Constants]\n" "persist global $active_profile_id = 0\n\n" "[KeyProfile]\n" "key = VK_CLEAR VK_SPACE\n" "run = CommandListProfile\n\n" "[CommandListProfile]\n" "$active_profile_id = cursor_screen_y\n")
            with open(global_config_path, "w") as f: f.write(content)
            
    def load_config(self):
        path = os.path.join(self.app_data_path, "config.json") 
        if os.path.exists(path):
            try:
                with open(path, 'r') as f: return json.load(f)
            except json.JSONDecodeError: return {}
        return {}
        
    def save_config(self):
        path = os.path.join(self.app_data_path, "config.json") 
        with open(path, 'w') as f: json.dump(self.config, f, indent=4)
        
    def load_profiles(self):
        path = os.path.join(self.app_data_path, "mod_manager_profiles.json")
        if os.path.exists(path):
            try:
                with open(path, 'r') as f: return json.load(f)
            except json.JSONDecodeError: return {}
        return {}
    
    def _setup_tray_icon(self):
        icon_path = resource_path("app_icon.ico")
        app_icon = QIcon(icon_path)
        
        if app_icon.isNull():
            print("ADVERTENCIA: No se pudo cargar 'app_icon.ico'. Usando icono por defecto.")
            app_icon = QIcon(self.style().standardPixmap(QStyle.StandardPixmap.SP_ComputerIcon))
        
        self.setWindowIcon(app_icon)
        self.tray_icon = QSystemTrayIcon(app_icon, self)

        self.tray_icon.setToolTip("Model Importer Mod Manager")

        tray_menu = QMenu()
        self.tray_menu_actions = {
            "tray_open": QAction(self.translator.translate("tray_open"), self),
            "tray_overlay": QAction(self.translator.translate("tray_overlay"), self),
            "tray_quit": QAction(self.translator.translate("tray_quit"), self)
        }
        
        self.tray_menu_actions["tray_open"].triggered.connect(self.show_window_from_tray)
        self.tray_menu_actions["tray_overlay"].setCheckable(True)
        self.tray_menu_actions["tray_overlay"].setChecked(True)
        self.tray_menu_actions["tray_overlay"].toggled.connect(self.toggle_overlay_functionality)
        self.tray_menu_actions["tray_quit"].triggered.connect(self.quit_application)
        
        tray_menu.addAction(self.tray_menu_actions["tray_open"])
        tray_menu.addSeparator()
        tray_menu.addAction(self.tray_menu_actions["tray_overlay"])
        tray_menu.addSeparator()
        tray_menu.addAction(self.tray_menu_actions["tray_quit"])
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.tray_icon.show()

    def save_profiles(self):
        path = os.path.join(self.app_data_path, "mod_manager_profiles.json") 
        with open(path, 'w') as f:
            json.dump(self.profiles, f, indent=4)
        if hasattr(self, 'overlay_controller'):
            self.overlay_controller.reload_profiles()

    def show_window_from_tray(self):
        self.setVisible(True)
        self.activateWindow()
        self.raise_()

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_window_from_tray()

    def toggle_overlay_functionality(self, checked):
        if checked:
            if not hasattr(self, 'overlay_controller') or self.overlay_controller is None:
                print("Iniciando funcionalidad del Overlay...")
                self.overlay_controller = OverlayController(self, self.translator)
                self.overlay_controller.mod_state_changed_from_overlay.connect(self.on_mod_state_changed_from_overlay)
        else:
            if hasattr(self, 'overlay_controller') and self.overlay_controller is not None:
                print("Deteniendo funcionalidad del Overlay...")

                if hasattr(self.overlay_controller, 'key_listener') and self.overlay_controller.key_listener:
                    self.overlay_controller.key_listener.stop()
                if hasattr(self.overlay_controller, 'controller_listener') and self.overlay_controller.controller_listener:
                    self.overlay_controller.controller_listener.stop()
                self.overlay_controller = None

    def quit_application(self):
        print("Saliendo de la aplicación...")
        self.is_quitting = True 
        self.close() 

    def closeEvent(self, event):
        if self.is_quitting:
            self.config['window_maximized'] = self.isMaximized()
            self.config['window_geometry'] = self.saveGeometry().toBase64().data().decode('utf-8')
            self.save_config()
            self.tray_icon.hide()
            if hasattr(self, 'overlay_controller') and self.overlay_controller is not None:
                if hasattr(self.overlay_controller, 'key_listener'):
                    self.overlay_controller.key_listener.stop()
            QApplication.instance().quit()
            event.accept()
        else:
            self.hide()
            self.tray_icon.showMessage(
                self.translator.translate("tray_running_title"),
                self.translator.translate("tray_running_message"),
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
            event.ignore()

if __name__ == '__main__':
    app_data_path = os.path.join(os.getenv('APPDATA'), "MIMM")
    os.makedirs(app_data_path, exist_ok=True)
    command_file_path = os.path.join(app_data_path, "mimm_command.lock")
    startup_url = None
    if len(sys.argv) > 1 and sys.argv[1].strip().lower().startswith("mimm:"):
        startup_url = sys.argv[1].strip()
    mutex_name = "MIMM_Global_Mutex_XxR09xX"
    instance = SingleInstance(name=mutex_name)

    if instance.is_running:
        if startup_url:
            try:
                with open(command_file_path, 'w') as f:
                    f.write(startup_url)
                window_title = "Model Importer - Gestor de Mods"
                hwnd = win32gui.FindWindow(None, window_title)
                if hwnd:
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    win32gui.SetForegroundWindow(hwnd)
            except Exception as e:
                print(f"Error en la instancia mensajera: {e}")
        sys.exit(0)
    
    app = QApplication(sys.argv)

    missing_deps = []
    if not win32api: missing_deps.append("'pywin32'")
    if not patoolib: missing_deps.append("'patool' y 'py7zr'")
    if not requests: missing_deps.append("'requests'")
    
    if missing_deps:
        QMessageBox.critical(None, "Faltan Dependencias", f"Faltan las siguientes librerías: {', '.join(missing_deps)}.")
        sys.exit(1)

    QApplication.setQuitOnLastWindowClosed(False)
    manager = ModManager(startup_url=startup_url)

    if "window_geometry" in manager.config:
        geom_data = manager.config['window_geometry'].encode('utf-8')
        manager.restoreGeometry(QByteArray.fromBase64(geom_data))

    if not manager.config.get("start_minimized", False):
        if manager.config.get("window_maximized", False):
            manager.showMaximized()
        else:
            manager.show()
        
    sys.exit(app.exec())