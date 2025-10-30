import os
import json
import math
import time
import threading
import win32api
import win32con
import win32gui
import ctypes
from ctypes import wintypes
import base64
from inputs import get_gamepad, UnpluggedError
from PyQt6.QtWidgets import QApplication, QWidget, QMessageBox
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QPointF, QRectF, QRect
from PyQt6.QtGui import QPainter, QPixmap, QColor, QPen, QBrush, QPainterPath, QFont, QFontMetrics, QLinearGradient, QImage
from lib.icons_base64 import ICONS

ACTIVATION_HOTKEY = "s"
PROFILES_PER_PAGE = 10
APP_DATA_PATH = os.path.join(os.getenv('APPDATA'), "MIMM")
CONFIG_PATH = os.path.join(APP_DATA_PATH, "config.json")
PROFILES_PATH = os.path.join(APP_DATA_PATH, "mod_manager_profiles.json")

GAME_WINDOW_TITLES = {
    "Genshin Impact": "Genshin Impact", "Honkai: Star Rail": "Honkai: Star Rail",
    "Wuthering Waves": "Wuthering Waves", "Zenless Zone Zero": "ZenlessZoneZero",
}
GAME_FOLDERS = {
    "Genshin Impact": "GIMI", "Honkai: Star Rail": "SRMI",
    "Wuthering Waves": "WWMI", "Zenless Zone Zero": "ZZMI",
}

VK_CODES = {
    "s": 0x53, "q": 0x51, "w": 0x57, "e": 0x45,
    "enter": 0x0D,
    "clear": 0x0C,
    "space": 0x20,
}
MOD_ALT, MOD_NOREPEAT, WM_HOTKEY = 0x0001, 0x4000, 0x0312

def force_focus(window):
    if window is None: return
    try:
        hwnd = int(window.winId())
        win32gui.SetForegroundWindow(hwnd)
        window.raise_()
        window.activateWindow()
    except Exception as e:
        print(f"Focus force failed: {e}")
        window.activateWindow()

class ControllerListener(QObject):
    dpad_y = pyqtSignal(int)
    dpad_x = pyqtSignal(int)
    button_a = pyqtSignal()
    button_b = pyqtSignal()
    toggle_overlay_combo = pyqtSignal()
    sync_combo_pressed = pyqtSignal() 
    bumper_pressed = pyqtSignal(int)
    trigger_pressed = pyqtSignal(int)
    joystick_y = pyqtSignal(int)
    joystick_x = pyqtSignal(int)
    any_input_detected = pyqtSignal()

    def __init__(self, translator):
        super().__init__()
        self.translator = translator
        self.is_running = True
        self.BTN_SOUTH = 'BTN_SOUTH'
        self.BTN_EAST = 'BTN_EAST'
        self.BTN_TL = 'BTN_TL'
        self.BTN_TR = 'BTN_TR'
        self.BTN_THUMBL = 'BTN_THUMBL'
        self.BTN_THUMBR = 'BTN_THUMBR'
        self.l_bumper_held = False
        self.r_bumper_held = False
        self.l_thumb_held = False
        self.r_thumb_held = False
        self.left_stick_up_held = False
        self.joystick_y_active = False
        self.joystick_x_active = False
        self.JOYSTICK_DEADZONE = 8192
        self.TRIGGER_THRESHOLD = 128
        self.lt_pressed = False
        self.rt_pressed = False

    def run(self):
        print(self.translator.translate("log_controller_listener_start"))
        while self.is_running:
            try:
                events = get_gamepad()
                if events: self.any_input_detected.emit()
                for event in events:
                    if not self.is_running: break
                    self.process_event(event)
            except UnpluggedError:
                print(self.translator.translate("log_controller_unplugged"))
                time.sleep(5)
            except Exception as e:
                print(self.translator.translate("log_controller_error", error=e))
                time.sleep(5)

    def process_event(self, event):
        if event.ev_type == 'Absolute':
            if event.code == 'ABS_HAT0Y': self.dpad_y.emit(event.state)
            elif event.code == 'ABS_HAT0X': self.dpad_x.emit(event.state)
            elif event.code == 'ABS_Y':
                self.left_stick_up_held = event.state < -self.JOYSTICK_DEADZONE
                if self.left_stick_up_held and not self.joystick_y_active: self.joystick_y_active = True; self.joystick_y.emit(-1)
                elif not self.left_stick_up_held and event.state > self.JOYSTICK_DEADZONE and not self.joystick_y_active: self.joystick_y_active = True; self.joystick_y.emit(1)
                elif -self.JOYSTICK_DEADZONE < event.state < self.JOYSTICK_DEADZONE: self.joystick_y_active = False
            elif event.code == 'ABS_X':
                if event.state < -self.JOYSTICK_DEADZONE and not self.joystick_x_active: self.joystick_x_active = True; self.joystick_x.emit(-1)
                elif event.state > self.JOYSTICK_DEADZONE and not self.joystick_x_active: self.joystick_x_active = True; self.joystick_x.emit(1)
                elif -self.JOYSTICK_DEADZONE < event.state < self.JOYSTICK_DEADZONE: self.joystick_x_active = False
            elif event.code == 'ABS_Z':
                if event.state > self.TRIGGER_THRESHOLD and not self.lt_pressed:
                    self.lt_pressed = True
                    self.trigger_pressed.emit(-1)
                elif event.state < self.TRIGGER_THRESHOLD:
                    self.lt_pressed = False
            elif event.code == 'ABS_RZ':
                if event.state > self.TRIGGER_THRESHOLD and not self.rt_pressed:
                    self.rt_pressed = True
                    self.trigger_pressed.emit(1)
                elif event.state < self.TRIGGER_THRESHOLD:
                    self.rt_pressed = False

        elif event.ev_type == 'Key':
            is_pressed = (event.state == 1)
            if event.code == self.BTN_TL:
                self.l_bumper_held = is_pressed
            elif event.code == self.BTN_TR:
                self.r_bumper_held = is_pressed
            elif event.code == self.BTN_THUMBL:
                self.l_thumb_held = is_pressed
            elif event.code == self.BTN_THUMBR:
                self.r_thumb_held = is_pressed
            if not is_pressed:
                return
            sync_combo_1 = self.l_bumper_held and (event.code == self.BTN_THUMBL or event.code == self.BTN_THUMBR)
            sync_combo_2 = (self.l_thumb_held and event.code == self.BTN_THUMBR) or \
                           (self.r_thumb_held and event.code == self.BTN_THUMBL)
            if sync_combo_1 or sync_combo_2:
                self.sync_combo_pressed.emit()
                return
            if self.l_bumper_held and event.code == self.BTN_EAST and self.left_stick_up_held:
                self.toggle_overlay_combo.emit()
                return
            if event.code == self.BTN_SOUTH:
                self.button_a.emit()
            elif event.code == self.BTN_EAST:
                self.button_b.emit()
            elif event.code == self.BTN_TL:
                self.bumper_pressed.emit(-1)
            elif event.code == self.BTN_TR:
                self.bumper_pressed.emit(1)

