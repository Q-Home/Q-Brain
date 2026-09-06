from pathlib import Path
import zipfile
import os
import argparse

parser=argparse.ArgumentParser()
parser.add_argument('source',type=Path)
args=parser.parse_args()
p=args.source
out=Path(__file__).resolve().parents[1]/'vendor'
out.mkdir(exist_ok=True)
f=p/'build/index.html'
s=f.read_text(encoding='utf-8').replace('"/_app/','"./_app/').replace('href="/favicon','href="./favicon')
s='\n'.join(line for line in s.splitlines() if './fonts/' not in line)
s=s.replace('<head>','''<head>
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'">
<style>.attachments-toolbar,.segmented-nav__button:nth-child(2),[role=tablist] button:nth-child(2){display:none!important}</style>''')
f.write_text(s,encoding='utf-8',newline='\n')
(p/'build/LICENSE-HOLLAMA.txt').write_bytes((p/'LICENSE').read_bytes())
notices=[]
for license in (p/'node_modules/.pnpm').glob('*/node_modules/*/LICENSE*'):
 if license.is_file():
  try: notices.append(str(license.relative_to(p/'node_modules/.pnpm'))+'\n'+license.read_text(encoding='utf-8'))
  except UnicodeDecodeError: pass
(p/'build/THIRD-PARTY-NOTICES.txt').write_text('\n\n'.join(notices),encoding='utf-8',newline='\n')
with zipfile.ZipFile(out/'hollama-ui.zip','w',zipfile.ZIP_DEFLATED) as z:
 for f in sorted((p/'build').rglob('*')):
  if f.is_file() and 'fonts' not in f.relative_to(p/'build').parts:z.write(f,f.relative_to(p/'build').as_posix())
with zipfile.ZipFile(out/'hollama-source.zip','w',zipfile.ZIP_DEFLATED) as z:
 for folder, dirs, files in os.walk(p):
  dirs[:] = sorted(d for d in dirs if d not in ('node_modules','.svelte-kit','build','.git','fonts','tests','electron','.github'))
  for name in sorted(files):
   f=Path(folder)/name
   if name not in ('preview.html','.env'):z.write(f,f.relative_to(p).as_posix())
print([(f.name,f.stat().st_size) for f in out.glob('*.zip')])
