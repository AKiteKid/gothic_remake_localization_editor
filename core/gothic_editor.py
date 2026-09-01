import sys
import os
import struct
import traceback
import csv
import tempfile
import copy
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTableWidget, QTableWidgetItem,
    QLineEdit, QLabel, QFileDialog, QMessageBox,
    QHeaderView, QTextEdit, QProgressDialog, QSplitter,
    QMenu, QToolButton
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSettings, QRect
from PyQt6.QtGui import (
    QColor, QCloseEvent, QShortcut, QKeySequence, QAction, QMouseEvent,
    QPalette, QUndoStack, QUndoCommand, QIcon, QPainter,
    QPen, QBrush, QPixmap
)

def log_error(error_msg):
    try:
        with open("error_log.txt", "a", encoding="utf-8") as log_file:
            log_file.write(error_msg + "\n" + "="*50 + "\n")
    except Exception:
        pass

try:
    from Crypto.Cipher import AES
except ImportError as e:
    log_error(f"ImportError: {str(e)}\n{traceback.format_exc()}")
    raise ImportError("Install pycryptodome: pip install pycryptodome")

AES_KEY = b"8f93ff6fa254d9c536ad88c1ff1d812b"

def aes_ecb_decrypt(data: bytes) -> bytes:
    cipher = AES.new(AES_KEY, AES.MODE_ECB)
    return cipher.decrypt(data)

def aes_ecb_encrypt(data: bytes) -> bytes:
    cipher = AES.new(AES_KEY, AES.MODE_ECB)
    return cipher.encrypt(data)

try:
    from modules.editor_patch import DarkProgressDialog
except ImportError:
    DarkProgressDialog = None

def read_fstring(data: bytes, offset: int):
    if offset + 4 > len(data):
        raise ValueError("Not enough data for FString length")
    length = struct.unpack_from("<i", data, offset)[0]
    offset += 4
    if length == 0:
        return "", "utf-8", offset
    if length > 0:
        if offset + length > len(data):
            raise ValueError("Not enough data for UTF-8 FString")
        raw = data[offset:offset+length]
        offset += length
        if raw and raw[-1] == 0:
            raw = raw[:-1]
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")
        return text, "utf-8", offset
    else:
        unit_count = -length
        byte_count = unit_count * 2
        if offset + byte_count > len(data):
            raise ValueError("Not enough data for UTF-16 FString")
        raw = data[offset:offset+byte_count]
        offset += byte_count
        if len(raw) >= 2 and raw[-2:] == b'\x00\x00':
            raw = raw[:-2]
        try:
            text = raw.decode("utf-16le")
        except UnicodeDecodeError:
            text = raw.decode("utf-16le", errors="replace")
        return text, "utf-16le", offset

def write_fstring(text: str, encoding: str = "utf-16le") -> bytes:
    if not text:
        return struct.pack("<i", 0)
    if encoding == "utf-8":
        encoded = (text + "\x00").encode("utf-8")
        return struct.pack("<i", len(encoded)) + encoded
    else:
        encoded = (text + "\x00").encode("utf-16le")
        char_count = len(encoded) // 2
        return struct.pack("<i", -char_count) + encoded

def parse_lcache(encrypted_data: bytes):
    if len(encrypted_data) % 16 != 0:
        raise ValueError("Encrypted file size is not a multiple of 16")
    plain = aes_ecb_decrypt(encrypted_data)
    if len(plain) < 16:
        raise ValueError("Decrypted data is too short")
    offset = 0
    prefix = plain[offset]
    offset += 1
    magic_len = struct.unpack_from("<i", plain, offset)[0]
    offset += 4
    magic = plain[offset:offset+magic_len]
    offset += magic_len
    if magic != b"LCACHE":
        raise ValueError("Invalid LCACHE magic")
    lang_count = struct.unpack_from("<i", plain, offset)[0]
    offset += 4
    languages = []
    for _ in range(lang_count):
        lang, enc, offset = read_fstring(plain, offset)
        languages.append((lang, enc))
    group_count = struct.unpack_from("<i", plain, offset)[0]
    offset += 4
    raw_data = {}
    for _ in range(group_count):
        key, key_enc, offset = read_fstring(plain, offset)
        pair_count = struct.unpack_from("<i", plain, offset)[0]
        offset += 4
        main_langs = {}
        for _ in range(pair_count):
            lang, _, offset = read_fstring(plain, offset)
            value, val_enc, offset = read_fstring(plain, offset)
            main_langs[lang] = (value, val_enc)
        meta_key, meta_key_enc, offset = read_fstring(plain, offset)
        meta_pair_count = struct.unpack_from("<i", plain, offset)[0]
        offset += 4
        meta_langs = {}
        for _ in range(meta_pair_count):
            lang, _, offset = read_fstring(plain, offset)
            value, mval_enc, offset = read_fstring(plain, offset)
            meta_langs[lang] = (value, mval_enc)
        raw_data[key] = (main_langs, (meta_key, meta_key_enc), meta_langs, key_enc)
    return raw_data, languages

def build_lcache(raw_data: dict, languages: list) -> bytes:
    plain = bytearray()
    plain.append(0)
    magic = b"LCACHE"
    plain.extend(struct.pack("<i", len(magic)))
    plain.extend(magic)
    plain.extend(struct.pack("<i", len(languages)))
    for lang, enc in languages:
        plain.extend(write_fstring(lang, enc))
    plain.extend(struct.pack("<i", len(raw_data)))
    for key, (main_langs, (meta_key, meta_key_enc), meta_langs, key_enc) in raw_data.items():
        plain.extend(write_fstring(key, key_enc))
        plain.extend(struct.pack("<i", len(main_langs)))
        for lang, (text, val_enc) in main_langs.items():
            plain.extend(write_fstring(lang, "utf-8"))
            plain.extend(write_fstring(text, val_enc))
        plain.extend(write_fstring(meta_key, meta_key_enc))
        plain.extend(struct.pack("<i", len(meta_langs)))
        for lang, (text, mval_enc) in meta_langs.items():
            plain.extend(write_fstring(lang, "utf-8"))
            plain.extend(write_fstring(text, mval_enc))
    pad = (16 - (len(plain) % 16)) % 16
    plain.extend(b'\x00' * pad)
    encrypted = aes_ecb_encrypt(bytes(plain))
    return encrypted

