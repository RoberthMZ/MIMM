import sys
import os
import time
import json
import requests
import tempfile
import shutil
import patoolib
import re
import base64
from datetime import datetime
try:
    import win32api
    import win32con
    import win32gui
except ImportError:
    win32api = None
    win32gui = None
    win32con = None
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QDialog, QCheckBox, QComboBox, QSizePolicy,
    QProgressBar, QListView, QMessageBox, QFrame,
)
from PyQt6.QtCore import (
    Qt, QSize, QUrl, QTimer, pyqtSignal, QThreadPool, QRectF, QObject, QRunnable, QEvent, pyqtProperty, QPropertyAnimation, QByteArray, QEasingCurve, QSequentialAnimationGroup
)
from PyQt6.QtGui import (
    QPixmap, QIcon, QAction, QColor, QPalette, QPainter, QBrush, QPainterPath, QCursor
)
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PyQt6.QtSvg import QSvgRenderer

class LogoLoadingWidget(QWidget):
    GAMEBANANA_LOGO_B64 = "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAABP0lEQVRYhWNkoD74j0OcEZsgEw0cQBKgmQN8HPgYfBz4Bs4BxAKs8UIlQFRaGP4h8OuhDYRz/zUDAwMDA7vDTRS7BzwEWOht4c8d3AwMDAwM7B5f/zMwDNMQ+M/AwMDw+002hPP1Il7FAx4Cow4YdQA1c8F/BgYGhj8fJkA4f24TpWlIhgDWWu7P5yUQyZ/HIfSfxxCJN1/wGjYoQgBXvY0VwHzK8PcNijjM5wz/f0Dop48g3M/fIfwfTxgYGBgYPn/7jaJvwEOAkQFWb581gIhIy0EkmEWhKjiw64T5FMZ9dBaVj+ZzGGD3+Ips98CHADwXwFzMCIs7kXdkGYjL56/e/8KqfsBDALlN+J+BgYHh5wF1ykzE4XPZSHjqH/ytYpRyAdaGIxbA8rlIEEacD86+ITH9ApJKShLNHvgQAACCt2baH3vA9wAAAABJRU5ErkJggg=="

    def __init__(self, parent=None, size=100):
        super().__init__(parent)
        self._opacity = 0.3
        self._pixmap = None
        self.setHidden(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(size, size)

        self.animation_group = QSequentialAnimationGroup(self)
        fade_in = QPropertyAnimation(self, b"opacity", self)
        fade_in.setDuration(800); fade_in.setStartValue(0.3); fade_in.setEndValue(1.0); fade_in.setEasingCurve(QEasingCurve.Type.InOutSine)
        fade_out = QPropertyAnimation(self, b"opacity", self)
        fade_out.setDuration(800); fade_out.setStartValue(1.0); fade_out.setEndValue(0.3); fade_out.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.animation_group.addAnimation(fade_in); self.animation_group.addAnimation(fade_out); self.animation_group.setLoopCount(-1)

    def get_opacity(self): return self._opacity
    def set_opacity(self, value): self._opacity = value; self.update()
    opacity = pyqtProperty(float, get_opacity, set_opacity)

    def _update_pixmap(self, color):
        image_data = QByteArray(base64.b64decode(self.GAMEBANANA_LOGO_B64))
        source_pixmap = QPixmap()
        source_pixmap.loadFromData(image_data, "PNG")
        target_pixmap = QPixmap(source_pixmap.size())
        target_pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(target_pixmap)
        painter.drawPixmap(0, 0, source_pixmap.mask())
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(target_pixmap.rect(), color)
        painter.end()
        self._pixmap = target_pixmap

    def paintEvent(self, event):
        if not self._pixmap: return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self._opacity)
        painter.drawPixmap(self.rect(), self._pixmap)

    def start_animation(self):
        highlight_color = self.palette().color(QPalette.ColorRole.Highlight)
        self._update_pixmap(highlight_color)
        self.recenter_in_parent()
        self.show()
        self.animation_group.start()

    def stop_animation(self):
        self.animation_group.stop()
        self.hide()
        
    def recenter_in_parent(self):
        if self.parentWidget():
            parent_rect = self.parentWidget().rect()
            self.move(
                parent_rect.center().x() - self.width() // 2,
                parent_rect.center().y() - self.height() // 2
            )

