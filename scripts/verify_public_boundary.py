from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
for rel in ['manuscript','supplement','provenance','results/inference','scripts/recovered']:
    if (ROOT/rel).exists(): raise SystemExit(f'PRIVATE_PATH_PRESENT={rel}')
patterns=[r'REF_BACEN',r'NU_ORDEM',r'\b205619\b',r'\b205183\b',r'\b199318\b',r'\b192576\b',r'\b13538\b',r'\b185780\b',r'ProAgro',r'DT_ENTREGA',r'COP_count']
for p in ROOT.rglob('*'):
    if p.resolve() == Path(__file__).resolve(): continue
    if not p.is_file() or any(part in {'.git','__pycache__','.pytest_cache'} for part in p.parts) or p.suffix.lower() in {'.png','.jpg','.jpeg','.zip','.sqlite'}: continue
    t=p.read_text(encoding='utf-8',errors='ignore')
    for pat in patterns:
        if re.search(pat,t,re.I): raise SystemExit(f'PRIVATE_PATTERN_FOUND={pat}::{p.relative_to(ROOT)}')
print('PUBLIC_BOUNDARY_SCAN=PASS')
