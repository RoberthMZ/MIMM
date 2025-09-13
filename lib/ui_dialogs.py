import os
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QListWidget, QPushButton, QFileDialog, QFrame, QListWidgetItem
)
from PyQt6.QtCore import Qt, QSize, QRectF
from PyQt6.QtGui import QPixmap, QIcon, QPainter, QPainterPath, QBrush, QColor, QPalette, QImage

class ProfileItemWidget(QWidget):
    def __init__(self, icon_path, name, icon_size=80, parent=None):
        super().__init__(parent)
        self.is_selected = False
        self.is_hovered = False
        self.original_icon_size = icon_size
        self.name = name

        original_pixmap = QPixmap(icon_path)
        self.original_scaled_pixmap = original_pixmap.scaled(
            icon_size, icon_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )

        is_recolorable = self._is_strictly_dark_grayscale(original_pixmap.toImage())

        if is_recolorable:
            default_text_color = self.palette().color(QPalette.ColorRole.Text)
            highlight_bg_color = self.palette().color(QPalette.ColorRole.Highlight)
            luminance = 0.2126 * highlight_bg_color.redF() + 0.7152 * highlight_bg_color.greenF() + 0.0722 * highlight_bg_color.blueF()
            highlight_text_color = QColor("#000000") if luminance > 0.5 else QColor("#FFFFFF")

            self.default_pixmap = self._create_colored_version(self.original_scaled_pixmap, default_text_color)
            self.highlight_pixmap = self._create_colored_version(self.original_scaled_pixmap, highlight_text_color)
        else:
            self.default_pixmap = self.original_scaled_pixmap
            self.highlight_pixmap = self.original_scaled_pixmap

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.layout.setSpacing(4)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.icon_label.setFixedSize(icon_size, icon_size)
        self.icon_label.setPixmap(self.default_pixmap)

        words = name.split()
        num_words = len(words)
        formatted_name = name

        if num_words > 1:
            split_index = (num_words + 1) // 2
            first_line = " ".join(words[:split_index])
            second_line = " ".join(words[split_index:])
            formatted_name = f"{first_line}\n{second_line}"

        self.name_label = QLabel(formatted_name)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setWordWrap(True)
        self.name_label.hide()

        self.layout.addWidget(self.icon_label)
        self.layout.addWidget(self.name_label)
        self.setLayout(self.layout)

        self.setMouseTracking(True)

    def _is_strictly_dark_grayscale(self, image: QImage):
        if image.isNull():
            return False

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
                if r > DARKNESS_THRESHOLD or g > DARKNESS_THRESHOLD or b > DARKNESS_THRESHOLD:
                    return False
                min_c, max_c = min(r, g, b), max(r, g, b)
                if (max_c - min_c) > COLOR_TOLERANCE:
                    return False
        if not has_visible_pixels:
            return False
        return True

    def _create_colored_version(self, source_pixmap: QPixmap, target_color: QColor):
        if source_pixmap.isNull(): return QPixmap()
        recolored_pixmap = QPixmap(source_pixmap.size())
        recolored_pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(recolored_pixmap)
        painter.drawPixmap(0, 0, source_pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(recolored_pixmap.rect(), target_color)
        painter.end()
        return recolored_pixmap

    def _adjust_for_long_name(self, reduce):
        current_pixmap_size = self.icon_label.pixmap().width()
        target_size = self.original_icon_size

        if reduce:
            font_metrics = self.name_label.fontMetrics()
            text_height = font_metrics.boundingRect(self.name_label.rect(), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.name_label.text()).height()
            single_line_height = font_metrics.height()

            if text_height > single_line_height * 2.2:
                target_size = int(self.original_icon_size * 0.75)

        if current_pixmap_size == target_size:
            return

        scaled_pixmap = self.original_scaled_pixmap.scaled(
            target_size, target_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )

        is_recolorable = self._is_strictly_dark_grayscale(self.original_scaled_pixmap.toImage())
        if is_recolorable:
            default_text_color = self.palette().color(QPalette.ColorRole.Text)
            highlight_bg_color = self.palette().color(QPalette.ColorRole.Highlight)
            luminance = 0.2126 * highlight_bg_color.redF() + 0.7152 * highlight_bg_color.greenF() + 0.0722 * highlight_bg_color.blueF()
            highlight_text_color = QColor("#000000") if luminance > 0.5 else QColor("#FFFFFF")
            self.default_pixmap = self._create_colored_version(scaled_pixmap, default_text_color)
            self.highlight_pixmap = self._create_colored_version(scaled_pixmap, highlight_text_color)
        else:
            self.default_pixmap = scaled_pixmap
            self.highlight_pixmap = scaled_pixmap

        if self.is_selected:
            self.icon_label.setPixmap(self.highlight_pixmap)
        else:
            self.icon_label.setPixmap(self.default_pixmap)

    def set_selected(self, selected):
        if self.is_selected == selected: return
        self.is_selected = selected

        if self.is_selected:
            self.name_label.show()
            self._adjust_for_long_name(reduce=True)
            highlight_color = self.palette().color(QPalette.ColorRole.Highlight)
            luminance = 0.2126 * highlight_color.redF() + 0.7152 * highlight_color.greenF() + 0.0722 * highlight_color.blueF()
            text_color_name = "#000000" if luminance > 0.5 else "#FFFFFF"
            self.name_label.setStyleSheet(f"color: {text_color_name};")
            self.icon_label.setPixmap(self.highlight_pixmap)
        else:
            self._adjust_for_long_name(reduce=False)
            text_color = self.palette().color(QPalette.ColorRole.Text)
            self.name_label.setStyleSheet(f"color: {text_color.name()};")
            if not self.is_hovered:
                self.name_label.hide()
            self.icon_label.setPixmap(self.default_pixmap)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        brush_to_use = None
        if self.is_selected:
            brush_to_use = self.palette().brush(QPalette.ColorRole.Highlight)
        elif self.is_hovered:
            highlight_color = self.palette().color(QPalette.ColorRole.Highlight)
            highlight_color.setAlpha(40)
            brush_to_use = QBrush(highlight_color)
        if brush_to_use:
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()), 4, 4)
            painter.fillPath(path, brush_to_use)

    def enterEvent(self, event):
        self.is_hovered = True
        self.name_label.show()
        self._adjust_for_long_name(reduce=True)
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.is_hovered = False
        if not self.is_selected:
            self.name_label.hide()
            self._adjust_for_long_name(reduce=False)
        self.update()
        super().leaveEvent(event)

