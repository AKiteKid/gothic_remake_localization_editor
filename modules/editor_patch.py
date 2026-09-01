# modules/editor_patch.py
import re
import os
import sys
import tempfile
import copy
import traceback

from PyQt6.QtWidgets import (
    QApplication, QTextEdit, QStyledItemDelegate,
    QPushButton, QMessageBox, QWidget, QHBoxLayout,
    QDialog, QLabel, QVBoxLayout, QFrame,
    QFileDialog, QProgressBar
)
from PyQt6.QtGui import QAction, QPainter, QPen, QBrush, QColor, QPixmap, QIcon, QTextCursor
from PyQt6.QtCore import Qt, QRect, pyqtSignal

from . import editor_localization


# Кастомные окна в стиле редактора
class CustomDialogBase(QDialog):
    """Базовый контейнер для кастомных окон. Полностью изолирован от ОС."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.drag_pos = None
        if QApplication.instance():
            self.setStyleSheet(QApplication.instance().styleSheet())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_pos is not None:
            delta = event.globalPosition().toPoint() - self.drag_pos
            self.move(self.pos() + delta)
            self.drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.drag_pos = None


class DarkMessageBox(CustomDialogBase):
    """Кастомное окно сообщений (Yes/No/Cancel/OK) в стиле редактора."""
    def __init__(self, title, text, buttons, parent=None):
        super().__init__(parent)
        self.result_button = QMessageBox.StandardButton.Cancel
        self.init_ui(title, text, buttons)

    def init_ui(self, title, text, buttons):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        main_frame = QFrame(self)
        main_frame.setObjectName("custom_dialog_container")
        frame_layout = QVBoxLayout(main_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)

        title_widget = QWidget()
        title_widget.setObjectName("custom_dialog_title")
        title_layout = QHBoxLayout(title_widget)
        title_layout.setContentsMargins(16, 10, 16, 10)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("custom_dialog_title_text")
        title_layout.addWidget(title_lbl)
        title_layout.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setObjectName("custom_dialog_close_btn")
        close_btn.setFixedSize(18, 18)
        close_btn.clicked.connect(self.reject)
        title_layout.addWidget(close_btn)
        frame_layout.addWidget(title_widget)

        body_widget = QWidget()
        body_widget.setObjectName("custom_dialog_body")
        body_layout = QVBoxLayout(body_widget)
        body_layout.setContentsMargins(24, 24, 24, 24)
        body_layout.setSpacing(20)
        msg_lbl = QLabel(text)
        msg_lbl.setWordWrap(True)
        msg_lbl.setObjectName("custom_dialog_message")
        body_layout.addWidget(msg_lbl)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        btn_layout.addStretch()
        for btn_type in buttons:
            btn_text = "Yes"
            if btn_type == QMessageBox.StandardButton.No:
                btn_text = "No"
            elif btn_type == QMessageBox.StandardButton.Cancel:
                btn_text = "Cancel"
            elif btn_type == QMessageBox.StandardButton.Ok:
                btn_text = "OK"
            btn = QPushButton(btn_text)
            btn.setMinimumWidth(80)
            btn.clicked.connect(lambda checked, b=btn_type: self.on_btn_clicked(b))
            btn_layout.addWidget(btn)
        body_layout.addLayout(btn_layout)
        frame_layout.addWidget(body_widget)

        main_layout.addWidget(main_frame)

    def on_btn_clicked(self, button_type):
        self.result_button = button_type
        if button_type in [QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.Ok]:
            self.accept()
        else:
            self.reject()


class DarkProgressDialog(CustomDialogBase):
    """Кастомное окно прогресса (парсинг, импорт) – полностью без нативной рамки."""
    canceled = pyqtSignal()

    def __init__(self, label_text, cancel_text, min_v, max_v, parent=None):
        CustomDialogBase.__init__(self, parent)
        self.is_cancelled = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Dialog |
            Qt.WindowType.NoDropShadowWindowHint
        )
        self.setFixedSize(400, 160)
        self.init_ui(label_text, cancel_text, min_v, max_v)

    def init_ui(self, label_text, cancel_text, min_v, max_v):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        main_frame = QFrame(self)
        main_frame.setObjectName("custom_dialog_container")
        frame_layout = QVBoxLayout(main_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)

        title_widget = QWidget()
        title_widget.setObjectName("custom_dialog_title")
        title_layout = QHBoxLayout(title_widget)
        title_layout.setContentsMargins(16, 10, 16, 10)
        title_lbl = QLabel("Обработка локализации...")
        title_lbl.setObjectName("custom_dialog_title_text")
        title_layout.addWidget(title_lbl)
        frame_layout.addWidget(title_widget)

        body_widget = QWidget()
        body_widget.setObjectName("custom_dialog_body")
        body_layout = QVBoxLayout(body_widget)
        body_layout.setContentsMargins(24, 24, 24, 24)
        body_layout.setSpacing(14)
        self.label = QLabel(label_text)
        self.label.setObjectName("custom_dialog_message")
        body_layout.addWidget(self.label)

        self.pbar = QProgressBar()
        self.pbar.setRange(min_v, max_v)
        body_layout.addWidget(self.pbar)

        self.cancel_btn = QPushButton(cancel_text)
        self.cancel_btn.clicked.connect(self.on_cancel)
        btn_lay = QHBoxLayout()
        btn_lay.addStretch()
        btn_lay.addWidget(self.cancel_btn)
        body_layout.addLayout(btn_lay)

        frame_layout.addWidget(body_widget)
        main_layout.addWidget(main_frame)

    def setValue(self, v):
        self.pbar.setValue(v)

    def setLabelText(self, t):
        self.label.setText(t)

    def labelText(self):
        return self.label.text()

    def on_cancel(self):
        self.is_cancelled = True
        self.canceled.emit()
        self.reject()


def patch_source_text_logic(editor_instance, main_module=None):
    """
    Динамически накладывает патчи на главный редактор LCacheEditor:
    1–10 – все предыдущие исправления.
    11. Глобальный перехват QMessageBox и кастомные диалоги (исправлено).
    """

    # Патч 1: логика суффиксов языков RE-MAKE (_newer)
    def improved_get_source_text(main_langs, source_lang, current_key=""):
        lang_candidates = [
            source_lang + "_newer", source_lang + "_new", source_lang + "_v3",
            source_lang + "_v2", source_lang + "_patch", source_lang
        ]

        data_pool = getattr(editor_instance, 'raw_data', {})
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

    editor_instance._get_source_text = improved_get_source_text
    print("[Patch] 1. Исправлен поиск суффиксов _newer в LCache")

    # Патч 2: логика замка и иконки
    if hasattr(editor_instance, 'source_editor'):
        se = editor_instance.source_editor

        def dynamic_create_lock_icon(locked):
            pixmap = QPixmap(24, 24)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            color = QColor(210, 210, 210) if getattr(se, '_dark_mode', False) else QColor(50, 50, 50)
            painter.setPen(QPen(color, 2, Qt.PenStyle.SolidLine))
            painter.setBrush(QBrush(color))

            if locked:
                duga_rect = QRect(6, 4, 12, 10)
                painter.drawArc(duga_rect, 0, 180 * 16)
            else:
                duga_rect = QRect(3, 1, 12, 10)
                painter.drawArc(duga_rect, 0, 180 * 16)
                painter.drawLine(15, 6, 15, 11)

            body_rect = QRect(4, 11, 16, 10)
            painter.drawRect(body_rect)

            painter.setBrush(QBrush(Qt.GlobalColor.transparent))
            painter.drawEllipse(QRect(10, 13, 4, 4))
            painter.end()
            return QIcon(pixmap)

        def dynamic_update_icons():
            se.icon_open = dynamic_create_lock_icon(locked=False)
            se.icon_closed = dynamic_create_lock_icon(locked=True)
            if se.lock_button.isChecked():
                se.lock_button.setIcon(se.icon_open)
            else:
                se.lock_button.setIcon(se.icon_closed)

        def dynamic_on_lock_toggled(checked):
            se.text_edit.setReadOnly(not checked)
            if checked:
                se.lock_button.setIcon(se.icon_open)
            else:
                se.lock_button.setIcon(se.icon_closed)

        def dynamic_set_read_only(readonly):
            se.lock_button.blockSignals(True)
            se.lock_button.setChecked(not readonly)
            se.lock_button.blockSignals(False)
            se.text_edit.setReadOnly(readonly)
            se._update_icons()

        se._create_lock_icon = dynamic_create_lock_icon
        se._update_icons = dynamic_update_icons
        se.on_lock_toggled = dynamic_on_lock_toggled
        se.setReadOnly = dynamic_set_read_only

        try:
            se.lock_button.toggled.disconnect()
        except:
            pass
        se.lock_button.toggled.connect(se.on_lock_toggled)

        se.lock_button.setChecked(False)
        se.text_edit.setReadOnly(True)
        se._update_icons()
        print("[Patch] 2. Логика замка исправлена: закрыт по умолчанию для Reference.")

    # Патч 3: безопасный двойной клик и растяжение колонки
    if hasattr(editor_instance, 'table'):
        original_refresh_table = editor_instance.refresh_table

        def patched_refresh_table():
            original_refresh_table()
            editor_instance.table.blockSignals(True)
            for row in range(editor_instance.table.rowCount()):
                item = editor_instance.table.item(row, 2)
                if item:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            editor_instance.table.blockSignals(False)
            if hasattr(editor_instance.table, 'horizontalHeader'):
                editor_instance.table.horizontalHeader().setStretchLastSection(True)

        editor_instance.refresh_table = patched_refresh_table

        def custom_on_cell_double_clicked(row, column):
            if column != 2:
                return
            index = editor_instance.table.model().index(row, column)
            if hasattr(editor_instance, 'on_table_row_clicked'):
                editor_instance.on_table_row_clicked(index)
            item = editor_instance.table.item(row, column)
            if item:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                editor_instance.table.editItem(item)

        try:
            editor_instance.table.cellDoubleClicked.disconnect()
        except:
            pass
        editor_instance.table.cellDoubleClicked.connect(custom_on_cell_double_clicked)

        editor_instance.table.blockSignals(True)
        for row in range(editor_instance.table.rowCount()):
            item = editor_instance.table.item(row, 2)
            if item:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        editor_instance.table.blockSignals(False)
        if hasattr(editor_instance.table, 'horizontalHeader'):
            editor_instance.table.horizontalHeader().setStretchLastSection(True)

        print("[Patch] 3. Синхронизация двойного клика и растяжение Target колонки настроены.")

    # Патч 4: стили (исправление серого фона вкладок в теплом светлом режиме)
    original_apply_styles = editor_instance.apply_styles

    def patched_apply_styles():
        original_apply_styles()
        current_qss = QApplication.instance().styleSheet()

        is_dark = getattr(editor_instance, 'dark_mode', False)
        
        is_warm = False
        if hasattr(editor_instance, 'btn_warm'):
            is_warm = editor_instance.btn_warm.isChecked()
        elif hasattr(editor_instance, 'warm_mode'):
            is_warm = editor_instance.warm_mode

        if is_dark:
            bg = "#232731" if is_warm else "#1e222b"
            t_bg = "#2a2f3a" if is_warm else "#21252b"
            fg = "#e6dbb2" if is_warm else "#d4d4d4"
            grid = "#4b5263" if is_warm else "#3e4451"
            btn = "#3e4452" if is_warm else "#3a3f4d"
            hdr = "#2d3139" if is_warm else "#282c34"
            active_btn = "#564d3b" if is_warm else "#4b6e9c"
        else:
            bg = "#f4ecd8" if is_warm else "#f5f5f5"
            t_bg = "#fdfaf2" if is_warm else "#ffffff"
            fg = "#2b2625" if is_warm else "#000000"
            grid = "#c8b8a0" if is_warm else "#d0d0d0"
            btn = "#e4dcc4" if is_warm else "#e1e1e1"
            hdr = "#e4dcc4" if is_warm else "#e1e1e1"
            active_btn = "#dfcfa5" if is_warm else "#b6d7a8"

        extra_qss = f"""
