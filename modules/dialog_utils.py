# modules/dialog_utils.py
import os
import re
from .dialog_database import GOTHIC_NPC_DATABASE, GOTHIC_ROLE_SHORTCUTS

def camel_to_snake(name: str) -> str:
    s = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', '_', name)
    return s.lower()

def normalize_class_name(name: str) -> str:
    if not name:
        return ""
    name = re.sub(r'_C$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'_c$', '', name, flags=re.IGNORECASE)
    for suffix in ["_newer", "_new", "_v3", "_v2", "_patch"]:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    return name.lower()

def pretty_name(name: str) -> str:
    if not name:
        return ""
    name = name.replace('_', ' ')
    return name.capitalize()

def get_translated_name(npc_key: str, lang: str) -> str:
    if not npc_key or not lang:
        return None
    key_lower = npc_key.lower().strip()
    entry = GOTHIC_NPC_DATABASE.get(key_lower)
    if entry:
        return entry.get(lang)

    base = key_lower
    for suffix in ["_newer", "_new", "_v3", "_v2", "_patch"]:
        if base.endswith(suffix):
            base = base[:-len(suffix)]
            break
    if base != key_lower:
        entry = GOTHIC_NPC_DATABASE.get(base)
        if entry:
            return entry.get(lang)

    snake_key = camel_to_snake(npc_key)
    if snake_key != key_lower:
        entry = GOTHIC_NPC_DATABASE.get(snake_key)
        if entry:
            return entry.get(lang)

    for db_key, db_entry in GOTHIC_NPC_DATABASE.items():
        if db_key in key_lower or key_lower in db_key:
            return db_entry.get(lang)
    return None

def get_fallback_npc_role(file_name: str, lang: str) -> str:
    if not file_name or not lang:
        return None
    base = os.path.splitext(os.path.basename(file_name))[0]
    for short, role_dict in GOTHIC_ROLE_SHORTCUTS.items():
        if short in base:
            return role_dict.get(lang)
    return None

def extract_npc_from_class(class_name: str) -> str:
    if not class_name:
        return None
    clean = class_name
    for prefix in ["UTopic_", "UChoice_", "Hero_", "CUTSCENE_", "GENERIC_"]:
        if clean.startswith(prefix):
            clean = clean[len(prefix):]
            break
    return clean if clean else None

def extract_npc_from_file(data: dict) -> str:
    if not data:
        return None
    file_name = data.get('file', '')
    if not file_name:
        return None
    base = os.path.splitext(os.path.basename(file_name))[0]
    base = re.sub(r'(_newer|_new|_v3|_v2|_patch)$', '', base)
    return base