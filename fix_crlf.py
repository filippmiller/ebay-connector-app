#!/usr/bin/env python3
"""Convert start.sh to LF line endings"""

path = "backend/start.sh"

with open(path, 'rb') as f:
    content = f.read()

content = content.replace(b'\r\n', b'\n')

with open(path, 'wb') as f:
    f.write(content)

print(f"Converted {path} to LF")
