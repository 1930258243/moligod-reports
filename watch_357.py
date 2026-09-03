# -*- coding: utf-8 -*-
"""watch_357.py — moligod .357 Magnum FMJ（四级弹）脉冲定向监控
价格破阈值(默认800)微信提醒，带冷却去重。云端(GitHub Actions)与本地均可用。
用法: SCT_KEY=xxx python watch_357.py  （SCT_KEY 不传则读本地 sct_sendkey.txt）
"""
import json, os, urllib.request, urllib.parse, gzip, time, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
STATEF = os.path.join(BASE, 'watch357_state.json')
AMMO = '.357 Magnum FMJ'
THRESH = int(os.environ.get('WATCH357_THRESH', '800'))      # 触发提醒的价格阈值
COOLDOWN_H = float(os.environ.get('WATCH357_COOLDOWN', '6'))  # 冷却小时（同事件不重复推）


def fetch_357():
    cj = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
    cj.open('https://moligod.com/', timeout=20)
    req = urllib.request.Request('https://moligod.com/api/market/ammo-catalog',
                                 headers={'Accept-Encoding': 'gzip', 'User-Agent': 'Mozilla/5.0'})
    resp = cj.open(req, timeout=20)
    data = resp.read()
    if data[:2] == b'\x1f\x8b':
        data = gzip.decompress(data)
    cat = json.loads(data)
    items = cat['items'] if isinstance(cat, dict) and 'items' in cat else cat
    for it in items:
        if it.get('name') == AMMO:
            return it
    return None


def get_key():
    k = os.environ.get('SCT_KEY', '')
    if k:
        return k
    kf = os.path.join(BASE, 'sct_sendkey.txt')
    if os.path.exists(kf):
        return open(kf, encoding='utf-8').read().strip()
    return ''


def push(key, title, desp):
    url = 'https://sctapi.ftqq.com/%s.send?' % key + urllib.parse.urlencode(
        {'title': title, 'desp': desp})
    with urllib.request.urlopen(url, timeout=15) as r:
        return r.read().decode('utf-8', 'ignore')[:300]


def main():
    it = fetch_357()
    if not it:
        print('NO_ITEM')
        return
    latest = it.get('latest_price')
    th = it.get('today_high_price') or latest
    now = datetime.datetime.now()
    now_ts = time.time()

    st = {}
    if os.path.exists(STATEF):
        try:
            st = json.load(open(STATEF, encoding='utf-8'))
        except Exception:
            st = {}
    last = st.get('last_alert', 0)

    hit = (latest is not None and latest >= THRESH) or (th is not None and th >= THRESH)
    cooled = (now_ts - last) > COOLDOWN_H * 3600

    if hit and cooled:
        key = get_key()
        if not key:
            print('NO_KEY hit=%s' % hit)
            return
        msg = [
            '🚨 .357 Magnum FMJ（四级弹）冲高提醒',
            '',
            '监测时间：%s' % now.strftime('%m-%d %H:%M'),
            '最新价：%s',
            '今日最高：%s',
            '',
            '操作建议（按计划）：',
            '1. 现在价格已破 %d，打开挂单',
            '2. 挂 3000 发 @1225 出货',
            '3. 成交后立刻补挂下一批',
            '4. 止损线 590（9/18 前没等到就降590落袋）',
            '—— moligod .357 定向监控',
        ]
        desp = '\n'.join(msg) % (latest, th, THRESH)
        title = '🔔 .357 脉冲提醒 %s' % (latest if latest else th)
        r = push(key, title, desp)
        st['last_alert'] = now_ts
        st['last_price'] = latest
        st['last_high'] = th
        json.dump(st, open(STATEF, 'w', encoding='utf-8'), ensure_ascii=False)
        print('ALERT latest=%s high=%s resp=%s' % (latest, th, r[:80]))
    else:
        print('NO_ALERT latest=%s high=%s hit=%s cooled=%s' % (latest, th, hit, cooled))


if __name__ == '__main__':
    main()
