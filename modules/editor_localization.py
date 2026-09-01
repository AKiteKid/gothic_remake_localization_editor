# modules/editor_localization.py
from PyQt6.QtWidgets import QMenu, QPushButton, QSizePolicy
from PyQt6.QtGui import QAction
from PyQt6.QtCore import QSettings, QTimer

UI_TRANSLATIONS = {
    "russian": {
        "import": "Импорт",
        "export": "Экспорт",
        "choose_lang": "Язык UI",
        "theme": "Темная тема",
        "warm": "Теплый свет",
        "search_placeholder": "Поиск по ключу или тексту...",
        "hide_empty": "Скрыть пустые строки",
        "hide_edited": "Скрыть измененные",
        "show_empty": "Только пустые строки",
        "show_edited": "Только измененные",
        "tab_table": "📋 Таблица строк",
        "tab_tree": "🗣️ Дерево диалогов",
        "tree_header": "Структура диалога",
        "ui_lang_btn": "A / 文",
        "status_plugin_ready": "Подключено: дерево диалогов активно",
        "status_plugin_off": "Контекст диалогов отключен",
        "placeholder_ref": "Оригинал (Reference)",
        "placeholder_target": "Перевод (Target)...",
    },
    "english": {
        "import": "Import",
        "export": "Export",
        "choose_lang": "UI Language",
        "theme": "Dark Theme",
        "warm": "Warm Mode",
        "search_placeholder": "Search key or text...",
        "hide_empty": "Hide Empty Rows",
        "hide_edited": "Hide Edited",
        "show_empty": "Empty Rows Only",
        "show_edited": "Edited Only",
        "tab_table": "📋 String Table",
        "tab_tree": "🗣️ Dialogue Tree",
        "tree_header": "Dialogue Structure",
        "ui_lang_btn": "A / 文",
        "status_plugin_ready": "Dialogue context plugin active",
        "status_plugin_off": "Dialogue context disabled",
        "placeholder_ref": "Reference text",
        "placeholder_target": "Translation editor...",
    },
    "polish": {
        "import": "Importuj",
        "export": "Eksportuj",
        "choose_lang": "Język UI",
        "theme": "Ciemny motyw",
        "warm": "Ciepłe barwy",
        "search_placeholder": "Szukaj klucza lub tekstu...",
        "hide_empty": "Ukryj puste wiersze",
        "hide_edited": "Ukryj zmodyfikowane",
        "show_empty": "Tylko puste wiersze",
        "show_edited": "Tylko zmodyfikowane",
        "tab_table": "📋 Tabela ciągów",
        "tab_tree": "🗣️ Drzewo dialogów",
        "tree_header": "Struktura dialogu",
        "ui_lang_btn": "A / 文",
        "status_plugin_ready": "Kontekst dialogów aktywny",
        "status_plugin_off": "Kontekst dialogów wyłączony",
        "placeholder_ref": "Tekst źródłowy (Reference)",
        "placeholder_target": "Miejsce na tłumaczenie...",
    },
    "german": {
        "import": "Importieren",
        "export": "Exportieren",
        "choose_lang": "UI-Sprache",
        "theme": "Dunkles Design",
        "warm": "Warmlicht",
        "search_placeholder": "Schlüssel oder Text suchen...",
        "hide_empty": "Leere Zeilen ausblenden",
        "hide_edited": "Geänderte ausblenden",
        "show_empty": "Nur leere Zeilen",
        "show_edited": "Nur Geänderte",
        "tab_table": "📋 Zeichenfolgentabelle",
        "tab_tree": "🗣️ Dialogbaum",
        "tree_header": "Dialogstruktur",
        "ui_lang_btn": "A / 文",
        "status_plugin_ready": "Dialogkontext aktiv",
        "status_plugin_off": "Dialogkontext deaktiviert",
        "placeholder_ref": "Referenztext (Original)",
        "placeholder_target": "Übersetzung bearbeiten...",
    },
    "french": {
        "import": "Importer",
        "export": "Exporter",
        "choose_lang": "Langue",
        "theme": "Thème sombre",
        "warm": "Mode chaud",
        "search_placeholder": "Rechercher...",
        "hide_empty": "Masquer lignes vides",
        "hide_edited": "Masquer modifiés",
        "show_empty": "Uniquement lignes vides",
        "show_edited": "Uniquement modifiés",
        "tab_table": "📋 Table des chaînes",
        "tab_tree": "🗣️ Arbre de dialogue",
        "tree_header": "Structure du dialogue",
        "ui_lang_btn": "A / 文",
        "status_plugin_ready": "Contexte de dialogue actif",
        "status_plugin_off": "Contexte de dialogue désactivé",
        "placeholder_ref": "Texte de référence",
        "placeholder_target": "Saisir la traduction...",
    },
    "spanish": {
        "import": "Importar",
        "export": "Exportar",
        "choose_lang": "Idioma",
        "theme": "Tema oscuro",
        "warm": "Modo cálido",
        "search_placeholder": "Buscar clave o texto...",
        "hide_empty": "Ocultar filas vacías",
        "hide_edited": "Ocultar editados",
        "show_empty": "Solo filas vacías",
        "show_edited": "Solo editados",
        "tab_table": "📋 Tabla de cadenas",
        "tab_tree": "🗣️ Árbol de diálogo",
        "tree_header": "Estructura del diálogo",
        "ui_lang_btn": "A / 文",
        "status_plugin_ready": "Contexto de diálogo activo",
        "status_plugin_off": "Contexto de diálogo desactivado",
        "placeholder_ref": "Texto de referencia",
        "placeholder_target": "Editar traducción...",
    },
}

