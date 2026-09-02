# -*- coding: utf-8 -*-
"""cloud_report.py — 云端报告生成（GitHub Actions 运行）v2 完整版
基于 data/catalog.json + data/history_latest.json + data/news.json 生成 HTML 报告。
口径：低价期=赛季末最后一周 8/25-9/2；日常期=8/2-8/24；出售到手=挂价*0.87；SPIKE 不特殊处理。
用法: python cloud_report.py [daily|weekly|monthly] [output.html]
"""
import json, os, sys, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, 'data')

LOW_START, LOW_END = '2026-08-25', '2026-09-02'   # 低价期
DAY_START, DAY_END = '2026-08-02', '2026-08-24'   # 日常期
TAX = 0.87

WEEKDAYS = ['周一','周二','周三','周四','周五','周六','周日']

def load_json(name):
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        return None
    with open(p, encoding='utf-8') as f:
        return json.load(f)

def collect_daily(hist):
    """把 r30/r15 按日期聚合到统一 dict: {date: {low,high,avg_sum,avg_n,last}}"""
    days = {}
    def feed(rows):
        for r in rows or []:
            t = r.get('time', '')
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

def pct_str(v):
    return ('+%.1f%%' % v) if v and v >= 0 else ('%.1f%%' % (v or 0))

def cls(v):
    if v is None: return 'gray'
    return 'pos' if v > 0 else ('neg' if v < 0 else 'gray')

def build_daily_rows(history, catalog):
    """返回 [{name, grade, latest, th, tl, prev, chg, amp, low_*, day_*, tax_net, profit, margin}]"""
    rows = []
    for iid, h in history.items():
        cat = (catalog or {}).get(iid, {})
        days = collect_daily(h)
        ls = stats(days, LOW_START, LOW_END)
        ds = stats(days, DAY_START, DAY_END)
        latest = h.get('latest') or cat.get('latest')
        th = cat.get('today_high'); tl = cat.get('today_low')
        yh = cat.get('yesterday_high'); yl = cat.get('yesterday_low')
        prev = ((yh or 0) + (yl or 0)) / 2.0 if (yh and yl) else None
        chg = ((latest - prev) / prev * 100) if (latest and prev) else None
        amp = ((th - tl) / tl * 100) if (th and tl and tl) else None
        tax_net = (ds['avg'] * TAX) if ds['avg'] else None
        profit = (tax_net - ls['avg']) if (tax_net and ls['avg']) else None
        margin = (profit / ls['avg'] * 100) if (profit is not None and ls['avg']) else None
        # 当前可入手：现价买 -> 日常卖
        cur_space = (tax_net - latest) if (tax_net and latest) else None
        cur_margin = (cur_space / latest * 100) if (cur_space is not None and latest) else None
        rows.append({
            'name': h.get('name') or cat.get('name') or iid, 'grade': cat.get('grade') or '?',
            'latest': latest, 'th': th, 'tl': tl, 'prev': prev, 'chg': chg, 'amp': amp,
            'low_low': ls['low'], 'low_avg': round(ls['avg']) if ls['avg'] else None,
            'low_high': ls['high'], 'day_low': ds['low'],
            'day_avg': round(ds['avg']) if ds['avg'] else None, 'day_high': ds['high'],
            'tax_net': round(tax_net) if tax_net else None,
            'profit': round(profit) if profit is not None else None,
            'margin': round(margin, 1) if margin is not None else None,
            'cur_space': round(cur_space) if cur_space is not None else None,
            'cur_margin': round(cur_margin, 1) if cur_margin is not None else None,
        })
    return rows

