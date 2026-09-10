# -*- coding: utf-8 -*-
"""watch_g3_trade.py — 三级弹买卖策略监控（依据"十七"交易表）
现价 ≤ 买入价 → 微信推"买入提醒"；现价 ≥ 卖出价 → 推"卖出提醒"。
状态变化才推送（buy/mid/sell 切换），避免刷屏。云端与本地均可用。
用法: SCT_KEY=xxx python watch_g3_trade.py
"""
import json, os, urllib.request, urllib.parse, gzip, time

BASE = os.path.dirname(os.path.abspath(__file__))
STATEF = os.path.join(BASE, 'g3trade_state.json')

# id -> (名称, 买入价或None, 卖出价, 保本价或None)
WATCH = {
    '1355': ('7.62x39mm PS', 416, 581, 480),
    '1365': ('9x19mm AP6.3', 351, 501, 405),
    '1363': ('.45 ACP FMJ', 446, 611, 515),
    '1360': ('7.62x51mm BPZ', 408, 528, 471),
    '1376': ('蓝.300BLK', 437, 602, 505),
    '1356': ('5.45x39mm PS', 369, 534, 426),
    '1361': ('7.62x54R T46M', 402, 522, 464),
    '1374': ('4.6x30mm Subsonic SX', 237, 387, 273),
    '1358': ('9x39mm SP5', 284, 604, 328),
    '1354': ('5.56x45mm M855', None, 526, None),
    '1357': ('5.8x42mm DVP88', 418, 538, 482),
}


def fetch_catalog():
    cj = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
    cj.open('https://moligod.com/', timeout=20)
    req = urllib.request.Request('https://moligod.com/api/market/ammo-catalog',
                                 headers={'Accept-Encoding': 'gzip', 'User-Agent': 'Mozilla/5.0'})
    data = cj.open(req, timeout=20).read()
    if data[:2] == b'\x1f\x8b':
        data = gzip.decompress(data)
    cat = json.loads(data)
    items = cat['items'] if isinstance(cat, dict) and 'items' in cat else cat
    return {str(it.get('id')): it.get('latest_price') for it in items}


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
        return r.read().decode('utf-8', 'ignore')[:200]


def main():
    prices = fetch_catalog()
    prev = {}
    if os.path.exists(STATEF):
        try:
            prev = json.load(open(STATEF, encoding='utf-8'))
        except Exception:
            prev = {}
    now = time.strftime('%m-%d %H:%M')
    buys, sells = [], []
    cur = {}
    for iid, (name, buy, sell, bep) in WATCH.items():
        p = prices.get(iid)
        if p is None:
            continue
        if buy is not None and p <= buy:
            zone = 'buy'
        elif sell is not None and p >= sell:
            zone = 'sell'
        else:
            zone = 'mid'
        cur[iid] = zone
        old = prev.get(iid)
        if zone == 'buy' and old != 'buy':
            buys.append((name, p, buy, bep))
        elif zone == 'sell' and old != 'sell':
            sells.append((name, p, sell, bep))
    key = get_key()
    if (buys or sells) and key:
        if buys:
            title = '🟢 三级弹买入提醒 %d 项' % len(buys)
            lines = ['监测时间 %s' % now, '']
            for name, p, buy, bep in buys:
                lines.append('■ %s' % name)
                lines.append('  现价 %s ≤ 买入线 %s' % (p, buy))
                if bep:
                    lines.append('  保本价 %s' % bep)
            lines.append('—— 三级弹买卖监控')
            print('PUSH_BUY:', push(key, title, '\n'.join(lines)))
        if sells:
            title = '🔴 三级弹卖出提醒 %d 项' % len(sells)
            lines = ['监测时间 %s' % now, '']
            for name, p, sell, bep in sells:
                lines.append('■ %s' % name)
                lines.append('  现价 %s ≥ 卖出线 %s' % (p, sell))
                if bep:
                    lines.append('  保本价 %s' % bep)
            lines.append('—— 三级弹买卖监控')
            print('PUSH_SELL:', push(key, title, '\n'.join(lines)))
    json.dump(cur, open(STATEF, 'w', encoding='utf-8'), ensure_ascii=False)
    print('done: buy=%d sell=%d' % (len(buys), len(sells)))


if __name__ == '__main__':
    main()
