# -*- coding: utf-8 -*-
"""score → revise → rescore 骨架的共用層。

設計原則:
- 打分器只負責「找出缺陷」,不決定門檻;分數與過關與否由這裡算,threshold 由 loop 決定。
- 每個缺陷都必須帶 fix(可執行的修正指示),否則 loop 沒辦法自動修。
- 輸出一律可轉 JSON,讓 loop 用程式判斷收斂,而不是靠人讀散文。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

# 嚴重度扣分權重。blocker 一個就足以壓到 75 分以下,且無論分數多高都不算過關。
WEIGHT = {'blocker': 25, 'major': 8, 'minor': 2}
SEVERITY_ORDER = {'blocker': 0, 'major': 1, 'minor': 2}


@dataclass
class Finding:
    id: str            # 檢查項代號,loop 用它來追蹤同一缺陷是否已修掉
    severity: str      # blocker | major | minor
    message: str       # 缺陷本身(客觀描述,不要寫成建議)
    where: str = ''    # 位置:表格編號/列號/段落前 30 字
    fix: str = ''      # 修正指示,要具體到可以直接動手

    def __post_init__(self):
        if self.severity not in WEIGHT:
            raise ValueError(f'unknown severity: {self.severity!r}')

    def to_dict(self):
        return dict(id=self.id, severity=self.severity, message=self.message,
                    where=self.where, fix=self.fix)


@dataclass
class Report:
    target: str
    scorer: str
    findings: list = field(default_factory=list)
    checks_run: list = field(default_factory=list)
    checks_skipped: dict = field(default_factory=dict)   # {check_id: 跳過原因}
    meta: dict = field(default_factory=dict)             # 打分器抓到的事實,供人核對

    # ---- 記錄 ----
    def add(self, id, severity, message, where='', fix=''):
        self.findings.append(Finding(id, severity, message, where, fix))
        return self

    def ran(self, check_id):
        if check_id not in self.checks_run:
            self.checks_run.append(check_id)
        return self

    def skip(self, check_id, reason):
        self.checks_skipped[check_id] = reason
        return self

    # ---- 計分 ----
    @property
    def score(self):
        return max(0, 100 - sum(WEIGHT[f.severity] for f in self.findings))

    @property
    def blockers(self):
        return [f for f in self.findings if f.severity == 'blocker']

    def passed(self, threshold=90):
        return not self.blockers and self.score >= threshold

    def sorted_findings(self):
        return sorted(self.findings, key=lambda f: (SEVERITY_ORDER[f.severity], f.id))

    # ---- 輸出 ----
    def to_dict(self, threshold=90):
        return dict(
            target=self.target, scorer=self.scorer,
            score=self.score, threshold=threshold, passed=self.passed(threshold),
            counts={s: sum(1 for f in self.findings if f.severity == s) for s in WEIGHT},
            findings=[f.to_dict() for f in self.sorted_findings()],
            checks_run=self.checks_run, checks_skipped=self.checks_skipped,
            meta=self.meta,
        )

    def to_json(self, threshold=90):
        return json.dumps(self.to_dict(threshold), ensure_ascii=False, indent=1)

    def render(self, threshold=90):
        mark = 'PASS' if self.passed(threshold) else 'FAIL'
        n = {s: sum(1 for f in self.findings if f.severity == s) for s in WEIGHT}
        out = [f'[{mark}] {self.scorer}  {self.score}/100 (門檻 {threshold})  '
               f'blocker {n["blocker"]} / major {n["major"]} / minor {n["minor"]}',
               f'   target: {self.target}']
        if self.meta:
            out.append('   -- 抓到的事實 --')
            for k, v in self.meta.items():
                out.append(f'      {k}: {v}')
        if self.findings:
            out.append('   -- 缺陷 --')
            for f in self.sorted_findings():
                out.append(f'   [{f.severity:<7}] {f.id}  {f.message}')
                if f.where:
                    out.append(f'             位置: {f.where}')
                if f.fix:
                    out.append(f'             修正: {f.fix}')
        if self.checks_skipped:
            out.append('   -- 跳過的檢查 --')
            for k, v in self.checks_skipped.items():
                out.append(f'      {k}: {v}')
        return '\n'.join(out)


# ---------- 共用小工具 ----------
def parse_num(s):
    """把儲存格文字轉成數字。'86,527'->86527 '26.65'->26.65 '－'/''/'立即'->None"""
    if s is None:
        return None
    t = str(s).strip().replace(',', '').replace('，', '').replace(' ', '')
    if not t or t in ('-', '－', '—', 'N/A', '立即', '不適用'):
        return None
    try:
        v = float(t)
    except ValueError:
        return None
    return int(v) if v == int(v) and '.' not in t else v


def close(a, b, tol=0.02):
    """相對誤差在 tol 以內視為相符。b 為 0 時退回絕對比較。"""
    if a is None or b is None:
        return False
    if b == 0:
        return abs(a) < 1e-9
    return abs(a - b) / abs(b) <= tol