def render_daily(rows, today):
    with_chg = [r for r in rows if r['chg'] is not None]
    g3 = [r for r in with_chg if r['grade'] == 3]
    g4 = [r for r in with_chg if r['grade'] == 4]
    idx3 = sum(r['chg'] for r in g3) / len(g3) if g3 else None
    idx4 = sum(r['chg'] for r in g4) / len(g4) if g4 else None

    # 今日行情表（按涨跌幅）
    tbody = []
    for r in sorted(with_chg, key=lambda x: -(x['chg'] or 0)):
        tbody.append('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td class="%s">%s</td></tr>' % (
            r['name'], r['grade'], r['latest'],
            r['th'] if r['th'] is not None else '-', r['tl'] if r['tl'] is not None else '-',
            round(r['prev']) if r['prev'] else '-', cls(r['chg']), pct_str(r['chg'])))

    # 涨跌榜 TOP5
    def top(n, rev):
        return sorted(with_chg, key=lambda x: x['chg'] or 0, reverse=rev)[:n]
    def board(lst):
        return ''.join('<tr><td>%s</td><td>%s</td><td class="%s">%s</td><td>%s</td></tr>' % (
            r['name'], r['grade'], cls(r['chg']), pct_str(r['chg']), r['latest']) for r in lst)
    up5, down5 = top(5, True), top(5, False)

    # 异动（振幅 TOP5）
    amp_rows = sorted([r for r in with_chg if r['amp'] is not None], key=lambda x: -(x['amp'] or 0))[:5]
    amp_tbody = ''.join('<tr><td>%s</td><td>%s</td><td class="%s">%s</td><td>%.0f%%</td></tr>' % (
        r['name'], r['grade'], cls(r['chg']), pct_str(r['chg']), r['amp']) for r in amp_rows)

    # 低价期 vs 日常期全表（按税后利润率）
    valid = [r for r in rows if r['margin'] is not None]
    valid.sort(key=lambda r: -(r['margin'] or -999))
    full_tbody = []
    for r in valid:
        full_tbody.append('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s / %s / %s</td><td>%s / %s / %s</td>'
                          '<td>%s</td><td class="%s">%s (%.1f%%)</td></tr>' % (
            r['name'], r['grade'], r['latest'],
            r['low_low'], r['low_avg'], r['low_high'],
            r['day_low'], r['day_avg'], r['day_high'],
            r['tax_net'], cls(r['margin']), r['profit'], r['margin']))
    pos_n = sum(1 for r in valid if (r['margin'] or 0) > 0)

    # 当前可入手清单（3级弹，现价 vs 日常期均价×0.87）
    cur_rows = [r for r in rows if r['grade'] == 3 and r['cur_space'] is not None]
    cur_rows.sort(key=lambda r: -(r['cur_margin'] or -999))
    cur_tbody = []
    for r in cur_rows:
        cur_tbody.append('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td class="%s">%s (%.1f%%)</td></tr>' % (
            r['name'], r['latest'], r['day_avg'], r['tax_net'],
            cls(r['cur_margin']), r['cur_space'], r['cur_margin']))
    cur_pos = sum(1 for r in cur_rows if (r['cur_margin'] or 0) > 0)

    # 消息面
    news = load_json('news.json') or {}
    season = news.get('season_label', '')
    nl = []
    for i, h in enumerate(news.get('headlines', []), 1):
        nl.append('<b>%d. %s</b> —— %s。<span class="src">（来源：%s）</span>' % (
            i, h.get('title',''), h.get('text',''), h.get('src','')))
    ol = ''.join('<li>%s：<b class="%s">%s</b> —— %s</li>' % (
        x.get('line','').split('：')[0], x.get('tone','gray'),
        x.get('line','').split('：')[-1], x.get('text','')) for x in news.get('outlook', []))
    risk = news.get('risk', '')

    wd = WEEKDAYS[datetime.date.fromisoformat(today).weekday()]
    low_tag = '低价期最后一天' if today >= LOW_END else ('低价期进行中' if today >= LOW_START else '日常期')

    return """<h2>今日行情表（{n} 种 3/4 级，按最新价涨跌幅）</h2>
<table><tr><th>子弹</th><th>等级</th><th>最新价</th><th>今高</th><th>今低</th><th>昨收(近似)</th><th>涨跌幅</th></tr>{tbody}</table>
<h2>涨幅榜 TOP5</h2>
<table><tr><th>子弹</th><th>等级</th><th>涨跌幅</th><th>最新价</th></tr>{up5}</table>
<h2>跌幅榜 TOP5</h2>
<table><tr><th>子弹</th><th>等级</th><th>涨跌幅</th><th>最新价</th></tr>{down5}</table>
<h2>异动与关注（振幅 TOP5）</h2>
<table><tr><th>子弹</th><th>等级</th><th>涨跌幅</th><th>振幅</th></tr>{amp_tbody}</table>
<h2>低价期 vs 日常期 行情表（按税后利润率排序）</h2>
<div class="sub">利润 = 日常期均价×0.87 − 低价期均价（低价期买入、日常期卖出，单发税后空间）</div>
<table><tr><th>子弹</th><th>等级</th><th>最新价</th><th>低价期 低/均/高</th><th>日常期 低/均/高</th><th>日常卖出到手</th><th>税后利润</th></tr>{full_tbody}</table>
<h2>当前可入手清单（3 级弹，现价 vs 日常期均价×0.87）</h2>
<div class="sub">现价买入 → 日常期卖出 的税后空间（正数=现在买划算，负=已无空间）</div>
<table><tr><th>子弹</th><th>当前价</th><th>日常期均价</th><th>税后保本线</th><th>税后空间/发</th></tr>{cur_tbody}</table>
<h2>消息面与价格走势预测</h2>
<div class="card">{nl}<br><b>🔮 价格升降可能性：</b><ul>{ol}</ul></div>
<div class="warn"><b>风险提示：</b> {risk}</div>""".format(
        n=len(with_chg), tbody=''.join(tbody), up5=board(up5), down5=board(down5),
        amp_tbody=amp_tbody, full_tbody=''.join(full_tbody), cur_tbody=''.join(cur_tbody),
        nl='<br>'.join(nl), ol=ol, risk=risk)

