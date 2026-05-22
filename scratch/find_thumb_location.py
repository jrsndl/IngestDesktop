import glob
import os

for path in glob.glob('**/*.py', recursive=True):
    if '.venv' in path or 'scratch' in path: continue
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        for i, line in enumerate(f):
            if 'thumb_location' in line or 'Thumbnail Location' in line:
                print(f'{path}:{i+1}: {line.strip()}')
