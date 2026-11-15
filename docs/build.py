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
