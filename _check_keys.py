import re
f = r'C:\Users\Dev Saini\AppData\Local\Programs\Python\Python312\Lib\site-packages\pytubefix\innertube.py'
with open(f) as fh:
    content = fh.read()
# Find _default_clients keys
keys = re.findall(r"^\s+'(\w+)'\s*:\s*\{", content, re.MULTILINE)
print('_default_clients keys:')
for k in keys:
    print(f'  {k}')
