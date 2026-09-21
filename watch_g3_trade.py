# -*- coding: utf-8 -*-
"""watch_g3_trade.py — 三级弹买卖策略监控（依据"十七"交易表 + 用户持仓）
现价 ≤ 买入价 → 微信推"买入提醒"；现价 ≥ 卖出价 → 推"卖出提醒"。
状态变化才推送（buy/mid/sell 切换），避免刷屏。云端与本地均可用。

推送渠道：Server酱（SCT_KEY 环境变量或本地 sct_sendkey.txt）
每日推送上限：DAILY_LIMIT 条（默认 5，Server酱免费版上限），达到后当天静默。
"""
import json, os, urllib.request, urllib.parse, gzip, time

BASE = os.path.dirname(os.path.abspath(__file__))
STATEF = os.path.join(BASE, 'g3trade_state.json')
DAILYF = os.path.join(BASE, 'daily_push_count.json')
DAILY_LIMIT = int(os.environ.get('DAILY_LIMIT', 5))

# id -> (名称, 买入价或None, 卖出价, 保本价或None)
# 2026-09-19 用户指定：只监控这三款持仓弹
WATCH = {
    '14418': ('4.6x30mm FMJ ST', 780, 1200, 885),   # 用户持仓 970x2000 + 800x2000
    '1358': ('9x39mm SP5', 250, 604, 328),           # 用户持仓 204x5000
    '1356': ('5.45x39mm PS', 360, 534, 426),         # 用户持仓 360x?（数量待补）
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


def get_key():
    k = os.environ.get('SCT_KEY', '')
    if k:
        return k
    kf = os.path.join(BASE, 'sct_sendkey.txt')
    if os.path.exists(kf):
        return open(kf, encoding='utf-8').read().strip()
    return ''


def load_daily():
    """返回 (今日已发条数, 今日日期)"""
    today = time.strftime('%Y-%m-%d')
    try:
        d = json.load(open(DAILYF, encoding='utf-8'))
        if d.get('date') == today:
            return int(d.get('count', 0)), today
    except Exception:
        pass
    return 0, today


def save_daily(count, today):
    json.dump({'date': today, 'count': count}, open(DAILYF, 'w', encoding='utf-8'))
    # 云端：用 GITHUB_TOKEN 通过 API 写回仓库，保证跨 run 计数持久化
    token = os.environ.get('GITHUB_TOKEN', '')
    if token:
        _sync_cloud(DAILYF, {'date': today, 'count': count}, token)


def _sync_cloud(path, obj, token):
    import ssl
    ctx = ssl._create_unverified_context()
    base = 'https://api.github.com/repos/1930258243/moligod-reports/contents/' + path
    req = urllib.request.Request(base)
    req.add_header('Authorization', 'token %s' % token)
    req.add_header('Accept', 'application/vnd.github+json')
    sha = None
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=20) as r:
            sha = json.loads(r.read().decode('utf-8')).get('sha')
    except Exception:
        pass  # 文件不存在则直接创建
    payload = {'message': 'daily push count sync', 'content': __import__('base64').b64encode(
        json.dumps(obj, ensure_ascii=False).encode('utf-8')).decode()}
    if sha:
        payload['sha'] = sha
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(base, data=data, method='PUT')
    req.add_header('Authorization', 'token %s' % token)
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=20) as r:
            return r.status
    except Exception as e:
        print('cloud sync fail:', repr(e)[:120])
        return None


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
    used, today = load_daily()
    if (buys or sells) and key and used < DAILY_LIMIT:
        pushed = 0
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
            pushed += 1
        if sells and used + pushed < DAILY_LIMIT:
            title = '🔴 三级弹卖出提醒 %d 项' % len(sells)
            lines = ['监测时间 %s' % now, '']
            for name, p, sell, bep in sells:
                lines.append('■ %s' % name)
                lines.append('  现价 %s ≥ 卖出线 %s' % (p, sell))
                if bep:
                    lines.append('  保本价 %s' % bep)
            lines.append('—— 三级弹买卖监控')
            print('PUSH_SELL:', push(key, title, '\n'.join(lines)))
            pushed += 1
        save_daily(used + pushed, today)
    elif (buys or sells):
        print('DAILY_LIMIT 已达上限(%d)，今日不再推送' % DAILY_LIMIT)
    json.dump(cur, open(STATEF, 'w', encoding='utf-8'), ensure_ascii=False)
    print('done: buy=%d sell=%d' % (len(buys), len(sells)))


if __name__ == '__main__':
    main()