class ArcLoadingWidget(QWidget):
    def __init__(self, parent=None, size=60, thickness=6):
        super().__init__(parent)
        self._angle = 0
        self._thickness = thickness
        self.setHidden(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground) 
        self.setFixedSize(size, size)

        self.animation = QPropertyAnimation(self, b"angle", self)
        self.animation.setDuration(1200)
        self.animation.setStartValue(0)
        self.animation.setEndValue(360)
        self.animation.setLoopCount(-1)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutSine)

    def get_angle(self): return self._angle
    def set_angle(self, value): self._angle = value; self.update()
    angle = pyqtProperty(int, get_angle, set_angle)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = painter.pen()
        pen.setColor(self.palette().color(QPalette.ColorRole.Highlight))
        pen.setWidth(self._thickness)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        rect = self.rect().adjusted(pen.width() // 2, pen.width() // 2, -pen.width() // 2, -pen.width() // 2)
        painter.drawArc(rect, self._angle * 16, 90 * 16)

    def start_animation(self):
        self.recenter_in_parent()
        self.show()
        self.animation.start()

    def stop_animation(self):
        self.animation.stop()
        self.hide()
        
    def recenter_in_parent(self):
        if self.parentWidget():
            parent_rect = self.parentWidget().rect()
            self.move(
                parent_rect.center().x() - self.width() // 2,
                parent_rect.center().y() - self.height() // 2
            )

class WorkerSignals(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(tuple)
    result = pyqtSignal(object)
    progress = pyqtSignal(int)

class Worker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        if 'progress_callback' not in self.kwargs:
            self.kwargs['progress_callback'] = self.signals.progress

    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:
            import traceback
            self.signals.error.emit((type(e), e, traceback.format_exc()))
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()


class DownloadProgressDialog(QDialog):
    def __init__(self, translator, parent=None):
        super().__init__(parent)
        self.translator = translator
        self.setWindowTitle(self.translator.translate("download_progress_title"))
        self.setModal(True)
        self.setFixedSize(400, 100)
        layout = QVBoxLayout(self)
        self.info_label = QLabel(self.translator.translate("download_progress_info"))
        self.progress_bar = QProgressBar()
        layout.addWidget(self.info_label)
        layout.addWidget(self.progress_bar)
        self.setWindowFlag(Qt.WindowType.Dialog)
        self.setWindowFlag(Qt.WindowType.CustomizeWindowHint, True)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

    def update_progress(self, percentage):
        self.progress_bar.setValue(percentage)

    def set_info_text(self, text):
        self.info_label.setText(text)


class ApiModCardWidget(QWidget):
    download_requested = pyqtSignal(dict)

    def __init__(self, mod_data, manager, image_manager, parent=None):
        super().__init__(parent)
        self.mod_data = mod_data
        self.manager = manager
        self.translator = manager.translator
        self.image_manager = image_manager
        self.is_hovered = False
        self.setFixedSize(290, 290)
        self.setMouseTracking(True)
        self.setStyleSheet("ApiModCardWidget { background-color: rgba(128, 128, 128, 0.05); border: 1px solid rgba(128, 128, 128, 0.1); border-radius: 8px; outline: none; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8); layout.setSpacing(5)

        self.image_label = QLabel()
        self.image_label.setFixedSize(264, 148)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: rgba(0,0,0,0.1); border-radius: 4px; outline: none;")
    
        self.loading_spinner = ArcLoadingWidget(self.image_label)
        
        layout.addWidget(self.image_label)
        self.load_image()

        name = mod_data.get('_sName', self.translator.translate("api_card_unknown_name"))
        creator = mod_data.get('_aSubmitter', {}).get('_sName', self.translator.translate("api_card_unknown_creator"))
        self.name_label = QLabel(f"<b>{name}</b>"); self.name_label.setWordWrap(True)
        self.creator_label = QLabel(f"<i>{self.translator.translate('api_card_creator_prefix', creator=creator)}</i>"); self.creator_label.setWordWrap(True)
        layout.addWidget(self.name_label); layout.addWidget(self.creator_label); layout.addStretch()

        stats_layout = QHBoxLayout(); stats_layout.setSpacing(10)
        likes, downloads, views = mod_data.get('_nLikeCount', 0), mod_data.get('_nDownloadCount', 0), mod_data.get('_nViewCount', 0)
        stats_layout.addWidget(self._create_stat_label(self.manager.ICON_LIKE, str(likes), self.translator.translate("api_card_likes")))
        stats_layout.addWidget(self._create_stat_label(self.manager.ICON_DOWNLOAD, str(downloads), self.translator.translate("api_card_downloads")))
        stats_layout.addWidget(self._create_stat_label(self.manager.ICON_VIEWS, str(views), self.translator.translate("api_card_views")))
        layout.addLayout(stats_layout)

        self.download_button = QPushButton(self.translator.translate("api_card_download_button"))
        highlight_color = self.palette().color(QPalette.ColorRole.Highlight)
        icon_color = QColor(Qt.GlobalColor.white) if (0.2126 * highlight_color.redF() + 0.7152 * highlight_color.greenF() + 0.0722 * highlight_color.blueF()) < 0.6 else QColor(Qt.GlobalColor.black)
        self.download_button.setIcon(self.manager._create_colored_icon(self.manager.ICON_DOWNLOAD, icon_color))
        self.download_button.clicked.connect(lambda: self.download_requested.emit(self.mod_data))
        self.download_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.download_button.setStyleSheet(f"QPushButton {{ background-color: {highlight_color.name()}; color: {icon_color.name()}; border: none; padding: 6px 12px; border-radius: 14px; font-weight: bold; outline: none; }} QPushButton:hover {{ background-color: {highlight_color.lighter(120).name()}; }} QPushButton:pressed {{ background-color: {highlight_color.darker(110).name()}; }}")
        layout.addWidget(self.download_button)

    def _create_stat_label(self, icon_b64, text, tooltip):
        widget = QWidget(); layout = QHBoxLayout(widget); layout.setContentsMargins(0,0,0,0)
        icon_label = QLabel(); icon_label.setPixmap(self.manager._create_colored_icon(icon_b64, self.palette().color(QPalette.ColorRole.Text)).pixmap(16, 16))
        text_label = QLabel(text); layout.addWidget(icon_label); layout.addWidget(text_label); widget.setToolTip(tooltip)
        return widget

    def load_image(self):
        previews = self.mod_data.get('_aPreviewMedia', [])
        if isinstance(previews, list) and previews:
            img_info = previews[0]; file_key = '_sFile670' if '_sFile670' in img_info else '_sFile'
            if img_info.get('_sBaseUrl') and img_info.get(file_key):
                img_url = img_info['_sBaseUrl'] + '/' + img_info[file_key]
                self.loading_spinner.start_animation()
                reply = self.image_manager.get(QNetworkRequest(QUrl(img_url)))
                reply.finished.connect(self.on_image_loaded)
            else: self.image_label.setText(self.translator.translate("api_card_invalid_image_url"))
        else: self.image_label.setText(self.translator.translate("api_card_no_image"))

    def on_image_loaded(self):
        reply = self.sender()
        if not reply: return
        self.loading_spinner.stop_animation()
        if reply.error() == QNetworkReply.NetworkError.NoError:
            pixmap = QPixmap(); pixmap.loadFromData(reply.readAll().data())
            self.image_label.setPixmap(pixmap.scaled(self.image_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            print(self.translator.translate("log_image_download_error", error=reply.errorString()))
            self.image_label.setText(self.translator.translate("api_card_load_error"))
        reply.deleteLater()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.is_hovered:
            painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            highlight_color = self.palette().color(QPalette.ColorRole.Highlight); highlight_color.setAlpha(40)
            path = QPainterPath(); path.addRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 7, 7); painter.fillPath(path, QBrush(highlight_color))

    def enterEvent(self, event): self.is_hovered = True; self.update(); super().enterEvent(event)
    def leaveEvent(self, event): self.is_hovered = False; self.update(); super().leaveEvent(event)


class FileSelectionDialog(QDialog):
    def __init__(self, files, parent=None):
        super().__init__(parent)
        self.translator = parent.translator
        self.setWindowTitle(self.translator.translate("file_select_title"))
        self.setMinimumSize(500, 350)
        self.selected_file = None
        highlight_color = self.palette().color(QPalette.ColorRole.Highlight)
        luminance = 0.2126 * highlight_color.redF() + 0.7152 * highlight_color.greenF() + 0.0722 * highlight_color.blueF()
        text_color_on_highlight = "#000000" if luminance > 0.5 else "#FFFFFF"
        list_widget_style = f"""
            QListWidget {{ border: 1px solid #d0d0d0; border-radius: 4px; outline: none; }}
            QListWidget::item {{ padding: 8px; }}
            QListWidget::item:hover {{ border: 3px solid {highlight_color.name()}; background-color: none; }}
            QListWidget::item:selected {{ background-color: {highlight_color.name()}; color: {text_color_on_highlight}; border-radius: 4px; }}
        """
        secondary_button_style = f"""
            QPushButton {{ border: 1px solid #cccccc; border-radius: 4px; padding: 6px 12px; outline: none;}}
            QPushButton:hover {{ border-color: {highlight_color.name()}; }}
            QPushButton:pressed {{ background-color: {highlight_color.darker(120).name()}; }}
        """
        primary_button_style = f"""
            QPushButton {{ background-color: {highlight_color.name()}; color: {text_color_on_highlight}; border: none; border-radius: 4px; padding: 8px 16px; font-weight: bold; outline: none;}}
            QPushButton:hover {{ background-color: {highlight_color.lighter(115).name()}; }}
            QPushButton:pressed {{ background-color: {highlight_color.darker(115).name()}; }}
            QPushButton:disabled {{ background-color: #d0d0d0; color: #808080; }}
        """
        self.layout = QVBoxLayout(self); self.layout.setContentsMargins(15, 15, 15, 15); self.layout.setSpacing(10)
        instruction_label = QLabel(self.translator.translate("file_select_instruction")); instruction_label.setStyleSheet("font-weight: bold;"); instruction_label.setWordWrap(True); self.layout.addWidget(instruction_label)
        self.list_widget = QListWidget(); self.list_widget.setStyleSheet(list_widget_style)
        for file_info in files:
            filename = file_info.get('_sFile', self.translator.translate("filename_not_available")); size_kb = file_info.get('_nFilesize', 0) / 1024
            timestamp = file_info.get('_tsDateAdded'); date_added_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S') if timestamp else self.translator.translate("date_not_available")
            description = file_info.get('_sDescription', '').strip(); added_label = self.translator.translate("list_item_added"); description_label = self.translator.translate("list_item_description")
            item_text = f"{filename} ({size_kb:.2f} KB)\n{added_label}: {date_added_str}";
            if description: item_text += f"\n{description_label}: {description}"
            item = QListWidgetItem(item_text); item.setData(Qt.ItemDataRole.UserRole, file_info); self.list_widget.addItem(item)
        if self.list_widget.count() > 0: self.list_widget.setCurrentRow(0)
        self.list_widget.itemDoubleClicked.connect(self.accept); self.list_widget.currentItemChanged.connect(self.on_selection_changed); self.layout.addWidget(self.list_widget)
        separator = QFrame(); separator.setFrameShape(QFrame.Shape.HLine); separator.setFrameShadow(QFrame.Shadow.Sunken); self.layout.addWidget(separator)
        self.buttons_layout = QHBoxLayout(); self.buttons_layout.addStretch()
        self.cancel_button = QPushButton(self.translator.translate("button_cancel")); self.cancel_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor)); self.cancel_button.setStyleSheet(secondary_button_style); self.cancel_button.clicked.connect(self.reject); self.buttons_layout.addWidget(self.cancel_button)
        self.ok_button = QPushButton(self.translator.translate("button_ok")); self.ok_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor)); self.ok_button.setStyleSheet(primary_button_style); self.ok_button.clicked.connect(self.accept); self.ok_button.setEnabled(self.list_widget.currentItem() is not None); self.buttons_layout.addWidget(self.ok_button)
        self.layout.addLayout(self.buttons_layout)

    def on_selection_changed(self, current_item, previous_item): self.ok_button.setEnabled(current_item is not None)
    def accept(self):
        current_item = self.list_widget.currentItem()
        if current_item: self.selected_file = current_item.data(Qt.ItemDataRole.UserRole)
        super().accept()
    def get_selected_file(self): return self.selected_file

