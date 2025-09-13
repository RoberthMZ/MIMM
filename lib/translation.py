import os
import json
from PyQt6.QtCore import QObject, pyqtSignal

class Translator(QObject):
    language_changed = pyqtSignal()

    def __init__(self, translations_dir, parent=None):
        super().__init__(parent)
        self.translations_dir = translations_dir
        self.language_data = {}
        self.fallback_data = {}
        self.current_language = None
        self._load_language('en')
        self.fallback_data = self.language_data.copy()

    def _load_language(self, lang_code):
        file_path = os.path.join(self.translations_dir, f"{lang_code}.json")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.language_data = json.load(f)
                self.current_language = lang_code
                print(f"Idioma '{lang_code}' cargado correctamente.")
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error al cargar el archivo de idioma '{lang_code}': {e}. Se usará el de respaldo.")
            self.language_data = self.fallback_data.copy()
            self.current_language = 'en'

    def set_language(self, lang_code):
        if lang_code != self.current_language:
            self._load_language(lang_code)
            self.language_changed.emit()

    def translate(self, translation_key, **kwargs):
        text = self.language_data.get(translation_key)
        if text is None:
            text = self.fallback_data.get(translation_key, translation_key)
        
        if kwargs:
            try:
                return text.format(**kwargs)
            except KeyError as e:
                print(f"Advertencia de traducción: Falta el argumento {e} para la clave '{translation_key}'")
                return text
        return text