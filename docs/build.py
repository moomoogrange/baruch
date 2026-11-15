"""소개 쪽 만들기: page.src.html에 타일 스프라이트와 프리즈를 넣어 index.html을 쓴다.
실행: python3 docs/tiles_baruch.py && python3 docs/build.py"""
import os, re
H = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(H, 'page.src.html'), encoding='utf-8').read()
sprite = open(os.path.join(H, 'tiles.svg'), encoding='utf-8').read().replace('style="display:none"', 'width="0" height="0" style="position:absolute" aria-hidden="true"')
sprite = re.sub(r'<title>[^<]*</title>', '', sprite)
def frieze(m):
    ids = m.group(1).split()
    run = ''.join(f'<svg viewBox="0 0 96 96"><use href="#{i}"/></svg>' for i in ids) * 14   # 한 바퀴
    return run + run                                                     # 두 번 이어 끊김 없이 흐른다
out = src.replace('<!--TILES-->', sprite)
out = re.sub(r'<!--FRIEZE:([^>]*?)-->', frieze, out)
open(os.path.join(H, 'index.html'), 'w', encoding='utf-8').write(out)
open(os.path.join(H, '.nojekyll'), 'w').write('')
print('index.html', len(out) // 1024, 'KB')
# 색 견본 — 같은 쪽을 먹남색과 인주색으로 칠한 것 (비교용)
NAVY = {'#2C6349': '#1E2A44', '#43825E': '#3D4C6E', '#6FA98B': '#8090B2', '#A2CCB6': '#B6C1D8', '#D0E5D9': '#DEE3EE',
        '#8FCB77': '#C4452F', '#BEE0AA': '#C9D2E4', '#E4F2D8': '#E9ECF3', '#DCEDF1': '#E2E6EE', '#F7F2E6': '#F7F5F1',
        '#34694B': '#34425F', '#3D7356': '#4B5978', '#EAF3EC': '#EEF1F6', '#DDEBE0': '#DEE3EE',
        'rgba(44,99,73': 'rgba(30,42,68', 'rgba(247,242,230': 'rgba(247,245,241'}
alt = out
for k, v in NAVY.items():
    alt = alt.replace(k, v).replace(k.lower(), v)
alt = alt.replace('<pre><i>', '<pre><i style="color:#E8B4A8">').replace('pre i{font-style:normal;color:var(--b3)}', 'pre i{font-style:normal;color:#E8B4A8}')
open(os.path.join(H, 'preview-navy.html'), 'w', encoding='utf-8').write(alt)
