# -*- coding: utf-8 -*-
"""打分器:skill 本身的表現(regression eval)。

用途:改了某個 skill 的 prompt 之後,確認它在固定案例上有沒有變差。
程式不會自己去跑 skill(那要模型),它負責的是:
  1. 告訴 loop「哪些案例還沒跑」(case_not_run,blocker)
  2. 把已跑案例的輸出用可判定的規則打分

流程(由 loop 執行):
  py score.py skill_eval eval.json      → 列出未跑案例
  loop 依 case.prompt 實際執行 skill,把結果寫回 case.output
  py score.py skill_eval eval.json      → 重打分,直到過關

check 型別:
  must_include / must_not_include  : value 為子字串
  must_match   / must_not_match    : value 為 regex
  min_chars    / max_chars         : value 為整數,比對 output 長度
  file_exists                      : value 為路徑,檢查是否產出檔案
"""
from __future__ import annotations

import json
import os
import re

from scorelib import Report

DEFAULT_SEVERITY = {'must_include': 'major', 'must_not_include': 'major',
                    'must_match': 'major', 'must_not_match': 'major',
                    'min_chars': 'minor', 'max_chars': 'minor',
                    'file_exists': 'blocker'}


def score(path, **_):
    rep = Report(target=path, scorer='skill_eval')
    data = json.load(open(path, encoding='utf-8'))
    rep.meta['受測 skill'] = data.get('skill', '(未填)')
    cases = data.get('cases', [])
    rep.meta['案例數'] = len(cases)

    ran = 0
    for case in cases:
        cid = case.get('id', '?')
        out = case.get('output')
        if not out:
            rep.add('case_not_run', 'blocker', f'案例 {cid} 尚未執行',
                    where=case.get('prompt', '')[:60],
                    fix=f'依 prompt 實際執行 skill,把結果寫回 cases[{cid}].output 後重跑打分')
            continue
        ran += 1
        for chk in case.get('checks', []):
            _apply(rep, cid, out, chk)
    rep.meta['已執行案例'] = f'{ran}/{len(cases)}'
    rep.ran('skill_eval')
    return rep


def _apply(rep, cid, out, chk):
    kind = chk.get('type')
    val = chk.get('value')
    sev = chk.get('severity', DEFAULT_SEVERITY.get(kind, 'major'))
    ckid = chk.get('id', kind)
    where = f'案例 {cid}'
    note = chk.get('note', '')

    def fail(msg, fix):
        rep.add(ckid, sev, msg, where=where, fix=fix or note)

    if kind == 'must_include':
        if val not in out:
            fail(f'輸出未包含必要內容「{val}」', chk.get('fix', f'讓 skill 產出包含「{val}」'))
    elif kind == 'must_not_include':
        if val in out:
            fail(f'輸出包含不該出現的「{val}」', chk.get('fix', f'修正 skill 使其不再產生「{val}」'))
    elif kind == 'must_match':
        if not re.search(val, out):
            fail(f'輸出不符合樣式 /{val}/', chk.get('fix', ''))
    elif kind == 'must_not_match':
        m = re.search(val, out)
        if m:
            fail(f'輸出出現不該有的樣式 /{val}/ → {m.group()!r}', chk.get('fix', ''))
    elif kind == 'min_chars':
        if len(out) < int(val):
            fail(f'輸出僅 {len(out)} 字,未達 {val}', chk.get('fix', ''))
    elif kind == 'max_chars':
        if len(out) > int(val):
            fail(f'輸出 {len(out)} 字,超過 {val}', chk.get('fix', ''))
    elif kind == 'file_exists':
        if not os.path.exists(val):
            fail(f'預期產出的檔案不存在:{val}', chk.get('fix', '確認 skill 有實際寫檔'))
    else:
        rep.skip(ckid, f'未知的 check 型別 {kind!r}')
