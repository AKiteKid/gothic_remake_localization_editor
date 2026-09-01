# modules/dialog_context_plugin.py
import os
import json
import re
from PyQt6.QtWidgets import (
    QSplitter, QTreeView, QListWidget, QListWidgetItem,
    QFileDialog, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QStyledItemDelegate
)
from PyQt6.QtCore import Qt, QRect, QSize
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QFontMetrics

from .dialog_utils import (
    normalize_class_name,
    pretty_name,
    get_translated_name,
    get_fallback_npc_role,
    extract_npc_from_class,
    extract_npc_from_file
)
from .dialog_database import GOTHIC_NPC_DATABASE, GOTHIC_ROLE_SHORTCUTS

LANG_TOKENS = {
    "russian": {"hero": "Герой", "npc": "НПС"},
    "english": {"hero": "Hero", "npc": "NPC"},
    "polish": {"hero": "Bohater", "npc": "NPC"},
    "german": {"hero": "Held", "npc": "NPC"},
    "french": {"hero": "Héros", "npc": "PNJ"},
    "spanish": {"hero": "Héroe", "npc": "PNJ"},
    "italian": {"hero": "Eroe", "npc": "PNG"},
    "brazilian": {"hero": "Herói", "npc": "NPC"},
    "japanese": {"hero": "ヒーロー", "npc": "NPC"},
    "schinese": {"hero": "英雄", "npc": "NPC"},
}


class TreeItemDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, margin=4):
        super().__init__(parent)
        self.margin = margin

    def sizeHint(self, option, index):
        if not index.isValid():
            return QSize(0, 0)
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        font = option.font
        fm = QFontMetrics(font)
        width = option.rect.width() - 2 * self.margin
        if width <= 0:
            width = 200
        rect = fm.boundingRect(QRect(0, 0, width, 10000),
                               Qt.TextFlag.TextWordWrap, text)
        height = rect.height() + 2 * self.margin
        return QSize(width, max(height, 25))


