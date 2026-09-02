# -*- coding: utf-8 -*-
"""cloud_report.py — 云端报告生成（GitHub Actions 运行）
基于 data/history_latest.json 生成 HTML 报告。
口径：低价期=赛季末最后一周 8/25-9/2；日常期=8/2-8/24；出售到手=挂价*0.87；SPIKE 不特殊处理。
用法: python cloud_report.py [daily|weekly|monthly] [output.html]
"""
import json, os, sys, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, 'data')

LOW_START, LOW_END = '2026-08-25', '2026-09-02'   # 低价期
DAY_START, DAY_END = '2026-08-02', '2026-08-24'   # 日常期
TAX = 0.87

def collect_daily(hist):
    """把 r30/r15 按日期聚合到统一 dict: {date: {low,high,avg,last}}"""
    days = {}
    def feed(rows):
        for r in rows or []:
            t = r.get('time', '')
            # r30 是 2026-08-02 格式, r7/r15 是 08-26 格式, 需补年份
            if len(t) == 10 and t[:4] == '2026':
                date = t
            elif len(t) == 5:
                date = '2026-' + t
            else:
                continue
            cur = days.setdefault(date, {'low': None, 'high': None, 'avg_sum': 0.0, 'avg_n': 0, 'last': None})
            cur['low'] = r['min'] if cur['low'] is None else min(cur['low'], r['min'])
            cur['high'] = r['max'] if cur['high'] is None else max(cur['high'], r['max'])
            if r.get('avg') is not None:
                cur['avg_sum'] += r['avg']; cur['avg_n'] += 1
            if r.get('last') is not None:
                cur['last'] = r['last']
    feed(hist.get('r30'))
    feed(hist.get('r15'))
    feed(hist.get('r7'))
    return days

def stats(days, start, end):
    lows, highs, avgs = [], [], []
    for d in sorted(days):
        if start <= d <= end:
            r = days[d]
            if r['low'] is not None: lows.append(r['low'])
            if r['high'] is not None: highs.append(r['high'])
            if r['avg_n'] > 0: avgs.append(r['avg_sum'] / r['avg_n'])
    return {
        'low': min(lows) if lows else None,
        'high': max(highs) if highs else None,
        'avg': (sum(avgs) / len(avgs)) if avgs else None,
        'n': len(avgs),
    }

def main():
    rtype = sys.argv[1] if len(sys.argv) > 1 else 'daily'
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(BASE, 'reports', 'report_%s.html' % rtype)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(os.path.join(DATA, 'history_latest.json'), encoding='utf-8') as f:
        history = json.load(f)
    rows = []
    for iid, h in history.items():
        days = collect_daily(h)
        ls = stats(days, LOW_START, LOW_END)
        ds = stats(days, DAY_START, DAY_END)
        if ls['avg'] is None or ds['avg'] is None:
            continue
        tax_net = ds['avg'] * TAX          # 日常期均价卖出到手
        profit = (tax_net - ls['avg']) if ls['avg'] else None  # 低价买 -> 日常卖
        margin = (profit / ls['avg'] * 100) if (ls['avg'] and profit is not None) else None
        rows.append({
            'name': h.get('name') or iid, 'latest': h.get('latest'),
            'low_low': ls['low'], 'low_avg': round(ls['avg']), 'low_high': ls['high'],
            'day_low': ds['low'], 'day_avg': round(ds['avg']), 'day_high': ds['high'],
            'tax_net': round(tax_net), 'profit': round(profit) if profit is not None else None,
            'margin': round(margin, 1) if margin is not None else None,
        })
    rows.sort(key=lambda r: -(r['margin'] or -999))
    today = datetime.date.today().isoformat()
    title_map = {'daily': '行情日报', 'weekly': '行情周报', 'monthly': '行情月报'}
    t = title_map.get(rtype, '行情报告')

    trs = []
    for r in rows:
        col = 'color:#3fbf7f' if (r['margin'] or 0) > 0 else ('color:#e05252' if (r['margin'] or 0) < 0 else 'color:#aaa')
        trs.append('<tr><td>%s</td><td>%s</td><td>%s / %s / %s</td><td>%s / %s / %s</td>'
                   '<td>%s</td><td style="%s">%s (%.1f%%)</td></tr>' % (
                       r['name'], r['latest'],
                       r['low_low'], r['low_avg'], r['low_high'],
                       r['day_low'], r['day_avg'], r['day_high'],
                       r['tax_net'],
                       col, r['profit'], r['margin']))
    pos = sum(1 for r in rows if (r['margin'] or 0) > 0)
    html = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>{t} {today}</title>
<style>
body{{font-family:'Microsoft YaHei',sans-serif;background:#0f1115;color:#e6e6e6;padding:24px;}}
h1{{color:#f0b90b;font-size:22px;}} h2{{color:#8ab4f8;font-size:16px;margin-top:26px;}}
.meta{{color:#888;font-size:12px;margin-bottom:16px;}}
table{{border-collapse:collapse;width:100%;font-size:13px;}}
th,td{{border:1px solid #333;padding:6px 8px;text-align:center;}}
th{{background:#1a1d24;color:#f0b90b;}} tr:nth-child(even){{background:#15171c;}}
.kpi{{display:inline-block;background:#1a1d24;border:1px solid #333;padding:10px 18px;margin-right:12px;border-radius:8px;}}
.kpi b{{font-size:20px;color:#f0b90b;}}
</style></head><body>
<h1>moligod {t} · {today}</h1>
<div class="meta">口径：低价期 {LOW} | 日常期 {DAY} | 出售到手=挂价×0.87（税13%）| SPIKE 不特殊处理 | 数据源 moligod.com 实时K线</div>
<div class="kpi">监控子弹 <b>{total}</b></div>
<div class="kpi">低价期可买(税后正利润) <b style="color:#3fbf7f">{pos}</b></div>
<h2>全部 3/4 级子弹：低价期 vs 日常期 行情表（按税后利润率排序）</h2>
<table><tr><th>子弹</th><th>最新价</th><th>低价期 低/均/高</th><th>日常期 低/均/高</th><th>日常卖出到手</th><th>税后利润</th></tr>
{trs}
</table>
<p style="color:#666;font-size:11px;margin-top:18px;">利润 = 日常期均价×0.87 − 低价期均价（即低价期买入、日常期卖出，单发税后空间）。</p>
</body></html>""".format(
        t=t, today=today, LOW='%s~%s' % (LOW_START[5:], LOW_END[5:]), DAY='%s~%s' % (DAY_START[5:], DAY_END[5:]),
        total=len(rows), pos=pos, trs=''.join(trs))
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print('REPORT', rtype, 'rows=', len(rows), 'pos=', pos, '->', out)

if __name__ == '__main__':
    main()
