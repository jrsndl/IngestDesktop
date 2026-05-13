import PyInstaller.__main__
import os
import sys

# Entry point
entry_point = "main.py"

# Define the data files to include
# Syntax: (source, destination)
# For PyInstaller CLI it's 'source;destination' on Windows
data_files = [
    ("gui/style.qss", "gui"),
]

# Build arguments
args = [
    entry_point,
    "--onefile",
    "--windowed",
    "--name=IngestDesktop",
    "--clean",
]

for src, dest in data_files:
    args.append(f"--add-data={src}{os.pathsep}{dest}")

# Run PyInstaller
print(f"Building IngestDesktop with arguments: {args}")
PyInstaller.__main__.run(args)
