import sys
from PyQt6.QtWidgets import QApplication

from core.gothic_editor import LCacheEditor

from modules.dialog_context_plugin import DialogContextManager

from modules.editor_patch_2 import apply_table_focus_patch


def main():
    app = QApplication(sys.argv)

    editor = LCacheEditor()
    editor.show()
    
    manager = DialogContextManager(editor)
    manager.activate()

    apply_table_focus_patch(editor)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()