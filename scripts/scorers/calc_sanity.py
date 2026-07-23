# -*- coding: utf-8 -*-
"""打分器:節能量試算的合理性。

輸入是一份 JSON(格式見 templates/calc.example.json)。
只查「這個數字有沒有可能是打錯的」,不查商業判斷。
區間來自實際輔導案的經驗值,超出就要求在報告裡寫出依據。
"""
from __future__ import annotations

import json

from scorelib import Report, close

# (欄位, 合理下限, 合理上限, 嚴重度, 說明)
RANGES = [
    ('hours',   1,    8760, 'blocker', '年運轉時數'),
    ('load',    0.30, 1.00, 'major',   '負載率'),
    ('decay',   0.005, 0.02, 'major',  '每年效率衰退率'),
    ('age',     0,    40,   'major',   '機齡(年)'),
    ('kw_rt',   0.40, 2.00, 'major',   '每冷凍噸耗電量 kW/RT'),
    ('cspf',    2.00, 8.00, 'major',   '季節性能因數 CSPF'),
    ('price',   2.00, 7.00, 'major',   '平均電價 元/kWh'),
]
# 單價慣例(ESCO 成本慣例):kind -> (基準量欄位, 單價)
UNIT_COST = {'vfd': ('hp', 3000), 'pump': ('lpm', 28), 'chiller': ('rt', 20000)}
CO2 = 0.466      # kgCO2e/kWh,能源署 114 年度電力排碳係數


def score(path, threshold=None, **_):
    rep = Report(target=path, scorer='calc_sanity')
    data = json.load(open(path, encoding='utf-8'))
    price = data.get('price')
    rep.meta['案名'] = data.get('case', '(未填)')
    rep.meta['平均電價'] = price

    _range_check(rep, {'price': price}, '全案')
    for i, m in enumerate(data.get('measures', []), 1):
        tag = f"措施{i} {m.get('name', '')[:24]}"
        _range_check(rep, m, tag)
        _energy_math(rep, m, tag, m.get('price', price))
        _unit_cost(rep, m, tag)
    if not data.get('measures'):
        rep.skip('energy_math', 'JSON 裡沒有 measures')
    return rep


def _range_check(rep, m, tag):
    rep.ran('range_check')
    for key, lo, hi, sev, label in RANGES:
        v = m.get(key)
        if v is None:
            continue
        if not (lo <= v <= hi):
            rep.add('range_check', sev,
                    f'{label} = {v},落在合理區間 {lo}~{hi} 之外',
                    where=tag,
                    fix=f'確認 {key} 是否打錯;若確實如此,請在報告內文寫出依據')
    h = m.get('hours')
    if h is not None and h > 3000 and m.get('kind') == 'school':
        rep.add('hours_school', 'minor',
                f'學校型場域運轉時數 {h} h/年偏高(扣寒暑假與例假日後通常 ≤ 2,000)',
                where=tag, fix='確認是否已扣除寒暑假與例假日')


def _energy_math(rep, m, tag, price):
    rep.ran('energy_math')
    before, after = m.get('kwh_before'), m.get('kwh_after')
    if before is None or after is None:
        return rep.skip('energy_math', f'{tag} 缺 kwh_before / kwh_after')
    if after > before:
        rep.add('energy_math', 'blocker',
                f'改善後耗電量 {after:,} 大於改善前 {before:,}',
                where=tag, fix='檢查改善前後的效率值是否寫反')
        return
    save = before - after
    rate = save / before * 100 if before else 0
    rep.meta[f'{tag} 推算'] = (f'節電 {save:,} kWh/年、節能率 {rate:.2f}%')

    if m.get('save') is not None and not close(m['save'], save, 0.005):
        rep.add('energy_math', 'blocker',
                f'申報節電量 {m["save"]:,} 與「改善前－改善後」推得的 {save:,} 不符',
                where=tag, fix=f'把節電量改為 {save:,}')
    if rate > 70:
        rep.add('rate_too_high', 'major',
                f'節能率 {rate:.1f}% 過高,審查會要求佐證',
                where=tag, fix='檢查改善前效率是否推估過差;或補上實測值作為依據')

    if price:
        money = save * price
        if m.get('money') is not None and not close(m['money'], money, 0.02):
            rep.add('money_math', 'major',
                    f'年節費 {m["money"]:,.0f} 與「節電量×電價{price}」推得的 {money:,.0f} 不符',
                    where=tag, fix=f'把年節費改為 {money:,.0f} 元')
        inv = m.get('invest')
        if inv and money > 0:
            pay = inv / money
            rep.meta[f'{tag} 回收年限'] = f'{pay:.2f} 年'
            if m.get('payback') is not None and not close(m['payback'], pay, 0.02):
                rep.add('payback_math', 'major',
                        f'回收年限 {m["payback"]} 與「投資÷年節費」推得的 {pay:.2f} 不符',
                        where=tag, fix=f'把回收年限改為 {pay:.2f} 年')
            if pay > 50 and not m.get('long_payback_ack'):
                rep.add('payback_too_long', 'major',
                        f'回收年限 {pay:.1f} 年,不具經濟效益',
                        where=tag,
                        fix='改列為運轉管理案,或在措施表內明寫「主要效益為可靠度、'
                            '節費為附帶效益」並於 JSON 設 long_payback_ack=true 抑制本項')
            elif 15 < pay <= 50:
                rep.add('payback_long', 'minor',
                        f'回收年限 {pay:.1f} 年偏長',
                        where=tag, fix='確認投資費用是否高估,或說明非經濟性效益')
    if m.get('co2') is not None:
        c = save * CO2 / 1000
        if not close(m['co2'], c, 0.02):
            rep.add('co2_math', 'minor',
                    f'減碳量 {m["co2"]} 與「節電量×{CO2}÷1000」推得的 {c:.2f} 不符',
                    where=tag, fix=f'把減碳量改為 {c:.2f} tCO2e/年')


def _unit_cost(rep, m, tag):
    rep.ran('unit_cost')
    for item in m.get('unit_costs', []):
        kind = item.get('kind')
        if kind not in UNIT_COST:
            continue
        field, rate = UNIT_COST[kind]
        qty, cost = item.get(field), item.get('cost')
        if not qty or cost is None:
            continue
        ref = qty * rate
        if not close(cost, ref, 0.30):
            rep.add('unit_cost', 'minor',
                    f'{kind} 報價 {cost:,.0f} 元與慣例值({field}{qty}×{rate}={ref:,.0f})'
                    f'差距超過 30%',
                    where=tag,
                    fix=f'確認報價;若確為特殊規格,請在投資費用說明中寫出原因')
