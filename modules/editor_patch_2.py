import re
from PyQt6.QtWidgets import QApplication, QSizePolicy, QPushButton, QMenu, QMessageBox
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt, QObject, QTimer

class TableTabFilter(QObject):
    def __init__(self, table_widget, editor_instance):
        super().__init__(table_widget)
        self.table = table_widget
        self.editor = editor_instance

    def eventFilter(self, obj, event):
        if event.type() == event.Type.KeyPress and event.key() == Qt.Key.Key_Tab:
            current_row = self.table.currentRow()
            current_col = self.table.currentColumn()
            if current_row != -1 and current_row < self.table.rowCount() - 1:
                next_row = current_row + 1
                if hasattr(self.editor, 'target_editor'):
                    self.editor.target_editor.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                self.table.setCurrentCell(next_row, current_col)
                index = self.table.model().index(next_row, current_col)
                if hasattr(self.editor, 'on_table_clicked'):
                    self.editor.on_table_clicked(index)
                elif hasattr(self.editor, 'on_table_row_clicked'):
                    self.editor.on_table_row_clicked(index)
                if hasattr(self.editor, 'target_editor'):
                    self.editor.target_editor.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                self.table.setFocus()
                return True
        return super().eventFilter(obj, event)


def fix_button_sizes_and_restore_lang_btn(editor):
    button_names = [
        'btn_import', 'btn_export', 'btn_choose_lang', 'btn_theme', 'btn_warm',
        'btn_hide_empty', 'btn_hide_edited', 'btn_show_empty', 'btn_show_edited'
    ]
    for name in button_names:
        if hasattr(editor, name):
            btn = getattr(editor, name)
            btn.setFixedWidth(16777215)
            btn.setMaximumWidth(16777215)
            text_width = btn.fontMetrics().horizontalAdvance(btn.text())
            btn.setMinimumWidth(text_width + 28)
            btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            btn.adjustSize()
    if hasattr(editor, 'btn_choose_lang'):
        editor.btn_choose_lang.setVisible(True)


def patch_apply_ui_language(editor):
    try:
        from modules import editor_localization
        original_apply = editor_localization.apply_ui_language
        BUTTON_TRANSLATIONS = {
            "russian": "Выбрать язык",
            "english": "Choose Language",
            "polish": "Wybierz język",
            "german": "Sprache wählen",
            "french": "Choisir la langue",
            "spanish": "Elegir idioma",
        }
        def patched_apply_ui_language(editor_instance, lang_code):
            original_apply(editor_instance, lang_code)
            if hasattr(editor_instance, 'btn_choose_lang'):
                btn = editor_instance.btn_choose_lang
                btn.setVisible(True)
                new_text = BUTTON_TRANSLATIONS.get(lang_code, "Choose Language")
                btn.setText(new_text)
                btn.setFixedWidth(16777215)
                btn.setMaximumWidth(16777215)
                text_width = btn.fontMetrics().horizontalAdvance(btn.text())
                btn.setMinimumWidth(text_width + 28)
                btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
                btn.adjustSize()
            try:
                fix_button_sizes_and_restore_lang_btn(editor_instance)
            except Exception:
                pass
        editor_localization.apply_ui_language = patched_apply_ui_language
        print("[Patch 2] Перехват apply_ui_language выполнен.")
    except ImportError:
        print("[Patch 2] Модуль editor_localization не найден, пропускаем перехват.")
    except Exception as e:
        print(f"[Patch 2] Ошибка при перехвате apply_ui_language: {e}")


def patch_splitter_saving(editor_instance):
    if not hasattr(editor_instance, 'main_vertical_splitter'):
        return
    original_load = editor_instance.load_settings
    original_save = editor_instance.save_settings

    def patched_load_settings():
        original_load()
        settings = editor_instance.settings._settings
        main_sizes = settings.value("main_splitter", [], type=list)
        if main_sizes and len(main_sizes) == 2:
            try:
                main_sizes = [int(x) for x in main_sizes]
                editor_instance.main_vertical_splitter.setSizes(main_sizes)
            except ValueError:
                pass
        if hasattr(editor_instance, 'bottom_splitter') and editor_instance.bottom_splitter:
            bottom_sizes = settings.value("bottom_splitter", [], type=list)
            if bottom_sizes and len(bottom_sizes) == 3:
                try:
                    bottom_sizes = [int(x) for x in bottom_sizes]
                    editor_instance.bottom_splitter.setSizes(bottom_sizes)
                except ValueError:
                    pass

    def patched_save_settings():
        original_save()
        settings = editor_instance.settings._settings
        settings.setValue("main_splitter", editor_instance.main_vertical_splitter.sizes())
        if hasattr(editor_instance, 'bottom_splitter') and editor_instance.bottom_splitter:
            settings.setValue("bottom_splitter", editor_instance.bottom_splitter.sizes())

    editor_instance.load_settings = patched_load_settings
    editor_instance.save_settings = patched_save_settings

    def on_splitter_moved():
        editor_instance.save_settings()
    editor_instance.main_vertical_splitter.splitterMoved.connect(on_splitter_moved)
    if hasattr(editor_instance, 'bottom_splitter') and editor_instance.bottom_splitter:
        editor_instance.bottom_splitter.splitterMoved.connect(on_splitter_moved)


