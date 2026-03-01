import re
f = r'C:\Users\Dev Saini\AppData\Local\Programs\Python\Python312\Lib\site-packages\pytubefix\innertube.py'
with open(f) as fh:
    content = fh.read()

# Find all client blocks
blocks = re.findall(r"'clientName':\s*'(\w+)'.*?'require_po_token':\s*(True|False)", content, re.DOTALL)
for name, needs_po in blocks:
    print(f'{name:30s} require_po_token={needs_po}')
