---
name: score-revise-loop
description: 打分修改迴圈 — 對產出物跑「打分 → 修正 → 重打分」直到過關或跑滿輪數。支援三種打分器:節能報告/ESCO計畫書 docx(docx_report)、節能量試算合理性(calc_sanity)、skill 表現迴歸測試(skill_eval)。當使用者說「跑打分」「打分修改」「檢查這份報告到過關」「幫我跑 loop」「送審前把它跑到過關」「這份計畫書幾分」「跑 eval 看 skill 有沒有變差」時使用此技能。
---

# 打分修改迴圈

一份產出物好不好,不能由我在對話裡說「我覺得可以了」。這個 skill 的重點是把
**收斂條件外包給程式**:打分器吐出分數與缺陷清單,我照著修,再重跑,直到程式說過關。

## 骨架

```
score.py <scorer> <target> [--json]
   │
   ├─ docx_report   節能報告 / ESCO 計畫書 .docx
   ├─ calc_sanity   節能量試算 .json
   └─ skill_eval    skill 迴歸測試 .json
```

- 每個缺陷是一個 **Finding**:`id / severity / message / where / fix`。
- 嚴重度扣分:`blocker 25`、`major 8`、`minor 2`,滿分 100。
- **過關 = 沒有任何 blocker 且分數 ≥ 門檻(預設 90)**。
- 離開碼:`0` 過關、`1` 未過關、`2` 執行錯誤。

## 迴圈協定(照做,不要自由發揮)

1. **先打一次基準分**,把分數與缺陷數回報給使用者,不要先改。
2. 進迴圈,每輪:
   1. `py score.py <scorer> <target> --json` 取得 findings。
   2. **依 severity 由重到輕修**,一次修完該輪所有 blocker 與 major;minor 可留到最後一輪。
   3. 每個 Finding 的 `fix` 欄就是修正指示,照著做;**不要為了衝分數而動內容的實質**
      (例如不可以把字數不足的段落用空話灌到 200 字)。
   4. 重跑打分。
3. **停止條件**(先到先停):
   - 過關(exit 0);或
   - 跑滿 **5 輪**;或
   - 連續 2 輪分數沒有上升(卡住了)。
4. 停止後回報:基準分 → 最終分、每輪修了什麼、**還沒修掉的缺陷與原因**。

### 三條硬規矩

- **修 docx 一律另存遞增版號**,絕不覆蓋輸入檔(`_v2`、`_v3`…)。使用者手改過的檔更是如此。
- **打分器說不出口的,不要自己加戲**。程式沒抓到的問題可以另外提,但不要混進分數裡。
- **改不掉的要講**。有些 finding 是刻意為之(例如回收年限 194 年是使用者指定保留),
  這種要在回報中明列「已知且刻意保留」,不要偷偷放著假裝沒看到。

## 三個打分器

### docx_report — 報告 docx

| 檢查 | 嚴重度 | 抓什麼 |
|---|---|---|
| `stale_client` | blocker | 母版舊客戶字串殘留(需 `--forbid`) |
| `stale_client_auto` | minor | 自動偵測文中出現的機構名,非本案者提報(regex 有誤差,只當提示;真正把關靠 `--forbid`) |
| `summary_consistency` | blocker | 摘要表各列 vs 改善措施建議表的節電量/效益/投資/回收 |
| `summary_subtotal` | blocker | 小計 = 各列加總;加權回收 = 總投資÷總效益 |
| `rate_mismatch` | major | 節能率 ≠ 節電量÷本項耗能量 |
| `payback_mismatch` | major | 回收年限 ≠ 投資÷節能效益 |
| `section_min_chars` | major | 現況說明/改善方案 < 200 字 |
| `heading_style` / `heading_outline` | major | 章標題樣式不一致、或樣式沒有大綱階層(F9 後會掉章) |
| `placeholder` | major | 殘留「待補」「TBD」「XXX」 |
| `numbering_missing` | major | 母版的措施表內文有自動編號、本檔卻沒有(`set_cell_text()` 會弄丟) |
| `numbering_partial` | major | 同一節內有段落漏掉編號 |
| `numbering_shared_numid` | major | 不同節共用同一個 numId,編號不會重新從 1 起算 |
| `font_uniformity` | minor | 同一張表格內混用多種字型/字級 |
| `halfwidth_comma` | minor | 中文敘述用半形逗號 |
| `integer_kwh` | minor | 耗電量欄出現小數 |

用法:
```
py score.py docx_report 報告.docx --forbid 舊客戶名,舊地址 --own 本案機構全名 \n    --allow 執行單位公司名 --master 格式母版.docx
```

`--master` 是格式母版拷貝案型的關鍵:母版就是格式的標準答案,給了它就能比對
「母版有、本檔沒有」這類肉眼難察的格式流失(自動編號是最典型的一項——編號是 Word
算出來的,不在文字裡,傾印文字完全看不出差別)。

### calc_sanity — 試算合理性

輸入 JSON(範本見 `templates/calc.example.json`)。查區間(運轉時數、負載率、衰退率、
kW/RT、CSPF、電價)、查算式自洽(節電量、節費、回收年限、減碳量)、查單價慣例
(VFD=HP×3000、泵=LPM×28、主機=RT×2萬,偏離 30% 提報)。

回收年限 > 50 年會出 major;若是刻意保留,在該措施加 `"long_payback_ack": true` 抑制。

### skill_eval — skill 迴歸測試

輸入 JSON(範本見 `templates/eval.example.json`)。程式**不會自己跑 skill**,
它只做兩件事:標出「尚未執行」的案例(blocker),以及對已填入 `output` 的案例套規則。

迴圈:打分 → 看哪些案例 `case_not_run` → 依 `prompt` 實際執行 skill → 把結果寫回
`cases[].output` → 重打分。改了 skill 的 prompt 之後,把所有 `output` 清空重跑,
比較前後分數,就知道有沒有改壞。

## 新增打分器

在 `scripts/scorers/` 放一個模組,提供 `score(path, **kwargs) -> Report`,
再到 `score.py` 的 `SCORERS` 註冊。`Report.add(id, severity, message, where, fix)`
就是全部要用的 API,`fix` 一定要寫,否則迴圈修不動它。