def patch_language_change(editor):
    """Перехватывает методы смены языка и уведомляет плагин."""
    if not hasattr(editor, '_dialog_manager') or not editor._dialog_manager:
        return
    original_set_source = editor.set_source_language
    original_set_target = editor.set_target_language

    def patched_set_source(self, lang):
        original_set_source(lang)
        if hasattr(self, '_dialog_manager') and self._dialog_manager:
            self._dialog_manager.on_language_changed()

    def patched_set_target(self, lang):
        original_set_target(lang)
        if hasattr(self, '_dialog_manager') and self._dialog_manager:
            self._dialog_manager.on_language_changed()

    editor.set_source_language = patched_set_source.__get__(editor, type(editor))
    editor.set_target_language = patched_set_target.__get__(editor, type(editor))
    print("[Patch 2] Перехват смены языка для обновления имён NPC выполнен.")


def apply_table_focus_patch(editor_instance):
    if not hasattr(editor_instance, 'table'):
        print("[Patch 2] Ошибка: В редакторе не найдена таблица 'table'.")
        return

    table = editor_instance.table
    table.setSelectionBehavior(table.SelectionBehavior.SelectItems)
    table.setSelectionMode(table.SelectionMode.SingleSelection)
    table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    if hasattr(table, '_tab_filter_v4'):
        table.removeEventFilter(table._tab_filter_v4)
    table._tab_filter_v4 = TableTabFilter(table, editor_instance)
    table.installEventFilter(table._tab_filter_v4)

    try:
        fix_button_sizes_and_restore_lang_btn(editor_instance)
    except Exception as ex:
        print(f"[Patch 2] Ошибка при фиксе размеров: {ex}")

    patch_apply_ui_language(editor_instance)

    if hasattr(editor_instance, 'apply_styles'):
        original_apply_styles = editor_instance.apply_styles

        def patched_apply_styles():
            original_apply_styles()
            try:
                fix_button_sizes_and_restore_lang_btn(editor_instance)
            except Exception as ex:
                print(f"[Patch 2] Ошибка в apply_styles: {ex}")

            current_qss = QApplication.instance().styleSheet()
            is_dark = getattr(editor_instance, 'dark_mode', False)
            is_warm = getattr(editor_instance, 'warm_mode', False)

            if is_dark:
                t_bg = "#2a2f3a" if is_warm else "#21252b"
                fg = "#e6dbb2" if is_warm else "#d4d4d4"
                active_btn = "#564d3b" if is_warm else "#4b6e9c"
            else:
                t_bg = "#fdfaf2" if is_warm else "#ffffff"
                fg = "#2b2625" if is_warm else "#000000"
                active_btn = "#dfcfa5" if is_warm else "#b6d7a8"

            rgba_select = "rgba(75, 110, 156, 0.15)"
            if isinstance(active_btn, str) and re.match(r'#[0-9a-fA-F]{6}', active_btn):
                r = int(active_btn[1:3], 16)
                g = int(active_btn[3:5], 16)
                b = int(active_btn[5:7], 16)
                rgba_select = f"rgba({r}, {g}, {b}, 0.15)"

            extra_qss = f"""
            QTableWidget QTableWidgetItem, QTableWidget::item {{
                background-color: {t_bg} !important;
                color: {fg} !important;
            }}
            QTableWidget::item:selected,
            QTableWidget::item:selected:!active {{
                background-color: {rgba_select} !important;
                color: {fg} !important;
                border: 2px solid {active_btn} !important;
            }}
            QTableWidget::item:hover {{
                background-color: {rgba_select} !important;
            }}
            """
            QApplication.instance().setStyleSheet(current_qss + extra_qss)

        editor_instance.apply_styles = patched_apply_styles
        editor_instance.apply_styles()

    original_on_row_clicked = getattr(editor_instance, 'on_table_row_clicked', None)
    if original_on_row_clicked and not hasattr(editor_instance, '_patched_row_click'):
        def safe_row_clicked(index):
            if hasattr(editor_instance, 'target_editor'):
                editor_instance.target_editor.blockSignals(True)
            original_on_row_clicked(index)
            table.setFocus()
            if hasattr(editor_instance, 'target_editor'):
                editor_instance.target_editor.blockSignals(False)
        editor_instance.on_table_row_clicked = safe_row_clicked
        editor_instance._patched_row_click = True

    patch_splitter_saving(editor_instance)
    patch_language_change(editor_instance)  # <--- ПЕРЕХВАТ СМЕНЫ ЯЗЫКА

    editor_instance.load_settings()

    QTimer.singleShot(300, lambda: fix_button_sizes_and_restore_lang_btn(editor_instance))

    print("[Patch 2] Патчи применены (Tab, кнопки, сплиттер, смена языка).")