import sys
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
from inputs import get_gamepad, UnpluggedError
from PyQt6.QtWidgets import QApplication, QWidget, QMessageBox
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QPointF, QRectF, QRect
from PyQt6.QtGui import QPainter, QPixmap, QColor, QPen, QBrush, QPainterPath, QFont, QFontMetrics, QLinearGradient, QImage

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

VK_CODES = {"s": 0x53}
MOD_ALT, MOD_NOREPEAT, WM_HOTKEY, HOTKEY_ID = 0x0001, 0x4000, 0x0312, 1

def force_focus(window):
    try:
        hwnd = int(window.winId())
        win32gui.SetForegroundWindow(hwnd)
        window.raise_()
        window.activateWindow()
        print("Focus forced successfully using SetForegroundWindow.")
    except Exception as e:
        print(f"Focus force failed: {e}")
        window.activateWindow()

class ControllerListener(QObject):
    dpad_y = pyqtSignal(int)
    dpad_x = pyqtSignal(int)
    button_a = pyqtSignal()
    button_b = pyqtSignal()
    toggle_overlay_combo = pyqtSignal()
    bumper_pressed = pyqtSignal(int)
    trigger_pressed = pyqtSignal(int)
    joystick_y = pyqtSignal(int)
    joystick_x = pyqtSignal(int)

    def __init__(self, translator):
        super().__init__()
        self.translator = translator
        self.is_running = True
        
        self.BTN_SOUTH = 'BTN_SOUTH'; self.BTN_EAST = 'BTN_EAST'
        self.BTN_TL = 'BTN_TL'; self.BTN_TR = 'BTN_TR'

        self.l_bumper_held = False        
        self.left_stick_up_held = False 
        
        self.left_trigger_active = False
        self.right_trigger_active = False
        self.joystick_x_active = False
        self.joystick_y_active = False
        self.JOYSTICK_DEADZONE = 8192

    def run(self):
        print(self.translator.translate("log_controller_listener_start"))
        while self.is_running:
            try:
                events = get_gamepad()
                for event in events:
                    if not self.is_running: break
                    self.process_event(event)
            except UnpluggedError:
                print(self.translator.translate("log_controller_unplugged")); time.sleep(5)
            except Exception as e:
                print(self.translator.translate("log_controller_error", error=e)); time.sleep(5)

    def process_event(self, event):
        if event.ev_type == 'Absolute':
            if event.code == 'ABS_HAT0Y': self.dpad_y.emit(event.state)
            elif event.code == 'ABS_HAT0X': self.dpad_x.emit(event.state)
            elif event.code == 'ABS_Z':
                if event.state > 128 and not self.left_trigger_active: self.left_trigger_active = True; self.trigger_pressed.emit(-1)
                elif event.state < 32: self.left_trigger_active = False
            elif event.code == 'ABS_RZ':
                if event.state > 128 and not self.right_trigger_active: self.right_trigger_active = True; self.trigger_pressed.emit(1)
                elif event.state < 32: self.right_trigger_active = False
            
            elif event.code == 'ABS_Y':
                if event.state < -self.JOYSTICK_DEADZONE:
                    self.left_stick_up_held = True
                elif event.state >= -self.JOYSTICK_DEADZONE:
                    self.left_stick_up_held = False
                if event.state < -self.JOYSTICK_DEADZONE and not self.joystick_y_active: self.joystick_y_active = True; self.joystick_y.emit(-1)
                elif event.state > self.JOYSTICK_DEADZONE and not self.joystick_y_active: self.joystick_y_active = True; self.joystick_y.emit(1)
                elif -self.JOYSTICK_DEADZONE < event.state < self.JOYSTICK_DEADZONE: self.joystick_y_active = False
            
            elif event.code == 'ABS_X':
                if event.state < -self.JOYSTICK_DEADZONE and not self.joystick_x_active: self.joystick_x_active = True; self.joystick_x.emit(-1)
                elif event.state > self.JOYSTICK_DEADZONE and not self.joystick_x_active: self.joystick_x_active = True; self.joystick_x.emit(1)
                elif -self.JOYSTICK_DEADZONE < event.state < self.JOYSTICK_DEADZONE: self.joystick_x_active = False

        elif event.ev_type == 'Key':
            is_pressed = (event.state == 1)
            if event.code == self.BTN_TL:
                self.l_bumper_held = is_pressed
            if event.code == self.BTN_EAST and is_pressed:
                if self.l_bumper_held and self.left_stick_up_held:
                    self.toggle_overlay_combo.emit()
                    self.l_bumper_held = False
                    self.left_stick_up_held = False
                    return
            if is_pressed:
                if event.code == self.BTN_SOUTH: self.button_a.emit()
                elif event.code == self.BTN_EAST: self.button_b.emit() 
                elif event.code == self.BTN_TL: self.bumper_pressed.emit(-1) 
                elif event.code == self.BTN_TR: self.bumper_pressed.emit(1)

    def stop(self):
        self.is_running = False
        print(self.translator.translate("log_controller_listener_stop"))

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

