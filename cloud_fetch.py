# -*- coding: utf-8 -*-
"""cloud_fetch.py — moligod 云端数据抓取（GitHub Actions 运行）
抓取全部 3/4 级子弹（52 款）实时价 + 30天/7天/15天 K 线，输出 JSON 供报告与盯价使用。
输出: data/catalog.json (实时价) + data/history_{date}.json (K线快照) + data/latest.json (汇总)
"""
import json, urllib.request, urllib.parse, gzip, os, time, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, 'data')
os.makedirs(DATA, exist_ok=True)

# 52 款 3/4 级子弹 item_id
ITEM_IDS_G3 = [1376,1368,1369,1363,1362,1378,1370,1371,1372,1373,1359,1374,1356,1354,1367,1366,1357,4498,1355,1360,1361,1365,1364,4497,1358,1375]
ITEM_IDS_G4 = [1351,1344,1341,4476,1353,1345,1347,1346,1338,1337,1349,1332,1329,1343,4467,1334,4471,1336,1330,1339,1340,4478,1342,4469,1335,1350]
# 16 款 5 级弹 item_id
ITEM_IDS_G5 = ['1318','1324','1328','1314','1311','1322','4443','1315','4447','1317','1312','1319','1320','1316','1325','1327']
ITEM_IDS = ITEM_IDS_G3 + ITEM_IDS_G4 + ITEM_IDS_G5

def build_opener():
    cj = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
    cj.open('https://moligod.com/', timeout=30)
    return cj

def get_json(opener, url):
    req = urllib.request.Request(url, headers={'Accept-Encoding': 'gzip', 'User-Agent': 'Mozilla/5.0'})
    data = opener.open(req, timeout=30).read()
    if data[:2] == b'\x1f\x8b':
        data = gzip.decompress(data)
    return json.loads(data)

def main():
    opener = build_opener()
    today = datetime.date.today().isoformat()

    # 1. 目录(实时价)
    cat = get_json(opener, 'https://moligod.com/api/market/ammo-catalog')
    items = cat['items'] if isinstance(cat, dict) and 'items' in cat else cat
    catalog = {}
    for it in items:
        catalog[str(it.get('id'))] = {
            'name': it.get('name'), 'grade': it.get('grade'),
            'sub': it.get('subcategory_label'), 'latest': it.get('latest_price'),
            'today_high': it.get('today_high_price'), 'today_low': it.get('today_low_price'),
            'yesterday_high': it.get('yesterday_high_price'), 'yesterday_low': it.get('yesterday_low_price'),
            'seven_high': it.get('seven_day_high_price'), 'seven_low': it.get('seven_day_low_price'),
        }
    with open(os.path.join(DATA, 'catalog.json'), 'w', encoding='utf-8') as f:
        json.dump(catalog, f, ensure_ascii=False, indent=1)

    # 2. 详情(30d/7d/15d K线)
    history = {}
    for iid in ITEM_IDS:
        try:
            d = get_json(opener, 'https://moligod.com/api/market/item-detail?item_id=%s' % iid)
            m = d.get('market') or {}
            ranges = (m.get('charts') or {}).get('price', {}).get('ranges', {})
            history[str(iid)] = {
                'name': (d.get('identity') or {}).get('name'),
                'latest': m.get('latest_price'),
                'r30': ranges.get('30d') or [],
                'r7': ranges.get('7d') or [],
                'r15': ranges.get('15d') or [],
            }
        except Exception as e:
            print('skip', iid, e)
        time.sleep(0.15)

    with open(os.path.join(DATA, 'history_%s.json' % today), 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False)
    with open(os.path.join(DATA, 'history_latest.json'), 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False)

    print('fetched items=', len(history), 'date=', today)
    print('OK')

if __name__ == '__main__':
    main()
