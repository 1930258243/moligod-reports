# -*- coding: utf-8 -*-
"""watch_g3_trade.py — 三级弹买卖策略监控（依据"十七"交易表）
现价 ≤ 买入价 → 微信推"买入提醒"；现价 ≥ 卖出价 → 推"卖出提醒"。
状态变化才推送（buy/mid/sell 切换），避免刷屏。云端与本地均可用。

推送渠道（按优先级）：
  1) PUSH_PLUS_TOKEN 环境变量 → PushPlus 微信推送（免费 200 条/天）
  2) SCT_KEY 环境变量或本地 sct_sendkey.txt → Server酱（免费 5 条/天）

用法: PUSH_PLUS_TOKEN=xxx python watch_g3_trade.py
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

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
HDR = {
    'User-Agent': UA,
    'Referer': 'https://moligod.com/',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
}


def http_get(url, opener, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=HDR)
            data = opener.open(req, timeout=25).read()
            if data[:2] == b'\x1f\x8b':
                data = gzip.decompress(data)
            return data
        except Exception as e:
            last = e
            time.sleep(2 + 3 * i)
    raise last


def fetch_catalog():
    cj = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
    # 1) 建会话 cookie（首页）
    try:
        http_get('https://moligod.com/', cj)
    except Exception:
        pass  # 首页失败不致命，继续试 API
    # 2) 抓 catalog
    data = http_get('https://moligod.com/api/market/ammo-catalog', cj)
    cat = json.loads(data)
    items = cat['items'] if isinstance(cat, dict) and 'items' in cat else cat
    return {str(it.get('id')): it.get('latest_price') for it in items}


def get_tokens():
    """返回 (pushplus_token, sct_key)"""
    pp = os.environ.get('PUSH_PLUS_TOKEN', '')
    sct = os.environ.get('SCT_KEY', '')
    if not sct:
        kf = os.path.join(BASE, 'sct_sendkey.txt')
        if os.path.exists(kf):
            sct = open(kf, encoding='utf-8').read().strip()
    return pp, sct


def push_pushplus(token, title, content):
    url = 'https://www.pushplus.plus/send?' + urllib.parse.urlencode(
        {'token': token, 'title': title, 'content': content, 'template': 'txt'})
    with urllib.request.urlopen(url, timeout=15) as r:
        return r.read().decode('utf-8', 'ignore')[:200]


def push_sct(key, title, desp):
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
    pp, sct = get_tokens()
    if (buys or sells) and (pp or sct):
        if buys:
            title = '🟢 三级弹买入提醒 %d 项' % len(buys)
            lines = ['监测时间 %s' % now, '']
            for name, p, buy, bep in buys:
                lines.append('■ %s' % name)
                lines.append('  现价 %s ≤ 买入线 %s' % (p, buy))
                if bep:
                    lines.append('  保本价 %s' % bep)
            lines.append('—— 三级弹买卖监控')
            content = '\n'.join(lines)
            if pp:
                print('PP_BUY:', push_pushplus(pp, title, content))
            elif sct:
                print('SCT_BUY:', push_sct(sct, title, content))
        if sells:
            title = '🔴 三级弹卖出提醒 %d 项' % len(sells)
            lines = ['监测时间 %s' % now, '']
            for name, p, sell, bep in sells:
                lines.append('■ %s' % name)
                lines.append('  现价 %s ≥ 卖出线 %s' % (p, sell))
                if bep:
                    lines.append('  保本价 %s' % bep)
            lines.append('—— 三级弹买卖监控')
            content = '\n'.join(lines)
            if pp:
                print('PP_SELL:', push_pushplus(pp, title, content))
            elif sct:
                print('SCT_SELL:', push_sct(sct, title, content))
    json.dump(cur, open(STATEF, 'w', encoding='utf-8'), ensure_ascii=False)
    print('done: buy=%d sell=%d' % (len(buys), len(sells)))


if __name__ == '__main__':
    main()