class DataManager:
    def __init__(self, translator):
        self.translator = translator
        os.makedirs(APP_DATA_PATH, exist_ok=True)
        self.config = self._load_json(CONFIG_PATH)
        self.profiles = self._load_json(PROFILES_PATH)
        self.xxmi_path = self.config.get("xxmi_path", "")

    def _load_json(self, path):
        if not os.path.exists(path): return {}
        try:
            with open(path, 'r', encoding='utf-8') as f: return json.load(f)
        except (json.JSONDecodeError, IOError): return {}

    def refresh_data(self):
        print(self.translator.translate("log_dm_reloading_profiles"))
        self.profiles = self._load_json(PROFILES_PATH)

    def get_categorized_profiles_for_game(self, game_name):
        game_data = self.profiles.get(game_name, {})
        categorized_profiles = {}
        for category, profiles in game_data.items():
            profile_list = [{'original_name': name, **data} for name, data in profiles.items()]
            if profile_list:
                categorized_profiles[category] = sorted(profile_list, key=lambda p: p.get('original_name'))
        return categorized_profiles

    def save_profiles(self):
        try:
            with open(PROFILES_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.profiles, f, indent=4)
        except IOError as e:
            print(self.translator.translate("log_dm_save_error", error=e))
            
    def save_config(self):
        try:
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4)
        except IOError as e:
            print(self.translator.translate("log_config_save_error", error=e))

class HotkeyListener(QObject):
    hotkey_pressed = pyqtSignal(str)

    def __init__(self, translator):
        super().__init__()
        self.translator = translator
        self.is_running = True
        self.thread_id = None
        self.id_to_key = {}

    def run(self):
        self.thread_id = threading.get_native_id()
        hotkey_id_counter = 1
        for key_name, vk_code in VK_CODES.items():
            current_id = hotkey_id_counter
            if not ctypes.windll.user32.RegisterHotKey(None, current_id, MOD_ALT | MOD_NOREPEAT, vk_code):
                error_code = ctypes.windll.kernel32.GetLastError()
                print(self.translator.translate("log_hotkey_register_error", key=key_name, code=error_code))
            else:
                print(self.translator.translate("log_hotkey_registered", key=f"Alt+{key_name.upper()}"))
                self.id_to_key[current_id] = key_name
            hotkey_id_counter += 1

        try:
            msg = wintypes.MSG()
            while self.is_running and ctypes.windll.user32.GetMessageA(ctypes.byref(msg), None, 0, 0) != 0:
                if msg.message == WM_HOTKEY:
                    hotkey_id = msg.wParam
                    if hotkey_id in self.id_to_key:
                        key_name = self.id_to_key[hotkey_id]
                        self.hotkey_pressed.emit(key_name)
        finally:
            for hotkey_id in self.id_to_key.keys():
                ctypes.windll.user32.UnregisterHotKey(None, hotkey_id)
            print(self.translator.translate("log_hotkey_unregistered"))
            
    def stop(self):
        self.is_running = False
        if self.thread_id:
             ctypes.windll.user32.PostThreadMessageW(self.thread_id, win32con.WM_NULL, 0, 0)

class ActionExecutorWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setGeometry(0, 0, 1, 1)

    def showEvent(self, event):
        force_focus(self)
        super().showEvent(event)

class ActiveWindowMonitor(QObject):
    game_detected = pyqtSignal(str)
    game_lost = pyqtSignal()

    def __init__(self, translator, overlay_title, controller):
        super().__init__()
        self.translator = translator
        self.overlay_title = overlay_title
        self.controller = controller
        self.current_game = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_active_window)
        self.timer.start(1000)

    def check_active_window(self):
        if self.controller.is_internal_action_active:
            return

        found_game_name = None
        try:
            hwnd = win32gui.GetForegroundWindow()
            active_window_title = win32gui.GetWindowText(hwnd)
            
            if active_window_title == self.overlay_title: return
            
            if active_window_title:
                for game_name, title_keyword in GAME_WINDOW_TITLES.items():
                    if title_keyword in active_window_title:
                        found_game_name = game_name
                        break
        except Exception: pass

        if found_game_name and self.current_game != found_game_name:
            self.current_game = found_game_name
            self.game_detected.emit(self.current_game)
        elif not found_game_name and self.current_game is not None:
            self.current_game = None
            self.game_lost.emit()

class WelcomeMessageWidget(QWidget):
    def __init__(self, translator, manager):
        super().__init__()
        self.translator = translator
        self.manager = manager
        self.setup_ui()

    def setup_ui(self):
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.SplashScreen
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setGeometry(QApplication.primaryScreen().geometry())

    def showEvent(self, event):
        super().showEvent(event)
        QApplication.setOverrideCursor(Qt.CursorShape.BlankCursor)
        try:
            hwnd = int(self.winId())
            win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, 0, 0, 0, 0)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            ctypes.windll.user32.BringWindowToTop(hwnd)
            self.raise_()
            self.activateWindow()
        except Exception:
            self.activateWindow()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 170))
        panel_width, panel_height = 650, 220
        panel_x = (self.width() - panel_width) / 2
        panel_y = (self.height() - panel_height) / 2
        panel_rect = QRectF(panel_x, panel_y, panel_width, panel_height)
        main_panel_path = QPainterPath()
        main_panel_path.addRoundedRect(panel_rect, 15, 15)
        gradient = QLinearGradient(panel_rect.topLeft(), panel_rect.bottomLeft())
        gradient.setColorAt(0, QColor(45, 45, 50, 235))
        gradient.setColorAt(1, QColor(35, 35, 40, 245))
        painter.fillPath(main_panel_path, gradient)
        accent_width = 80
        accent_rect = QRectF(panel_x, panel_y, accent_width, panel_height)
        painter.setClipPath(main_panel_path)
        painter.fillRect(accent_rect, QColor(55, 55, 60, 255))
        painter.setClipping(False)
        icon_center_x = panel_x + accent_width / 2
        icon_center_y = panel_y + accent_width / 2
        emphasis_color = self.manager.palette().color(self.manager.palette().ColorRole.Highlight)
        painter.setPen(QPen(emphasis_color, 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(icon_center_x, icon_center_y), 20, 20)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(emphasis_color)
        painter.drawEllipse(QPointF(icon_center_x, icon_center_y - 8), 3, 3)
        body_rect = QRectF(icon_center_x - 3, icon_center_y - 2, 6, 11)
        painter.drawRoundedRect(body_rect, 2, 2)
        content_x = panel_x + accent_width + 30
        content_width = panel_width - accent_width - 60
        title_font = QFont("Segoe UI", 24, QFont.Weight.Bold)
        painter.setFont(title_font)
        painter.setPen(emphasis_color)
        title_rect = QRectF(content_x, panel_y + 30, content_width, 50)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.translator.translate("welcome_title"))
        body_font = QFont("Segoe UI", 14)
        painter.setFont(body_font)
        painter.setPen(QColor(230, 230, 230))
        body_rect = QRectF(content_x, panel_y + 80, content_width, 80)
        painter.drawText(body_rect, int(Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap), self.translator.translate("welcome_text"))
        prompt_font = QFont("Segoe UI", 11, italic=True)
        painter.setFont(prompt_font)
        painter.setPen(QColor(150, 150, 150))
        prompt_rect = QRectF(content_x, panel_y + panel_height - 50, content_width, 20)
        painter.drawText(prompt_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom, self.translator.translate("welcome_continue_prompt"))

    def mousePressEvent(self, event):
        QApplication.restoreOverrideCursor()
        self.close()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape):
            self.close()

    def closeEvent(self, event):
        QApplication.restoreOverrideCursor()
        super().closeEvent(event)