class HotkeyListener(QObject):
    activated = pyqtSignal()

    def __init__(self, translator):
        super().__init__()
        self.translator = translator
        self.is_running = True
        self.thread_id = None

    def run(self):
        self.thread_id = threading.get_native_id()
        vk_code = VK_CODES.get(ACTIVATION_HOTKEY.lower())
        if not vk_code:
            print(self.translator.translate("log_hotkey_invalid", key=ACTIVATION_HOTKEY))
            return

        if not ctypes.windll.user32.RegisterHotKey(None, HOTKEY_ID, MOD_ALT | MOD_NOREPEAT, vk_code):
            error_code = ctypes.windll.kernel32.GetLastError()
            print(self.translator.translate("log_hotkey_register_error", code=error_code))
            return
        
        print(self.translator.translate("log_hotkey_registered", key=ACTIVATION_HOTKEY))
        try:
            msg = wintypes.MSG()
            while self.is_running and ctypes.windll.user32.GetMessageA(ctypes.byref(msg), None, 0, 0) != 0:
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    self.activated.emit()
        finally:
            ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)
            print(self.translator.translate("log_hotkey_unregistered"))
            
    def stop(self):
        self.is_running = False
        if self.thread_id:
             ctypes.windll.user32.PostThreadMessageW(self.thread_id, win32con.WM_NULL, 0, 0)

class ActiveWindowMonitor(QObject):
    game_detected = pyqtSignal(str)
    game_lost = pyqtSignal()

    def __init__(self, translator, overlay_title):
        super().__init__()
        self.translator = translator
        self.overlay_title = overlay_title
        self.current_game = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_active_window)
        self.timer.start(2000)

    def check_active_window(self):
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
    def __init__(self, translator):
        super().__init__()
        self.translator = translator
        self.setup_ui()

    def setup_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setGeometry(QApplication.primaryScreen().geometry())

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
        emphasis_color = QColor("#00aaff")
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
        painter.setPen(QColor("#00aaff")) 
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
        self.close()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape):
            self.close()

    def closeEvent(self, event):
        QApplication.restoreOverrideCursor()
        super().closeEvent(event) 