QTreeView, QListWidget {{
    background-color: {t_bg} !important;
    color: {fg} !important;
    border: 1px solid {grid} !important;
    border-radius: 6px;
}}
QTreeView::item:hover, QListWidget::item:hover {{
    background-color: {btn} !important;
}}
QTreeView::item:selected, QListWidget::item:selected {{
    background-color: {active_btn} !important;
    color: {fg} !important;
}}

/* Фикс серого фона основного контейнера вкладок */
QTabWidget::pane {{
    border: 1px solid {grid} !important;
    background-color: {bg} !important; /* Теперь здесь будет честный бежевый #f4ecd8 */
    border-radius: 6px;
    position: absolute;
    top: -1px;
}}
QTabWidget::tab-bar {{
    left: 4px;
}}

/* Фикс цвета самих кнопок-вкладок */
QTabBar::tab {{
    background-color: {btn} !important;
    color: {fg} !important;
    border: 1px solid {grid} !important;
    border-bottom-color: transparent !important;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 6px 16px;
    margin-right: 2px;
}}

/* Выбранная вкладка сливается с фоном подложки */
QTabBar::tab:selected {{
    background-color: {bg} !important; /* Сама активная вкладка тоже красится в цвет темы */
    border-bottom-color: {bg} !important;
    font-weight: bold !important;
}}
QTabBar::tab:!selected:hover {{
    background-color: {hdr} !important;
}}