class DownloadTab(QWidget):
    BASE_API_URL = "https://gamebanana.com/apiv6/Mod/ByCategory"
    MODS_PER_PAGE = 20

    def __init__(self, profile_name, category_id, manager, parent=None):
        super().__init__(parent)
        self.profile_name, self.category_id, self.manager, self.translator = profile_name, category_id, manager, manager.translator
        self.current_page, self.is_loading, self.can_go_next = 1, False, True
        self.threadpool = QThreadPool(); self.image_manager = QNetworkAccessManager(self); self.is_first_load = True
        self.setup_ui()
        self.list_container.installEventFilter(self)
        self.retranslate_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self); controls_layout = QHBoxLayout(); controls_layout.setSpacing(10)
        highlight_color = self.palette().color(QPalette.ColorRole.Highlight); text_color_name = self.palette().color(QPalette.ColorRole.Text).name()
        search_bar_stylesheet = f"QLineEdit {{outline: none; border: 1px solid #cccccc; border-radius: 15px; padding-left: 10px; padding-right: 10px; height: 30px; background-color: rgba(128, 128, 128, 0.08); }} QLineEdit:focus {{ border: 1px solid {highlight_color.name()}; }}"
        raw_svg_arrow = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{text_color_name}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>'
        encoded_svg_arrow = base64.b64encode(raw_svg_arrow.encode('utf-8')).decode('utf-8')
        combo_box_stylesheet = f"QComboBox {{ border: 1px solid #cccccc; border-radius: 15px; padding: 1px 18px 1px 10px; height: 28px; background-color: rgba(128, 128, 128, 0.08); }} QComboBox:focus {{ border: 1px solid {highlight_color.name()}; }} QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: top right; width: 20px; border-left-width: 0px; border-top-right-radius: 15px; border-bottom-right-radius: 15px; }} QComboBox::down-arrow {{ image: url(data:image/svg+xml;base64,{encoded_svg_arrow}); width: 14px; height: 14px; }} QComboBox QAbstractItemView {{ border: 1px solid #cccccc; border-radius: 4px; background-color: {self.palette().color(QPalette.ColorRole.Base).name()}; selection-background-color: {highlight_color.name()}; }}"
        checkbox_stylesheet = f"QCheckBox::indicator {{ width: 18px; height: 18px; border: 1px solid #cccccc; border-radius: 4px; }} QCheckBox::indicator:unchecked:hover {{ border: 1px solid {highlight_color.name()}; }} QCheckBox::indicator:checked {{ background-color: {highlight_color.name()}; border: 1px solid {highlight_color.name()}; image: url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IndoaXRlIiBzdHJva2Utd2lkdGg9IjIiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCI+PHBvbHlsaW5lIHBvaW50cz0iMjAgNiA5IDE3IDQgMTIiPjwvcG9seWxpbmU+PC9zdmc+); }}"
        profile_data = self.manager.profiles[self.manager.current_game][self.manager.current_category].get(self.profile_name, {})
        icon_path = profile_data.get('icon') or self.manager.default_icon_path
        profile_icon = QLabel(); profile_icon.setFixedSize(32, 32)
        if icon_path and os.path.exists(icon_path):
            processed_icon = self._create_processed_icon(icon_path)
            profile_icon.setPixmap(processed_icon.pixmap(QSize(32, 32)))
        controls_layout.addWidget(profile_icon)
        self.sort_combo = QComboBox(); self.sort_combo.currentIndexChanged.connect(self.on_filter_changed); self.sort_combo.setStyleSheet(combo_box_stylesheet); controls_layout.addWidget(self.sort_combo)
        category_type = self.manager.category_widgets[self.manager.current_category]['type']
        if category_type == 'direct_management':
            self.subcategory_combo = QComboBox(); self.subcategory_combo.addItem(self.translator.translate("category_others"), self.category_id)
            for subcat in self.manager.game_data[self.manager.current_game]['categories'][self.manager.current_category].get('sub_categories', []): self.subcategory_combo.addItem(self.translator.translate(subcat['t_key']), subcat['id'])
            self.subcategory_combo.currentIndexChanged.connect(self.on_filter_changed); self.subcategory_combo.setStyleSheet(combo_box_stylesheet); controls_layout.addWidget(self.subcategory_combo)
        else: self.subcategory_combo = None
        self.search_bar = QLineEdit(); self.search_bar.setClearButtonEnabled(True)
        search_icon = self.manager._create_colored_icon(self.manager.ICON_SEARCH, self.palette().color(QPalette.ColorRole.Text))
        self.search_bar.addAction(QAction(search_icon, "", self), QLineEdit.ActionPosition.LeadingPosition)
        self.search_bar.returnPressed.connect(self.on_filter_changed); self.search_bar.setStyleSheet(search_bar_stylesheet); controls_layout.addWidget(self.search_bar, 1)
        self.nsfw_check = QCheckBox(); self.nsfw_check.stateChanged.connect(self.on_filter_changed); self.nsfw_check.setStyleSheet(checkbox_stylesheet); controls_layout.addWidget(self.nsfw_check); main_layout.addLayout(controls_layout)
        self.list_container = QWidget(); container_layout = QVBoxLayout(self.list_container); container_layout.setContentsMargins(0, 0, 0, 0)
        self.mods_list_widget = QListWidget(); self.mods_list_widget.setViewMode(QListView.ViewMode.IconMode); self.mods_list_widget.setResizeMode(QListView.ResizeMode.Adjust); self.mods_list_widget.setMovement(QListView.Movement.Static); self.mods_list_widget.setUniformItemSizes(True); self.mods_list_widget.setGridSize(QSize(295, 310)); self.mods_list_widget.setStyleSheet("QListWidget { border: none; outline: none; background-color: transparent; } QListWidget::item { border: none; } QListWidget::item:selected { background-color: transparent; }")
        container_layout.addWidget(self.mods_list_widget)
        self.main_loading_animation = LogoLoadingWidget(self.list_container, size=120)
        main_layout.addWidget(self.list_container)
        nav_layout = QHBoxLayout()
        self.prev_button = QPushButton(); self.prev_button.setIcon(self.manager._create_colored_icon("PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxwb2x5bGluZSBwb2ludHM9IjE1IDE4IDkgMTIgMTUgNiI+PC9wb2x5bGluZT48L3N2Zz4=", highlight_color)); self.prev_button.clicked.connect(self.previous_page)
        self.page_label = QLabel(); self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.next_button = QPushButton(); self.next_button.setIcon(self.manager._create_colored_icon("PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxwb2x5bGluZSBwb2ludHM9IjkgMTggMTUgMTIgOSA2Ij48L3BvbHlsaW5lPjwvc3ZnPg==", highlight_color)); self.next_button.setLayoutDirection(Qt.LayoutDirection.RightToLeft); self.next_button.clicked.connect(self.next_page)
        for btn in [self.prev_button, self.next_button]: btn.setStyleSheet("QPushButton { border: none; outline: none; }")
        nav_layout.addStretch(); nav_layout.addWidget(self.prev_button); nav_layout.addWidget(self.page_label); nav_layout.addWidget(self.next_button); nav_layout.addStretch(); main_layout.addLayout(nav_layout)

    def showEvent(self, event):
        super().showEvent(event)
        if self.is_first_load: self.is_first_load = False; self.fetch_mods()

    def eventFilter(self, source, event):
        if source is self.list_container and event.type() == QEvent.Type.Resize:
            self.main_loading_animation.recenter_in_parent()
        return super().eventFilter(source, event)
    
    def _is_strictly_dark_grayscale(self, image):
        if image.isNull(): return False

        DARKNESS_THRESHOLD = 120
        COLOR_TOLERANCE = 15

        scaled_image = image.scaled(16, 16, Qt.AspectRatioMode.IgnoreAspectRatio)

        has_visible_pixels = False
        for y in range(scaled_image.height()):
            for x in range(scaled_image.width()):
                color = QColor(scaled_image.pixel(x, y))
                if color.alpha() < 50: continue
                has_visible_pixels = True

                r, g, b = color.red(), color.green(), color.blue()
                if r > DARKNESS_THRESHOLD or g > DARKNESS_THRESHOLD or b > DARKNESS_THRESHOLD: return False
                if (max(r, g, b) - min(r, g, b)) > COLOR_TOLERANCE: return False

        return has_visible_pixels

    def _create_processed_icon(self, icon_path):
        if not icon_path or not os.path.exists(icon_path):
            return QIcon()

        original_pixmap = QPixmap(icon_path)
        if original_pixmap.isNull():
            return QIcon()

        if self._is_strictly_dark_grayscale(original_pixmap.toImage()):
            target_color = self.palette().color(QPalette.ColorRole.Text)
            
            recolored_pixmap = QPixmap(original_pixmap.size())
            recolored_pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(recolored_pixmap)
            painter.drawPixmap(0, 0, original_pixmap)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            painter.fillRect(recolored_pixmap.rect(), target_color)
            painter.end()
            return QIcon(recolored_pixmap)

        return QIcon(original_pixmap)
    
    def retranslate_ui(self):
        self.sort_combo.blockSignals(True);
        if self.subcategory_combo: self.subcategory_combo.blockSignals(True)
        self.sort_combo.clear(); self.sort_combo.addItem(self.translator.translate("download_tab_sort_updated"), "_tsDateUpdated,DESC"); self.sort_combo.addItem(self.translator.translate("download_tab_sort_newest"), "_tsDateAdded,DESC"); self.sort_combo.addItem(self.translator.translate("download_tab_sort_popular"), "_nLikeCount,DESC")
        if self.subcategory_combo:
            self.subcategory_combo.clear(); self.subcategory_combo.addItem(self.translator.translate("download_tab_cat_others"), self.category_id)
            for subcat in self.manager.game_data[self.manager.current_game]['categories'][self.manager.current_category].get('sub_categories', []): self.subcategory_combo.addItem(subcat['name'], subcat['id'])
        self.search_bar.setPlaceholderText(self.translator.translate("download_tab_search_placeholder")); self.nsfw_check.setText(self.translator.translate("download_tab_nsfw_checkbox")); self.prev_button.setText(self.translator.translate("download_tab_nav_previous")); self.next_button.setText(self.translator.translate("download_tab_nav_next"))
        self.sort_combo.blockSignals(False)
        if self.subcategory_combo: self.subcategory_combo.blockSignals(False)
        self.update_navigation_controls()

    def fetch_mods(self):
        if self.is_loading: return
        self.is_loading = True; self.can_go_next = False; self.mods_list_widget.clear(); self.update_navigation_controls()
        self.page_label.setText(self.translator.translate("download_tab_searching"))
        self.main_loading_animation.start_animation()
        effective_category_id = self.subcategory_combo.currentData() if self.subcategory_combo else self.category_id
        worker = Worker(self._fetch_and_filter_mods_paginated, page_to_display=self.current_page, search_text=self.search_bar.text().strip(), category_id=effective_category_id, sort_order=self.sort_combo.currentData(), show_nsfw=self.nsfw_check.isChecked())
        worker.signals.result.connect(self.on_fetch_result); worker.signals.error.connect(self.on_fetch_error); worker.signals.finished.connect(self.on_fetch_finished); self.threadpool.start(worker)

    def _fetch_and_filter_mods_paginated(self, page_to_display, search_text, category_id, sort_order, show_nsfw, progress_callback):
        mods_for_page, num_to_skip, skipped_count, api_page, can_fetch_more = [], (page_to_display - 1) * self.MODS_PER_PAGE, 0, 1, True; game_id = self.manager.game_data[self.manager.current_game].get("game_id"); common_properties = "_idRow,_sName,_sProfileUrl,_aSubmitter,_tsDateUpdated,_tsDateAdded,_aPreviewMedia,_nViewCount,_nLikeCount,_nDownloadCount,_aFiles,_bIsNsfw,_aCategory"
        if search_text: base_url, base_params = "https://gamebanana.com/apiv6/Mod/ByName", [("_csvProperties", common_properties), ("_nPerpage", str(self.MODS_PER_PAGE)), ("_sName", f"*{search_text}*"), ("_idGameRow", str(game_id))]
        else: base_url, base_params = self.BASE_API_URL, [("_csvProperties", common_properties), ("_nPerpage", str(self.MODS_PER_PAGE)), ("_sOrderBy", sort_order), ("_aCategoryRowIds[]", str(category_id))]
        while len(mods_for_page) < self.MODS_PER_PAGE and can_fetch_more:
            params = base_params + [("_nPage", str(api_page))]
            if not show_nsfw: params.append(("_aArgs[]", "_sbIsNsfw = false"))
            try:
                response = requests.get(base_url, params=params, timeout=20, headers={'User-Agent': 'MIMM/1.0'}); response.raise_for_status(); mods_from_api = response.json()
                if not mods_from_api: can_fetch_more = False; continue
                for mod in mods_from_api:
                    if not show_nsfw and mod.get('_bIsNsfw', False): continue
                    if search_text and mod.get('_aCategory', {}).get('_idRow') != int(category_id): continue
                    if skipped_count < num_to_skip: skipped_count += 1; continue
                    mods_for_page.append(mod)
                    if len(mods_for_page) >= self.MODS_PER_PAGE: can_fetch_more = False; break
                api_page += 1
            except Exception as e: print(f"Error en la página API {api_page}: {e}"); can_fetch_more = False
        return mods_for_page

    def on_fetch_result(self, mods_data): self.populate_list(mods_data)
    def on_fetch_error(self, error_tuple): print(f"Error en hilo API: {error_tuple}"); self.show_message(self.translator.translate("error_title"), self.translator.translate("generic_error_message", error=error_tuple[1]), "critical"); self.can_go_next = False
    
    def on_fetch_finished(self):
        self.main_loading_animation.stop_animation()
        self.is_loading = False
        self.update_navigation_controls()

    def populate_list(self, mods_data):
        self.can_go_next = len(mods_data) == self.MODS_PER_PAGE
        if not mods_data and self.current_page == 1:
            placeholder = QWidget(); layout = QVBoxLayout(placeholder); layout.setAlignment(Qt.AlignmentFlag.AlignCenter); label = QLabel(self.translator.translate("download_tab_no_mods_found")); label.setStyleSheet("outline: none; font-size: 14px; color: grey;"); layout.addWidget(label); item = QListWidgetItem(); item.setSizeHint(QSize(self.mods_list_widget.width() - 30, 100)); self.mods_list_widget.addItem(item); self.mods_list_widget.setItemWidget(item, placeholder)
        else:
            for mod_info in mods_data:
                item = QListWidgetItem(); card = ApiModCardWidget(mod_info, self.manager, self.image_manager); card.download_requested.connect(self.on_download_request); item.setSizeHint(card.sizeHint()); self.mods_list_widget.addItem(item); self.mods_list_widget.setItemWidget(item, card)

    def update_navigation_controls(self): self.page_label.setText(self.translator.translate("download_tab_nav_page", page=self.current_page)); self.prev_button.setEnabled(self.current_page > 1 and not self.is_loading); self.next_button.setEnabled(self.can_go_next and not self.is_loading)
    def next_page(self):
        if not self.is_loading: self.current_page += 1; self.mods_list_widget.clear(); self.fetch_mods()
    def previous_page(self):
        if not self.is_loading and self.current_page > 1: self.current_page -= 1; self.mods_list_widget.clear(); self.fetch_mods()
    def on_filter_changed(self):
        if not self.is_loading: self.current_page = 1; self.mods_list_widget.clear(); self.fetch_mods()

    def on_download_request(self, mod_data):
        files = mod_data.get('_aFiles', [])
        if not files: self.show_message(self.translator.translate("error_title"), self.translator.translate("error_no_downloadable_files")); return
        file_to_download = files[0]
        if len(files) > 1:
            dialog = FileSelectionDialog(files, self);
            if dialog.exec(): file_to_download = dialog.selected_file
            else: return
        if file_to_download: self.start_download_worker(self.profile_name, mod_data, file_to_download)

    def start_download_worker(self, profile_name, mod_data, file_data):
        self.progress_dialog = DownloadProgressDialog(self.translator, self)
        worker = Worker(self._execute_download_and_install, profile_name, mod_data, file_data)
        worker.signals.progress.connect(self.progress_dialog.update_progress); worker.signals.result.connect(self.on_download_success); worker.signals.error.connect(self.on_download_error); worker.signals.finished.connect(self.progress_dialog.close)
        self.threadpool.start(worker); self.progress_dialog.exec()

    def on_download_success(self, result_message):
        self.show_message(self.translator.translate("success_title"), result_message)
        category_type = self.manager.category_widgets[self.manager.current_category]['type']
        if category_type == 'direct_management': self.manager.update_direct_mods_list_cards(self.profile_name)
        else: self.manager.update_managed_mods_list(self.profile_name)

    def on_download_error(self, error_tuple): _, err, _ = error_tuple; self.show_message(self.translator.translate("install_error_title"), self.translator.translate("generic_error_message", error=err), "critical")
    def _execute_download_and_install(self, profile_name, mod_data, file_data, progress_callback):
        download_url = file_data.get('_sDownloadUrl');
        if not download_url: raise ValueError(self.translator.translate("error_no_download_url"))
        archive_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_file:
                archive_path = tmp_file.name; response = requests.get(download_url, stream=True, headers={'User-Agent': 'MIMM/1.0'}); response.raise_for_status()
                total_size = int(response.headers.get('content-length', 0)); downloaded_size = 0
                for chunk in response.iter_content(chunk_size=8192):
                    tmp_file.write(chunk); downloaded_size += len(chunk)
                    if total_size > 0: progress_callback.emit(int((downloaded_size / total_size) * 100))
            progress_callback.emit(100)
            category_type = self.manager.category_widgets[self.manager.current_category]['type']
            if category_type == 'direct_management': return self._install_direct_mod_from_api(profile_name, mod_data, archive_path)
            else: return self._install_managed_mod_from_api(profile_name, mod_data, archive_path)
        finally:
            if archive_path and os.path.exists(archive_path): os.remove(archive_path)

    def _install_direct_mod_from_api(self, profile_name, mod_data, archive_path):
        mod_folder_name = self.manager._sanitize_filename(mod_data.get('_sName'))
        mod_dest_path = os.path.join(self.manager.get_game_mods_path(self.manager.current_game), mod_folder_name)
        if os.path.exists(mod_dest_path): raise FileExistsError(self.translator.translate("error_mod_exists_direct", name=mod_folder_name))
        self._extract_and_copy_mod(archive_path, mod_dest_path)
        profile = self.manager.profiles[self.manager.current_game][self.manager.current_category][profile_name]
        icon_path = self._download_and_save_mod_icon(mod_data, profile_name, mod_folder_name)
        new_mod_info = {"name": mod_folder_name, "folder_name": mod_folder_name, "display_name": mod_data.get('_sName'), "creator": mod_data.get('_aSubmitter', {}).get('_sName'), "url": mod_data.get('_sProfileUrl'), "profile_url": mod_data.get('_sProfileUrl'), "icon": icon_path}
        profile["mods"].append(new_mod_info); self.manager.save_profiles(); self._simulate_f10_press()
        return self.translator.translate("success_mod_installed", name=mod_folder_name)

    def _install_managed_mod_from_api(self, profile_name, mod_data, archive_path):
        mod_name = self.manager._sanitize_filename(mod_data.get('_sName'))
        profile = self.manager.profiles[self.manager.current_game][self.manager.current_category][profile_name]
        if any(m.get('name') == mod_name for m in profile.get("mods", [])): raise FileExistsError(self.translator.translate("error_mod_exists_managed", name=mod_name))
        profile_folder_name = profile['folder_name']; slot_id = len(profile.get("mods", [])) + 1
        mod_dest_path = os.path.join(self.manager.get_management_path(self.manager.current_game), profile_folder_name, mod_name)
        self._extract_and_copy_mod(archive_path, mod_dest_path)
        for root, _, files in os.walk(mod_dest_path):
            for file in files:
                if file.lower().endswith('.ini'): self.manager._rewrite_ini_file(os.path.join(root, file), slot_id, profile_folder_name, mod_name)
        icon_path = self._download_and_save_mod_icon(mod_data, profile_name, mod_name)
        new_mod_info = {"name": mod_name, "path": mod_dest_path, "slot_id": slot_id, "display_name": mod_data.get('_sName'), "creator": mod_data.get('_aSubmitter', {}).get('_sName'), "url": mod_data.get('_sProfileUrl'), "profile_url": mod_data.get('_sProfileUrl'), "icon": icon_path}
        profile["mods"].append(new_mod_info); self.manager.save_profiles(); self._simulate_f10_press()
        return self.translator.translate("success_mod_installed", name=mod_name)

    def _simulate_f10_press(self):
        if not win32api: print(self.translator.translate("log_pywin32_unavailable")); return
        try:
            VK_F10 = 0x79; win32api.keybd_event(VK_F10, 0, 0, 0); time.sleep(0.05); win32api.keybd_event(VK_F10, 0, win32con.KEYEVENTF_KEYUP, 0)
            print(self.translator.translate("log_f10_simulated_download"))
        except Exception as e: print(self.translator.translate("log_f10_sim_error_download", e=e))

    def _extract_and_copy_mod(self, archive_path, dest_path):
        with tempfile.TemporaryDirectory() as temp_dir:
            patoolib.extract_archive(archive_path, outdir=temp_dir); extracted_contents = os.listdir(temp_dir)
            source_folder = temp_dir
            if len(extracted_contents) == 1 and os.path.isdir(os.path.join(temp_dir, extracted_contents[0])):
                source_folder = os.path.join(temp_dir, extracted_contents[0])
            shutil.copytree(source_folder, dest_path)

    def _download_and_save_mod_icon(self, mod_data, profile_name, mod_name):
        previews = mod_data.get('_aPreviewMedia', []);
        if not isinstance(previews, list) or not previews: return None
        img_info = previews[0]; file_key = '_sFile670' if '_sFile670' in img_info else '_sFile'
        if not (isinstance(img_info, dict) and img_info.get('_sBaseUrl') and img_info.get(file_key)): return None
        img_url = img_info['_sBaseUrl'] + '/' + img_info[file_key]
        try:
            response = requests.get(img_url, timeout=15, headers={'User-Agent': 'MIMM/1.0'}); response.raise_for_status()
            image_content = response.content;
            if not QPixmap().loadFromData(image_content): return None
            final_name = self.manager._sanitize_filename(f"mod_{profile_name}_{mod_name}_{int(time.time() * 1000)}.png")
            final_path = os.path.join(self.manager.icons_cache_path, final_name)
            with open(final_path, 'wb') as f: f.write(image_content)
            return final_path
        except Exception as e: print(f"No se pudo descargar el icono del mod: {e}"); return None

    def start_install_from_data(self, mod_data):
        if not mod_data: return
        self.display_mod_details(mod_data)
        self.install_button.setEnabled(True)
        self.current_mod_data = mod_data

    def show_message(self, title, message, level="info"):
        msg_box = QMessageBox(self); msg_box.setWindowTitle(title); msg_box.setText(message)
        if level == "critical": msg_box.setIcon(QMessageBox.Icon.Critical)
        elif level == "warning": msg_box.setIcon(QMessageBox.Icon.Warning)
        else: msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.exec()