class OverlayWindow(QWidget):
    def __init__(self, game_name, categorized_profiles, controller, translator, default_icon_path):
        super().__init__()
        self.game_name = game_name
        self.categorized_profiles = categorized_profiles
        self.controller = controller
        self.translator = translator
        self.default_icon_path = default_icon_path
        self.game_data_structure = self.controller.manager.game_data
        game_categories_in_order = self.game_data_structure.get(self.game_name, {}).get('categories', {}).keys()
        self.categories = [cat for cat in game_categories_in_order if cat in self.categorized_profiles]
        self.view_mode, self.current_category_index, self.current_page = 'profiles', 0, 0
        self.total_pages, self.selected_profile_index, self.rotation_angle = 0, 0, 0.0
        self.selected_profile_data, self.selected_profile_mods = None, []
        self.mods_per_page, self.current_mod_page, self.total_mod_pages = 16, 0, 0
        self.selected_mod_index = 0
        self.mod_page_nav_rects, self.category_rects, self.profile_rects, self.nav_arrow_rects = {}, [], [], {}
        self.setup_ui()
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
        self.selected_profile_index, self.rotation_angle = 0, 0.0

    def _simulate_f10_press(self):
        try:
            win32api.keybd_event(0x79, 0, 0, 0); time.sleep(0.05)
            win32api.keybd_event(0x79, 0, win32con.KEYEVENTF_KEYUP, 0)
            print(self.translator.translate("log_f10_simulated"))
        except Exception as e:
            print(self.translator.translate("log_f10_sim_error", error=e))

    def _activate_mod(self, profile_id, slot_id):
        try:
            original_pos = win32gui.GetCursorPos()
            win32api.SetCursorPos((slot_id, profile_id))
            time.sleep(0.05); win32api.keybd_event(0x0C, 0, 0, 0); win32api.keybd_event(0x20, 0, 0, 0); time.sleep(0.05)
            win32api.keybd_event(0x20, 0, win32con.KEYEVENTF_KEYUP, 0); win32api.keybd_event(0x0C, 0, win32con.KEYEVENTF_KEYUP, 0); time.sleep(0.05)
            win32api.keybd_event(0x0C, 0, 0, 0); win32api.keybd_event(0x0D, 0, 0, 0); time.sleep(0.05)
            win32api.keybd_event(0x0D, 0, win32con.KEYEVENTF_KEYUP, 0); win32api.keybd_event(0x0C, 0, win32con.KEYEVENTF_KEYUP, 0); time.sleep(0.05)
            win32api.SetCursorPos(original_pos)
            print(self.translator.translate("log_mod_activated", group=profile_id, slot=slot_id))
        except Exception as e:
            print(self.translator.translate("log_mod_activation_error", error=e))

    def change_category(self, direction):
        if self.view_mode != 'profiles' or not self.categories:
            return
        num_categories = len(self.categories)
        self.current_category_index = (self.current_category_index + direction + num_categories) % num_categories
        self.current_page = 0
        self._update_display_data()
        self.update()

    def handle_dpad_y(self, value):
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
        if self.view_mode == 'profiles' and self.profiles_on_page[self.selected_profile_index].get('type') != 'empty':
            self.selected_profile_data = self.profiles_on_page[self.selected_profile_index]
            self.view_mode = 'mods'
            self._set_initial_mods_page() 
            self.prepare_mods_view()
            self.update()
        elif self.view_mode == 'mods':
            self._trigger_mod_action(self.selected_mod_index)

    def handle_button_b(self):
        if self.view_mode == 'mods':
            self.view_mode, self.current_mod_page = 'profiles', 0
            self.update()
        else:
            self.close()

    def handle_bumper_press(self, direction):
        if self.view_mode == 'profiles':
            self.change_page(direction)
        elif self.view_mode == 'mods':
            self.change_mod_page(direction)

    def handle_trigger_press(self, direction):
        self.change_category(direction)

    def handle_joystick_y(self, value):
        if value == 0:
            return
        if self.view_mode == 'profiles':
            return
        self.handle_dpad_y(-value)

    def handle_joystick_x(self, value):
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
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 150))
        if self.view_mode == 'profiles':
            self.draw_category_tabs(painter)
            self.draw_profile_circle(painter)
            self.draw_page_navigation(painter)
        elif self.view_mode == 'mods':
            self.draw_mods_view(painter)

    def draw_category_tabs(self, painter):
        self.category_rects.clear()
        font = QFont("Segoe UI", 16, QFont.Weight.Bold)
        painter.setFont(font)
        fm = QFontMetrics(font)
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
                painter.setPen(QColor("#00aaff")); painter.setBrush(QColor(0, 170, 255, 50))
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
                painter.setPen(QPen(QColor("#00aaff"), 6))
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
        if self.view_mode == 'profiles': self._update_display_data()
        elif self.view_mode == 'mods' and self.selected_profile_data:
            cat_name = self.categories[self.current_category_index]; profile_name = self.selected_profile_data.get('original_name')
            updated_profile = next((p for p in self.categorized_profiles.get(cat_name, []) if p.get('original_name') == profile_name), None)
            if updated_profile: self.selected_profile_data = updated_profile; self.prepare_mods_view()
            else: self.view_mode = 'profiles'; self._update_display_data()
        self.update()

    def _trigger_mod_action(self, index):
        if not (0 <= index < len(self.selected_profile_mods)):
            return
        mod = self.selected_profile_mods[index]
        if mod.get('type') == 'empty':
            return
        last_selected_index = self.selected_mod_index
        cat, name = self.categories[self.current_category_index], self.selected_profile_data['original_name']
        if "slot_id" in mod:
            new_active_path = mod.get('path')
            self.controller.update_and_save_active_mod(cat, name, new_active_path)
            self.selected_profile_data['active_mod'] = new_active_path
            self._activate_mod(self.selected_profile_data.get('profile_id', 0), mod.get('slot_id', 0))
        elif self._toggle_direct_mod(mod):
            self.controller.update_and_save_direct_mod_status(cat, name, mod['folder_name'])
        self.prepare_mods_view()
        self.selected_mod_index = last_selected_index
        self.update()

    def draw_mod_card(self, painter, rect, mod_info, index):
        path = QPainterPath(); path.addRoundedRect(rect, 10, 10)
        is_active = mod_info.get('active', False) or mod_info.get('is_active_managed', False)
        is_selected = (index == self.selected_mod_index)
        painter.setBrush(QColor(40, 40, 40, 220)); painter.setPen(Qt.PenStyle.NoPen); painter.drawPath(path)
        if is_selected:
            normal_yellow = QColor("#FFD700")
            selected_active_color = QColor("#28A745")
            selection_color = selected_active_color if is_active else normal_yellow
            painter.setPen(QPen(selection_color, 6))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
        elif is_active:
            painter.setPen(QPen(QColor("#00aaff"), 6))
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
        if self.view_mode == 'profiles': self.rotate_selection(1 if event.angleDelta().y() < 0 else -1)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            if self.view_mode == 'mods': self.view_mode, self.current_mod_page = 'profiles', 0; self.update()
            else: self.close()
        elif event.button() == Qt.MouseButton.LeftButton:
            if self.view_mode == 'profiles':
                self.handle_profile_click(event.pos())
            elif self.view_mode == 'mods':
                for direction, rect in self.mod_page_nav_rects.items():
                    if rect.contains(event.pos()): self.change_mod_page(1 if direction == 'right' else -1); return
                self.handle_mod_click(event.pos())

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
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.handle_button_b()
        elif self.view_mode == 'profiles':
            if key == Qt.Key.Key_Left: self.rotate_selection(-1)
            elif key == Qt.Key.Key_Right: self.rotate_selection(1)
            elif key in (Qt.Key.Key_Up, Qt.Key.Key_A): self.change_page(-1)
            elif key in (Qt.Key.Key_Down, Qt.Key.Key_D): self.change_page(1)
            elif key == Qt.Key.Key_Q: self.change_category(-1)
            elif key == Qt.Key.Key_E: self.change_category(1)
            elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.handle_button_a()
        elif self.view_mode == 'mods':
            if key in (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_A):
                self.change_mod_page(-1)
            elif key in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_D):
                self.change_mod_page(1)

