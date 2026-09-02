# -*- coding: utf-8 -*-
"""cloud_watch.py — 云端盯价 + 微信推送（GitHub Actions 运行）
读取 data/catalog.json 实时价，对比上次快照，波动 >= 阈值 推送 Server酱。
SendKey 从环境变量 SCT_KEY 读取（GitHub Actions Secret 注入）。
"""
import json, os, urllib.request, urllib.parse, time

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, 'data')
SNAP = os.path.join(DATA, 'watch_snapshot.json')

WATCH = ['玻纤柳叶箭矢', '12.7x55mm PS12A', '45-70 Govt RN', '5.7x28mm L191', '9x39mm SP5',
         '5.8x42mm DVP88', '7.62x54R T46M', '.45 ACP FMJ', '7.62x51mm BPZ', '9x19mm AP6.3',
         '7.62x39mm PS', '9*39mm PAB-7', '5.56x45mm M855', '12.7x55mm PS12', '5.8x42mm DBP10']
THRESH = float(os.environ.get('WATCH_THRESH', '5'))
SCT_KEY = os.environ.get('SCT_KEY', '').strip()

def push(title, desp):
    if not SCT_KEY:
        print('NO_SCT_KEY')
        return
    url = 'https://sctapi.ftqq.com/%s.send?' % SCT_KEY + urllib.parse.urlencode(
        {'title': title, 'desp': desp})
    with urllib.request.urlopen(url, timeout=15) as r:
        print(r.read().decode('utf-8', 'ignore')[:200])

def main():
    with open(os.path.join(DATA, 'catalog.json'), encoding='utf-8') as f:
        catalog = json.load(f)
    price = {}
    for iid, it in catalog.items():
        if it.get('latest') is not None:
            price[it['name']] = it['latest']
    prev = {}
    if os.path.exists(SNAP):
        try:
            prev = json.load(open(SNAP, encoding='utf-8'))
        except Exception:
            prev = {}
    now = time.strftime('%m-%d %H:%M')
    alerts = []
    for name in WATCH:
        cur = price.get(name)
        if cur is None:
            continue
        old = prev.get(name)
        if old is None or old <= 0:
            continue
        chg = (cur - old) / old * 100
        if abs(chg) >= THRESH:
            alerts.append((name, old, cur, chg))
    if alerts:
        title = 'moligod 价格异动 %d 项' % len(alerts)
        lines = ['监测时间 %s' % now]
        for name, old, cur, chg in alerts:
            arrow = '上涨' if chg > 0 else '下跌'
            lines.append('- %s %s %.1f%% (%d -> %d)' % (name, arrow, chg, old, cur))
        lines.append('-- moligod 云端盯价')
        push(title, '\n'.join(lines))
        print('ALERT %d' % len(alerts))
    # 更新快照
    snap = {k: price[k] for k in WATCH if k in price}
    json.dump(snap, open(SNAP, 'w', encoding='utf-8'), ensure_ascii=False)
    print('done watch=%d alerts=%d' % (len(snap), len(alerts)))

if __name__ == '__main__':
    main()
