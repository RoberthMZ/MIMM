import requests
import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QComboBox, QPushButton, QMessageBox, QSpacerItem, QSizePolicy, QApplication)
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QPalette, QIcon, QPixmap, QPainter, QColor, QImage

class OneClickInstallDialog(QDialog):
    def __init__(self, mod_id, file_id, main_window):
        super().__init__(main_window)
        self.mod_id = mod_id
        self.file_id = file_id
        self.main_window = main_window
        self.translator = main_window.translator
        
        self.mod_api_data = None
        self.file_api_data = None
        self.selected_game_name = None
        self.selected_category_key = None
        self.api_category_cache = {}

        self.setWindowTitle(self.translator.translate("one_click_title"))
        self.setMinimumWidth(500)

        highlight_color = self.main_window.palette().color(QPalette.ColorRole.Highlight)
        luminance = 0.2126 * highlight_color.redF() + 0.7152 * highlight_color.greenF() + 0.0722 * highlight_color.blueF()
        text_color_on_highlight = "#000000" if luminance > 0.5 else "#FFFFFF"
        button_stylesheet = f"""
            QPushButton {{ background-color: {highlight_color.name()}; color: {text_color_on_highlight}; border: none; border-radius: 8px; padding: 8px 16px; font-weight: bold; outline: none; }}
            QPushButton:hover {{ background-color: {highlight_color.lighter(115).name()}; }}
            QPushButton:pressed {{ background-color: {highlight_color.darker(115).name()}; }}
            QPushButton:disabled {{ background-color: #d3d3d3; color: #a0a0a0; }}
        """
        cancel_button_stylesheet = "QPushButton { border: 1px solid #d0d0d0; border-radius: 8px; padding: 7px 16px; font-weight: bold; } QPushButton:hover { background-color: #e0e0e0; color: #a0a0a0;}"
        combo_stylesheet = f"""
            QComboBox {{ border: 1px solid #cccccc; border-radius: 8px; padding: 6px; padding-left: 10px; }}
            QComboBox:focus {{ border: 2px solid {highlight_color.name()}; }}
            QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: top right; width: 25px; border-left-width: 1px; border-left-color: #cccccc; border-left-style: solid; border-top-right-radius: 8px; border-bottom-right-radius: 8px; }}
            QComboBox::down-arrow {{ image: url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxwb2x5bGluZSBwb2ludHM9IjYgOSAxMiAxNSAxOCA5Ij48L3BvbHlsaW5lPjwvc3ZnPg==); width: 16px; height: 16px; }}
        """
        layout = QVBoxLayout(self)
        self.info_label = QLabel(self.translator.translate("one_click_fetching_info"))
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("font-size: 11pt; padding-bottom: 10px;")
        layout.addWidget(self.info_label)

        self.game_combo = self._create_combo("one_click_game")
        self.category_combo = self._create_combo("one_click_category")
        self.profile_combo = self._create_combo("one_click_profile")
        
        for combo in [self.game_combo, self.category_combo, self.profile_combo]:
            combo.setStyleSheet(combo_stylesheet); combo.setIconSize(QSize(28, 28)); combo.setFixedHeight(42)

        layout.addWidget(self.game_combo); layout.addWidget(self.category_combo); layout.addWidget(self.profile_combo)
        layout.addSpacerItem(QSpacerItem(20, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        button_layout = QHBoxLayout()
        self.install_button = QPushButton(self.translator.translate("one_click_install_btn"))
        self.install_button.setEnabled(False)
        self.install_button.clicked.connect(self.on_install_clicked)
        self.install_button.setStyleSheet(button_stylesheet)
        
        cancel_button = QPushButton(self.translator.translate("one_click_cancel_btn")); cancel_button.clicked.connect(self.reject)
        cancel_button.setStyleSheet(cancel_button_stylesheet)
        
        button_layout.addStretch(); button_layout.addWidget(cancel_button); button_layout.addWidget(self.install_button)
        layout.addLayout(button_layout)
        
        self.game_combo.currentIndexChanged.connect(self._on_game_changed)
        self.category_combo.currentIndexChanged.connect(self._on_category_changed)
        
        QTimer.singleShot(100, self.fetch_mod_data)

    def _is_strictly_dark_grayscale(self, image: QImage):
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

    def _create_combo(self, t_key_placeholder):
        combo = QComboBox()
        combo.setPlaceholderText(self.translator.translate(t_key_placeholder))
        combo.setEnabled(False)
        return combo

    def fetch_mod_data(self):
        url = f"https://gamebanana.com/apiv11/Mod/{self.mod_id}?_csvProperties=@gbprofile"
        try:
            response = requests.get(url, timeout=15, headers={'User-Agent': 'MIMM/1.0'})
            response.raise_for_status()
            self.mod_api_data = response.json()
            
            files_list = self.mod_api_data.get('_aFiles', [])
            self.file_api_data = next((f for f in files_list if str(f.get('_idRow')) == self.file_id), None)
            
            if not self.file_api_data:
                self.show_error("one_click_err_file_not_found")
                return
                
            self._populate_and_verify_ui()

        except requests.RequestException as e:
            self.show_error("one_click_err_api_fetch", e=e)
        except Exception as e:
            self.show_error("one_click_err_unexpected", e=e)
            
    def _find_mod_category(self, game_name, profile_name_to_find):
        game_categories = self.main_window.game_data[game_name]["categories"]
        for key, data in game_categories.items():
            if data.get("type") == "direct_management": continue
            category_api_id = data.get("id") or data.get("api_id")
            if not category_api_id: continue

            if category_api_id in self.api_category_cache:
                profiles_in_category = self.api_category_cache[category_api_id]
            else:
                api_profiles = self.main_window.fetch_gamebanana_data(category_api_id)
                if not api_profiles:
                    self.api_category_cache[category_api_id] = set()
                    continue
                profiles_in_category = {p['name'] for p in api_profiles}
                self.api_category_cache[category_api_id] = profiles_in_category
            
            if profile_name_to_find in profiles_in_category:
                return key
        return None

    def _populate_and_verify_ui(self):
        if not self.mod_api_data: return

        mod_name = self.mod_api_data.get('_sName', 'N/A')
        api_game_name = self.mod_api_data.get('_aGame', {}).get('_sName')
        api_profile_name = self.mod_api_data.get('_aCategory', {}).get('_sName')

        self.info_label.setText(self.translator.translate("one_click_installing_mod", mod_name=mod_name))

        self.game_combo.blockSignals(True)
        self.game_combo.clear()
        game_icons_path = os.path.join(self.main_window.user_icons_path, "Games")
        for name, data in self.main_window.game_data.items():
            icon_path = next((os.path.join(game_icons_path, f"{data['short_name']}{ext}") for ext in ['.png', '.jpg', '.jpeg'] if os.path.exists(os.path.join(game_icons_path, f"{data['short_name']}{ext}"))), None)
            icon = self._create_processed_icon(icon_path)
            self.game_combo.addItem(icon, name)

        game_index = self.game_combo.findText(api_game_name, Qt.MatchFlag.MatchFixedString)
        if game_index < 0:
            self.show_error("one_click_err_game_not_supported", game=api_game_name)
            return
            
        self.game_combo.setCurrentIndex(game_index)
        self.game_combo.setEnabled(False)
        self.game_combo.blockSignals(False)
        self._on_game_changed(game_index)

        self.info_label.setText(self.translator.translate("one_click_verifying_category"))
        QApplication.processEvents()

        category_key_to_select = self._find_mod_category(api_game_name, api_profile_name)
        is_managed_type = True

        if not category_key_to_select:
            game_categories = self.main_window.game_data[api_game_name]["categories"]
            category_key_to_select = next((k for k,v in game_categories.items() if v.get("type") == "direct_management"), None)
            is_managed_type = False
        
        if not category_key_to_select:
            self.show_error("one_click_err_category_not_found")
            return

        self.info_label.setText(self.translator.translate("one_click_installing_mod", mod_name=mod_name))
        
        self.category_combo.blockSignals(True)
        category_index = self.category_combo.findData(category_key_to_select)
        if category_index >= 0:
            self.category_combo.setCurrentIndex(category_index)
            self.category_combo.setEnabled(False)
        self.category_combo.blockSignals(False)
        self._on_category_changed(category_index)
        
        category_data = self.main_window.game_data[api_game_name]["categories"].get(category_key_to_select, {})
        is_weapon_category = self.translator.translate(category_data.get('t_key', '')) == self.translator.translate('category_weapons')

        if is_weapon_category:
            if self.profile_combo.count() > 0:
                self.profile_combo.setEnabled(True)
                self.profile_combo.setPlaceholderText(self.translator.translate("one_click_select_weapon_profile"))
                self.install_button.setEnabled(False)
                self.profile_combo.currentIndexChanged.connect(lambda idx: self.install_button.setEnabled(idx >= 0))
            else:
                self.show_error("one_click_err_no_weapon_profiles")
                
        elif is_managed_type:
            profiles = self.main_window.profiles.get(api_game_name, {}).get(category_key_to_select, {})
            if api_profile_name in profiles:
                profile_index = self.profile_combo.findText(api_profile_name)
                self.profile_combo.setCurrentIndex(profile_index)
                self.install_button.setText(self.translator.translate("one_click_install_btn"))
            else:
                self.profile_combo.setPlaceholderText(self.translator.translate("one_click_will_create_profile", name=api_profile_name))
                self.install_button.setText(self.translator.translate("one_click_create_install_btn"))
            
            self.profile_combo.setEnabled(False)
            self.install_button.setEnabled(True)
            
        else:
            if self.profile_combo.count() > 0:
                self.profile_combo.setEnabled(True)
                self.install_button.setEnabled(self.profile_combo.currentIndex() >= 0)
                self.profile_combo.currentIndexChanged.connect(lambda idx: self.install_button.setEnabled(idx >= 0))
                self.profile_combo.setPlaceholderText(self.translator.translate("one_click_select_other_profile"))
            else:
                self.show_error("one_click_no_other_profiles")

    def _on_game_changed(self, index):
        self.selected_game_name = self.game_combo.itemText(index)
        self.category_combo.clear()
        if not self.selected_game_name: return
        
        categories = self.main_window.game_data[self.selected_game_name]["categories"]
        for key, data in categories.items():
            self.category_combo.addItem(self.translator.translate(data['t_key']), key)
        self.category_combo.setEnabled(True)

    def _on_category_changed(self, index):
        self.selected_category_key = self.category_combo.itemData(index)
        self.profile_combo.clear()
        if not self.selected_game_name or not self.selected_category_key: return

        profiles = self.main_window.profiles.get(self.selected_game_name, {}).get(self.selected_category_key, {})
        for name, profile_data in sorted(profiles.items()):
            icon_path = profile_data.get('icon') or self.main_window.default_icon_path
            icon = self._create_processed_icon(icon_path)
            self.profile_combo.addItem(icon, name)

    def on_install_clicked(self):
        self.install_button.setEnabled(False)
        
        profile_name = self.profile_combo.currentText()
        if not profile_name:
            profile_name = self.mod_api_data.get('_aCategory', {}).get('_sName')

        if not profile_name:
            self.show_error("one_click_err_unexpected", e="No se pudo determinar el nombre del perfil.")
            self.install_button.setEnabled(True)
            return

        profiles_for_category = self.main_window.profiles.get(self.selected_game_name, {}).get(self.selected_category_key, {})
        profile_exists = profile_name in profiles_for_category
        
        if not profile_exists:
            self.info_label.setText(self.translator.translate("one_click_creating_profile", name=profile_name))
            QApplication.processEvents()

            category_data = self.main_window.game_data[self.selected_game_name]['categories'][self.selected_category_key]
            category_type = category_data.get('type')

            cached_icon_path = None
            game_short_name = self.main_window.game_data[self.selected_game_name]['short_name']
            game_icon_folder = os.path.join(self.main_window.user_icons_path, game_short_name)
            local_icon_path = next((
                os.path.join(game_icon_folder, f"{profile_name}{ext}") 
                for ext in ['.png', '.jpg', '.jpeg', '.webp'] 
                if os.path.exists(os.path.join(game_icon_folder, f"{profile_name}{ext}"))
            ), None)

            if local_icon_path:
                cached_icon_path = self.main_window._copy_icon_to_cache(local_icon_path, profile_name)

            self.main_window.current_game = self.selected_game_name
            self.main_window.current_category = self.selected_category_key

            operation_successful = False
            if category_type == 'direct_management':
                operation_successful = self.main_window.create_direct_profile(
                    name=profile_name, icon_path=cached_icon_path, update_ui=False
                )
            else:
                api_category_id = self.mod_api_data.get('_aCategory', {}).get('_idRow')
                operation_successful = self.main_window.create_managed_profile(
                    name=profile_name, icon_path=cached_icon_path, category_id=api_category_id, update_ui=False
                )

            if not operation_successful:
                self.show_error("one_click_err_profile_creation_failed", name=profile_name)
                self.install_button.setEnabled(True)
                return

        self.start_installation(profile_name)

    def start_installation(self, profile_name):
        self.info_label.setText(self.translator.translate("one_click_starting_download"))
        QApplication.processEvents()

        self.main_window.current_game = self.selected_game_name
        self.main_window.current_category = self.selected_category_key
        
        try:
            self.main_window.install_mod_from_api(
                profile_name=profile_name,
                mod_data=self.mod_api_data,
                file_data=self.file_api_data
            )
            QMessageBox.information(self, self.translator.translate("success_title"), self.translator.translate("one_click_success_msg"))

            self.main_window.update_profile_list(select_profile_name=profile_name)
            self.main_window.focus_on_profile(
                game_name=self.selected_game_name,
                category_key=self.selected_category_key,
                profile_name=profile_name
            )
            self.accept()

        except Exception as e:
            self.show_error("one_click_err_install_failed", e=e)
            self.install_button.setEnabled(True)

    def show_error(self, t_key, **kwargs):
        error_message = self.translator.translate(t_key, **kwargs)
        self.info_label.setText(error_message)
        self.info_label.setStyleSheet("font-size: 11pt; padding-bottom: 10px; color: #cc0000;")
        self.install_button.setEnabled(False)
        for combo in [self.game_combo, self.category_combo, self.profile_combo]:
            combo.setEnabled(False)