class OverlayController(QObject):
    mod_state_changed_from_overlay = pyqtSignal(str, str, str, object)
    
    def __init__(self, manager, translator):
        super().__init__()
        self.manager = manager
        self.translator = translator
        self.data_manager = DataManager(translator)
        self.overlay_window, self.current_game = None, None
        
        self.welcome_message_shown = False
        self.welcome_widget = None

        if not self.data_manager.xxmi_path: 
            print(translator.translate("log_xxmi_path_not_found"))
            return
        
        self.window_monitor = ActiveWindowMonitor(translator, translator.translate("overlay_window_title"))
        self.window_monitor.game_detected.connect(self.on_game_detected)
        self.window_monitor.game_lost.connect(self.on_game_lost)
        
        self.translator.language_changed.connect(self.on_language_changed)
        
        self.hotkey_thread = threading.Thread(target=self.setup_hotkey_listener, daemon=True)
        self.hotkey_thread.start()

        self.controller_thread = threading.Thread(target=self.setup_controller_listener, daemon=True)
        self.controller_thread.start()

    def setup_controller_listener(self):
        self.controller_listener = ControllerListener(self.translator)
        self.controller_listener.toggle_overlay_combo.connect(self.toggle_overlay)
        self.controller_listener.run()

    def reload_profiles(self):
        self.data_manager.refresh_data()
        if self.overlay_window and self.overlay_window.isVisible():
            new_profiles = self.data_manager.get_categorized_profiles_for_game(self.current_game)
            self.overlay_window.update_data_and_refresh_view(new_profiles)

    def setup_hotkey_listener(self):
        self.key_listener = HotkeyListener(self.translator)
        self.key_listener.activated.connect(self.toggle_overlay)
        self.key_listener.run()

    def on_game_detected(self, game_name):
        self.current_game = game_name
        print(self.translator.translate("log_game_detected", game=game_name))
        
        if not self.welcome_message_shown:
            QTimer.singleShot(100, self.show_welcome_message)
            self.welcome_message_shown = True

    def show_welcome_message(self):
        if self.welcome_widget is None or not self.welcome_widget.isVisible():
            self.welcome_widget = WelcomeMessageWidget(self.translator)
            self.welcome_widget.show()
            QTimer.singleShot(50, lambda: force_focus(self.welcome_widget))

    def on_game_lost(self):
        print(self.translator.translate("log_game_lost"))
        self.current_game = None
        if self.overlay_window:
            self.overlay_window.close()
            self.overlay_window = None

    def show_welcome_message(self):
        if self.welcome_widget is None or not self.welcome_widget.isVisible():
            self.welcome_widget = WelcomeMessageWidget(self.translator)
            self.welcome_widget.show()
            QApplication.setOverrideCursor(Qt.CursorShape.BlankCursor)
            QTimer.singleShot(50, lambda: force_focus(self.welcome_widget))

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

    def toggle_overlay(self):
        if self.welcome_widget and self.welcome_widget.isVisible():
            return
            
        if not self.current_game: print(self.translator.translate("log_overlay_no_game")); return
        if self.overlay_window and self.overlay_window.isVisible():
            self.overlay_window.close(); self.overlay_window = None
        else:
            profiles = self.data_manager.get_categorized_profiles_for_game(self.current_game)
            if not profiles: print(self.translator.translate("log_overlay_no_profiles", game=self.current_game)); return
            self.overlay_window = OverlayWindow(self.current_game, profiles, self, self.translator, self.manager.default_icon_path)
            
            if hasattr(self, 'controller_listener'):
                try:
                    self.controller_listener.dpad_y.disconnect()
                    self.controller_listener.dpad_x.disconnect()
                    self.controller_listener.button_a.disconnect()
                    self.controller_listener.button_b.disconnect()
                    self.controller_listener.bumper_pressed.disconnect()
                    self.controller_listener.trigger_pressed.disconnect()
                    self.controller_listener.joystick_y.disconnect()
                    self.controller_listener.joystick_x.disconnect()
                except TypeError: pass

                self.controller_listener.dpad_y.connect(self.overlay_window.handle_dpad_y)
                self.controller_listener.dpad_x.connect(self.overlay_window.handle_dpad_x)
                self.controller_listener.button_a.connect(self.overlay_window.handle_button_a)
                self.controller_listener.button_b.connect(self.overlay_window.handle_button_b)
                self.controller_listener.bumper_pressed.connect(self.overlay_window.handle_bumper_press)
                self.controller_listener.trigger_pressed.connect(self.overlay_window.handle_trigger_press)
                self.controller_listener.joystick_y.connect(self.overlay_window.handle_joystick_y)
                self.controller_listener.joystick_x.connect(self.overlay_window.handle_joystick_x)

            self.overlay_window.show()
            QTimer.singleShot(50, lambda: force_focus(self.overlay_window))