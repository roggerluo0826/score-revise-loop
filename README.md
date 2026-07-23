# 打分修改迴圈 (score-revise-loop)

Claude Code skill:對產出物跑「**打分 → 修正 → 重打分**」,直到程式判定過關為止。

一份產出物好不好,不該由模型在對話裡自己說「我覺得可以了」。這個 skill 的核心是把
**收斂條件外包給程式**——打分器輸出分數與缺陷清單(每個缺陷都帶可執行的修正指示),
模型照著修、重跑,用離開碼決定要不要再跑一輪。

## 骨架

```
py score.py <scorer> <target> [--json]
   ├─ docx_report   節能報告 / ESCO 計畫書 .docx
   ├─ calc_sanity   節能量試算 .json
   └─ skill_eval    skill 迴歸測試 .json
```

- 缺陷分三級,扣分 `blocker 25` / `major 8` / `minor 2`,滿分 100
- **過關 = 零 blocker 且分數 ≥ 門檻(預設 90)**
- 離開碼 `0` 過關 / `1` 未過關 / `2` 執行錯誤
- 停止條件:過關、跑滿 5 輪、或連續 2 輪分數沒上升

## 三個打分器

| 打分器 | 對象 | 最有價值的檢查 |
|---|---|---|
| `docx_report` | 報告 docx | **獨立驗算**摘要表 vs 改善措施建議表的數字一致性、小計＝各列加總(blocker);節能率＝節電量÷本項耗能量、回收年限＝投資÷節能效益(major) |
| `calc_sanity` | 試算 JSON | 參數區間(運轉時數/負載率/衰退率/kW·RT⁻¹/CSPF/電價)、算式自洽、設備單價慣例 |
| `skill_eval` | skill 迴歸 | 標出未執行案例;對已填入 output 的案例套 must_include / must_not_match / min_chars 等規則 |

前兩個的價值在於**它不看你寫了什麼,它自己把表格裡的數字讀出來重算一遍**。

## 用法

```bash
set PYTHONUTF8=1

# 報告 docx
py scripts/score.py docx_report 報告.docx \
    --forbid 舊客戶名,舊地址 --own 本案機構全名 --allow 執行單位公司名

# 試算合理性(範本見 templates/calc.example.json)
py scripts/score.py calc_sanity 試算.json

# skill 迴歸測試(範本見 templates/eval.example.json)
py scripts/score.py skill_eval eval.json

# 兩個一起跑
py scripts/score.py all 報告.docx --calc 試算.json --json
```

Windows 繁體中文環境務必先設 `PYTHONUTF8=1`,否則讀 UTF-8 檔會炸在 cp950。

## 新增打分器

在 `scripts/scorers/` 放一個模組,提供 `score(path, **kwargs) -> Report`,
再到 `scripts/score.py` 的 `SCORERS` 註冊。要用到的 API 只有一個:

```python
rep.add(id, severity, message, where, fix)
```

`fix` 一定要寫成「可以直接動手做」的指示,否則迴圈修不動它。

## 相依

Python 3 + `python-docx`(僅 `docx_report` 需要)。

## 授權

MIT
