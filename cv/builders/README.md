# Builders 模块

把逐帧分析结果整理成前端和数据库需要的 JSON 结构。

| 文件 | 作用 |
| --- | --- |
| `match.py` | 组装比赛帧、战术、point 和 shot 数据 |
| `imputation.py` | 补全缺失的球场坐标，并生成补全报告 |
| `shots.py` | 关联击球、落点、球员和 point，生成最终记录 |

主流程一般按 `match` -> `imputation` -> `shots` 的顺序使用。这里负责数据整形，不应加入检测模型逻辑。
