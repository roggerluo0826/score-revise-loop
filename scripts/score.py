# -*- coding: utf-8 -*-
"""score → revise → rescore 骨架的入口。

用法(Windows 繁中請先 set PYTHONUTF8=1):
    py score.py docx_report  報告.docx [--forbid 舊客戶名,舊地址] [--own 本案機構全名]
                                       [--master 格式母版.docx]
    py score.py calc_sanity  試算.json
    py score.py skill_eval   eval.json
    py score.py all          報告.docx --calc 試算.json

選項:
    --threshold N   過關門檻分數,預設 90
    --json          輸出 JSON(給 loop 判斷收斂用),不加就輸出人看的文字
    --min-chars N   現況說明/改善方案的字數下限,預設 200

離開碼:0 = 過關,1 = 未過關,2 = 執行錯誤(loop 用它判斷是否收斂)。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, 'scorers'))

import docx_report          # noqa: E402
import calc_sanity          # noqa: E402
import skill_eval           # noqa: E402

SCORERS = {'docx_report': docx_report.score,
           'calc_sanity': calc_sanity.score,
           'skill_eval': skill_eval.score}


def main(argv=None):
    ap = argparse.ArgumentParser(description='score → revise → rescore 打分器')
    ap.add_argument('scorer', choices=list(SCORERS) + ['all'])
    ap.add_argument('target')
    ap.add_argument('--calc', help='scorer=all 時附帶的試算 JSON')
    ap.add_argument('--forbid', default='', help='舊客戶字串,逗號分隔')
    ap.add_argument('--own', default=None, help='本案機構全名,用來判定機構名殘影')
    ap.add_argument('--allow', default='', help='允許出現的其他機構名(執行單位等),逗號分隔')
    ap.add_argument('--master', default=None, help='格式母版 docx,用來比對自動編號等格式慣例')
    ap.add_argument('--threshold', type=int, default=90)
    ap.add_argument('--min-chars', type=int, default=200)
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args(argv)

    kw = dict(forbid=[s for s in a.forbid.split(',') if s.strip()],
              allow=[s for s in a.allow.split(',') if s.strip()],
              own_name=a.own, min_chars=a.min_chars, master=a.master)

    jobs = []
    if a.scorer == 'all':
        jobs.append(('docx_report', a.target))
        if a.calc:
            jobs.append(('calc_sanity', a.calc))
    else:
        jobs.append((a.scorer, a.target))

    reports = []
    for name, target in jobs:
        if not os.path.exists(target):
            print(f'找不到檔案:{target}', file=sys.stderr)
            return 2
        reports.append(SCORERS[name](target, **kw))

    if a.json:
        payload = [r.to_dict(a.threshold) for r in reports]
        print(json.dumps(payload if len(payload) > 1 else payload[0],
                         ensure_ascii=False, indent=1))
    else:
        for r in reports:
            print(r.render(a.threshold))
            print()

    return 0 if all(r.passed(a.threshold) for r in reports) else 1


if __name__ == '__main__':
    sys.exit(main())