class AppSettings:
    def __init__(self, ini_path="./settings.ini"):
        self._settings = QSettings(ini_path, QSettings.Format.IniFormat)
    def dark_mode(self) -> bool:
        return self._settings.value("dark_mode", False, type=bool)
    def set_dark_mode(self, v: bool):
        self._settings.setValue("dark_mode", v)
    def warm_mode(self) -> bool:
        return self._settings.value("warm_mode", False, type=bool)
    def set_warm_mode(self, v: bool):
        self._settings.setValue("warm_mode", v)
    def hide_empty(self) -> bool:
        return self._settings.value("hide_empty", False, type=bool)
    def set_hide_empty(self, v: bool):
        self._settings.setValue("hide_empty", v)
    def hide_edited(self) -> bool:
        return self._settings.value("hide_edited", False, type=bool)
    def set_hide_edited(self, v: bool):
        self._settings.setValue("hide_edited", v)
    def show_empty(self) -> bool:
        return self._settings.value("show_empty", False, type=bool)
    def set_show_empty(self, v: bool):
        self._settings.setValue("show_empty", v)
    def show_edited(self) -> bool:
        return self._settings.value("show_edited", False, type=bool)
    def set_show_edited(self, v: bool):
        self._settings.setValue("show_edited", v)
    def source_lang(self) -> str:
        return self._settings.value("source_lang", "english", type=str)
    def set_source_lang(self, v: str):
        self._settings.setValue("source_lang", v)
    def target_lang(self) -> str:
        return self._settings.value("target_lang", "english", type=str)
    def set_target_lang(self, v: str):
        self._settings.setValue("target_lang", v)
    def col_width(self, idx: int) -> int:
        return self._settings.value(f"col_width_{idx}", 250 if idx==0 else 450, type=int)
    def set_col_width(self, idx: int, w: int):
        self._settings.setValue(f"col_width_{idx}", w)
    def last_file_path(self) -> str:
        return self._settings.value("last_file_path", "", type=str)
    def set_last_file_path(self, v: str):
        self._settings.setValue("last_file_path", v)

class LockableTextEdit(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.text_edit = QTextEdit(self)
        self.text_edit.setObjectName("source_editor")
        self.text_edit.setPlaceholderText("Reference")
        self.lock_button = QToolButton(self)
        self.lock_button.setCheckable(True)
        self.lock_button.setFixedSize(24, 24)
        self.lock_button.setStyleSheet("background: transparent; border: none;")
        self.lock_button.toggled.connect(self.on_lock_toggled)
        self._dark_mode = False
        self._update_icons()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.text_edit)
        self.setLayout(layout)
        self.lock_button.show()
        self.update_button_position()

    def _create_lock_icon(self, locked):
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._dark_mode:
            color = QColor(210, 210, 210)
        else:
            color = QColor(50, 50, 50)
        painter.setPen(QPen(color, 2, Qt.PenStyle.SolidLine))
        painter.setBrush(QBrush(color))
        duga_rect = QRect(6, 4, 12, 8)
        painter.drawArc(duga_rect, 0, 180 * 16)
        body_rect = QRect(4, 10, 16, 10)
        painter.drawRect(body_rect)
        if not locked:
            painter.setPen(QPen(color, 2, Qt.PenStyle.SolidLine))
            painter.drawLine(12, 8, 12, 12)
        painter.setBrush(QBrush(Qt.GlobalColor.transparent))
        painter.drawEllipse(QRect(10, 12, 4, 4))
        painter.end()
        return QIcon(pixmap)

    def _update_icons(self):
        self.icon_open = self._create_lock_icon(False)
        self.icon_closed = self._create_lock_icon(True)
        if self.lock_button.isChecked():
            self.lock_button.setIcon(self.icon_closed)
        else:
            self.lock_button.setIcon(self.icon_open)

    def set_dark_mode(self, dark):
        self._dark_mode = dark
        self._update_icons()

    def update_button_position(self):
        rect = self.text_edit.rect()
        btn_size = self.lock_button.size()
        x = rect.right() - btn_size.width() - 6
        y = rect.bottom() - btn_size.height() - 6
        self.lock_button.move(x, y)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_button_position()

    def on_lock_toggled(self, checked):
        self.text_edit.setReadOnly(not checked)
        if checked:
            self.lock_button.setIcon(self.icon_closed)
        else:
            self.lock_button.setIcon(self.icon_open)

    def setPlainText(self, text):
        self.text_edit.setPlainText(text)

    def toPlainText(self):
        return self.text_edit.toPlainText()

    def setReadOnly(self, readonly):
        self.text_edit.setReadOnly(readonly)
        self.lock_button.setChecked(not readonly)
        self.on_lock_toggled(self.lock_button.isChecked())

