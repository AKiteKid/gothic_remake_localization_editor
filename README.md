<details>
  summary><h2>📸Screenshots</h2></summary>
<img width="1774" height="956" alt="image_2026-09-01_10-47-34" src="https://github.com/user-attachments/assets/9c5fd1e6-a475-4017-8c97-0ae629b3cc98" />
<img width="1906" height="1023" alt="image" src="https://github.com/user-attachments/assets/54b15227-f983-4421-a26c-b6e6d452fa05" />
<img width="1912" height="1033" alt="image" src="https://github.com/user-attachments/assets/b8c25fd5-0421-4271-9db1-af8afd4788a5" />
</details>

## Gothic 1 Remake .lcache Localization Editor

An editor for .lcache localization files in Gothic 1 Remake.

This tool works directly with the file in RAM, processing the internal structure of the format, including AES encryption, dialogue trees, and duplicate key synchronization.

## Running from Source

If you prefer to run the editor directly from Python source:

### 1. Install or Update Python

This editor requires **Python 3.9 or newer** (current recommended: 3.12+). Older versions (3.8 or below) will cause crashes.

- **Windows:** Download from [python.org](https://python.org). During installation, check "Add Python to PATH".
- **macOS:** Run the `.pkg` installer. Use the `python3` command in terminal.
- **Linux:**
    
    sudo apt update && sudo apt install python3 python3-pip

Verify the installation:

    python --version   # or python3 --version

Should print `Python 3.9.x` or higher.

### 2. Open Terminal in the Project Folder

Make sure you are in the root project folder — the one that contains `main.py`.

- **Windows (fastest):** Open the folder, click the address bar, type `cmd`, press Enter.
- **Windows (alternative):** Shift + Right-click inside the folder → "Open PowerShell window here".
- **macOS/Linux:** Open Terminal, type `cd` (with a space), drag the project folder into the terminal, press Enter.

### 3. Install Required Libraries

    pip install PyQt6 pycryptodome

If you get a `pip: command not found` error, try:

    python -m pip install PyQt6 pycryptodome   # or python3 -m pip ...

### 4. Run the Editor

    python main.py   # or python3 main.py

The editor window will appear.  
On startup, point the app to the `json` folder inside the project directory (if asked). Then click **Import**, select your `.lcache` file, and start editing.

## Building a Standalone Executable

If you want to run the editor without Python or share it with others:

1. Install PyInstaller:
    
    pip install pyinstaller

2. Build for your OS:

   - **Windows:**
     
     pyinstaller --onefile --windowed --add-data "core;core" --add-data "modules;modules" --add-data "json;json" --name "GothicEditor" main.py
     
   - **macOS / Linux** (use `:` as separator):
     
     pyinstaller --onefile --windowed --add-data "core:core" --add-data "modules:modules" --add-data "json:json" --name "GothicEditor" main.py

After a few minutes, the standalone executable will appear in the `dist` folder. You can move it anywhere — it runs completely on its own.

## Main Features

- **Full `.lcache` parsing and rebuilding** – Handles native structures with correct internal AES encryption.
- **Dialogue Tree Workspace** – Interactive hierarchy view that maps flat translation strings into structured dialogue flows.
- **Automated encoding management** – Automatically switches to UTF‑16LE if any non‑ASCII characters (Cyrillic, Umlauts) are detected. Pure Latin strings are saved in compact UTF‑8.
- **Auto‑sync of translations** – Updating a translation automatically changes the text across all related duplicate keys with suffixes (`_new`, `_newer`, `_v3`, `_v2`, `_patch`).
- **Action history** – Centralized undo/redo manager (`Ctrl+Z` / `Ctrl+Y`).
- **Search and filtering** – Full‑text search and quick filters to isolate or hide specific strings.
- **Standalone UI Localization** – The editor interface can be fully translated into English, Russian, Polish, German, French, or Spanish via the toolbar button.
- **Settings retention (`settings.ini`)** – Remembers the selected theme (including dark and warm modes), layout preferences, and column widths.
- **Status indication** – Displays total keys, translation completion percentage, and unsaved changes tracking.

## What it CANNOT (and will not) do

- Add new text keys or inject entirely new languages into the file.
- Work with games other than Gothic 1 Remake.
- Fix developers' skill issues.
- Prevent you from accidentally breaking your own text or making typos.
- Serve as an example of perfect code.

## System Requirements

- **Operating System:** Windows 10 / Windows 11 (64‑bit) or Linux (64‑bit distributions via Proton/Wine).
- Supports file paths containing Cyrillic characters and spaces.
- When saving, the old file is automatically renamed to `.bak` to prevent data loss.
- Application errors and crashes are cleanly logged into `error_log.txt` next to the executable.

## Project Structure

    .
    ├── main.py          # Entry point
    ├── core/            # Core logic (parsing, encryption, etc.)
    ├── modules/         # UI modules and plugins
    ├── json/            # JSON data files (used for UI translation)
    ├── settings.ini     # Auto‑generated user settings
    └── error_log.txt    # Auto‑generated error log (if any)

## Credits

Thanks to dh0er for parsing the file format and providing the basic layout.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: No module named 'Crypto'` | Run `pip install pycryptodome` again. |
| `ModuleNotFoundError: No module named 'PyQt6'` | Run `pip install PyQt6` again. |
| Error about `dialog_context_plugin` | You accidentally moved or deleted the `modules` folder. It must remain in the same directory alongside `main.py`. |
| The data table inside the editor is empty | The program doesn't automatically load files on startup. Click **Import** and manually open your `.lcache` file. |