/* Фикс фонов внутренних панелей плагина диалогов, чтобы они не были серыми */
QWidget#dialog_tab_widget, QWidget#left_container, QWidget#central_container, QWidget#right_container {{
    background-color: {bg} !important;
}}

QLabel#visible_status_label {{
    font-size: 11px;
    font-weight: 600;
    padding: 2px 4px;
    min-height: 20px;
}}
QFrame#custom_dialog_container {{
    background-color: {bg};
    border: 2px solid {grid};
    border-radius: 10px;
}}
QWidget#custom_dialog_title {{
    background-color: {hdr};
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    border-bottom: 1px solid {grid};
}}
QLabel#custom_dialog_title_text {{
    color: {fg};
    font-weight: 600;
    font-size: 12px;
}}
QPushButton#custom_dialog_close_btn {{
    background: transparent;
    border: none;
    color: {fg};
    font-size: 12px;
    font-weight: bold;
    padding: 0px;
}}
QPushButton#custom_dialog_close_btn:hover {{
    color: #ff5f57;
}}
QWidget#custom_dialog_body {{
    background-color: {bg};
    border-bottom-left-radius: 8px;
    border-bottom-right-radius: 8px;
}}
QLabel#custom_dialog_message {{
    color: {fg};
    font-size: 13px;
}}
QWidget#custom_dialog_body QPushButton {{
    background-color: {btn};
    color: {fg};
    border: 1px solid {grid};
    border-radius: 6px;
    padding: 5px 16px;
}}
QWidget#custom_dialog_body QPushButton:hover {{
    background-color: {active_btn};
}}
QProgressBar {{
    border: 1px solid {grid};
    border-radius: 4px;
    text-align: center;
    background-color: {t_bg};
    color: {fg};
}}
QProgressBar::chunk {{
    background-color: {active_btn};
}}
"""
        QApplication.instance().setStyleSheet(current_qss + extra_qss)

    editor_instance.apply_styles = patched_apply_styles
    editor_instance.apply_styles()
    print("[Patch] 4. Стили вкладок и панелей полностью адаптированы под Теплый свет.")

    # Патч 5: удалён

    # Патч 6: делегат редактирования (destroyEditor + курсор в конец)
    if hasattr(editor_instance, 'table'):
        class TargetEditorDelegate(QStyledItemDelegate):
            def __init__(self, table, parent=None):
                super().__init__(parent)
                self.table = table
                self.original_height = None
                self.editing_row = -1

            def createEditor(self, parent, option, index):
                if index.column() == 2:
                    self.editing_row = index.row()
                    self.original_height = self.table.rowHeight(index.row())
                    self.table.setRowHeight(index.row(), 50)
                    editor = QTextEdit(parent)
                    editor.setMinimumHeight(45)
                    editor.setStyleSheet("padding: 4px;")
                    return editor
                return super().createEditor(parent, option, index)

            def setEditorData(self, editor, index):
                text = index.model().data(index, Qt.ItemDataRole.EditRole)
                editor.setPlainText(text)
                editor.moveCursor(QTextCursor.MoveOperation.End)

            def setModelData(self, editor, model, index):
                model.setData(index, editor.toPlainText(), Qt.ItemDataRole.EditRole)

            def updateEditorGeometry(self, editor, option, index):
                editor.setGeometry(option.rect)

            def closeEditor(self, editor, hint):
                super().closeEditor(editor, hint)

            def destroyEditor(self, editor, index):
                if self.editing_row >= 0 and self.original_height is not None:
                    text = editor.toPlainText()
                    if "\n" in text or len(text) > 50:
                        self.table.setRowHeight(self.editing_row, 50)
                    else:
                        self.table.setRowHeight(self.editing_row, self.original_height)
                    self.original_height = None
                    self.editing_row = -1
                super().destroyEditor(editor, index)

        delegate = TargetEditorDelegate(editor_instance.table)
        editor_instance.table.setItemDelegateForColumn(2, delegate)
        print("[Patch] 6. Делегат редактирования обновлён (destroyEditor, курсор в конец).")

    # Патч 8: исправленное меню языков
    if hasattr(editor_instance, '_build_language_menu'):
        def patched_update_language_menus():
            if not hasattr(editor_instance, 'source_menu') or not editor_instance.source_menu:
                return

            editor_instance.source_menu.clear()
            editor_instance.target_menu.clear()

            base_langs = set()
            for lang in editor_instance.available_languages:
                base = lang
                for suffix in ["_newer", "_new", "_v3", "_v2", "_patch"]:
                    if base.endswith(suffix):
                        base = base[:-len(suffix)]
                        break
                base_langs.add(base)
            langs = sorted(base_langs)

            current_src = str(editor_instance.source_lang).lower().strip()
            current_tgt = str(editor_instance.target_lang).lower().strip()

            for lang in langs:
                act = QAction(lang, editor_instance)
                act.setCheckable(True)
                if lang.lower().strip() == current_src:
                    act.setChecked(True)
                act.triggered.connect(lambda checked, l=lang: editor_instance.set_source_language(l))
                editor_instance.source_menu.addAction(act)

            for lang in langs:
                if lang.lower().strip() == current_src:
                    continue
                act = QAction(lang, editor_instance)
                act.setCheckable(True)
                if lang.lower().strip() == current_tgt:
                    act.setChecked(True)
                act.triggered.connect(lambda checked, l=lang: editor_instance.set_target_language(l))
                editor_instance.target_menu.addAction(act)

            if hasattr(editor_instance, '_dialog_manager') and editor_instance._dialog_manager:
                try:
                    editor_instance._dialog_manager.refresh_npc_list()
                except:
                    pass

        editor_instance._update_language_menus = patched_update_language_menus
        if hasattr(editor_instance, 'language_menu') and editor_instance.language_menu:
            editor_instance._update_language_menus()
        print("[Patch] 8. Меню языков синхронизировано с базовым редактором.")

    # Патч 9: статусная метка
    if hasattr(editor_instance, 'visible_status_label'):
        label = editor_instance.visible_status_label
        label.setMinimumHeight(20)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        label.setStyleSheet("padding: 2px 4px; font-size: 11px; font-weight: 600;")
        print("[Patch] 9. Исправлено отображение статусной метки.")

    # Патч 10: локализация интерфейса (UI Language)
    top_layout = None
    anchor_widget = None
    if hasattr(editor_instance, 'search_box'):
        anchor_widget = editor_instance.search_box
    elif hasattr(editor_instance, 'btn_theme'):
        anchor_widget = editor_instance.btn_theme
    elif hasattr(editor_instance, 'btn_import'):
        anchor_widget = editor_instance.btn_import

    if anchor_widget:
        for layout in editor_instance.findChildren(QHBoxLayout):
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item and item.widget() == anchor_widget:
                    top_layout = layout
                    break
            if top_layout:
                break

    editor_localization.setup_localization(editor_instance, top_layout, anchor_widget)
    print("[Patch] 10. Добавлена локализация интерфейса (кнопка UI Language).")

    # Патч 11: глобальный перехват QMessageBox и кастомные диалоги
    def global_patched_question(parent, title, text, buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, defaultButton=QMessageBox.StandardButton.No):
        editor_instance.apply_styles()
        btn_list = []
        if buttons & QMessageBox.StandardButton.Yes: btn_list.append(QMessageBox.StandardButton.Yes)
        if buttons & QMessageBox.StandardButton.No: btn_list.append(QMessageBox.StandardButton.No)
        if buttons & QMessageBox.StandardButton.Cancel: btn_list.append(QMessageBox.StandardButton.Cancel)
        if buttons & QMessageBox.StandardButton.Ok: btn_list.append(QMessageBox.StandardButton.Ok)
        if not btn_list: btn_list = [QMessageBox.StandardButton.Ok]

        dlg = DarkMessageBox(title, text, btn_list, editor_instance)
        dlg.exec()
        return dlg.result_button

    def global_patched_warning(parent, title, text, buttons=QMessageBox.StandardButton.Ok, defaultButton=QMessageBox.StandardButton.Ok):
        editor_instance.apply_styles()
        dlg = DarkMessageBox(title, text, [QMessageBox.StandardButton.Ok], editor_instance)
        dlg.exec()
        return QMessageBox.StandardButton.Ok

    def global_patched_information(parent, title, text, buttons=QMessageBox.StandardButton.Ok, defaultButton=QMessageBox.StandardButton.Ok):
        editor_instance.apply_styles()
        dlg = DarkMessageBox(title, text, [QMessageBox.StandardButton.Ok], editor_instance)
        dlg.exec()
        return QMessageBox.StandardButton.Ok

    def global_patched_critical(parent, title, text, buttons=QMessageBox.StandardButton.Ok, defaultButton=QMessageBox.StandardButton.Ok):
        editor_instance.apply_styles()
        dlg = DarkMessageBox(title, text, [QMessageBox.StandardButton.Ok], editor_instance)
        dlg.exec()
        return QMessageBox.StandardButton.Ok

    QMessageBox.question = global_patched_question
    QMessageBox.warning = global_patched_warning
    QMessageBox.information = global_patched_information
    QMessageBox.critical = global_patched_critical

    def patched_closeEvent(event):
        if editor_instance.has_changes:
            editor_instance.apply_styles()
            dlg = DarkMessageBox(
                "Несохранённые изменения",
                "У вас есть несохранённые изменения. Хотите сохранить их перед выходом?",
                [QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No, QMessageBox.StandardButton.Cancel],
                editor_instance
            )
            dlg.exec()
            ret = dlg.result_button

            if ret == QMessageBox.StandardButton.Yes:
                editor_instance.save_lcache()
                if not editor_instance.has_changes:
                    event.accept()
                else:
                    event.ignore()
            elif ret == QMessageBox.StandardButton.No:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    editor_instance.closeEvent = patched_closeEvent

    def patched_update_progress(value, message):
        if hasattr(editor_instance, 'progress_dialog') and editor_instance.progress_dialog:
            editor_instance.progress_dialog.pbar.setValue(value)
            editor_instance.progress_dialog.label.setText(message)

    editor_instance.update_progress = patched_update_progress

    # Поиск LoadThread и parse_lcache (с поддержкой динамической загрузки)
    LoadThread = None
    parse_lcache = None

    if main_module is not None:
        LoadThread = getattr(main_module, 'LoadThread', None)
        parse_lcache = getattr(main_module, 'parse_lcache', None)

    if LoadThread is None or parse_lcache is None:
        main_mod = sys.modules.get(editor_instance.__module__)
        if main_mod:
            LoadThread = getattr(main_mod, 'LoadThread', None)
            parse_lcache = getattr(main_mod, 'parse_lcache', None)

    if LoadThread is None or parse_lcache is None:
        for mod in sys.modules.values():
            if hasattr(mod, 'LoadThread') and hasattr(mod, 'parse_lcache'):
                LoadThread = mod.LoadThread
                parse_lcache = mod.parse_lcache
                break

    if LoadThread is not None and parse_lcache is not None:
        def patched_load_lcache():
            if not editor_instance.maybe_save_changes():
                return

            dialog = QFileDialog(editor_instance, "Импорт файла локализации")
            dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
            dialog.setNameFilter("LCache Files (*.lcache);;All Files (*)")
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
            dialog.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)

            if dialog.exec():
                selected_files = dialog.selectedFiles()
                if not selected_files:
                    return
                file_path = selected_files[0]
            else:
                return

            editor_instance.current_file_path = file_path
            editor_instance.status_label.setText("Загрузка...")
            editor_instance.btn_import.setEnabled(False)
            editor_instance.btn_export.setEnabled(False)

            progress = DarkProgressDialog("Загрузка и парсинг файла...", "Отмена", 0, 100, editor_instance)
            progress.canceled.connect(editor_instance.cancel_load)
            progress.show()

            editor_instance.progress_dialog = progress
            editor_instance.load_thread = LoadThread(file_path, parse_lcache)
            editor_instance.load_thread.progress.connect(editor_instance.update_progress)
            editor_instance.load_thread.finished.connect(editor_instance.on_load_finished)
            editor_instance.load_thread.error.connect(editor_instance.on_load_error)
            editor_instance.load_thread.start()

        editor_instance.load_lcache = patched_load_lcache
        print("[Patch] 11. Кастомные диалоги без рамок полностью стабилизированы и адаптированы под потоки.")
    else:
        print("[Patch] 11. Не удалось найти LoadThread/parse_lcache — пропускаем патч загрузки.")

    print("[Patch] Все патчи успешно применены.")