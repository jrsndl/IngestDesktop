with open("gui/main_window.py", "r", encoding="utf-8") as f:
    for i, line in enumerate(f, 1):
        if "def " in line or "_update_ayon_visuals" in line:
            if "_update_ayon_visuals" in line:
                print(f"Line {i}: {line.strip()}")
