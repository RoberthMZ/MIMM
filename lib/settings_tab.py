from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, QLineEdit, 
    QPushButton, QComboBox, QCheckBox, QFileDialog, QSpacerItem, 
    QSizePolicy, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette

class SettingsTab(QWidget):
    def __init__(self, profile_name, manager, parent=None):
        super().__init__(parent)
        self.profile_name = profile_name
        self.manager = manager
        self.translator = self.manager.translator
        highlight_color = self.palette().color(QPalette.ColorRole.Highlight)
        base_color = self.palette().color(QPalette.ColorRole.Base)
        frame_bg_color = base_color.lighter(105) if base_color.lightness() < 128 else base_color.darker(105)

        self.frame_style = f"""
            QFrame#settingsFrame {{
                background-color: {frame_bg_color.name()};
                border: 1px solid rgba(128, 128, 128, 0.15);
                border-radius: 8px;
                outline: none;
            }}
        """
        self.input_style = f"""
            QLineEdit, QComboBox {{
                min-height: 28px;
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 1px 8px;
                background-color: {base_color.name()};
                outline: none;
            }}
            QLineEdit:focus, QComboBox:focus {{
                border: 1px solid {highlight_color.name()};
            }}
            QComboBox::drop-down {{
                border: none;
            }}
        """
        self.secondary_button_style = f"""
            QPushButton {{
                min-height: 28px; 
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 0px 12px;
                background-color: {base_color.name()};
                outline: none;
            }}
            QPushButton:hover {{
                border-color: {highlight_color.name()};
            }}
            QPushButton:pressed {{
                background-color: {highlight_color.darker(110).name()};
            }}
        """
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(25, 20, 25, 20)
        main_layout.setSpacing(20)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size: 18px; font-weight: bold; padding-bottom: 5px;")
        main_layout.addWidget(self.title_label)
        
        path_frame = QFrame()
        path_frame.setObjectName("settingsFrame")
        path_frame.setStyleSheet(self.frame_style)
        path_layout = QVBoxLayout(path_frame)
        path_layout.setContentsMargins(15, 10, 15, 15)
        path_layout.setSpacing(8)

        self.path_group_label = QLabel()
        self.path_group_label.setStyleSheet(f"font-size: 11pt; font-weight: bold; color: {highlight_color.name()};")
        
        self.xxmi_path_label = QLabel()
        
        path_input_layout = QHBoxLayout()
        self.path_display = QLineEdit()
        self.path_display.setReadOnly(True)
        self.path_display.setStyleSheet(self.input_style) 
        
        self.change_path_button = QPushButton()
        self.change_path_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.change_path_button.setStyleSheet(self.secondary_button_style) 
        self.change_path_button.clicked.connect(self.change_xxmi_path)
        
        path_input_layout.addWidget(self.path_display)
        path_input_layout.addWidget(self.change_path_button)
        
        path_layout.addWidget(self.path_group_label)
        path_layout.addWidget(self.xxmi_path_label)
        path_layout.addLayout(path_input_layout)
        main_layout.addWidget(path_frame)

        general_frame = QFrame()
        general_frame.setObjectName("settingsFrame")
        general_frame.setStyleSheet(self.frame_style)
        general_layout = QVBoxLayout(general_frame)
        general_layout.setContentsMargins(15, 10, 15, 15)
        general_layout.setSpacing(15)

        self.general_group_label = QLabel()
        self.general_group_label.setStyleSheet(f"font-size: 11pt; font-weight: bold; color: {highlight_color.name()};")

        language_layout = QHBoxLayout()
        self.language_label = QLabel()
        self.language_combo = QComboBox()
        self.language_combo.setMinimumWidth(150)
        self.language_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.language_combo.setStyleSheet(self.input_style) 
        self.lang_map = {"Español": "es", "English": "en", "Português": "pt", "中文": "zh"}
        self.language_combo.addItems(self.lang_map.keys())
        self.language_combo.currentTextChanged.connect(self.on_language_change)
        language_layout.addWidget(self.language_label)
        language_layout.addWidget(self.language_combo)
        language_layout.addStretch(1) 
        self.start_minimized_checkbox = QCheckBox()
        self.start_minimized_checkbox.setChecked(self.manager.config.get("start_minimized", False))
        self.start_minimized_checkbox.stateChanged.connect(self.on_start_minimized_changed)
        general_layout.addWidget(self.general_group_label)
        general_layout.addLayout(language_layout)
        general_layout.addWidget(self.start_minimized_checkbox)
        main_layout.addWidget(general_frame)
        main_layout.addStretch()
        self.retranslate_ui()

    def change_xxmi_path(self):
        new_path = QFileDialog.getExistingDirectory(
            self, 
            self.translator.translate("select_xxmi_folder_title"),
            self.manager.xxmi_path
        )
        if new_path and new_path != self.manager.xxmi_path:
            self.manager.update_xxmi_path(new_path)
            self.path_display.setText(new_path)

    def on_language_change(self, language_name):
        lang_code = self.lang_map.get(language_name)
        if lang_code and lang_code != self.manager.config.get("language"):
            self.manager.config['language'] = lang_code
            self.manager.save_config()
            self.translator.set_language(lang_code)

    def on_start_minimized_changed(self, state):
        is_checked = (state == Qt.CheckState.Checked.value)
        self.manager.config['start_minimized'] = is_checked
        self.manager.save_config()
        
    def retranslate_ui(self):
        self.title_label.setText(self.translator.translate("settings_title"))
        
        self.path_group_label.setText(self.translator.translate("settings_path_group_title"))
        self.xxmi_path_label.setText(self.translator.translate("xxmi_path_label"))
        self.change_path_button.setText(self.translator.translate("change_button"))
        self.path_display.setText(self.manager.xxmi_path or self.translator.translate("path_not_set"))

        self.general_group_label.setText(self.translator.translate("settings_general_group_title"))
        self.language_label.setText(self.translator.translate("language_label"))
        self.start_minimized_checkbox.setText(self.translator.translate("start_minimized_label"))

        current_lang_code = self.manager.config.get("language", "en")
        for name, code in self.lang_map.items():
            if code == current_lang_code:
                self.language_combo.blockSignals(True)
                self.language_combo.setCurrentText(name)
                self.language_combo.blockSignals(False)
                break