class OverlayWindow(QWidget):
    kbm_activity_detected = pyqtSignal()
    
    def __init__(self, game_name, categorized_profiles, controller, translator, default_icon_path, initial_input_device):
        super().__init__()
        self.game_name = game_name
        self.GRID_SCROLL_SENSITIVITY_DIVISOR = 1
        self.categorized_profiles = categorized_profiles
        self.controller = controller
        self.translator = translator
        self.default_icon_path = default_icon_path
        self.game_data_structure = self.controller.manager.game_data
        game_categories_in_order = self.game_data_structure.get(self.game_name, {}).get('categories', {}).keys()
        self.categories = [cat for cat in game_categories_in_order if cat in self.categorized_profiles]
        self.current_input_device = initial_input_device
        self.nav_icons = {}
        self.view_mode = 'profiles'
        self.current_category_index = 0
        self.current_page = 0
        self.total_pages = 0
        self.selected_profile_index = 0
        self.rotation_angle = 0.0
        self.selected_profile_data = None
        self.selected_profile_mods = []
        self.mods_per_page = 16
        self.current_mod_page = 0
        self.total_mod_pages = 0
        self.selected_mod_index = 0
        self.mod_page_nav_rects = {}
        self.category_rects = []
        self.profile_rects = []
        self.nav_arrow_rects = {}
        self.setup_ui()
        self._load_icons()
        self._update_display_data()

    def setup_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setWindowTitle(self.translator.translate("overlay_window_title"))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setGeometry(QApplication.primaryScreen().geometry())
        self.setMouseTracking(True)

    def update_navigation_icons(self, device):
        if self.current_input_device != device:
            self.current_input_device = device
            self._load_icons()
            self.update()

    def _load_icons(self):
        self.nav_icons.clear()
        icon_set = ICONS.get(self.current_input_device, ICONS['keyboard'])
        print(f"--- Cargando set de iconos para: '{self.current_input_device}' ---")
        for action, b64_data in icon_set.items():
            try:
                image_data = base64.b64decode(b64_data)
                pixmap = QPixmap()
                success = pixmap.loadFromData(image_data, 'PNG')
                if success and not pixmap.isNull():
                    self.nav_icons[action] = pixmap
                    print(f"  - Ícono '{action}': Cargado con éxito.")
                else:
                    print(f"  - ERROR [libpng]: El ícono '{action}' no se pudo cargar. El pixmap es nulo.")
            except Exception as e:
                print(f"  - ERROR [decodificación]: El ícono '{action}' tiene datos Base64 inválidos. Error: {e}")

    def retranslate_ui(self):
        self.setWindowTitle(self.translator.translate("overlay_window_title"))
        self.update()

    def _update_display_data(self):
        category_name = self.categories[self.current_category_index]
        profiles_in_cat = self.categorized_profiles.get(category_name, [])
        self.total_pages = math.ceil(len(profiles_in_cat) / PROFILES_PER_PAGE) if profiles_in_cat else 1
        self.current_page = max(0, min(self.current_page, self.total_pages - 1))
        start, end = self.current_page * PROFILES_PER_PAGE, self.current_page * PROFILES_PER_PAGE + PROFILES_PER_PAGE
        self.profiles_on_page = profiles_in_cat[start:end]
        self.profiles_on_page.extend([{'type': 'empty'}] * (PROFILES_PER_PAGE - len(self.profiles_on_page)))
        self.selected_profile_index = 0
        self.rotation_angle = 0.0

    def _simulate_f10_press(self):
        try:
            win32api.keybd_event(0x79, 0, 0, 0)
            time.sleep(0.05)
            win32api.keybd_event(0x79, 0, win32con.KEYEVENTF_KEYUP, 0)
            print(self.translator.translate("log_f10_simulated"))
        except Exception as e:
            print(self.translator.translate("log_f10_sim_error", error=e))

    def change_category(self, direction):
        if self.view_mode != 'profiles' or not self.categories:
            return
        num_categories = len(self.categories)
        self.current_category_index = (self.current_category_index + direction + num_categories) % num_categories
        self.current_page = 0
        self._update_display_data()
        self.update()

    def handle_dpad_y(self, value):
        if not self.isVisible(): return
        if value == 0: return
        if self.view_mode == 'profiles':
            self.change_page(value)
        elif self.view_mode == 'mods':
            num_mods_on_page = sum(1 for m in self.selected_profile_mods if m.get('type') != 'empty')
            if num_mods_on_page == 0: return
            cols = 4
            new_index = self.selected_mod_index + (value * cols)
            if 0 <= new_index < num_mods_on_page:
                self.selected_mod_index = new_index
                self.update()

    def handle_dpad_x(self, value):
        if not self.isVisible(): return
        if value == 0: return
        if self.view_mode == 'profiles':
            self.rotate_selection(value)
        elif self.view_mode == 'mods':
            num_mods_on_page = sum(1 for m in self.selected_profile_mods if m.get('type') != 'empty')
            if num_mods_on_page == 0: return
            current_row = self.selected_mod_index // 4
            new_index = self.selected_mod_index + value
            new_row = new_index // 4
            if new_row == current_row and 0 <= new_index < num_mods_on_page:
                self.selected_mod_index = new_index
                self.update()

    def handle_button_a(self):
        if not self.isVisible(): return
        if self.view_mode == 'profiles' and self.profiles_on_page[self.selected_profile_index].get('type') != 'empty':
            self.selected_profile_data = self.profiles_on_page[self.selected_profile_index]
            self.view_mode = 'mods'
            self._set_initial_mods_page() 
            self.prepare_mods_view()
            self.update()
        elif self.view_mode == 'mods':
            self._trigger_mod_action(self.selected_mod_index)

    def handle_button_b(self):
        if not self.isVisible(): return
        if self.view_mode == 'mods':
            self.view_mode, self.current_mod_page = 'profiles', 0
            self.update()
        else:
            self.close()

    def handle_bumper_press(self, direction):
        if not self.isVisible(): return
        if self.view_mode == 'profiles':
            self.change_page(direction)
        elif self.view_mode == 'mods':
            self.change_mod_page(direction)

    def handle_trigger_press(self, direction):
        if not self.isVisible(): return
        self.change_category(direction)

    def handle_joystick_y(self, value):
        if not self.isVisible(): return
        if value == 0:
            return
        if self.view_mode == 'profiles':
            return
        self.handle_dpad_y(-value)

    def handle_joystick_x(self, value):
        if not self.isVisible(): return
        if value != 0:
            self.handle_dpad_x(value)

    def _toggle_direct_mod(self, mod_info):
        xxmi_path = self.controller.data_manager.xxmi_path
        game_folder = GAME_FOLDERS.get(self.game_name)
        if not xxmi_path or not game_folder:
            print(self.translator.translate("log_mod_path_error")); return False
        mod_path = os.path.join(xxmi_path, game_folder, "Mods", mod_info['folder_name'])
        if not os.path.isdir(mod_path):
            print(self.translator.translate("log_mod_folder_not_found", folder=mod_info['folder_name'])); return False
        try:
            action = '.disabled' if mod_info.get('active', False) else ''
            for root, _, files in os.walk(mod_path):
                for file_name in files:
                    if file_name.lower().endswith('.ini' + ('' if action else '.disabled')):
                        os.rename(os.path.join(root, file_name), os.path.join(root, file_name + action) if action else os.path.join(root, file_name[:-9]))
            self._simulate_f10_press(); return True
        except OSError as e:
            print(self.translator.translate("log_mod_rename_error", mod=mod_info['folder_name'], error=e)); return False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 150))

        if self.view_mode == 'profiles':
            self.draw_category_tabs(painter)
            self.draw_profile_circle(painter)
            self.draw_page_navigation(painter)
        elif self.view_mode == 'mods':
            self.draw_mods_view(painter)
        self.draw_navigation_footer(painter)

    def draw_navigation_footer(self, painter):
        footer_height = 100
        icon_height = 24
        right_margin = 40
        padding_icon_text = 10
        spacing_items = 30

        if self.view_mode == 'profiles':
            actions = [
                ('nav_wheel', "overlay_nav_profiles"),
                ('cycle_mod', "overlay_nav_categories"),
                ('nav_lr', "overlay_nav_pages"),
                ('accept', "overlay_action_select"),
                ('back', "overlay_action_close")
            ]
        elif self.view_mode == 'mods':
            actions = [('nav_ud', "overlay_nav_mods"), ('nav_lr', "overlay_nav_pages_mods"), ('accept', "overlay_action_toggle"), ('back', "overlay_action_back")]
        else:
            return

        painter.save()
        painter.setPen(Qt.GlobalColor.white)
        font = QFont("Segoe UI", 14)
        painter.setFont(font)
        fm = QFontMetrics(font)

        item_widths = []
        scaled_pixmaps = {}
        for icon_key, text_key in actions:
            pixmap = self.nav_icons.get(icon_key)
            icon_width = 0
            if pixmap and not pixmap.isNull():
                scaled_pixmap = pixmap.scaledToHeight(icon_height, Qt.TransformationMode.SmoothTransformation)
                scaled_pixmaps[icon_key] = scaled_pixmap
                icon_width = scaled_pixmap.width()
            
            text = self.translator.translate(text_key)
            text_width = fm.horizontalAdvance(text)
            item_widths.append(icon_width + padding_icon_text + text_width)
        
        total_width = sum(item_widths) + spacing_items * (len(actions) - 1)
        y = self.height() - footer_height
        x = (self.width() - total_width) - right_margin

        for i, (icon_key, text_key) in enumerate(actions):
            scaled_pixmap = scaled_pixmaps.get(icon_key)
            text = self.translator.translate(text_key)
            current_item_x_offset = 0

            if scaled_pixmap:
                icon_y = y + (footer_height - scaled_pixmap.height()) / 2
                painter.drawPixmap(int(x), int(icon_y), scaled_pixmap)
                current_item_x_offset = scaled_pixmap.width() + padding_icon_text

            text_y = y + (footer_height - fm.height()) / 2 + fm.ascent()
            painter.drawText(int(x + current_item_x_offset), int(text_y), text)
            x += item_widths[i] + spacing_items
        painter.restore()

    def draw_category_tabs(self, painter):
        self.category_rects.clear()
        font = QFont("Segoe UI", 16, QFont.Weight.Bold)
        painter.setFont(font)
        fm = QFontMetrics(font)
        highlight_color = self.controller.manager.palette().color(self.controller.manager.palette().ColorRole.Highlight)
        translated_categories = [self.translator.translate(self.game_data_structure[self.game_name]['categories'][cat_key]['t_key']) for cat_key in self.categories]
        category_spacing = 20
        total_width = sum(fm.horizontalAdvance(cat) + 40 for cat in translated_categories) + (len(translated_categories) - 1) * category_spacing
        x = (self.width() - total_width) / 2
        y = self.height() * 0.05
        for i, category_text in enumerate(translated_categories):
            is_selected = (i == self.current_category_index)
            text_width = fm.horizontalAdvance(category_text)
            rect = QRectF(x, y, text_width + 40, 50)
            self.category_rects.append(rect)
            if is_selected:
                painter.setPen(highlight_color)
                bg_color = QColor(highlight_color)
                bg_color.setAlpha(50)
                painter.setBrush(bg_color)
            else:
                painter.setPen(QColor(200, 200, 200)); painter.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath(); path.addRoundedRect(rect, 15, 15); painter.drawPath(path)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, category_text)
            x += rect.width() + category_spacing

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
        return has_visible_pixels

    def _create_white_version(self, source_pixmap: QPixmap):
        if source_pixmap.isNull():
            return QPixmap()
        recolored_pixmap = QPixmap(source_pixmap.size())
        recolored_pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(recolored_pixmap)
        painter.drawPixmap(0, 0, source_pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(recolored_pixmap.rect(), QColor("#FFFFFF"))
        painter.end()
        return recolored_pixmap

    def draw_profile_circle(self, painter: QPainter):
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.profile_rects.clear()
        content_rect = QRectF(0, self.height() * 0.2, self.width(), self.height() * 0.8)
        center, radius = content_rect.center(), min(content_rect.width(), content_rect.height()) * 0.30
        icon_size, selected_icon_size, angle_step = 110, 140, 360.0 / PROFILES_PER_PAGE
        highlight_color = self.controller.manager.palette().color(self.controller.manager.palette().ColorRole.Highlight)
        
        for i, profile in enumerate(self.profiles_on_page):
            is_selected = (i == self.selected_profile_index)
            size = selected_icon_size if is_selected else icon_size
            angle_rad = math.radians(self.rotation_angle + i * angle_step - 90)
            px, py = center.x() + radius * math.cos(angle_rad) - size / 2, center.y() + radius * math.sin(angle_rad) - size
            rect = QRectF(px, py, size, size)
            self.profile_rects.append(rect)
            path = QPainterPath()
            path.addEllipse(rect)

            if profile.get('type') == 'empty':
                painter.setPen(QColor(80, 80, 80, 150))
                painter.setBrush(QColor(50, 50, 50, 100))
                painter.drawEllipse(rect)
                continue

            icon_path = profile.get('icon')
            if not icon_path or not os.path.exists(icon_path):
                icon_path = self.default_icon_path
            
            pixmap = QPixmap(icon_path)
            
            if not pixmap.isNull() and self._is_strictly_dark_grayscale(pixmap.toImage()):
                pixmap = self._create_white_version(pixmap)

            if not pixmap.isNull():
                painter.setClipPath(path)
                painter.drawPixmap(rect.toRect(), pixmap)
                painter.setClipping(False)
            else:
                painter.setBrush(QColor("#333"))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(rect)

            if is_selected:
                painter.setPen(QPen(highlight_color, 6))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(rect)

        if self.profiles_on_page and 0 <= self.selected_profile_index < len(self.profiles_on_page):
            selected_profile = self.profiles_on_page[self.selected_profile_index]
            font = QFont("Segoe UI", 20, QFont.Weight.Bold)
            painter.setFont(font)
            painter.setPen(Qt.GlobalColor.white)
            name_rect = QRect(0, int(center.y() - radius - 220), self.width(), 60)
            painter.drawText(name_rect, Qt.AlignmentFlag.AlignCenter, selected_profile.get('original_name', ''))

    def draw_page_navigation(self, painter):
        if self.total_pages <= 1: self.nav_arrow_rects.clear(); return
        page_text = self.translator.translate("overlay_page_indicator", current=self.current_page + 1, total=self.total_pages)
        font = QFont("Segoe UI", 16); painter.setFont(font); painter.setPen(Qt.GlobalColor.white)
        text_rect = QRect(0, int(self.height() * 0.90), self.width(), 50)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, page_text)
        arrow_font = QFont("Segoe UI Symbol", 24, QFont.Weight.Bold); painter.setFont(arrow_font)
        fm = QFontMetrics(font)
        text_width = fm.horizontalAdvance(page_text)
        center_x = self.width() / 2
        left_rect = QRect(int(center_x - text_width/2 - 80), text_rect.y(), 60, 50)
        right_rect = QRect(int(center_x + text_width/2 + 20), text_rect.y(), 60, 50)
        painter.drawText(left_rect, Qt.AlignmentFlag.AlignCenter, "◄"); painter.drawText(right_rect, Qt.AlignmentFlag.AlignCenter, "►")
        self.nav_arrow_rects = {"left": left_rect, "right": right_rect}

    def draw_mods_view(self, painter):
        font = QFont("Segoe UI", 22, QFont.Weight.Bold); painter.setFont(font); painter.setPen(Qt.GlobalColor.white)
        painter.drawText(self.rect().adjusted(0, 20, 0, 0), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, self.selected_profile_data.get('original_name'))
        cols, w, h, p, top_m = 4, 220, 180, 40, 150
        grid_w = (w * cols) + (p * (cols - 1)); start_x = (self.width() - grid_w) // 2
        for i, mod in enumerate(self.selected_profile_mods):
            if mod.get('type') != 'empty':
                row, col = i // cols, i % cols
                self.draw_mod_card(painter, QRectF(start_x + col * (w + p), top_m + row * (h + p), w, h), mod, i)
        if self.total_mod_pages > 1:
            page_text = self.translator.translate("overlay_mod_page_indicator", current=self.current_mod_page + 1, total=self.total_mod_pages)
            font = QFont("Segoe UI", 16); painter.setFont(font); painter.setPen(Qt.GlobalColor.white)
            text_rect = QRect(0, int(self.height() * 0.95), self.width(), 50); painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, page_text)
            arrow_font = QFont("Segoe UI Symbol", 24, QFont.Weight.Bold); painter.setFont(arrow_font)
            fm = QFontMetrics(font)
            text_w = fm.horizontalAdvance(page_text)
            center_x = self.width() / 2
            left_rect = QRect(int(center_x - text_w/2 - 80), text_rect.y(), 60, 50); right_rect = QRect(int(center_x + text_w/2 + 20), text_rect.y(), 60, 50)
            painter.drawText(left_rect, Qt.AlignmentFlag.AlignCenter, "◄"); painter.drawText(right_rect, Qt.AlignmentFlag.AlignCenter, "►")
            self.mod_page_nav_rects = {"left": left_rect, "right": right_rect}
        else: self.mod_page_nav_rects.clear()

    def update_data_and_refresh_view(self, new_categorized_profiles):
        self.categorized_profiles = new_categorized_profiles
        category_name = self.categories[self.current_category_index]
        profiles_in_cat = self.categorized_profiles.get(category_name, [])
        self.total_pages = math.ceil(len(profiles_in_cat) / PROFILES_PER_PAGE) if profiles_in_cat else 1
        self.current_page = max(0, min(self.current_page, self.total_pages - 1))
        start, end = self.current_page * PROFILES_PER_PAGE, self.current_page * PROFILES_PER_PAGE + PROFILES_PER_PAGE
        self.profiles_on_page = profiles_in_cat[start:end]
        self.profiles_on_page.extend([{'type': 'empty'}] * (PROFILES_PER_PAGE - len(self.profiles_on_page)))
        if self.view_mode == 'profiles':
            self.selected_profile_index = max(0, min(self.selected_profile_index, len(self.profiles_on_page) - 1))
        elif self.view_mode == 'mods' and self.selected_profile_data:
            profile_name = self.selected_profile_data.get('original_name')
            updated_profile = next((p for p in self.profiles_on_page if p.get('original_name') == profile_name), None)
            if updated_profile:
                self.selected_profile_data = updated_profile
                self._set_initial_mods_page()
                self.prepare_mods_view()
            else:
                self.view_mode = 'profiles'
        self.update()

    def _trigger_mod_action(self, index):
        if not (0 <= index < len(self.selected_profile_mods)): return
        mod = self.selected_profile_mods[index]
        if mod.get('type') == 'empty': return
        
        last_selected_index = self.selected_mod_index
        cat, name = self.categories[self.current_category_index], self.selected_profile_data['original_name']
        
        if "slot_id" in mod:
            new_active_path = mod.get('path')
            self.controller.activate_mod_from_overlay(
                self.translator, 
                self.selected_profile_data.get('profile_id', 0), 
                mod.get('slot_id', 0)
            )
            self.controller.update_and_save_active_mod(cat, name, new_active_path)
            self.selected_profile_data['active_mod'] = new_active_path
        elif self._toggle_direct_mod(mod):
            self.controller.update_and_save_direct_mod_status(cat, name, mod['folder_name'])
        
        self.prepare_mods_view()
        self.selected_mod_index = last_selected_index
        self.update()

    def draw_mod_card(self, painter, rect, mod_info, index):
        path = QPainterPath(); path.addRoundedRect(rect, 10, 10)
        is_active = mod_info.get('active', False) or mod_info.get('is_active_managed', False)
        is_selected = (index == self.selected_mod_index)
        highlight_color = self.controller.manager.palette().color(self.controller.manager.palette().ColorRole.Highlight)
        painter.setBrush(QColor(40, 40, 40, 220)); painter.setPen(Qt.PenStyle.NoPen); painter.drawPath(path)
        if is_selected:
            normal_yellow = QColor("#FFD700")
            selected_active_color = QColor("#28A745")
            selection_color = selected_active_color if is_active else normal_yellow
            painter.setPen(QPen(selection_color, 6))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
        elif is_active:
            painter.setPen(QPen(highlight_color, 6))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
        icon_rect = QRectF(rect.x() + 10, rect.y() + 10, rect.width() - 20, rect.height() * 0.6)
        icon_path = mod_info.get("icon")
        if icon_path and os.path.exists(icon_path):
            pixmap, target_rect = QPixmap(icon_path), icon_rect.toRect()
            scaled_pixmap = pixmap.scaled(target_rect.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            draw_x, draw_y = target_rect.x() + (target_rect.width() - scaled_pixmap.width()) / 2, target_rect.y() + (target_rect.height() - scaled_pixmap.height()) / 2
            painter.drawPixmap(int(draw_x), int(draw_y), scaled_pixmap)
        else:
            font = QFont("Segoe UI", 12); painter.setFont(font); painter.setPen(Qt.GlobalColor.gray)
            painter.drawText(icon_rect, Qt.AlignmentFlag.AlignCenter, self.translator.translate("overlay_no_icon"))
        name_rect = QRectF(rect.x() + 10, icon_rect.bottom() + 5, rect.width() - 20, rect.height() * 0.25)
        font = QFont("Segoe UI", 11, QFont.Weight.Bold); painter.setFont(font); painter.setPen(Qt.GlobalColor.white)
        display_name = mod_info.get("display_name", mod_info.get("name", self.translator.translate("overlay_unknown_mod")))
        elided_name = QFontMetrics(font).elidedText(display_name, Qt.TextElideMode.ElideRight, int(name_rect.width()))
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, elided_name)

    def change_mod_page(self, direction):
        if self.total_mod_pages <= 1: return
        self.current_mod_page = (self.current_mod_page + direction + self.total_mod_pages) % self.total_mod_pages
        self.selected_mod_index = 0  
        self.prepare_mods_view()
        self.update()

    def change_page(self, direction):
        if self.total_pages <= 1: return
        self.current_page = (self.current_page + direction + self.total_pages) % self.total_pages; self._update_display_data(); self.update()

    def rotate_selection(self, direction):
        self.selected_profile_index = (self.selected_profile_index + direction + PROFILES_PER_PAGE) % PROFILES_PER_PAGE
        self.rotation_angle = -(360.0 / PROFILES_PER_PAGE) * self.selected_profile_index; self.update()

    def wheelEvent(self, event):
        self.kbm_activity_detected.emit()
        if self.view_mode == 'profiles':
            self.rotate_selection(1 if event.angleDelta().y() < 0 else -1)

    def mousePressEvent(self, event):
        self.kbm_activity_detected.emit()
        if event.button() == Qt.MouseButton.RightButton:
            if self.view_mode == 'mods':
                self.view_mode = 'profiles'
                self.current_mod_page = 0
                self.update()
            else:
                self.close()
            
        elif event.button() == Qt.MouseButton.LeftButton:
            if self.view_mode == 'profiles':
                self.handle_profile_click(event.pos())
            elif self.view_mode == 'mods':
                for direction, rect in self.mod_page_nav_rects.items():
                    if rect.contains(event.pos()):
                        self.change_mod_page(1 if direction == 'right' else -1)
                        return
                self.handle_mod_click(event.pos())

    def mouseMoveEvent(self, event):
        self.kbm_activity_detected.emit()
        super().mouseMoveEvent(event)

    def handle_profile_click(self, pos):
        for i, rect in enumerate(self.category_rects):
            if rect.contains(QPointF(pos)):
                if i != self.current_category_index: self.current_category_index, self.current_page = i, 0; self._update_display_data(); self.update()
                return
        for direction, rect in self.nav_arrow_rects.items():
            if rect.contains(pos): self.change_page(1 if direction == 'right' else -1); return
        for i, rect in enumerate(self.profile_rects):
            if rect.contains(QPointF(pos)):
                if self.profiles_on_page[i].get('type') != 'empty':
                    self.selected_profile_data = self.profiles_on_page[i]
                    self.view_mode = 'mods'
                    self._set_initial_mods_page()
                    self.prepare_mods_view()
                    self.update()
                return

    def _set_initial_mods_page(self):
        profile = self.selected_profile_data
        is_managed = 'profile_id' in profile
        all_mods = []
        if is_managed:
            all_mods.append({"display_name": self.translator.translate("overlay_none_mod"), "slot_id": 0, "is_active_managed": profile.get("active_mod") is None})
            for mod in profile.get("mods", []):
                mod_copy = mod.copy()
                mod_copy["is_active_managed"] = (profile.get("active_mod") == mod.get("path"))
                all_mods.append(mod_copy)
        else:
            cat = self.categories[self.current_category_index]
            profile_data = self.controller.data_manager.profiles.get(self.game_name, {}).get(cat, {}).get(profile['original_name'], {})
            all_mods.extend(profile_data.get("mods", []))

        active_index_in_full_list = 0
        for i, mod in enumerate(all_mods):
            if mod.get('is_active_managed', False) or mod.get('active', False):
                active_index_in_full_list = i
                break
        
        self.total_mod_pages = math.ceil(len(all_mods) / self.mods_per_page) if all_mods else 1
        self.current_mod_page = active_index_in_full_list // self.mods_per_page
        self.current_mod_page = max(0, min(self.current_mod_page, self.total_mod_pages - 1))
        self.selected_mod_index = active_index_in_full_list % self.mods_per_page

    def prepare_mods_view(self):
        profile = self.selected_profile_data
        is_managed = 'profile_id' in profile
        all_mods = []
        if is_managed:
            all_mods.append({"display_name": self.translator.translate("overlay_none_mod"), "slot_id": 0, "is_active_managed": profile.get("active_mod") is None})
            for mod in profile.get("mods", []):
                mod_copy = mod.copy()
                mod_copy["is_active_managed"] = (profile.get("active_mod") == mod.get("path"))
                all_mods.append(mod_copy)
        else:
            cat = self.categories[self.current_category_index]
            profile_data = self.controller.data_manager.profiles.get(self.game_name, {}).get(cat, {}).get(profile['original_name'], {})
            all_mods.extend(profile_data.get("mods", []))
        
        self.total_mod_pages = math.ceil(len(all_mods) / self.mods_per_page) if all_mods else 1
        start = self.current_mod_page * self.mods_per_page
        end = start + self.mods_per_page
        self.selected_profile_mods = all_mods[start:end]
        self.selected_profile_mods.extend([{'type': 'empty'}] * (self.mods_per_page - len(self.selected_profile_mods)))

    def handle_mod_click(self, click_pos):
        cols, w, h, p, top_m = 4, 220, 180, 40, 150; grid_w = (w * cols) + (p * (cols - 1)); start_x = (self.width() - grid_w) // 2
        for i, mod in enumerate(self.selected_profile_mods):
            row, col = i // cols, i % cols; rect = QRectF(start_x + col * (w + p), top_m + row * (h + p), w, h)
            if rect.contains(QPointF(click_pos)):
                self.selected_mod_index = i
                self._trigger_mod_action(i)
                return

    def keyPressEvent(self, event):
        self.kbm_activity_detected.emit()
        key = event.key()

        if key == Qt.Key.Key_Escape:
            if self.view_mode == 'mods':
                self.handle_button_b()
            else:
                self.close()
            return

        if self.view_mode == 'profiles':
            if key == Qt.Key.Key_Left: self.rotate_selection(-1)
            elif key == Qt.Key.Key_Right: self.rotate_selection(1)
            elif key in (Qt.Key.Key_Up, Qt.Key.Key_A): self.change_page(-1)
            elif key in (Qt.Key.Key_Down, Qt.Key.Key_D): self.change_page(1)
            elif key == Qt.Key.Key_Q: self.change_category(-1)
            elif key == Qt.Key.Key_E: self.change_category(1)
            elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter): self.handle_button_a()
        elif self.view_mode == 'mods':
            if key in (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_A): self.change_mod_page(-1)
            elif key in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_D): self.change_mod_page(1)