class IconBrowserDialog(QDialog):
    def __init__(self, icon_folder, parent=None):
        super().__init__(parent)
        self.translator = parent.translator
        self.setMinimumSize(665, 500)
        self.selected_path = None

        highlight_color = self.palette().color(QPalette.ColorRole.Highlight)
        luminance = 0.2126 * highlight_color.redF() + 0.7152 * highlight_color.greenF() + 0.0722 * highlight_color.blueF()
        text_color_on_highlight = "#000000" if luminance > 0.5 else "#FFFFFF"

        search_bar_style = f"QLineEdit {{ border: 1px solid #cccccc; border-radius: 15px; padding: 5px 10px; height: 30px; }} QLineEdit:focus {{ border: 1px solid {highlight_color.name()}; }}"
        list_widget_style = f"QListWidget {{ outline: none; border: 1px solid #d0d0d0; border-radius: 4px; }} QListWidget::item {{ padding: 10px; border-radius: 4px; }} QListWidget::item:hover {{ border: 2px solid {highlight_color.name()}; background-color: rgba({highlight_color.red()},{highlight_color.green()},{highlight_color.blue()},20); }} QListWidget::item:selected {{ background-color: {highlight_color.name()}; color: {text_color_on_highlight}; border: 2px solid {highlight_color.name()}; }}"
        secondary_button_style = f"QPushButton {{ border: 1px solid #cccccc; border-radius: 4px; padding: 6px 12px; }} QPushButton:hover {{ border-color: {highlight_color.name()}; }} QPushButton:pressed {{ background-color: {highlight_color.darker(120).name()}; }}"
        primary_button_style = f"QPushButton {{ background-color: {highlight_color.name()}; color: {text_color_on_highlight}; border: none; border-radius: 4px; padding: 8px 16px; font-weight: bold; }} QPushButton:hover {{ background-color: {highlight_color.lighter(115).name()}; }} QPushButton:pressed {{ background-color: {highlight_color.darker(115).name()}; }} QPushButton:disabled {{ background-color: #d0d0d0; color: #808080; }}"

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(15, 15, 15, 15)
        self.layout.setSpacing(10)
        
        self.search_bar = QLineEdit()
        self.search_bar.setStyleSheet(search_bar_style)
        self.search_bar.textChanged.connect(self.filter_icons)
        self.layout.addWidget(self.search_bar)
        
        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(80, 80))
        self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_widget.setSpacing(15)
        self.list_widget.setWordWrap(True)
        self.list_widget.setStyleSheet(list_widget_style)
        self.list_widget.itemDoubleClicked.connect(self.accept)
        self.list_widget.currentItemChanged.connect(self.on_selection_changed)
        
        self.populate_icons(icon_folder)
        self.layout.addWidget(self.list_widget)
        
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        self.cancel_button = QPushButton()
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.setStyleSheet(secondary_button_style)
        self.cancel_button.clicked.connect(self.reject)
        buttons_layout.addWidget(self.cancel_button)
        
        self.ok_button = QPushButton()
        self.ok_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ok_button.setStyleSheet(primary_button_style)
        self.ok_button.clicked.connect(self.accept)
        self.ok_button.setEnabled(False)
        buttons_layout.addWidget(self.ok_button)
        self.layout.addLayout(buttons_layout)
        self.retranslate_ui()

    def _is_dark_and_monochromatic(self, image: QImage, threshold=35, saturation_threshold=25):
        if image.isNull(): return False
        scaled_image = image.scaled(16, 16, Qt.AspectRatioMode.IgnoreAspectRatio)
        dark_pixels = sum(1 for y in range(scaled_image.height()) for x in range(scaled_image.width())
                          if (c := QColor(scaled_image.pixel(x, y))).saturation() < saturation_threshold and
                          (c.red() + c.green() + c.blue() < threshold * 3))
        return (dark_pixels / (scaled_image.width() * scaled_image.height())) > 0.7

    def _create_colored_pixmap(self, source_pixmap: QPixmap, target_color: QColor):
        if source_pixmap.isNull(): return QPixmap()
        recolored_pixmap = QPixmap(source_pixmap.size())
        recolored_pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(recolored_pixmap)
        painter.drawPixmap(0, 0, source_pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(recolored_pixmap.rect(), target_color)
        painter.end()
        return recolored_pixmap

    def retranslate_ui(self):
        self.setWindowTitle(self.translator.translate("icon_browser_title"))
        self.search_bar.setPlaceholderText(self.translator.translate("icon_browser_search_placeholder"))
        self.cancel_button.setText(self.translator.translate("button_cancel"))
        self.ok_button.setText(self.translator.translate("button_ok"))

    def populate_icons(self, icon_folder):
        image_extensions = ['.png', '.jpg', '.jpeg', '.webp']
        if not os.path.isdir(icon_folder): return

        default_text_color = self.palette().color(QPalette.ColorRole.Text)
        highlight_bg = self.palette().color(QPalette.ColorRole.Highlight)
        luminance = 0.2126 * highlight_bg.redF() + 0.7152 * highlight_bg.greenF() + 0.0722 * highlight_bg.blueF()
        highlight_text_color = QColor("#000000") if luminance > 0.5 else QColor("#FFFFFF")

        for filename in sorted(os.listdir(icon_folder)):
            if any(filename.lower().endswith(ext) for ext in image_extensions):
                full_path = os.path.join(icon_folder, filename)
                name = os.path.splitext(filename)[0]
                
                original_pixmap = QPixmap(full_path)
                final_icon = QIcon()

                if self._is_dark_and_monochromatic(original_pixmap.toImage()):
                    normal_pixmap = self._create_colored_pixmap(original_pixmap, default_text_color)
                    selected_pixmap = self._create_colored_pixmap(original_pixmap, highlight_text_color)
                    final_icon.addPixmap(normal_pixmap, QIcon.Mode.Normal)
                    final_icon.addPixmap(selected_pixmap, QIcon.Mode.Selected)
                else:
                    final_icon.addPixmap(original_pixmap)
                item = QListWidgetItem(final_icon, name)
                item.setData(Qt.ItemDataRole.UserRole, full_path)
                item.setToolTip(name)
                self.list_widget.addItem(item)
    
    def filter_icons(self):
        filter_text = self.search_bar.text().lower()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setHidden(filter_text not in item.text().lower())
            
    def on_selection_changed(self, current_item, previous_item):
        self.ok_button.setEnabled(current_item is not None)

    def accept(self):
        if self.list_widget.currentItem():
            self.selected_path = self.list_widget.currentItem().data(Qt.ItemDataRole.UserRole)
        super().accept()

    def get_selected_path(self):
        return self.selected_path

class ProfileDialog(QDialog):
    def __init__(self, profile_name="", is_name_editable=True, current_icon_path=None, parent=None):
        super().__init__(parent)
        self.app = parent
        self.translator = self.app.translator
        self.setMinimumWidth(450)
        self.icon_source_path = None

        highlight_color = self.palette().color(QPalette.ColorRole.Highlight)
        luminance = 0.2126 * highlight_color.redF() + 0.7152 * highlight_color.greenF() + 0.0722 * highlight_color.blueF()
        text_color_on_highlight = "#000000" if luminance > 0.5 else "#FFFFFF"

        line_edit_style = f"QLineEdit {{ border: 1px solid #cccccc; border-radius: 4px; padding: 6px; }} QLineEdit:focus {{ border: 1px solid {highlight_color.name()}; }} QLineEdit:read-only {{ border: 1px solid #c0c0c0; }}"
        secondary_button_style = f"QPushButton {{ border: 1px solid #cccccc; border-radius: 4px; padding: 6px 12px; }} QPushButton:hover {{ border-color: {highlight_color.name()}; }} QPushButton:pressed {{ background-color: {highlight_color.darker(120).name()}; }}"
        primary_button_style = f"QPushButton {{ background-color: {highlight_color.name()}; color: {text_color_on_highlight}; border: none; border-radius: 4px; padding: 8px 16px; font-weight: bold; }} QPushButton:hover {{ background-color: {highlight_color.lighter(115).name()}; }} QPushButton:pressed {{ background-color: {highlight_color.darker(115).name()}; }}"
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(15, 15, 15, 15)
        self.layout.setSpacing(10)

        self.name_label = QLabel()
        self.name_label.setStyleSheet("font-weight: bold;")
        self.layout.addWidget(self.name_label)
        
        self.name_edit = QLineEdit(profile_name)
        self.name_edit.setReadOnly(not is_name_editable)
        self.name_edit.setStyleSheet(line_edit_style)
        self.layout.addWidget(self.name_edit)
        self.layout.addSpacing(15)

        self.icon_title_label = QLabel()
        self.icon_title_label.setStyleSheet("font-weight: bold;")
        self.layout.addWidget(self.icon_title_label)
        icon_layout = QHBoxLayout()
        icon_layout.setSpacing(15)
        
        self.icon_preview = QLabel()
        self.icon_preview.setFixedSize(110, 110)
        self.icon_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        button_vlayout = QVBoxLayout()
        button_vlayout.setSpacing(8)
        
        self.select_icon_button = QPushButton()
        self.select_icon_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.select_icon_button.setStyleSheet(secondary_button_style)
        self.select_icon_button.clicked.connect(self.select_icon_from_pc)
        
        self.browse_icons_button = QPushButton()
        self.browse_icons_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.browse_icons_button.setStyleSheet(secondary_button_style)
        self.browse_icons_button.clicked.connect(self.browse_predefined_icons)
        
        button_vlayout.addWidget(self.select_icon_button)
        button_vlayout.addWidget(self.browse_icons_button)
        button_vlayout.addStretch()
        
        icon_layout.addWidget(self.icon_preview)
        icon_layout.addLayout(button_vlayout)
        self.layout.addLayout(icon_layout)
        self.layout.addStretch()

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        self.layout.addWidget(separator)
        
        self.buttons_layout = QHBoxLayout()
        self.buttons_layout.addStretch()
        
        self.cancel_button = QPushButton()
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.setStyleSheet(secondary_button_style)
        self.cancel_button.clicked.connect(self.reject)
        
        self.ok_button = QPushButton()
        self.ok_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ok_button.setStyleSheet(primary_button_style)
        self.ok_button.clicked.connect(self.accept)

        self.buttons_layout.addWidget(self.cancel_button)
        self.buttons_layout.addWidget(self.ok_button)
        self.layout.addLayout(self.buttons_layout)
        
        self.set_icon(current_icon_path)
        self.retranslate_ui()

    def _is_dark_and_monochromatic(self, image: QImage, threshold=35, saturation_threshold=25):
        if image.isNull(): return False
        scaled_image = image.scaled(16, 16, Qt.AspectRatioMode.IgnoreAspectRatio)
        dark_pixels = sum(1 for y in range(scaled_image.height()) for x in range(scaled_image.width())
                          if (c := QColor(scaled_image.pixel(x, y))).saturation() < saturation_threshold and
                          (c.red() + c.green() + c.blue() < threshold * 3))
        return (dark_pixels / (scaled_image.width() * scaled_image.height())) > 0.7

    def _process_icon(self, pixmap: QPixmap):
        if pixmap.isNull(): return QPixmap()
        if self._is_dark_and_monochromatic(pixmap.toImage()):
            target_color = self.palette().color(QPalette.ColorRole.Text)
            recolored_pixmap = QPixmap(pixmap.size())
            recolored_pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(recolored_pixmap)
            painter.drawPixmap(0, 0, pixmap)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            painter.fillRect(recolored_pixmap.rect(), target_color)
            painter.end()
            return recolored_pixmap
        return pixmap 

    def retranslate_ui(self):
        self.setWindowTitle(self.translator.translate("profile_dialog_title"))
        self.name_label.setText(self.translator.translate("profile_dialog_name_label"))
        self.icon_title_label.setText(self.translator.translate("profile_dialog_icon_label"))
        self.select_icon_button.setText(self.translator.translate("profile_dialog_select_image_button"))
        self.browse_icons_button.setText(self.translator.translate("profile_dialog_predefined_icons_button"))
        self.cancel_button.setText(self.translator.translate("button_cancel"))
        self.ok_button.setText(self.translator.translate("button_ok"))
        self.set_icon(self.icon_source_path)

    def set_icon(self, path):
        icon_to_load = None
        if path and os.path.exists(path):
            self.icon_source_path = path
            icon_to_load = path
        elif self.app.default_icon_path and os.path.exists(self.app.default_icon_path):
            self.icon_source_path = None
            icon_to_load = self.app.default_icon_path
        
        if icon_to_load:
            original_pixmap = QPixmap(icon_to_load)
            processed_pixmap = self._process_icon(original_pixmap)
            self.icon_preview.setPixmap(processed_pixmap.scaled(self.icon_preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self.icon_preview.setStyleSheet("border: 1px solid #c0c0c0; border-radius: 8px;")
        else:
            self.icon_source_path = None
            self.icon_preview.setText(self.translator.translate("no_icon_text"))
            self.icon_preview.setPixmap(QPixmap())
            self.icon_preview.setStyleSheet("border: 2px dashed #c0c0c0; border-radius: 8px; color: #808080; background-color: rgba(0,0,0,0.02);")

    def select_icon_from_pc(self):
        title = self.translator.translate("select_image_dialog_title")
        path, _ = QFileDialog.getOpenFileName(self, title, "", "Imágenes (*.png *.jpg *.jpeg *.webp)")
        if path: self.set_icon(path)

    def browse_predefined_icons(self):
        others_folder = os.path.join(self.app.user_icons_path, "Others")
        os.makedirs(others_folder, exist_ok=True)
        dialog = IconBrowserDialog(others_folder, self)
        if dialog.exec():
            path = dialog.get_selected_path()
            if path: self.set_icon(path)

    def get_details(self): 
        return { "name": self.name_edit.text().strip(), "icon_source_path": self.icon_source_path }

class ApiSelectionDialog(QDialog):
    def __init__(self, items, default_icon_path, parent=None):
        super().__init__(parent)
        self.translator = parent.translator 
        self.setMinimumSize(625, 550)
        self.items = items
        self.default_icon_path = default_icon_path

        highlight_color = self.palette().color(QPalette.ColorRole.Highlight)
        luminance = 0.2126 * highlight_color.redF() + 0.7152 * highlight_color.greenF() + 0.0722 * highlight_color.blueF()
        text_color_on_highlight = "#000000" if luminance > 0.5 else "#FFFFFF"

        search_bar_style = f"QLineEdit {{ border: 1px solid #cccccc; border-radius: 15px; padding: 5px 10px; height: 30px; }} QLineEdit:focus {{ border: 1px solid {highlight_color.name()}; }}"
        list_widget_style = f"QListWidget {{ border: 1px solid #d0d0d0; border-radius: 4px; outline: none; }} QListWidget::item {{ padding: 10px; border-radius: 4px; }} QListWidget::item:hover {{ border: 3px solid {highlight_color.name()}; background-color: none; }} QListWidget::item:selected {{ background-color: {highlight_color.name()}; color: {text_color_on_highlight}; }}"
        secondary_button_style = f"QPushButton {{ border: 1px solid #cccccc; border-radius: 4px; padding: 6px 12px; }} QPushButton:hover {{ border-color: {highlight_color.name()}; }} QPushButton:pressed {{ background-color: {highlight_color.darker(120).name()}; }}"
        primary_button_style = f"QPushButton {{ background-color: {highlight_color.name()}; color: {text_color_on_highlight}; border: none; border-radius: 4px; padding: 8px 8px; font-weight: bold; }} QPushButton:hover {{ background-color: {highlight_color.lighter(115).name()}; }} QPushButton:pressed {{ background-color: {highlight_color.darker(115).name()}; }} QPushButton:disabled {{ background-color: #d0d0d0; color: #808080; }}"

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(15, 15, 15, 15)
        self.layout.setSpacing(10)

        self.search_bar = QLineEdit()
        self.search_bar.setStyleSheet(search_bar_style)
        self.search_bar.textChanged.connect(self.filter_list)
        self.layout.addWidget(self.search_bar)

        self.list_widget = QListWidget()
        self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_widget.setIconSize(QSize(80, 80))
        self.list_widget.setSpacing(20)
        self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_widget.setUniformItemSizes(True)
        self.list_widget.setWordWrap(True)
        self.list_widget.setStyleSheet(list_widget_style)
        self.list_widget.itemDoubleClicked.connect(self.accept)
        self.list_widget.currentItemChanged.connect(self.on_selection_changed)
        
        self.populate_list()
        self.layout.addWidget(self.list_widget)

        self.buttons_layout = QHBoxLayout()
        self.buttons_layout.addStretch()

        self.cancel_button = QPushButton()
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.setStyleSheet(secondary_button_style)
        self.cancel_button.clicked.connect(self.reject)
        self.buttons_layout.addWidget(self.cancel_button)

        self.ok_button = QPushButton()
        self.ok_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ok_button.setStyleSheet(primary_button_style)
        self.ok_button.clicked.connect(self.accept)
        self.ok_button.setEnabled(False)
        self.buttons_layout.addWidget(self.ok_button)
        self.layout.addLayout(self.buttons_layout)
        
        self.retranslate_ui()

    def retranslate_ui(self):
        self.setWindowTitle(self.translator.translate("api_selection_dialog_title"))
        self.search_bar.setPlaceholderText(self.translator.translate("search_by_name_placeholder"))
        self.cancel_button.setText(self.translator.translate("button_cancel"))
        self.ok_button.setText(self.translator.translate("button_ok"))
        self.populate_list() 

    def populate_list(self):
        self.list_widget.clear()
        sorted_items = sorted(self.items, key=lambda x: x.get('name', ''))
        unknown_name_str = self.translator.translate("unknown_name")
        for item_data in sorted_items:
            name = item_data.get('name', unknown_name_str)
            icon_path = item_data.get('icon_path') or self.default_icon_path
            list_item = QListWidgetItem(name)
            if icon_path and os.path.exists(icon_path):
                list_item.setIcon(QIcon(icon_path))
            list_item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            list_item.setData(Qt.ItemDataRole.UserRole, item_data)
            list_item.setSizeHint(QSize(120, 140))
            self.list_widget.addItem(list_item)
            
    def on_selection_changed(self, current_item, previous_item):
        self.ok_button.setEnabled(current_item is not None)

    def filter_list(self):
        filter_text = self.search_bar.text().lower()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setHidden(filter_text not in item.text().lower())

    def get_selected_item(self):
        selected_items = self.list_widget.selectedItems()
        if selected_items:
            return selected_items[0].data(Qt.ItemDataRole.UserRole)
        return None

class ModInfoDialog(QDialog):
    def __init__(self, mod_info=None, parent=None):
        super().__init__(parent)
        self.app = parent
        self.translator = self.app.translator
        self.setMinimumWidth(450)
        self.icon_source_path = None
        self.mod_info = mod_info or {}

        highlight_color = self.palette().color(QPalette.ColorRole.Highlight)
        luminance = 0.2126 * highlight_color.redF() + 0.7152 * highlight_color.greenF() + 0.0722 * highlight_color.blueF()
        text_color_on_highlight = "#000000" if luminance > 0.5 else "#FFFFFF"

        line_edit_style = f"QLineEdit {{ border: 1px solid #cccccc; border-radius: 4px; padding: 6px; }} QLineEdit:focus {{ border: 1px solid {highlight_color.name()}; }}"
        secondary_button_style = f"QPushButton {{ border: 1px solid #cccccc; border-radius: 4px; padding: 6px 12px; }} QPushButton:hover {{ border-color: {highlight_color.name()}; }} QPushButton:pressed {{ background-color: {highlight_color.darker(120).name()}; }}"
        primary_button_style = f"QPushButton {{ background-color: {highlight_color.name()}; color: {text_color_on_highlight}; border: none; border-radius: 4px; padding: 8px 16px; font-weight: bold; }} QPushButton:hover {{ background-color: {highlight_color.lighter(115).name()}; }} QPushButton:pressed {{ background-color: {highlight_color.darker(115).name()}; }}"

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(15, 15, 15, 15)
        self.layout.setSpacing(10)

        self.display_name_label = QLabel()
        self.creator_label = QLabel()
        self.url_label = QLabel()
        self.icon_label = QLabel()
        
        self.name_edit = QLineEdit(self.mod_info.get("display_name", ""))
        self.creator_edit = QLineEdit(self.mod_info.get("creator", ""))
        self.url_edit = QLineEdit(self.mod_info.get("url", ""))

        fields = {
            self.display_name_label: self.name_edit,
            self.creator_label: self.creator_edit,
            self.url_label: self.url_edit,
        }

        for label, widget in fields.items():
            label.setStyleSheet("font-weight: bold;")
            self.layout.addWidget(label)
            widget.setStyleSheet(line_edit_style)
            self.layout.addWidget(widget)
        
        self.layout.addSpacing(15)

        self.icon_label.setStyleSheet("font-weight: bold;")
        self.layout.addWidget(self.icon_label)
        
        icon_section_layout = QVBoxLayout()
        icon_section_layout.setSpacing(8)

        self.icon_preview = QLabel()
        self.icon_preview.setFixedHeight(180) 
        self.icon_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.select_icon_button = QPushButton()
        self.select_icon_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.select_icon_button.setStyleSheet(secondary_button_style)
        self.select_icon_button.setMaximumWidth(200)
        self.select_icon_button.clicked.connect(self.select_icon)

        icon_section_layout.addWidget(self.icon_preview)
        icon_section_layout.addWidget(self.select_icon_button, alignment=Qt.AlignmentFlag.AlignCenter)
        
        self.layout.addLayout(icon_section_layout)
        self.layout.addStretch()
        
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        self.layout.addWidget(separator)

        self.buttons_layout = QHBoxLayout()
        self.buttons_layout.addStretch()
        self.cancel_button = QPushButton()
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.setStyleSheet(secondary_button_style)
        self.cancel_button.clicked.connect(self.reject)
        self.ok_button = QPushButton()
        self.ok_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ok_button.setStyleSheet(primary_button_style)
        self.ok_button.clicked.connect(self.accept)
        self.buttons_layout.addWidget(self.cancel_button)
        self.buttons_layout.addWidget(self.ok_button)
        self.layout.addLayout(self.buttons_layout)

        self.set_icon(self.mod_info.get("icon"))
        self.retranslate_ui()

    def retranslate_ui(self):
        self.setWindowTitle(self.translator.translate("mod_info_dialog_title"))
        self.display_name_label.setText(self.translator.translate("mod_info_display_name_label"))
        self.creator_label.setText(self.translator.translate("mod_info_creator_label"))
        self.url_label.setText(self.translator.translate("mod_info_url_label"))
        self.icon_label.setText(self.translator.translate("mod_info_icon_label"))
        self.select_icon_button.setText(self.translator.translate("profile_dialog_select_image_button"))
        self.cancel_button.setText(self.translator.translate("button_cancel"))
        self.ok_button.setText(self.translator.translate("button_ok"))
        self.set_icon(self.icon_source_path or self.mod_info.get("icon"))

    def set_icon(self, path):
        if path and os.path.exists(path):
            self.icon_source_path = path
            pixmap = QPixmap(path)
            self.icon_preview.setPixmap(pixmap.scaled(self.icon_preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self.icon_preview.setStyleSheet("border: 1px solid #c0c0c0; border-radius: 8px;")
        else:
            self.icon_source_path = None
            self.icon_preview.setText(self.translator.translate("no_icon_text"))
            self.icon_preview.setPixmap(QPixmap())
            self.icon_preview.setStyleSheet("border: 2px dashed #c0c0c0; border-radius: 8px; color: #808080; background-color: rgba(0,0,0,0.02);")

    def select_icon(self):
        title = self.translator.translate("select_image_dialog_title")
        path, _ = QFileDialog.getOpenFileName(self, title, "", "Imágenes (*.png *.jpg *.jpeg *.webp)")
        if path:
            self.set_icon(path)

    def get_details(self):
        return {
            "display_name": self.name_edit.text().strip(),
            "creator": self.creator_edit.text().strip(),
            "url": self.url_edit.text().strip(),
            "icon_source_path": self.icon_source_path
        }