class DialogContextManager:
    def __init__(self, editor):
        self.editor = editor
        self.string_index = {}
        self.dialog_tree = {}
        self.tree_view = None
        self.npc_list = None
        self.tab_widget = None
        self.dialog_tab_widget = None
        self.active = False
        self._old_table_index = -1
        self.lang_tokens = {"hero": "Герой", "npc": "НПС"}
        self.bottom_splitter = None
        self._original_table_clicked = None

    def update_tokens(self):
        lang = str(self.editor.target_lang).lower().strip()
        self.lang_tokens = LANG_TOKENS.get(lang, LANG_TOKENS["english"])

    def on_language_changed(self):
        """Обновляет имена NPC при смене языка."""
        if not self.active:
            return
        self.update_tokens()
        self._populate_npc_list()
        # Если был выбран NPC, перестроить дерево
        current_item = self.npc_list.currentItem()
        if current_item:
            self.on_npc_selected(current_item)
        else:
            self.tree_view.setModel(None)

    def load_data(self, index_path, tree_path):
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                self.string_index = json.load(f)
            with open(tree_path, 'r', encoding='utf-8') as f:
                self.dialog_tree = json.load(f)
            print(f"[DialogContext] OK: {len(self.string_index)} IDs {len(self.dialog_tree)} classes")
            return True
        except Exception as e:
            print(f"[DialogContext] Error loading JSON: {e}")
            return False

    def find_context(self, string_id):
        clean_id = str(string_id).lower().strip()
        clean_id_no_prefix = clean_id.replace("text_choice_", "")
        if string_id in self.string_index:
            return self.string_index[string_id]
        for k, v in self.string_index.items():
            low_k = str(k).lower()
            if low_k == clean_id or low_k == clean_id_no_prefix:
                return v
        return []

    def get_root_class(self, class_name):
        visited = set()
        current = normalize_class_name(class_name)
        while current and current not in visited:
            visited.add(current)
            parent = None
            for cls, data in self.dialog_tree.items():
                normalized_children = [normalize_class_name(c) for c in data.get('children', [])]
                if current in normalized_children:
                    parent = normalize_class_name(cls)
                    break
            if parent is None:
                break
            if "UTopic" in parent or "Hero" in parent:
                return parent
            current = parent
        return current

    def _get_text_from_lcache(self, string_id):
        if not string_id or not hasattr(self.editor, 'raw_data') or not self.editor.raw_data:
            return ""

        raw_data = self.editor.raw_data
        target = str(self.editor.target_lang).lower().strip()

        def extract_from_group(group):
            if not group:
                return ""
            if isinstance(group, (tuple, list)) and len(group) > 0:
                main_langs = group[0]
            else:
                main_langs = group
            if not isinstance(main_langs, dict):
                return ""

            for lang_name, tr_entry in main_langs.items():
                lang_lower = str(lang_name).lower().strip()
                if lang_lower == target or lang_lower.startswith(target):
                    if isinstance(tr_entry, (tuple, list)) and len(tr_entry) > 0:
                        return str(tr_entry[0])
                    return str(tr_entry)
            return ""

        clean_key = str(string_id).strip()
        group = raw_data.get(clean_key)
        if group:
            text = extract_from_group(group)
            if text:
                return text

        if clean_key.startswith("text_choice_"):
            alt_key = clean_key[len("text_choice_"):]
            group = raw_data.get(alt_key)
            if group:
                text = extract_from_group(group)
                if text:
                    return text

        low_key = clean_key.lower()
        group = raw_data.get(low_key)
        if group:
            text = extract_from_group(group)
            if text:
                return text

        for k, g in raw_data.items():
            if str(k).lower() == low_key or clean_key in str(k):
                text = extract_from_group(g)
                if text:
                    return text

        return "[текст не найден]"

    def _resolve_npc_display_name(self, class_key, data):
        # Используем оригинальное имя класса для правильного CamelCase -> snake_case
        npc_key = extract_npc_from_class(class_key)
        current_lang = str(self.editor.target_lang).lower().strip()

        if npc_key:
            name = get_translated_name(npc_key, current_lang)
            if name:
                return name

        file_name = data.get('file', '')
        if file_name:
            npc_key_file = extract_npc_from_file(data)
            if npc_key_file:
                name = get_translated_name(npc_key_file, current_lang)
                if name:
                    return name

        role = get_fallback_npc_role(file_name, current_lang)
        if role:
            return role

        caption_id = data.get('caption')
        caption_text = self._get_text_from_lcache(caption_id) if caption_id else ""
        if caption_text and caption_text != "[Forced Conversation]":
            return caption_text

        norm = normalize_class_name(class_key)
        clean = norm.replace("UTopic_", "").replace("UChoice", "").replace("Hero_", "")
        return pretty_name(clean) or "NPC"

    def get_speaker_name(self, actor, class_name, data, npc_fallback=None):
        actor_str = str(actor).strip()
        current_lang = str(self.editor.target_lang).lower().strip()

        if "Hero" in actor_str:
            return self.lang_tokens["hero"]

        pure_name = actor_str.replace("Get", "").replace("(", "").replace(")", "").strip()
        pure_name = re.sub(r'\d+', '', pure_name)
        if pure_name.lower() != "npc" and pure_name:
            name = get_translated_name(pure_name, current_lang)
            if name:
                return name

        if pure_name.lower() == "npc" and npc_fallback:
            return npc_fallback

        file_name = data.get('file', '')
        fallback_role = get_fallback_npc_role(file_name, current_lang)
        if fallback_role:
            return fallback_role

        npc_key = extract_npc_from_class(class_name)
        if npc_key:
            name = get_translated_name(npc_key, current_lang)
            if name:
                return name

        npc_key_file = extract_npc_from_file(data)
        if npc_key_file:
            name = get_translated_name(npc_key_file, current_lang)
            if name:
                return name

        if npc_fallback:
            return npc_fallback

        return self.lang_tokens["npc"]

    def build_tree_model(self, root_class):
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(["Структура диалога"])
        global_visited = set()

        def add_node(cls_name, parent_item):
            norm_name = normalize_class_name(cls_name)
            if norm_name in global_visited:
                return
            global_visited.add(norm_name)

            target_key = None
            for key in self.dialog_tree.keys():
                if normalize_class_name(key) == norm_name:
                    target_key = key
                    break

            if target_key is None:
                tr_text = self._get_text_from_lcache(cls_name)
                display_text = f'Выбор: "{tr_text}"' if tr_text else f"Выбор: {norm_name}"
                item = QStandardItem(display_text)
                item.setData(cls_name, Qt.ItemDataRole.UserRole)
                parent_item.appendRow(item)
                return

            data = self.dialog_tree[target_key]
            npc_fallback = self._resolve_npc_display_name(target_key, data)

            caption_id = data.get('caption')
            tr_text = self._get_text_from_lcache(caption_id) if caption_id else ""

            if not tr_text or tr_text == "[Forced Conversation]":
                replies = data.get('replies', [])
                if replies and len(replies) > 0:
                    first_reply = replies[0]
                    reply_id = first_reply[1] if isinstance(first_reply, list) else first_reply
                    first_text = self._get_text_from_lcache(reply_id)
                    if first_text and first_text != "[текст не найден]":
                        short_txt = first_text[:45] + "..." if len(first_text) > 45 else first_text
                        tr_text = f"💬 {short_txt}"

            if tr_text:
                display_text = tr_text if tr_text.startswith("💬") else f'Выбор: "{tr_text}"'
            elif npc_fallback and npc_fallback != "NPC":
                display_text = npc_fallback
            elif "UTopic_" in norm_name:
                display_text = f"🗣️ {norm_name.replace('UTopic_', '')}"
            else:
                clean_name = norm_name.replace("UChoice", "").replace("UTopic", "").replace("Hero_", "")
                pretty = pretty_name(clean_name)
                display_text = f"📂 Ветка: {pretty}" if pretty else "📂 Ветка"

            class_item = QStandardItem(display_text)
            class_item.setData(target_key, Qt.ItemDataRole.UserRole)
            parent_item.appendRow(class_item)

            for entry in data.get('replies', []):
                actor, reply_id = entry if isinstance(entry, list) else ("NPC", entry)
                rep_text = self._get_text_from_lcache(reply_id) or "[текст не найден]"
                speaker = self.get_speaker_name(actor, target_key, data, npc_fallback)

                reply_item = QStandardItem(f"└─ [{speaker}]: {rep_text}")
                reply_item.setData(reply_id, Qt.ItemDataRole.UserRole)
                reply_item.setFlags(reply_item.flags() | Qt.ItemFlag.ItemIsEditable)
                class_item.appendRow(reply_item)

            for child in data.get('children', []):
                add_node(child, class_item)

        if root_class:
            add_node(root_class, model.invisibleRootItem())

        model.dataChanged.connect(self.on_tree_data_changed)
        return model

    def on_tree_data_changed(self, topLeft, bottomRight, roles):
        if Qt.ItemDataRole.EditRole not in roles and Qt.ItemDataRole.DisplayRole not in roles:
            return

        item = self.tree_view.model().itemFromIndex(topLeft)
        if not item:
            return

        string_id = item.data(Qt.ItemDataRole.UserRole)
        if not string_id:
            return

        new_raw_text = item.text()
        clean_text = new_raw_text
        if "]: " in new_raw_text:
            clean_text = new_raw_text.split("]: ", 1)[1]
        elif 'Выбор: "' in new_raw_text and new_raw_text.endswith('"'):
            clean_text = new_raw_text.split('Выбор: "', 1)[1][:-1]

        target_lang = str(self.editor.target_lang).lower().strip()
        target_id = str(string_id).lower().strip()

        self.editor.table.blockSignals(True)
        for row in range(self.editor.table.rowCount()):
            t_item = self.editor.table.item(row, 0)
            if t_item and t_item.text().lower().strip() == target_id:
                translation_cell = self.editor.table.item(row, 2)
                if translation_cell:
                    translation_cell.setText(clean_text)
                break
        self.editor.table.blockSignals(False)

        if hasattr(self.editor, 'raw_data') and self.editor.raw_data:
            raw_keys = list(self.editor.raw_data.keys())
            found_key = None
            if string_id in self.editor.raw_data:
                found_key = string_id
            elif target_id in raw_keys:
                found_key = target_id
            else:
                base_key = target_id
                for suffix in ["_newer", "_new", "_v3", "_v2", "_patch"]:
                    candidate = base_key + suffix
                    if candidate in raw_keys:
                        found_key = candidate
                        break
                if not found_key:
                    for k in raw_keys:
                        if k.lower().startswith(base_key):
                            found_key = k
                            break

            if found_key:
                group = self.editor.raw_data[found_key]
                if isinstance(group, (tuple, list)) and len(group) > 0:
                    main_langs = group[0]
                else:
                    main_langs = group

                if isinstance(main_langs, dict):
                    if target_lang in main_langs:
                        entry = main_langs[target_lang]
                        if isinstance(entry, (tuple, list)) and len(entry) > 0:
                            main_langs[target_lang] = (clean_text, entry[1] if len(entry) > 1 else "utf-16le")
                        else:
                            main_langs[target_lang] = clean_text
                    else:
                        main_langs[target_lang] = (clean_text, "utf-16le")

                    if isinstance(group, (tuple, list)):
                        new_group = (main_langs, group[1], group[2], group[3]) if len(group) > 3 else (main_langs,)
                        self.editor.raw_data[found_key] = new_group
                    else:
                        self.editor.raw_data[found_key] = main_langs

                    self.editor.has_changes = True
                    self.editor.modified_keys.add(found_key)
                    self.editor.update_status_stats()

                    self.tree_view.model().blockSignals(True)
                    if "]: " in new_raw_text:
                        prefix = new_raw_text.split("]: ", 1)[0] + "]: "
                        item.setText(f"{prefix}{clean_text}")
                    self.tree_view.model().blockSignals(False)
                    return

    def get_root_topics(self):
        roots = []
        all_classes = set(self.dialog_tree.keys())
        children_set = set()
        for data in self.dialog_tree.values():
            for child in data.get('children', []):
                children_set.add(child)

        root_keys = [k for k in all_classes if k not in children_set]
        filtered = []
        for k in root_keys:
            k_low = k.lower()

            # Фильтр мусора
            if "document::" in k_low or "udocument" in k_low:
                continue
            if "genericvoiceline" in k_low or "ugvl" in k_low:
                continue
            if "aboutcamp" in k_low or "ambient" in k_low:
                continue
            if "uconversationcharactersettings" in k_low or "questdealer" in k_low:
                continue

            if "utopic_" in k_low or "hero_" in k_low or "cutscene_" in k_low or "uconversation" in k_low:
                filtered.append(k)
            elif self.dialog_tree.get(k, {}).get('replies'):
                filtered.append(k)

        for key in filtered:
            data = self.dialog_tree.get(key, {})
            display_name = self._resolve_npc_display_name(key, data)

            display_lower = display_name.lower()
            if "uconversationcharactersettings" in display_lower or "cutscene" in display_lower:
                match = re.search(r'cutscene\s*([\w\d_]+)', display_lower, re.IGNORECASE)
                if match:
                    scene_id = match.group(1).upper()
                    display_name = f"🎬 Сюжетная сцена: {scene_id}"
                else:
                    display_name = display_name.replace("UConversationCharacterSettings", "🎬 Сцена:")
                    display_name = display_name.replace("g1r", "").strip()
                    display_name = display_name.replace("  ", " ")
                    if not display_name.strip() or display_name == "🎬 Сцена:":
                        display_name = "🎬 Сюжетная сцена"

            elif "g1r::" in display_lower and "cutscene" not in display_lower:
                continue

            if not display_name.strip() or len(display_name.strip()) < 2:
                continue

            roots.append((key, display_name))

        roots.sort(key=lambda x: str(x[1]).lower())
        return roots

    def _populate_npc_list(self):
        self.npc_list.clear()
        roots = self.get_root_topics()
        for key, name in roots:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.npc_list.addItem(item)

    def on_npc_selected(self, item):
        if not item:
            return
        root_key = item.data(Qt.ItemDataRole.UserRole)
        if not root_key:
            return
        model = self.build_tree_model(root_key)
        self.tree_view.setModel(model)
        self.tree_view.expandAll()

    def on_table_clicked(self, index):
        if hasattr(self.editor, 'on_table_row_clicked'):
            self.editor.on_table_row_clicked(index)

        if not self.active or not self.editor.raw_data:
            return
        row = index.row()
        id_item = self.editor.table.item(row, 0)
        if not id_item:
            return
        string_id = id_item.text()
        contexts = self.find_context(string_id)
        if not contexts:
            self.tree_view.setModel(None)
            return

        dialog_class = None
        for ctx in contexts:
            if isinstance(ctx, dict) and ctx.get('class'):
                dialog_class = ctx.get('class')
                break
        if not dialog_class:
            return

        root = self.get_root_class(dialog_class)
        for i in range(self.npc_list.count()):
            item = self.npc_list.item(i)
            if normalize_class_name(item.data(Qt.ItemDataRole.UserRole)) == normalize_class_name(root):
                self.npc_list.setCurrentRow(i)
                self.on_npc_selected(item)
                break
        else:
            model = self.build_tree_model(root)
            self.tree_view.setModel(model)
            self.tree_view.expandAll()

    def on_tree_single_clicked(self, index):
        if not self.active:
            return
        item = self.tree_view.model().itemFromIndex(index)
        if not item:
            return
        reply_id = item.data(Qt.ItemDataRole.UserRole)
        if not reply_id:
            return
        target_id = str(reply_id).lower().strip()
        for row in range(self.editor.table.rowCount()):
            t_item = self.editor.table.item(row, 0)
            if t_item and t_item.text().lower().strip() == target_id:
                self.editor.table.setCurrentCell(row, 2)
                break

    def _update_bottom_panel_visibility(self, index):
        if not self.bottom_splitter:
            return
        tab_text = self.tab_widget.tabText(index)
        if "Дерево" in tab_text or "диалог" in tab_text.lower() or "Dialog" in tab_text:
            self.bottom_splitter.hide()
        else:
            self.bottom_splitter.show()

    def activate(self, index_path=None, tree_path=None):
        if self.active:
            return

        try:
            from .editor_patch import patch_source_text_logic
            patch_source_text_logic(self.editor)
        except Exception as e:
            pass

        if index_path is None or tree_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(base_dir)
            index_path = os.path.join(parent_dir, "json", "string_index.json")
            tree_path = os.path.join(parent_dir, "json", "dialog_tree.json")

        if not os.path.exists(index_path) or not os.path.exists(tree_path):
            index_path, _ = QFileDialog.getOpenFileName(
                self.editor, "Выберите string_index.json", "", "JSON (*.json)"
            )
            tree_path, _ = QFileDialog.getOpenFileName(
                self.editor, "Выберите dialog_tree.json", "", "JSON (*.json)"
            )
            if not index_path or not tree_path:
                return

        if not self.load_data(index_path, tree_path):
            return

        self.update_tokens()

        self._old_table_index = self.editor.main_vertical_splitter.indexOf(self.editor.table)

        self.tab_widget = QTabWidget()
        self.editor.table.setParent(None)
        self.tab_widget.addTab(self.editor.table, "📋 Таблица строк")

        self.dialog_tab_widget = QWidget()
        dialog_layout = QVBoxLayout(self.dialog_tab_widget)
        dialog_layout.setContentsMargins(2, 2, 2, 2)

        h_splitter = QSplitter(Qt.Orientation.Horizontal)
        h_splitter.setChildrenCollapsible(False)

        self.npc_list = QListWidget()
        self.npc_list.setMinimumWidth(150)
        self.npc_list.setMaximumWidth(350)
        self.npc_list.itemClicked.connect(self.on_npc_selected)
        h_splitter.addWidget(self.npc_list)

        self.tree_view = QTreeView()
        self.tree_view.setWordWrap(True)
        self.tree_view.setItemDelegate(TreeItemDelegate(self.tree_view, margin=4))

        h_splitter.addWidget(self.tree_view)
        h_splitter.setSizes([220, 580])

        dialog_layout.addWidget(h_splitter)
        self.tab_widget.addTab(self.dialog_tab_widget, "🗣️ Дерево диалогов")

        self.editor.main_vertical_splitter.insertWidget(self._old_table_index, self.tab_widget)

        if self.editor.main_vertical_splitter.count() > 1:
            self.bottom_splitter = self.editor.main_vertical_splitter.widget(1)
        else:
            self.bottom_splitter = None

        self.tab_widget.currentChanged.connect(self._update_bottom_panel_visibility)
        self._update_bottom_panel_visibility(self.tab_widget.currentIndex())

        self.editor._dialog_manager = self

        self._populate_npc_list()

        self.tree_view.clicked.connect(self.on_tree_single_clicked)

        try:
            self.editor.table.clicked.disconnect()
        except:
            pass
        self.editor.table.clicked.connect(self.on_table_clicked)

        self.active = True
        self.editor.status_label.setText("")

        if self.npc_list.count() > 0:
            self.npc_list.setCurrentRow(0)
            self.on_npc_selected(self.npc_list.item(0))

        if self.editor.table.currentRow() >= 0:
            self.on_table_clicked(self.editor.table.currentIndex())

    def deactivate(self):
        if not self.active or not hasattr(self, 'tab_widget'):
            return

        if self.bottom_splitter:
            self.bottom_splitter.show()
            self.bottom_splitter = None

        try:
            self.tab_widget.currentChanged.disconnect(self._update_bottom_panel_visibility)
        except:
            pass

        try:
            self.editor.table.clicked.disconnect()
        except:
            pass

        self.editor.table.setParent(None)
        index = self.editor.main_vertical_splitter.indexOf(self.tab_widget)
        if index != -1:
            self.editor.main_vertical_splitter.widget(index).setParent(None)
        self.tab_widget.deleteLater()

        self.editor.main_vertical_splitter.insertWidget(self._old_table_index, self.editor.table)

        self.tree_view = None
        self.npc_list = None
        self.dialog_tab_widget = None
        self.tab_widget = None
        self.active = False
        self.editor.status_label.setText("Контекст диалогов отключён")