class OverlayController(QObject):
    mod_state_changed_from_overlay = pyqtSignal(str, str, str, object)
    input_device_changed = pyqtSignal(str)

    def __init__(self, manager, translator):
        super().__init__()
        self.manager = manager
        self.translator = translator
        self.data_manager = DataManager(translator)
        self.overlay_window = None
        self.current_game = None
        self.welcome_message_shown = False
        self.welcome_widget = None
        self.action_window = None
        self.is_internal_action_active = False
        self.last_input_device = 'keyboard'
        self.first_run_setup_done = set()
        self.sync_timer = QTimer(self)
        self.sync_timer.setSingleShot(True)
        self.sync_timer.timeout.connect(self.sync_overlay_with_ini_file)
        
        if not self.data_manager.xxmi_path: 
            print(translator.translate("log_xxmi_path_not_found"))
            return
        
        if not self.data_manager.xxmi_path: 
            print(translator.translate("log_xxmi_path_not_found"))
            return
        
        self.window_monitor = ActiveWindowMonitor(translator, translator.translate("overlay_window_title"), self)
        self.window_monitor.game_detected.connect(self.on_game_detected)
        self.window_monitor.game_lost.connect(self.on_game_lost)
        self.translator.language_changed.connect(self.on_language_changed)
        
        self.hotkey_thread = threading.Thread(target=self.setup_hotkey_listener, daemon=True)
        self.hotkey_thread.start()
        self.controller_thread = threading.Thread(target=self.setup_controller_listener, daemon=True)
        self.controller_thread.start()

    def _simulate_f10_press(self):
        try:
            win32api.keybd_event(0x79, 0, 0, 0)
            time.sleep(0.05)
            win32api.keybd_event(0x79, 0, win32con.KEYEVENTF_KEYUP, 0)
            print("Simulada pulsación de F10.")
        except Exception as e:
            print(f"No se pudo simular la pulsación de F10: {e}")

    def setup_controller_listener(self):
        self.controller_listener = ControllerListener(self.translator)
        self.controller_listener.any_input_detected.connect(self._report_controller_input)
        self.controller_listener.toggle_overlay_combo.connect(self.on_toggle_overlay_combo)
        self.controller_listener.sync_combo_pressed.connect(self.on_sync_combo_pressed)
        self.controller_listener.run()

    def _set_input_device_to_controller(self):
        if self.last_input_device != 'controller':
            self.last_input_device = 'controller'
            self.input_device_changed.emit('controller')
            print("Input device changed to: Controller")

    def on_toggle_overlay_combo(self):
        self._set_input_device_to_controller()
        self.toggle_overlay()

    def reload_profiles(self, from_disk=True):
        if from_disk:
            self.data_manager.refresh_data()
        if self.overlay_window:
            new_profiles = self.data_manager.get_categorized_profiles_for_game(self.current_game)
            self.overlay_window.update_data_and_refresh_view(new_profiles)

    def setup_hotkey_listener(self):
        self.key_listener = HotkeyListener(self.translator)
        self.key_listener.hotkey_pressed.connect(self.on_hotkey_pressed)
        self.key_listener.run()

    def on_game_detected(self, game_name):
        self.current_game = game_name
        print(self.translator.translate("log_game_detected", game=game_name))
        
        if not self.welcome_message_shown:
            QTimer.singleShot(100, self.show_welcome_message)
            self.welcome_message_shown = True

    def show_welcome_message(self):
        if self.welcome_widget is None or not self.welcome_widget.isVisible():
            self.welcome_widget = WelcomeMessageWidget(self.translator, self.manager)
            self.welcome_widget.show()
            QApplication.setOverrideCursor(Qt.CursorShape.BlankCursor)
            QTimer.singleShot(50, lambda: force_focus(self.welcome_widget) if self.welcome_widget else None)

    def on_hotkey_pressed(self, key):
        if self.last_input_device != 'keyboard':
            self.last_input_device = 'keyboard'
            self.input_device_changed.emit('keyboard')
            print("Input device changed to: Keyboard")
        if key == 's':
            self.toggle_overlay()
        elif key in ('q', 'w', 'e'):
            self.trigger_sync()

    def on_sync_combo_pressed(self):
        self._set_input_device_to_controller()
        print("Sync combo detected from controller.")
        self.trigger_sync()

    def trigger_sync(self):
        print("Sync triggered. Starting timer...")
        self.sync_timer.start(1000)

    def sync_overlay_with_ini_file(self):
        if not self.current_game:
            print(self.translator.translate("log_sync_no_game"))
            return

        game_folder = GAME_FOLDERS.get(self.current_game)
        if not self.data_manager.xxmi_path or not game_folder:
            print(self.translator.translate("log_sync_path_error"))
            return

        ini_path = os.path.join(self.data_manager.xxmi_path, game_folder, 'd3dx_user.ini')
        
        print(f"\n--- INICIANDO SINCRONIZACIÓN DESDE INI ---")
        print(f"[DEPURACIÓN] Ruta del archivo INI: '{ini_path}'")

        if not os.path.exists(ini_path):
            print(self.translator.translate("log_sync_ini_not_found", path=ini_path))
            return

        active_profile_id = -1
        active_profile_name = None
        active_profile_category = None
        
        try:
            print("[DEPURACIÓN] PASO 1: Buscando 'active_profile_id' global en el INI...")
            with open(ini_path, 'r', encoding='utf-8') as f:
                for line in f:
                    clean_line = line.strip()
                    if clean_line.startswith(r'$\mimm\profile_manager\active_profile_id'):
                        active_profile_id = int(clean_line.split('=')[1].strip())
                        print(f"[DEPURACIÓN] ID de perfil activo encontrado en INI: {active_profile_id}")
                        break
            
            if active_profile_id == -1:
                print(self.translator.translate("log_sync_vars_not_found"))
                return
            
            print(f"[DEPURACIÓN] PASO 2: Buscando el perfil con ID {active_profile_id} en los datos JSON...")
            game_profiles = self.data_manager.profiles.get(self.current_game, {})
            profile_found_in_json = False
            for category, profiles in game_profiles.items():
                for name, data in profiles.items():
                    if data.get('profile_id') == active_profile_id:
                        active_profile_name = name
                        active_profile_category = category
                        profile_found_in_json = True
                        print(f"[DEPURACIÓN] Perfil encontrado en JSON: Nombre='{active_profile_name}', Categoría='{active_profile_category}'")
                        break
                if profile_found_in_json:
                    break
            
            if not active_profile_name:
                print(self.translator.translate("log_sync_profile_not_found_in_json", profile_id=active_profile_id))
                return

            profile_key_in_ini = active_profile_name.lower()
            slot_search_key = f"$\\mimm\\{profile_key_in_ini}\\active_slot"
            print(f"[DEPURACIÓN] PASO 3: Buscando la clave específica '{slot_search_key}' en el INI...")
            
            active_slot_id = 0
            with open(ini_path, 'r', encoding='utf-8') as f:
                for line in f:
                    clean_line = line.strip()
                    if clean_line.startswith(slot_search_key):
                        active_slot_id = int(clean_line.split('=')[1].strip())
                        print(f"[DEPURACIÓN] Slot activo para '{active_profile_name}' encontrado. Valor: {active_slot_id}")
                        break
            print(f"[DEPURACIÓN] SINCRONIZACIÓN COMPLETA. Perfil: '{active_profile_name}' (ID {active_profile_id}), Slot Activo: {active_slot_id}")
            profile_data = self.data_manager.profiles[self.current_game][active_profile_category][active_profile_name]
            new_mod_path = None
            if active_slot_id > 0:
                for mod in profile_data.get('mods', []):
                    if mod.get('slot_id') == active_slot_id:
                        new_mod_path = mod.get('path')
                        print(f"[DEPURACIÓN] El slot ID {active_slot_id} corresponde al mod: '{new_mod_path}'")
                        break
            
            self.update_and_save_active_mod(active_profile_category, active_profile_name, new_mod_path)
            self.reload_profiles(from_disk=False)
            print("--- SINCRONIZACIÓN DESDE INI FINALIZADA --- \n")

        except (IOError, ValueError, IndexError) as e:
            print(self.translator.translate("log_sync_ini_read_error", error=e))

    def activate_mod_from_overlay(self, translator, profile_id, slot_id):
        print(translator.translate("log_mod_activated", group=profile_id, slot=slot_id))
        
        def execute_action():
            self.is_internal_action_active = True
            try:
                original_pos = win32gui.GetCursorPos()
                win32api.SetCursorPos((slot_id, profile_id))
                time.sleep(0.05)
                win32api.keybd_event(VK_CODES['clear'], 0, 0, 0)
                win32api.keybd_event(VK_CODES['space'], 0, 0, 0)
                time.sleep(0.05)
                win32api.keybd_event(VK_CODES['space'], 0, win32con.KEYEVENTF_KEYUP, 0)
                win32api.keybd_event(VK_CODES['clear'], 0, win32con.KEYEVENTF_KEYUP, 0)
                time.sleep(0.05)
                win32api.keybd_event(VK_CODES['clear'], 0, 0, 0)
                win32api.keybd_event(VK_CODES['enter'], 0, 0, 0)
                time.sleep(0.05)
                win32api.keybd_event(VK_CODES['enter'], 0, win32con.KEYEVENTF_KEYUP, 0)
                win32api.keybd_event(VK_CODES['clear'], 0, win32con.KEYEVENTF_KEYUP, 0)
                time.sleep(0.05)
                win32api.SetCursorPos(original_pos)
            except Exception as e:
                print(translator.translate("log_mod_activation_error", error=e))
            finally:
                if self.action_window:
                    self.action_window.close()
                    self.action_window = None
                QTimer.singleShot(100, self.clear_internal_action_flag)

        self.action_window = ActionExecutorWindow()
        self.action_window.show()
        QTimer.singleShot(50, execute_action)
    
    def _report_keyboard_mouse_input(self):
        if self.last_input_device != 'keyboard':
            self.last_input_device = 'keyboard'
            self.input_device_changed.emit('keyboard')
            print("Input device switched to: Keyboard/Mouse")

    def _report_controller_input(self):
        if self.last_input_device != 'controller':
            self.last_input_device = 'controller'
            self.input_device_changed.emit('controller')
            print("Input device switched to: Controller")

    def clear_internal_action_flag(self):
        self.is_internal_action_active = False

    def on_game_lost(self):
        print(self.translator.translate("log_game_lost"))
        self.current_game = None
        if self.overlay_window:
            self.overlay_window.close()
            self.overlay_window = None

    def update_and_save_active_mod(self, category, profile_name, new_mod_path):
        if not self.current_game: return
        try:
            profile = self.data_manager.profiles[self.current_game][category][profile_name]
            profile['active_mod'] = new_mod_path; self.data_manager.save_profiles()
            mod_display = os.path.basename(new_mod_path) if new_mod_path else self.translator.translate("overlay_none_mod")
            print(self.translator.translate("log_active_mod_saved", profile=profile_name, mod=mod_display))
            self.mod_state_changed_from_overlay.emit(self.current_game, category, profile_name, new_mod_path)
        except KeyError as e: print(self.translator.translate("log_active_mod_save_error", error=e))

    def update_and_save_direct_mod_status(self, category, profile_name, mod_folder_name):
        if not self.current_game: return
        try:
            profile = self.data_manager.profiles[self.current_game][category][profile_name]
            updated_mod_info = None
            for mod in profile['mods']:
                if mod['folder_name'] == mod_folder_name:
                    mod['active'] = not mod.get('active', False); updated_mod_info = mod
                    print(self.translator.translate("log_direct_mod_status_changed", mod=mod_folder_name, status=mod['active']))
                    break
            self.data_manager.save_profiles()
            if updated_mod_info: self.mod_state_changed_from_overlay.emit(self.current_game, category, profile_name, updated_mod_info)
        except KeyError as e: print(self.translator.translate("log_direct_mod_save_error", error=e))

    def on_language_changed(self):
        self.window_monitor.overlay_title = self.translator.translate("overlay_window_title")
        if self.overlay_window and self.overlay_window.isVisible():
            self.overlay_window.retranslate_ui()

    def pause_listeners(self):
        if hasattr(self, 'window_monitor'):
            self.window_monitor.timer.stop()
        print("Listeners del Overlay pausados.")

    def resume_listeners(self):
        if hasattr(self, 'window_monitor'):
            self.window_monitor.timer.start(1000)
        print("Listeners del Overlay reanudados.")

    def toggle_overlay(self):
        if self.welcome_widget and self.welcome_widget.isVisible():
            return
        
        if not self.current_game: 
            print(self.translator.translate("log_overlay_no_game"))
            return
        
        if self.current_game not in self.first_run_setup_done:
            print(self.translator.translate("log_overlay_first_open_sync", game=self.current_game))
            self.sync_overlay_with_ini_file()
            self.first_run_setup_done.add(self.current_game)
            if self.overlay_window:
                try:
                    if hasattr(self, 'controller_listener'):
                        self.controller_listener.dpad_y.disconnect(self.overlay_window.handle_dpad_y)
                        self.controller_listener.dpad_x.disconnect(self.overlay_window.handle_dpad_x)
                except TypeError:
                    pass
                self.overlay_window.close()
                self.overlay_window = None

        if self.overlay_window and self.overlay_window.isVisible():
            self.overlay_window.close()
            return

        if not self.overlay_window:
            print("Creando una nueva instancia de OverlayWindow...")
            profiles = self.data_manager.get_categorized_profiles_for_game(self.current_game)
            if not profiles: 
                print(self.translator.translate("log_overlay_no_profiles", game=self.current_game))
                return

            self.overlay_window = OverlayWindow(
                self.current_game, 
                profiles, 
                self, 
                self.translator, 
                self.manager.default_icon_path,
                self.last_input_device
            )
            self.overlay_window.kbm_activity_detected.connect(self._report_keyboard_mouse_input)
            self.input_device_changed.connect(self.overlay_window.update_navigation_icons)
            
            if hasattr(self, 'controller_listener'):
                self.controller_listener.dpad_y.connect(self.overlay_window.handle_dpad_y)
                self.controller_listener.dpad_x.connect(self.overlay_window.handle_dpad_x)
                self.controller_listener.button_a.connect(self.overlay_window.handle_button_a)
                self.controller_listener.button_b.connect(self.overlay_window.handle_button_b)
                self.controller_listener.bumper_pressed.connect(self.overlay_window.handle_bumper_press)
                self.controller_listener.trigger_pressed.connect(self.overlay_window.handle_trigger_press)
                self.controller_listener.joystick_y.connect(self.overlay_window.handle_joystick_y)
                self.controller_listener.joystick_x.connect(self.overlay_window.handle_joystick_x)

        self.overlay_window.show()
        QTimer.singleShot(50, lambda: force_focus(self.overlay_window) if self.overlay_window else None)