def render_market_overview(rows, rtype, today):
    with_chg = [r for r in rows if r['chg'] is not None]
    g3 = [r for r in with_chg if r['grade'] == 3]
    g4 = [r for r in with_chg if r['grade'] == 4]
    idx3 = sum(r['chg'] for r in g3) / len(g3) if g3 else None
    idx4 = sum(r['chg'] for r in g4) / len(g4) if g4 else None
    low_tag = '低价期最后一天' if today >= LOW_END else ('低价期进行中' if today >= LOW_START else '日常期')
    tags = []
    tags.append('<span class="tag">3级指数 %s</span>' % pct_str(idx3))
    tags.append('<span class="tag">4级指数 %s</span>' % pct_str(idx4))
    tags.append('<span class="tag">覆盖 %d 种 3/4 级子弹</span>' % len(rows))
    tags.append('<span class="badge b-up">%s</span>' % low_tag)
    return '<div class="card"><b>📊 市场概览</b><br>' + ' '.join(tags) + '</div>'

def main():
    rtype = sys.argv[1] if len(sys.argv) > 1 else 'daily'
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(BASE, 'reports', 'report_%s.html' % rtype)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    catalog = load_json('catalog.json') or {}
    history = load_json('history_latest.json') or {}
    if not history:
        print('ERROR: no data/history_latest.json'); sys.exit(1)

    rows = build_daily_rows(history, catalog)
    today = datetime.date.today().isoformat()
    wd = WEEKDAYS[datetime.date.fromisoformat(today).weekday()]
    title_map = {'daily': '行情日报', 'weekly': '行情周报', 'monthly': '行情月报'}
    t = title_map.get(rtype, '行情报告')

    body = render_market_overview(rows, rtype, today)
    if rtype == 'daily':
        body += render_daily(rows, today)
    else:
        # weekly/monthly：市场概览 + 全表 + 消息面
        valid = [r for r in rows if r['margin'] is not None]
        valid.sort(key=lambda r: -(r['margin'] or -999))
        ft = []
        for r in valid:
            ft.append('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s / %s / %s</td><td>%s / %s / %s</td>'
                      '<td>%s</td><td class="%s">%s (%.1f%%)</td></tr>' % (
                r['name'], r['grade'], r['latest'],
                r['low_low'], r['low_avg'], r['low_high'],
                r['day_low'], r['day_avg'], r['day_high'],
                r['tax_net'], cls(r['margin']), r['profit'], r['margin']))
        pos_n = sum(1 for r in valid if (r['margin'] or 0) > 0)
        body += '<h2>%s 全表：低价期 vs 日常期（按税后利润率排序）</h2><div class="sub">利润 = 日常期均价×0.87 − 低价期均价；低价期可买(税后正利润) <b class="pos">%d</b> 款</div>' % (t, pos_n)
        body += '<table><tr><th>子弹</th><th>等级</th><th>最新价</th><th>低价期 低/均/高</th><th>日常期 低/均/高</th><th>日常卖出到手</th><th>税后利润</th></tr>' + ''.join(ft) + '</table>'
        # 消息面
        news = load_json('news.json') or {}
        nl = []
        for i, h in enumerate(news.get('headlines', []), 1):
            nl.append('<b>%d. %s</b> —— %s。<span class="src">（来源：%s）</span>' % (i, h.get('title',''), h.get('text',''), h.get('src','')))
        ol = ''.join('<li>%s：<b class="%s">%s</b> —— %s</li>' % (
            x.get('line','').split('：')[0], x.get('tone','gray'),
            x.get('line','').split('：')[-1], x.get('text','')) for x in news.get('outlook', []))
        body += '<h2>消息面与价格走势预测</h2><div class="card">' + '<br>'.join(nl) + '<br><b>🔮 价格升降可能性：</b><ul>' + ol + '</ul></div>'
        body += '<div class="warn"><b>风险提示：</b> ' + news.get('risk','') + '</div>'

    pos_n_total = sum(1 for r in rows if (r['margin'] or 0) > 0)
    html = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>moligod {t} · {today}</title>
