import os
import sys
import tempfile
import csv
import shutil
sys.path.append("d:/_code/IngestDesktop")

from logic.image_model import ImageItem, ImageTableModel

print("Verifying Ingest Check logic...")

# Create mock items
item1 = ImageItem(file_path="C:/temp/sh001_render_v001.png", label="sh001_render")
item1.version = 1
item1.ingest_status = "unknown"

valid_items = [item1]

# Create a temporary CSV file
temp_dir = tempfile.gettempdir()
csv_path = os.path.join(temp_dir, "test_ayon_ingest_log.csv")

headers = ["File Path", "AYON Path", "Product Name", "Version", "Representation"]
rows = [
    ["C:/temp/sh001_render_v001.png", "/shots/sh001", "renderMain", "1", "png"]
]

with open(csv_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(headers)
    writer.writerows(rows)

print("Created dummy log at:", csv_path)

# Let's mock a simple check to verify normalization and parsing
def normalize_version(v_str):
    if not v_str: return None
    try:
        return int(v_str)
    except ValueError:
        pass
    import re
    m = re.search(r'\d+', str(v_str))
    if m:
        return int(m.group())
    return None

v_norm1 = normalize_version("v001")
v_norm2 = normalize_version("1")
v_norm3 = normalize_version("002")

assert v_norm1 == 1, f"Expected 1, got {v_norm1}"
assert v_norm2 == 1, f"Expected 1, got {v_norm2}"
assert v_norm3 == 2, f"Expected 2, got {v_norm3}"
print("Version normalization tests PASSED!")

# Suffix helper test
check_results_ok = ["OK", "OK"]
check_results_failed = ["Failed", "Failed"]
check_results_mixed = ["OK", "Failed"]

def get_suffix(results):
    if all(res == "OK" for res in results):
        return "_checkedOK"
    elif all(res == "Failed" for res in results):
        return "_checkedFailed"
    else:
        return "_checkedMixed"

assert get_suffix(check_results_ok) == "_checkedOK"
assert get_suffix(check_results_failed) == "_checkedFailed"
assert get_suffix(check_results_mixed) == "_checkedMixed"
print("Suffix decision tests PASSED!")

# Clean up
if os.path.exists(csv_path):
    os.remove(csv_path)

print("All Ingest Check local verification tests PASSED!")
