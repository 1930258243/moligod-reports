# -*- coding: utf-8 -*-
"""cloud_push.py — 微信推送报告摘要+HTML/PDF链接（Server酱）
用法: SCT_KEY=xxx python cloud_push.py [daily|weekly|monthly] [date]
从 reports/{日报|周报|月报}_{date}.html 提取摘要，推送标题+摘要+在线链接。
"""
import json, os, sys, re, datetime, urllib.request, urllib.parse

BASE = os.path.dirname(os.path.abspath(__file__))
PAGES = 'https://1930258243.github.io/moligod-reports/reports/'
TYPE_MAP = {'daily': '日报', 'weekly': '周报', 'monthly': '月报'}

def push(key, title, desp):
    url = 'https://sctapi.ftqq.com/%s.send' % key
    data = urllib.parse.urlencode({'title': title, 'desp': desp}).encode('utf-8')
    req = urllib.request.Request(url, data=data)
    resp = json.loads(urllib.request.urlopen(req, timeout=30).read().decode('utf-8'))
    return resp

def extract_overview(html):
    """从报告 HTML 提取市场概览 tags 和可入手 TOP"""
    m = re.search(r'<b>📊 市场概览</b><br>(.*?)</div>', html, re.S)
    tags = []
    if m:
        tags = re.findall(r'<span class="tag">(.*?)</span>', m.group(1))
    # 可入手清单 TOP5（3级弹）
    top = []
    m2 = re.search(r'<h2>当前可入手清单.*?</table>', html, re.S)
    if m2:
        seg = m2.group(0)
        for row in re.findall(r'<tr><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td><td[^>]*>(.*?)</td></tr>', seg)[:5]:
            name, cur, dayavg, taxnet, space = row
            top.append((name, cur, space))
    return tags, top

def main():
    rtype = sys.argv[1] if len(sys.argv) > 1 else 'daily'
    date = sys.argv[2] if len(sys.argv) > 2 else datetime.date.today().isoformat()
    key = os.environ.get('SCT_KEY', '')
    if not key:
        print('NO_SCT_KEY'); sys.exit(1)
    label = TYPE_MAP.get(rtype, '日报')
    fname = '%s_%s' % (label, date)
    html_path = os.path.join(BASE, 'reports', fname + '.html')
    if not os.path.exists(html_path):
        print('NO_REPORT', html_path); sys.exit(1)
    html = open(html_path, encoding='utf-8').read()
    tags, top = extract_overview(html)
    lines = ['**%s · %s**' % (label, date)]
    lines.append('')
    if tags:
        lines.append('市场概览：')
        for t in tags:
            lines.append('- ' + t)
    lines.append('')
    if top:
        lines.append('当前可入手 TOP%d（3级弹，现价→日常卖税后空间）：' % min(len(top), 5))
        for i, (n, cur, sp) in enumerate(top, 1):
            lines.append('%d. %s：现价%s，空间%s' % (i, n, cur, sp))
    lines.append('')
    lines.append('📄 完整报告 HTML：%s%s.html' % (PAGES, fname))
    lines.append('📄 PDF 版：%s%s.pdf' % (PAGES, fname))
    desp = '\n'.join(lines)
    title = 'moligod %s %s' % (label, date)
    resp = push(key, title, desp)
    code = resp.get('code')
    if code == 0:
        print('PUSH_OK pushid=', resp.get('data', {}).get('pushid'))
    else:
        print('PUSH_FAIL', resp)
        sys.exit(1)

if __name__ == '__main__':
    main()