<style>
body{{font-family:'Microsoft YaHei',system-ui,sans-serif;background:#0e1420;color:#e6edf3;margin:0;padding:24px;line-height:1.6}}
.wrap{{max-width:1100px;margin:0 auto}}
h1{{font-size:22px;margin:0 0 4px}}
h2{{font-size:17px;border-left:4px solid #4a9eff;padding-left:10px;margin:30px 0 12px;color:#cfe3ff}}
.sub{{color:#8b98a9;font-size:12px;margin-bottom:10px}}
.tag{{display:inline-block;background:#1c2a44;color:#9ecbff;border:1px solid #2c4a7a;border-radius:4px;padding:2px 10px;font-size:12px;margin-right:8px}}
.badge{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:12px;margin:0 4px}}
.b-up{{background:#1e3a2f;color:#5ddb8e}}.b-down{{background:#3a1e24;color:#ff7d85}}
table{{width:100%;border-collapse:collapse;font-size:12.5px;margin:8px 0}}
th{{background:#16233a;color:#9ecbff;text-align:left;padding:7px 8px;border:1px solid #22314e}}
td{{padding:6px 8px;border:1px solid #1d2b44;text-align:left}}
tr:nth-child(even) td{{background:#101a2e}}
.pos{{color:#5ddb8e}}.neg{{color:#ff7d85}}.gray{{color:#8b98a9}}
.card{{background:#101a2e;border:1px solid #22314e;border-radius:8px;padding:14px 16px;margin:12px 0}}
.note{{background:#1a2438;border-left:4px solid #e0a63c;padding:10px 14px;border-radius:0 6px 6px 0;font-size:12.5px;margin:12px 0}}
.warn{{background:#2a1a20;border-left:4px solid #e0564a;padding:10px 14px;border-radius:0 6px 6px 0;font-size:12.5px;margin:12px 0}}
ul{{margin:6px 0;padding-left:20px}}
.src{{color:#6b7a8f;font-size:11px}}
</style></head><body><div class="wrap">
<h1>moligod {t} · {today}</h1>
<div class="sub">报告日期：{today}（{wd}）｜口径：低价期 {LOW} | 日常期 {DAY} | 出售到手=挂价×0.87（税13%）| SPIKE 不特殊处理 | 数据源 moligod.com 实时K线</div>
{body}
<div class="note">数据口径：行情单位为哈夫币；出售实际到手 = 挂单价 × 0.87（13% 交易税）；数据来自 moligod 公开行情，消息面来自公开网络信息（见各条来源），仅供游戏内交易参考。报告由 GitHub Actions 定时自动产出。</div>
</div></body></html>""".format(
        t=t, today=today, wd=wd, LOW='%s~%s' % (LOW_START[5:], LOW_END[5:]),
        DAY='%s~%s' % (DAY_START[5:], DAY_END[5:]), body=body)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print('REPORT', rtype, 'rows=', len(rows), '->', out)

if __name__ == '__main__':
    main()