def apply_ui_language(editor, lang_code):
    lang_code = str(lang_code).lower().strip()
    trans = UI_TRANSLATIONS.get(lang_code, UI_TRANSLATIONS["english"])

    if hasattr(editor, 'btn_import'):
        editor.btn_import.setText(trans["import"])
    if hasattr(editor, 'btn_export'):
        editor.btn_export.setText(trans["export"])
    if hasattr(editor, 'btn_theme'):
        editor.btn_theme.setText(trans["theme"])
    if hasattr(editor, 'btn_warm'):
        editor.btn_warm.setText(trans["warm"])
    if hasattr(editor, 'search_box'):
        editor.search_box.setPlaceholderText(trans["search_placeholder"])
    if hasattr(editor, 'btn_hide_empty'):
        editor.btn_hide_empty.setText(trans["hide_empty"])
    if hasattr(editor, 'btn_hide_edited'):
        editor.btn_hide_edited.setText(trans["hide_edited"])
    if hasattr(editor, 'btn_show_empty'):
        editor.btn_show_empty.setText(trans["show_empty"])
    if hasattr(editor, 'btn_show_edited'):
        editor.btn_show_edited.setText(trans["show_edited"])

    if hasattr(editor, 'btn_choose_lang'):
        editor.btn_choose_lang.setVisible(False)

    if hasattr(editor, 'source_editor') and hasattr(editor.source_editor, 'text_edit'):
        editor.source_editor.text_edit.setPlaceholderText(trans["placeholder_ref"])
    if hasattr(editor, 'target_editor'):
        editor.target_editor.setPlaceholderText(trans["placeholder_target"])

    if hasattr(editor, 'status_label'):
        if hasattr(editor, '_dialog_manager') and editor._dialog_manager and editor._dialog_manager.active:
            editor.status_label.setText(trans["status_plugin_ready"])
        else:
            editor.status_label.setText(trans["status_plugin_off"])
        editor.status_label.setMinimumWidth(300)
        editor.status_label.adjustSize()

    if hasattr(editor, 'visible_status_label'):
        editor.visible_status_label.setMinimumWidth(250)
        editor.visible_status_label.setMaximumWidth(16777215)
        editor.visible_status_label.adjustSize()

    if hasattr(editor, '_dialog_manager') and editor._dialog_manager and editor._dialog_manager.active:
        mgr = editor._dialog_manager
        if mgr.tab_widget:
            mgr.tab_widget.blockSignals(True)
            mgr.tab_widget.setTabText(0, trans["tab_table"])
            mgr.tab_widget.setTabText(1, trans["tab_tree"])
            mgr.tab_widget.blockSignals(False)
        if mgr.tree_view and mgr.tree_view.model():
            mgr.tree_view.model().blockSignals(True)
            mgr.tree_view.model().setHorizontalHeaderLabels([trans["tree_header"]])
            mgr.tree_view.model().blockSignals(False)
        mgr.update_tokens()

    if hasattr(editor, '_ui_lang_btn'):
        editor._ui_lang_btn.setText("A / 文")
        editor._ui_lang_btn.setMinimumWidth(60)

    all_buttons = [
        'btn_hide_empty', 'btn_hide_edited', 'btn_show_empty', 'btn_show_edited',
        'btn_theme', 'btn_warm'
    ]
    for btn_name in all_buttons:
        if hasattr(editor, btn_name):
            btn = getattr(editor, btn_name)
            btn.setFixedWidth(16777215)
            btn.setMaximumWidth(16777215)
            text_width = btn.fontMetrics().horizontalAdvance(btn.text())
            btn.setMinimumWidth(text_width + 28)
            btn.adjustSize()

    def fix_button_sizes():
        for btn_name in all_buttons:
            if hasattr(editor, btn_name):
                btn = getattr(editor, btn_name)
                btn.setFixedWidth(16777215)
                btn.setMaximumWidth(16777215)
                text_width = btn.fontMetrics().horizontalAdvance(btn.text())
                btn.setMinimumWidth(text_width + 28)
                btn.adjustSize()
                btn.updateGeometry()
    QTimer.singleShot(200, fix_button_sizes)

    if hasattr(editor, 'update_status_stats'):
        try:
            editor.update_status_stats()
        except:
            pass

    settings = QSettings("GothicModding", "LCacheEditor")
    settings.setValue("ui_language", lang_code)

def setup_localization(editor, top_layout, anchor_widget):
    if top_layout is None or anchor_widget is None:
        return

    ui_lang_btn = QPushButton("A / 文", editor)
    ui_lang_btn.setMinimumWidth(110)
    ui_lang_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
    ui_menu = QMenu(editor)

    supported_ui_langs = [
        ("🇷🇺 Русский", "russian"),
        ("🇺🇸 English", "english"),
        ("🇵🇱 Polski", "polish"),
        ("🇩🇪 Deutsch", "german"),
        ("🇫🇷 Français", "french"),
        ("🇪🇸 Español", "spanish"),
    ]

    for display_name, internal_code in supported_ui_langs:
        action = QAction(display_name, editor)
        action.triggered.connect(
            lambda checked, code=internal_code: apply_ui_language(editor, code)
        )
        ui_menu.addAction(action)

    ui_lang_btn.setMenu(ui_menu)
    ui_lang_btn.setObjectName("ui_lang_btn")

    anchor_index = -1
    for i in range(top_layout.count()):
        item = top_layout.itemAt(i)
        if item and item.widget() == anchor_widget:
            anchor_index = i
            break

    if anchor_index != -1:
        top_layout.insertWidget(anchor_index, ui_lang_btn)
    else:
        top_layout.addWidget(ui_lang_btn)

    editor._ui_lang_btn = ui_lang_btn

    settings = QSettings("GothicModding", "LCacheEditor")
    saved_lang = settings.value("ui_language", "english")
    apply_ui_language(editor, saved_lang)