class LoadThread(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(dict, list)
    error = pyqtSignal(str)
    def __init__(self, file_path, parser_func):
        super().__init__()
        self.file_path = file_path
        self._parser = parser_func
        self._is_cancelled = False
    def cancel(self):
        self._is_cancelled = True
    def run(self):
        try:
            self.progress.emit(10, "Reading file...")
            with open(self.file_path, "rb") as f:
                data = f.read()
            if self._is_cancelled:
                return
            self.progress.emit(40, "Parsing...")
            raw_data, languages = self._parser(data)
            if self._is_cancelled:
                return
            self.progress.emit(100, "Done")
            self.finished.emit(raw_data, languages)
        except Exception as e:
            err_details = f"{str(e)}\n{traceback.format_exc()}"
            log_error(f"LoadThread error:\n{err_details}")
            self.error.emit(err_details)

class TitleBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent_window = parent
        self.setFixedHeight(38)
        self.drag_pos = None
        self.setObjectName("title_bar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)
        self.title_label = QLabel("Gothic Remake Localization Editor 0.5")
        self.title_label.setObjectName("title_label")
        self.title_label.setStyleSheet("background: transparent; font-weight: 600; font-size: 13px;")
        layout.addWidget(self.title_label)
        layout.addStretch()
        self.btn_minimize = QPushButton()
        self.btn_minimize.setFixedSize(14, 14)
        self.btn_minimize.setObjectName("btn_minimize")
        self.btn_minimize.setStyleSheet("border-radius: 7px; background-color: #28c840; border: 1px solid #24b838;")
        self.btn_minimize.clicked.connect(self.parent_window.showMinimized)
        layout.addWidget(self.btn_minimize)
        self.btn_maximize = QPushButton()
        self.btn_maximize.setFixedSize(14, 14)
        self.btn_maximize.setObjectName("btn_maximize")
        self.btn_maximize.setStyleSheet("border-radius: 7px; background-color: #ffbd2e; border: 1px solid #e0a82a;")
        self.btn_maximize.clicked.connect(self.toggle_maximize)
        layout.addWidget(self.btn_maximize)
        self.btn_close = QPushButton()
        self.btn_close.setFixedSize(14, 14)
        self.btn_close.setObjectName("btn_close")
        self.btn_close.setStyleSheet("border-radius: 7px; background-color: #ff5f57; border: 1px solid #e04a44;")
        self.btn_close.clicked.connect(self.parent_window.close)
        layout.addWidget(self.btn_close)
        self.setStyleSheet("""
            TitleBar { background: transparent; border-top-left-radius: 12px; border-top-right-radius: 12px; }
            TitleBar QPushButton#btn_minimize:hover { background-color: #34d94a; border: 1px solid #2cc040; }
            TitleBar QPushButton#btn_maximize:hover { background-color: #ffd04a; border: 1px solid #e8b830; }
            TitleBar QPushButton#btn_close:hover { background-color: #ff7a73; border: 1px solid #e85a54; }
        """)
    def toggle_maximize(self):
        if self.parent_window.isMaximized():
            self.parent_window.showNormal()
        else:
            self.parent_window.showMaximized()
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint()
    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_pos is not None:
            delta = event.globalPosition().toPoint() - self.drag_pos
            self.parent_window.move(self.parent_window.pos() + delta)
            self.drag_pos = event.globalPosition().toPoint()
    def mouseReleaseEvent(self, event: QMouseEvent):
        self.drag_pos = None
    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximize()

class BulkEditCommand(QUndoCommand):
    def __init__(self, model, changes):
        super().__init__()
        self.model = model
        self.changes = changes
        self.old_states = []
        for k, col, lang, old_text, old_enc in changes:
            self.old_states.append((k, col, lang, old_text, old_enc))
    def redo(self):
        for k, col, lang, new_text, new_enc in self.changes:
            self.model._apply_change(k, col, lang, new_text, new_enc)
    def undo(self):
        for k, col, lang, old_text, old_enc in self.old_states:
            self.model._apply_change(k, col, lang, old_text, old_enc)

class LCacheEditor(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowSystemMenuHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.resize(1200, 800)
        self.setMinimumSize(800, 600)
        self.settings = AppSettings()
        self.raw_data = {}
        self.baseline_data = {}
        self.flattened_data = []
        self.available_languages = set()
        self.locales_list = []
        self.current_editing_row = -1
        self.dark_mode = False
        self.warm_mode = False
        self.has_changes = False
        self.load_thread = None
        self.progress_dialog = None
        self.current_file_path = ""
        self.modified_keys = set()
        self._bulk_update = False
        self.source_lang = "english"
        self.target_lang = "english"
        self.undo_stack = QUndoStack(self)
        self.initUI()
        self.load_settings()
        self.apply_styles()
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(lambda: self.search_box.setFocus())
        self.undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        self.undo_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.undo_shortcut.activated.connect(self.custom_undo)
        self.redo_shortcut = QShortcut(QKeySequence("Ctrl+Y"), self)
        self.redo_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.redo_shortcut.activated.connect(self.custom_redo)
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self.save_lcache)
        self.filter_timer = QTimer()
        self.filter_timer.setSingleShot(True)
        self.filter_timer.setInterval(300)
        self.filter_timer.timeout.connect(self.filter_table)

    def _get_key_id(self, row):
        item = self.table.item(row, 0)
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return None

    def _apply_change(self, key_id, col, lang, text, enc):
        if key_id not in self.raw_data:
            return
        group = self.raw_data[key_id]
        main_langs = group[0] if isinstance(group, tuple) else group
        if isinstance(main_langs, dict):
            main_langs[lang] = (text, enc)
        self._update_table_for_key(key_id, col, text)
        self._update_modified_status(key_id)
        self.has_changes = True
        if not self._bulk_update:
            self.update_status_stats()

    def _update_table_for_key(self, key_id, col, text):
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == key_id:
                self.table.item(row, col).setText(text)
                if row == self.current_editing_row and col == 2:
                    if self.target_editor.toPlainText() != text:
                        self._bulk_update = True
                        cursor = self.target_editor.textCursor()
                        old_pos = cursor.position()
                        self.target_editor.blockSignals(True)
                        self.target_editor.setPlainText(text)
                        self.target_editor.blockSignals(False)
                        cursor.setPosition(min(old_pos, len(text)))
                        self.target_editor.setTextCursor(cursor)
                        self._bulk_update = False
                break
        self.table.blockSignals(False)

    def _update_translation_data(self, key_id, target_lang, new_text):
        if key_id not in self.raw_data:
            return
        base_key = self.get_base_key(key_id)
        changes = []
        for k, (m_langs, m_meta, m_meta_langs, m_key_enc) in self.raw_data.items():
            if self.get_base_key(k) != base_key:
                continue
            old_entry = m_langs.get(target_lang, ("", "utf-16le"))
            old_text = old_entry[0] if isinstance(old_entry, tuple) else old_entry
            old_enc = old_entry[1] if isinstance(old_entry, tuple) else "utf-16le"
            if old_text == new_text:
                continue
            final_enc = "utf-16le" if any(ord(ch) > 127 for ch in new_text) else old_enc
            m_langs[target_lang] = (new_text, final_enc)
            self.raw_data[k] = (m_langs, m_meta, m_meta_langs, m_key_enc)
            changes.append((k, 2, target_lang, old_text, old_enc))
            self.modified_keys.add(k)
        if target_lang not in self.available_languages:
            self._ensure_language_in_locales(target_lang)
        return changes

    def _update_modified_status(self, key_id):
        if key_id not in self.raw_data or key_id not in self.baseline_data:
            return
        current_main = self.raw_data[key_id][0]
        baseline_main = self.baseline_data[key_id][0]
        changed = False
        all_langs = set(current_main.keys()) | set(baseline_main.keys())
        for lang in all_langs:
            cur_text = current_main.get(lang, ("", "utf-16le"))[0]
            base_text = baseline_main.get(lang, ("", "utf-16le"))[0]
            if cur_text != base_text:
                changed = True
                break
        if changed:
            self.modified_keys.add(key_id)
        else:
            self.modified_keys.discard(key_id)

    def _ensure_language_in_locales(self, lang):
        if lang not in self.available_languages:
            self.available_languages.add(lang)
            self.locales_list.append((lang, "utf-16le"))
            self._update_language_menus()

    def _build_language_menu(self):
        menu = QMenu(self)
        self.source_menu = QMenu("Source Language", self)
        self.target_menu = QMenu("Target Language", self)
        menu.addMenu(self.source_menu)
        menu.addMenu(self.target_menu)
        self.language_menu = menu
        self._update_language_menus()
        return menu

    def _update_language_menus(self):
        if not hasattr(self, 'available_languages') or not self.available_languages:
            return
        self.source_menu.clear()
        self.target_menu.clear()
        langs = sorted(self.available_languages)
        for lang in langs:
            act = QAction(lang, self)
            act.triggered.connect(lambda checked, l=lang: self.set_source_language(l))
            self.source_menu.addAction(act)
        for lang in langs:
            if lang == self.source_lang:
                continue
            act = QAction(lang, self)
            act.triggered.connect(lambda checked, l=lang: self.set_target_language(l))
            self.target_menu.addAction(act)

    def set_source_language(self, lang):
        if lang == self.target_lang:
            others = [l for l in self.available_languages if l != lang]
            self.target_lang = others[0] if others else lang
        self.source_lang = lang
        self._update_language_menus()
        self.refresh_table()
        self.save_settings()

    def set_target_language(self, lang):
        self.target_lang = lang
        self._update_language_menus()
        self.refresh_table()
        self.save_settings()

    def initUI(self):
        self.main_widget = QWidget()
        self.main_widget.setObjectName("main_widget")
        self.main_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        main_layout = QVBoxLayout(self.main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        self.title_bar = TitleBar(self)
        main_layout.addWidget(self.title_bar)
        content_widget = QWidget()
        content_widget.setObjectName("content_widget")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(16, 12, 16, 16)
        content_layout.setSpacing(8)
        top_layout = QHBoxLayout()
        top_layout.setSpacing(8)
        self.btn_import = QPushButton("Import")
        self.import_menu = QMenu(self)
        action_lcache = QAction("Import .lcache", self)
        action_lcache.triggered.connect(self.load_lcache)
        self.import_menu.addAction(action_lcache)
        action_csv_import = QAction("Import CSV", self)
        action_csv_import.triggered.connect(self.import_csv)
        self.import_menu.addAction(action_csv_import)
        self.btn_import.setMenu(self.import_menu)
        self.btn_import.setFixedWidth(80)
        top_layout.addWidget(self.btn_import)
        self.btn_export = QPushButton("Export")
        self.export_menu = QMenu(self)
        action_save_lcache = QAction("Save .lcache", self)
        action_save_lcache.triggered.connect(self.save_lcache)
        self.export_menu.addAction(action_save_lcache)
        action_csv_export = QAction("Export to CSV", self)
        action_csv_export.triggered.connect(self.export_csv)
        self.export_menu.addAction(action_csv_export)
        self.btn_export.setMenu(self.export_menu)
        self.btn_export.setEnabled(False)
        self.btn_export.setFixedWidth(80)
        top_layout.addWidget(self.btn_export)
        self.btn_choose_lang = QPushButton("Choose Language")
        self.btn_choose_lang.setMenu(self._build_language_menu())
        self.btn_choose_lang.setFixedWidth(150)
        top_layout.addWidget(self.btn_choose_lang)
        self.btn_theme = QPushButton("🌓 Theme")
        self.btn_theme.setCheckable(True)
        self.btn_theme.clicked.connect(self.toggle_theme)
        self.btn_theme.setFixedWidth(90)
        top_layout.addWidget(self.btn_theme)
        self.btn_warm = QPushButton("🌅 Warm")
        self.btn_warm.setCheckable(True)
        self.btn_warm.clicked.connect(self.toggle_warm)
        self.btn_warm.setFixedWidth(80)
        top_layout.addWidget(self.btn_warm)
        top_layout.addStretch()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍 Search Key or Text...")
        self.search_box.textChanged.connect(self.on_search_text_changed)
        self.search_box.setFixedWidth(220)
        top_layout.addWidget(self.search_box)
        self.btn_hide_empty = QPushButton("Hide Empty")
        self.btn_hide_empty.setCheckable(True)
        self.btn_hide_empty.clicked.connect(self.on_hide_empty_toggled)
        self.btn_hide_empty.setFixedWidth(100)
        top_layout.addWidget(self.btn_hide_empty)
        self.btn_hide_edited = QPushButton("Hide Edited")
        self.btn_hide_edited.setCheckable(True)
        self.btn_hide_edited.clicked.connect(self.on_hide_edited_toggled)
        self.btn_hide_edited.setFixedWidth(100)
        top_layout.addWidget(self.btn_hide_edited)
        self.btn_show_empty = QPushButton("Show Only Empty")
        self.btn_show_empty.setCheckable(True)
        self.btn_show_empty.clicked.connect(self.on_show_empty_toggled)
        self.btn_show_empty.setFixedWidth(130)
        top_layout.addWidget(self.btn_show_empty)
        self.btn_show_edited = QPushButton("Show Only Edited")
        self.btn_show_edited.setCheckable(True)
        self.btn_show_edited.clicked.connect(self.on_show_edited_toggled)
        self.btn_show_edited.setFixedWidth(130)
        top_layout.addWidget(self.btn_show_edited)
        content_layout.addLayout(top_layout)
        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.setSpacing(8)
        self.status_label = QLabel("Ready")
        status_row.addWidget(self.status_label)
        status_row.addStretch()
        self.visible_status_label = QLabel("Shown: 0 | Hidden: 0")
        self.visible_status_label.setObjectName("visible_status_label")
        self.visible_status_label.setFixedWidth(130)
        self.visible_status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        status_row.addWidget(self.visible_status_label)
        content_layout.addLayout(status_row)
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Key ID", f"Source ({self.source_lang})", "Target Language"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.sectionResized.connect(self._on_section_resized)
        self.table.setColumnWidth(0, 250)
        available = self.table.viewport().width() - 250
        col_width = max(200, available // 2)
        self.table.setColumnWidth(1, col_width)
        self.table.setColumnWidth(2, available - col_width)
        self.table.clicked.connect(self.on_table_row_clicked)
        self.main_vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_vertical_splitter.setChildrenCollapsible(False)
        self.main_vertical_splitter.setHandleWidth(8)
        self.main_vertical_splitter.addWidget(self.table)

        left_container = QWidget()
        left_container.setObjectName("left_container")
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.source_editor = LockableTextEdit()
        left_layout.addWidget(self.source_editor)

        central_container = QWidget()
        central_container.setObjectName("central_container")
        central_layout = QVBoxLayout(central_container)
        central_layout.setContentsMargins(0, 0, 0, 0)
        self.target_editor = QTextEdit()
        self.target_editor.setPlaceholderText("Target editable text...")
        self.target_editor.setObjectName("target_editor")
        self.target_editor.setUndoRedoEnabled(True)
        self.target_editor.textChanged.connect(self.on_target_editor_changed)
        central_layout.addWidget(self.target_editor)

        right_container = QWidget()
        right_container.setObjectName("right_container")
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.right_panel = QWidget()
        self.right_panel.setObjectName("right_panel")
        panel_layout = QVBoxLayout(self.right_panel)
        panel_layout.setContentsMargins(10, 10, 10, 10)
        panel_layout.setSpacing(8)
        panel_layout.addStretch()
        right_layout.addWidget(self.right_panel)

        bottom_splitter = QSplitter(Qt.Orientation.Horizontal)
        bottom_splitter.setChildrenCollapsible(False)
        bottom_splitter.setHandleWidth(8)
        bottom_splitter.addWidget(left_container)
        bottom_splitter.addWidget(central_container)
        bottom_splitter.addWidget(right_container)
        bottom_splitter.setSizes([400, 400, 200])

        self.main_vertical_splitter.addWidget(bottom_splitter)
        self.main_vertical_splitter.setSizes([500, 200])
        content_layout.addWidget(self.main_vertical_splitter)
        main_layout.addWidget(content_widget)
        self.setLayout(QVBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(self.main_widget)

        QTimer.singleShot(0, self._update_column_widths)

    def custom_undo(self):
        focused = QApplication.focusWidget()
        if isinstance(focused, QTextEdit) or (focused and focused.objectName() == "target_editor"):
            focused.undo()
        else:
            self.undo_stack.undo()

    def custom_redo(self):
        focused = QApplication.focusWidget()
        if isinstance(focused, QTextEdit) or (focused and focused.objectName() == "target_editor"):
            focused.redo()
        else:
            self.undo_stack.redo()

    def on_search_text_changed(self):
        self.filter_timer.start()

    def on_hide_empty_toggled(self):
        if self.btn_hide_empty.isChecked() and self.btn_show_empty.isChecked():
            self.btn_show_empty.setChecked(False)
        self.filter_timer.start()
        self.save_settings()

    def on_hide_edited_toggled(self):
        if self.btn_hide_edited.isChecked() and self.btn_show_edited.isChecked():
            self.btn_show_edited.setChecked(False)
        self.filter_timer.start()
        self.save_settings()

    def on_show_empty_toggled(self):
        if self.btn_show_empty.isChecked():
            self.btn_hide_empty.setChecked(False)
            self.btn_show_edited.setChecked(False)
        self.filter_timer.start()
        self.save_settings()

    def on_show_edited_toggled(self):
        if self.btn_show_edited.isChecked():
            self.btn_hide_edited.setChecked(False)
            self.btn_show_empty.setChecked(False)
        self.filter_timer.start()
        self.save_settings()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_column_widths()

    def _on_section_resized(self, logicalIndex, oldSize, newSize):
        if logicalIndex in (0, 1):
            self._update_column_widths()

    def _update_column_widths(self):
        if self.table.columnCount() < 3:
            return
        header = self.table.horizontalHeader()
        header.blockSignals(True)
        try:
            available = self.table.viewport().width() - self.table.columnWidth(0)
            col1_width = self.table.columnWidth(1)
            if col1_width > available:
                col1_width = available
            new_col2_width = available - col1_width
            if new_col2_width < 50:
                new_col2_width = 50
            if self.table.columnWidth(2) != new_col2_width:
                self.table.setColumnWidth(2, new_col2_width)
        finally:
            header.blockSignals(False)

    def load_settings(self):
        self.dark_mode = self.settings.dark_mode()
        self.warm_mode = self.settings.warm_mode()
        self.btn_theme.setChecked(self.dark_mode)
        self.btn_warm.setChecked(self.warm_mode)
        self.btn_hide_empty.setChecked(self.settings.hide_empty())
        self.btn_hide_edited.setChecked(self.settings.hide_edited())
        self.btn_show_empty.setChecked(self.settings.show_empty())
        self.btn_show_edited.setChecked(self.settings.show_edited())
        self.source_lang = self.settings.source_lang()
        self.target_lang = self.settings.target_lang()
        self.table.setColumnWidth(0, self.settings.col_width(0))
        self.table.setColumnWidth(1, self.settings.col_width(1))
        self.table.setColumnWidth(2, self.settings.col_width(2))
        last_path = self.settings.last_file_path()
        if last_path and os.path.exists(last_path):
            self.current_file_path = last_path
        else:
            self.current_file_path = ""

    def save_settings(self):
        self.settings.set_dark_mode(self.dark_mode)
        self.settings.set_warm_mode(self.warm_mode)
        self.settings.set_hide_empty(self.btn_hide_empty.isChecked())
        self.settings.set_hide_edited(self.btn_hide_edited.isChecked())
        self.settings.set_show_empty(self.btn_show_empty.isChecked())
        self.settings.set_show_edited(self.btn_show_edited.isChecked())
        self.settings.set_source_lang(self.source_lang)
        self.settings.set_target_lang(self.target_lang)
        self.settings.set_col_width(0, self.table.columnWidth(0))
        self.settings.set_col_width(1, self.table.columnWidth(1))
        self.settings.set_col_width(2, self.table.columnWidth(2))
        if self.current_file_path:
            self.settings.set_last_file_path(self.current_file_path)

    def toggle_theme(self):
        self.dark_mode = self.btn_theme.isChecked()
        self.apply_styles()
        self.save_settings()

    def toggle_warm(self):
        self.warm_mode = self.btn_warm.isChecked()
        self.apply_styles()
        self.save_settings()

    def apply_styles(self):
        if self.dark_mode:
            bg = "#232731" if self.warm_mode else "#1e222b"
            t_bg = "#2a2f3a" if self.warm_mode else "#21252b"
            fg = "#e6dbb2" if self.warm_mode else "#d4d4d4"
            grid = "#4b5263" if self.warm_mode else "#3e4451"
            btn = "#3e4452" if self.warm_mode else "#3a3f4d"
            hdr = "#2d3139" if self.warm_mode else "#282c34"
            active_btn = "#564d3b" if self.warm_mode else "#4b6e9c"
            title_bg = "#1a1e26" if self.warm_mode else "#171b24"
        else:
            bg = "#f4ecd8" if self.warm_mode else "#f5f5f5"
            t_bg = "#fdfaf2" if self.warm_mode else "#ffffff"
            fg = "#2b2625" if self.warm_mode else "#000000"
            grid = "#c8b8a0" if self.warm_mode else "#d0d0d0"
            btn = "#e4dcc4" if self.warm_mode else "#e1e1e1"
            hdr = "#e4dcc4" if self.warm_mode else "#e1e1e1"
            active_btn = "#dfcfa5" if self.warm_mode else "#b6d7a8"
            title_bg = "#e8e0cc" if self.warm_mode else "#e8e8e8"
        qss = f"""
            QWidget#main_widget {{ background-color: {bg}; border: 2px solid {grid}; border-radius: 12px; }}
            QWidget#content_widget {{ background-color: {bg}; }}
            TitleBar {{ background-color: {title_bg}; border-top-left-radius: 12px; border-top-right-radius: 12px; }}
            TitleBar QLabel#title_label {{ color: {fg}; }}
            QPushButton {{ background-color: {btn}; color: {fg}; border: 1px solid {grid}; padding: 5px 12px; border-radius: 6px; }}
            QPushButton:checked {{ background-color: {active_btn}; border: 1px solid {fg}; }}
            QPushButton:disabled {{ background-color: {bg}; color: {grid}; border: 1px solid {bg}; }}
            QLineEdit {{ background-color: {t_bg}; color: {fg}; border: 1px solid {grid}; padding: 4px 8px; border-radius: 6px; }}
            QTextEdit {{ background-color: {t_bg}; color: {fg}; border: 1px solid {grid}; border-radius: 6px; padding: 6px; }}
            QTableWidget {{ background-color: {t_bg}; color: {fg}; gridline-color: {grid}; border: 1px solid {grid}; border-radius: 6px; }}
            QTableWidget::item {{ background-color: {t_bg}; color: {fg}; }}
            QHeaderView::section {{ background-color: {hdr}; color: {fg}; border: 1px solid {grid}; padding: 4px; }}
            QTableCornerButton::section {{ background-color: {hdr}; color: {fg}; border: 1px solid {bg}; }}
            QLabel {{ background-color: transparent; color: {fg}; }}
            QSplitter::handle {{ background: transparent; }}
            QTextEdit#source_editor {{ background-color: {t_bg}; color: {fg}; border: 1px solid {grid}; border-radius: 6px; padding: 6px; }}
            QTextEdit#target_editor {{ background-color: {t_bg}; color: {fg}; border: 1px solid {grid}; border-radius: 6px; padding: 6px; }}
            QWidget#right_panel {{ background-color: {t_bg}; border: 1px solid {grid}; border-radius: 6px; }}
            QLabel#visible_status_label {{ font-size: 11px; font-weight: 600; opacity: 0.8; padding-right: 4px; margin-top: -2px; }}
            QMenuBar {{ background-color: {title_bg}; color: {fg}; }}
            QMenu {{ background-color: {t_bg}; color: {fg}; border: 1px solid {grid}; }}
            QMenu::item:selected {{ background-color: {active_btn}; }}
            QScrollBar:vertical {{ background: {bg}; width: 14px; margin: 0px; }}
            QScrollBar::handle:vertical {{ background: {grid}; min-height: 20px; border-radius: 7px; }}
            QScrollBar::handle:vertical:hover {{ background: {active_btn}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ background: none; height: 0px; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
            QScrollBar:horizontal {{ background: {bg}; height: 14px; margin: 0px; }}
            QScrollBar::handle:horizontal {{ background: {grid}; min-width: 20px; border-radius: 7px; }}
            QScrollBar::handle:horizontal:hover {{ background: {active_btn}; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ background: none; width: 0px; }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}
            QDialog, QMessageBox, QProgressDialog {{ background-color: {bg}; border: 2px solid {grid}; border-radius: 12px; }}
            QDialog QLabel, QMessageBox QLabel, QProgressDialog QLabel {{ color: {fg}; }}
            QDialog QPushButton, QMessageBox QPushButton, QProgressDialog QPushButton {{ background-color: {btn}; color: {fg}; border: 1px solid {grid}; border-radius: 6px; padding: 5px 12px; }}
            QProgressBar {{ border: 1px solid {grid}; border-radius: 4px; text-align: center; background-color: {t_bg}; color: {fg}; }}
            QProgressBar::chunk {{ background-color: {active_btn}; }}
        """
        QApplication.instance().setStyleSheet(qss)
        self.source_editor.set_dark_mode(self.dark_mode)

    def maybe_save_changes(self) -> bool:
        if self.has_changes:
            ret = QMessageBox.question(self, "Unsaved Changes", "You have unsaved changes. Do you want to export them?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
            if ret == QMessageBox.StandardButton.Yes:
                self.save_lcache()
                return not self.has_changes
            elif ret == QMessageBox.StandardButton.Cancel:
                return False
        return True

    def load_lcache(self):
        if not self.maybe_save_changes():
            return
        file_path, _ = QFileDialog.getOpenFileName(self, "Import Localization File", self.current_file_path or "", "LCache Files (*.lcache);;All Files (*)")
        if not file_path:
            return
        self.current_file_path = file_path
        self.status_label.setText("Loading...")
        self.btn_import.setEnabled(False)
        self.btn_export.setEnabled(False)

        if DarkProgressDialog is not None:
            self.progress_dialog = DarkProgressDialog("Loading file...", "Cancel", 0, 100, self)
        else:
            from PyQt6.QtWidgets import QProgressDialog
            self.progress_dialog = QProgressDialog("Loading file...", "Cancel", 0, 100, self)

        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.canceled.connect(self.cancel_load)

        self.progress_dialog.setStyleSheet(QApplication.instance().styleSheet())
        self.progress_dialog.show()
        self.load_thread = LoadThread(file_path, parse_lcache)
        self.load_thread.progress.connect(self.update_progress)
        self.load_thread.finished.connect(self.on_load_finished)
        self.load_thread.error.connect(self.on_load_error)
        self.load_thread.start()

    def cancel_load(self):
        if self.load_thread and self.load_thread.isRunning():
            self.load_thread.cancel()
            self.load_thread.quit()
            if not self.load_thread.wait(3000):
                self.load_thread.terminate()
                self.load_thread.wait()
        self.progress_dialog.close()
        self.status_label.setText("Load cancelled")
        self.btn_import.setEnabled(True)

    def update_progress(self, value, message):
        if self.progress_dialog:
            self.progress_dialog.setValue(value)
            self.progress_dialog.setLabelText(message)

    def on_load_finished(self, raw_data, languages):
        self.progress_dialog.close()
        self.raw_data = raw_data
        self.baseline_data = copy.deepcopy(raw_data)
        self.locales_list = languages
        self.flattened_data = [(key, main_langs) for key, (main_langs, _, _, _) in raw_data.items()]
        self.available_languages = set()
        for _, main_langs in self.flattened_data:
            for lang in main_langs.keys():
                self.available_languages.add(lang)
        self._update_language_menus()
        self.btn_export.setEnabled(True)
        self.btn_import.setEnabled(True)
        self.has_changes = False
        self.undo_stack.clear()
        self.modified_keys.clear()
        self.refresh_table()
        self.save_settings()

    def on_load_error(self, error_msg):
        self.progress_dialog.close()
        self.btn_import.setEnabled(True)
        self.status_label.setText("Load error")
        QMessageBox.critical(self, "Error", f"Failed to load file:\n{error_msg}")

    def get_base_key(self, key: str) -> str:
        for suffix in ["_newer", "_new", "_v3", "_v2", "_patch"]:
            if key.endswith(suffix):
                return key[:-len(suffix)]
        return key

    def _get_source_text(self, main_langs, source_lang, current_key=""):
        lang_candidates = [
            source_lang + "_newer", source_lang + "_new", source_lang + "_v3",
            source_lang + "_v2", source_lang + "_patch", source_lang
        ]
        data_pool = getattr(self, 'raw_data', {})
        if current_key and data_pool:
            base_key = current_key
            for suffix in ["_newer", "_new", "_v3", "_v2", "_patch"]:
                if base_key.endswith(suffix):
                    base_key = base_key[:-len(suffix)]
                    break
            search_order = [
                base_key + "_newer", base_key + "_new",
                base_key + "_v3", base_key + "_v2",
                base_key + "_patch", base_key
            ]
            for k in search_order:
                if k in data_pool:
                    target_group = data_pool[k]
                    if isinstance(target_group, tuple) and len(target_group) > 0:
                        target_main_langs = target_group[0]
                        if isinstance(target_main_langs, dict):
                            for lang_name in lang_candidates:
                                if lang_name in target_main_langs:
                                    val = target_main_langs[lang_name]
                                    return lang_name, val[0] if isinstance(val, tuple) else val
                            for actual_lang in target_main_langs.keys():
                                if actual_lang.lower().startswith(source_lang):
                                    val = target_main_langs[actual_lang]
                                    return actual_lang, val[0] if isinstance(val, tuple) else val
        if isinstance(main_langs, dict):
            for lang_name in lang_candidates:
                if lang_name in main_langs:
                    val = main_langs[lang_name]
                    return lang_name, val[0] if isinstance(val, tuple) else val
            for actual_lang in main_langs.keys():
                if actual_lang.lower().startswith(source_lang):
                    val = main_langs[actual_lang]
                    return actual_lang, val[0] if isinstance(val, tuple) else val
            if main_langs:
                lang = list(main_langs.keys())[0]
                val = main_langs[lang]
                return lang, val[0] if isinstance(val, tuple) else val
        return None, ""

    def refresh_table(self):
        try:
            if self.raw_data:
                self.flattened_data = [(key, main_langs) for key, (main_langs, _, _, _) in self.raw_data.items()]

            if not self.flattened_data:
                return

            source_lang = self.source_lang or "english"
            target_lang = self.target_lang or "english"

            self.table.setHorizontalHeaderLabels(["Key ID", f"Source ({source_lang})", "Target Language"])

            self.table.setUpdatesEnabled(False)
            self.table.blockSignals(True)
            self.table.setRowCount(len(self.flattened_data))
            self.current_editing_row = -1
            self.source_editor.setPlainText("")
            self.target_editor.clear()

            for row, (key_id, main_langs) in enumerate(self.flattened_data):
                id_item = QTableWidgetItem(key_id)
                id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                id_item.setData(Qt.ItemDataRole.UserRole, key_id)
                self.table.setItem(row, 0, id_item)

                _, source_text = self._get_source_text(main_langs, source_lang, current_key=key_id)
                source_item = QTableWidgetItem()
                if source_text.strip() == "":
                    source_item.setText("[No Source Text]")
                    source_item.setForeground(QColor("#7f7f7f"))
                else:
                    source_item.setText(source_text)
                source_item.setFlags(source_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 1, source_item)

                tr_entry = main_langs.get(target_lang, ("", "utf-16le"))
                tr_text = tr_entry[0] if isinstance(tr_entry, tuple) else tr_entry
                tr_item = QTableWidgetItem(tr_text)
                tr_item.setFlags(tr_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 2, tr_item)

            self.table.blockSignals(False)
            self.table.setUpdatesEnabled(True)
            self.filter_timer.start()
        except Exception as e:
            log_error(f"refresh_table fatal: {str(e)}\n{traceback.format_exc()}")

    def on_target_editor_changed(self):
        if self.current_editing_row == -1 or self._bulk_update:
            return
        new_text = self.target_editor.toPlainText()
        row = self.current_editing_row
        id_item = self.table.item(row, 0)
        if not id_item:
            return
        key_id = id_item.data(Qt.ItemDataRole.UserRole)
        target_lang = self.target_lang
        if key_id in self.raw_data:
            group = self.raw_data[key_id]
            main_langs = group[0] if isinstance(group, tuple) else group
            old_entry = main_langs.get(target_lang, ("", "utf-16le"))
            old_text = old_entry[0] if isinstance(old_entry, tuple) else old_entry
            if old_text != new_text:
                self._bulk_update = True
                self._update_translation_data(key_id, target_lang, new_text)
                self.table.blockSignals(True)
                self.table.item(row, 2).setText(new_text)
                self.table.blockSignals(False)
                self._update_modified_status(key_id)
                self.has_changes = True
                self.update_status_stats()
                self._bulk_update = False

    def on_table_row_clicked(self, index):
        row = index.row()
        if self.current_editing_row != -1 and self.current_editing_row != row:
            old_row = self.current_editing_row
            old_id_item = self.table.item(old_row, 0)
            if old_id_item:
                old_key_id = old_id_item.data(Qt.ItemDataRole.UserRole)
                base_group = self.baseline_data.get(old_key_id)
                base_text = ""
                if base_group:
                    base_text = base_group[0].get(self.target_lang, ("", "utf-16le"))[0]
                current_text = self.table.item(old_row, 2).text()
                if base_text != current_text:
                    changes = [(old_key_id, 2, self.target_lang, current_text, "utf-16le")]
                    cmd = BulkEditCommand(self, changes)
                    self.undo_stack.push(cmd)
        self.current_editing_row = row
        id_item = self.table.item(row, 0)
        if not id_item:
            return
        key_id = id_item.data(Qt.ItemDataRole.UserRole)
        group_data = self.raw_data.get(key_id)
        if not group_data or not isinstance(group_data, tuple):
            return
        main_langs = group_data[0]
        source_lang, source_text = self._get_source_text(main_langs, self.source_lang, current_key=key_id)
        self._bulk_update = True
        self.source_editor.setPlainText(source_text)

        tr_entry = main_langs.get(self.target_lang, ("", "utf-16le"))
        tr_text = tr_entry[0] if isinstance(tr_entry, tuple) else tr_entry
        self.target_editor.blockSignals(True)
        self.target_editor.setPlainText(tr_text)
        self.target_editor.blockSignals(False)
        cursor = self.target_editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.target_editor.setTextCursor(cursor)
        self._bulk_update = False
        self.target_editor.setFocus()

    def filter_table(self):
        query = self.search_box.text().lower()
        hide_empty = self.btn_hide_empty.isChecked()
        hide_edited = self.btn_hide_edited.isChecked()
        show_empty = self.btn_show_empty.isChecked()
        show_edited = self.btn_show_edited.isChecked()
        self.table.setUpdatesEnabled(False)
        for row in range(self.table.rowCount()):
            tr_item = self.table.item(row, 2)
            if tr_item is None:
                continue
            text = tr_item.text().strip()
            is_translated = text != ""
            is_edited = False
            id_item = self.table.item(row, 0)
            if id_item:
                key_id = id_item.data(Qt.ItemDataRole.UserRole)
                is_edited = key_id in self.modified_keys
            show = True
            if show_empty:
                show = not is_translated
            elif show_edited:
                show = is_edited
            else:
                if hide_empty and not is_translated:
                    show = False
                if hide_edited and is_edited:
                    show = False
            if show and query:
                found = False
                key_item = self.table.item(row, 0)
                en_item = self.table.item(row, 1)
                if key_item and query in key_item.text().lower():
                    found = True
                if en_item and query in en_item.text().lower():
                    found = True
                if tr_item and query in tr_item.text().lower():
                    found = True
                if not found:
                    show = False
            self.table.setRowHidden(row, not show)
        self.table.setUpdatesEnabled(True)
        visible = 0
        hidden = 0
        for row in range(self.table.rowCount()):
            if self.table.isRowHidden(row):
                hidden += 1
            else:
                visible += 1
        self.visible_status_label.setText(f"Shown: {visible} | Hidden: {hidden}")
        self.update_status_stats()

    def update_status_stats(self):
        if self._bulk_update:
            return
        if not self.flattened_data:
            self.status_label.setText("Ready")
            return
        total = self.table.rowCount()
        translated = 0
        for row in range(total):
            tr_item = self.table.item(row, 2)
            if tr_item and tr_item.text().strip() != "":
                translated += 1
        pct = (translated / total * 100) if total > 0 else 0.0
        status_txt = f"Total keys: {total} | Translated: {translated} ({pct:.1f}%)"
        if self.has_changes:
            status_txt += " * [Unsaved Changes]"
        self.status_label.setText(status_txt)

    def _rebuild_locales_list(self):
        all_langs = set()
        for key, (main_langs, _, _, _) in self.raw_data.items():
            all_langs.update(main_langs.keys())
        self.available_languages = all_langs
        existing = {lang: enc for lang, enc in self.locales_list}
        new_list = []
        for lang in sorted(all_langs):
            new_list.append((lang, existing.get(lang, "utf-16le")))
        self.locales_list = new_list
        self._update_language_menus()

    def save_lcache(self):
        try:
            if not self.current_file_path:
                QMessageBox.critical(self, "Error", "No loaded file")
                return
            target_path, _ = QFileDialog.getSaveFileName(self, "Export .lcache as", os.path.basename(self.current_file_path), "LCache Files (*.lcache);;All Files (*)")
            if not target_path:
                return
            self.status_label.setText("Saving...")
            self.btn_export.setEnabled(False)
            QApplication.processEvents()
            self._rebuild_locales_list()
            encrypted = build_lcache(self.raw_data, self.locales_list)
            temp_fd, temp_path = tempfile.mkstemp(suffix=".lcache", dir=os.path.dirname(target_path))
            try:
                with os.fdopen(temp_fd, "wb") as f:
                    f.write(encrypted)
                if os.path.exists(target_path):
                    bak_path = target_path + ".bak"
                    if os.path.exists(bak_path):
                        os.remove(bak_path)
                    os.rename(target_path, bak_path)
                os.rename(temp_path, target_path)
            except Exception:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                raise
            self.btn_export.setEnabled(True)
            self.has_changes = False
            self.baseline_data = copy.deepcopy(self.raw_data)
            self.modified_keys.clear()
            self.update_status_stats()
            QMessageBox.information(self, "Success", f"File exported successfully:\n{target_path}")
            self.save_settings()
        except Exception as e:
            self.btn_export.setEnabled(True)
            log_error(f"Save File fatal: {str(e)}\n{traceback.format_exc()}")
            QMessageBox.critical(self, "Error", f"Failed to save:\n{str(e)}")

    def export_csv(self):
        if self.raw_data:
            self.flattened_data = [(key, main_langs) for key, (main_langs, _, _, _) in self.raw_data.items()]
        if not self.flattened_data:
            QMessageBox.warning(self, "Export CSV", "No data to export.")
            return
        source_lang = self.source_lang or "english"
        target_lang = self.target_lang or "english"
        
        file_path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "", "CSV Files (*.csv)")
        if not file_path:
            return
        try:
            with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f, delimiter="\t")
                writer.writerow(["Key ID", f"Source ({source_lang})", f"Target ({target_lang})"])
                for key_id, main_langs in self.flattened_data:
                    _, source_text = self._get_source_text(main_langs, source_lang, current_key=key_id)
                    tr_entry = main_langs.get(target_lang, ("", "utf-16le"))
                    tr_text = tr_entry[0] if isinstance(tr_entry, tuple) else tr_entry
                    writer.writerow([key_id, source_text, tr_text])
            QMessageBox.information(self, "Success", f"CSV exported to {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export CSV:\n{str(e)}")

    def import_csv(self):
        if not self.flattened_data:
            QMessageBox.warning(self, "Import CSV", "Load a .lcache file first.")
            return
        target_lang = self.target_lang
        if not target_lang:
            target_lang = "english"
        file_path, _ = QFileDialog.getOpenFileName(self, "Import CSV", "", "CSV Files (*.csv)")
        if not file_path:
            return
        reply = QMessageBox.question(self, "Confirm Import",
                                     f"This will update translations for language '{target_lang}' from CSV.\nThis action cannot be undone.\nContinue?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self._bulk_update = True
            updated = 0
            with open(file_path, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f, delimiter="\t")
                header = next(reader, None)
                if not header or len(header) < 3:
                    QMessageBox.critical(self, "Error", "Invalid CSV format: missing header or columns.")
                    return
                for row in reader:
                    if len(row) < 3:
                        continue
                    key_id = row[0].strip()
                    new_text = row[2].strip()
                    if key_id in self.raw_data:
                        changes = self._update_translation_data(key_id, target_lang, new_text)
                        if changes:
                            cmd = BulkEditCommand(self, changes)
                            self.undo_stack.push(cmd)
                            for k, _, _, _, _ in changes:
                                self._update_table_for_key(k, 2, new_text)
                                self._update_modified_status(k)
                            updated += 1
            self._bulk_update = False
            if updated > 0:
                self.has_changes = True
                self.flattened_data = [(key, main_langs) for key, (main_langs, _, _, _) in self.raw_data.items()]
                self.filter_timer.start()
                self.update_status_stats()
                QMessageBox.information(self, "Success", f"Imported {updated} translations from CSV.")
            else:
                QMessageBox.information(self, "Info", "No matching keys found in CSV.")
            self.save_settings()
        except Exception as e:
            self._bulk_update = False
            log_error(f"Import CSV fatal: {str(e)}\n{traceback.format_exc()}")
            QMessageBox.critical(self, "Error", f"Failed to import CSV:\n{str(e)}")

    def closeEvent(self, event: QCloseEvent):
        if self.load_thread and self.load_thread.isRunning():
            self.load_thread.cancel()
            self.load_thread.quit()
            if not self.load_thread.wait(3000):
                self.load_thread.terminate()
                self.load_thread.wait()
        if self.has_changes:
            ret = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes in memory. Do you want to save them before exiting?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            if ret == QMessageBox.StandardButton.Yes:
                self.save_lcache()
                if self.has_changes:
                    event.ignore()
                    return
                else:
                    self.save_settings()
                    event.accept()
            elif ret == QMessageBox.StandardButton.No:
                self.save_settings()
                event.accept()
            else:
                event.ignore()
                return
        else:
            self.save_settings()
            event.accept()

if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        ex = LCacheEditor()
        ex.show()
        sys.exit(app.exec())
    except Exception as e:
        log_error(f"FATAL Application crash: {str(e)}\n{traceback.format_exc()}")