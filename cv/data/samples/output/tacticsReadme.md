这份 JSON 是一个非常典型的**体育运动分析（网球）结构化数据**。它采用了分层设计：**元数据（Metadata）**、**统计概览（Analysis）**以及**核心事件流（Shots & Net Hits）**。

下面是为你准备的各字段详细说明文档（README）：

---

## 🎾 网球机器人分析数据 JSON 说明文档

### 1. 根节点字段 (Top-level)
| 字段 | 类型 | 含义 | 示例/备注 |
| :--- | :--- | :--- | :--- |
| `metadata` | Object | 视频与场地的基础全局配置。 | 包含版本、FPS、分辨率。 |
| `rally_analysis` | Object | 核心运算结果，包含回合统计与逐拍分析。 | 算法逻辑的主要输出。 |
| `net_hits` | Array | 记录网球“落网”或“触网”的特殊事件。 | 由 `net_hit` 模块判定生成。 |

---

### 2. 元数据 (`metadata`)
* **`court_dimensions`**: 场地物理尺寸（单位：米）。用于将像素坐标映射为实际物理坐标，从而计算球速。

---

### 3. 回合分析 (`rally_analysis`)
#### 统计概览 (Summary)
* **`p1/p2_distance_m`**: 该回合内 P1（底部）和 P2（顶部）球员的累计跑动距离。
* **`p1/p2_max_speed_kmh`**: 球员在该回合中的最高瞬间移动速度。
* **`termination_reason`**: 回合结束原因（如：`video_end` 视频结束、`out` 出界）。

#### 逐拍数据 (`rallies[].shots[]`)
这是你图片中字段的核心实现，记录了每一拍击球的细节：

| 字段 | 含义 | 说明 |
| :--- | :--- | :--- |
| `shot_index` | 拍数序号 | 本分球的第几拍。 |
| `player_id` | 击球者 ID | 1 为底部球员，2 为顶部球员。 |
| `shot_type` | 击球类型 | 算法分类结果（Serve/Forehand/Backhand/Smash 等）。 |
| **`hitter_position`** | **击球者位置** | 包含像素坐标 `pixel` [x, y] 和物理坐标 `court_m` [x, y]。 |
| **`ball_position`** | **击球瞬间球位** | 即“击球点”。 |
| `incoming_speed_kmh` | 来球速度 | 上一拍球飞行过程中的平均时速。 |
| `post_hit_speed_kmh` | 出球速度 | 本拍击球后球飞行的瞬间/平均时速。 |
| `next_bounce_frame` | 落地帧号 | 击球后，球第一次触地的帧数。 |
| `bounce_result` | 落地判定 | `in`（界内）、`out`（界外）、`net`（落网）。 |



---

### 4. 触网检测 (`net_hits`)
该字段用于记录球未过网的情况：
* **`confidence`**: 算法判定为落网的置信度。
* **`reason`**: 判定原因。例如 `reversed_near_net`（在球网附近发生了 $y$ 轴轨迹反转）+ `did_not_cross_net`（球没有越过球网中心线）。
* **`signed_distance_px`**: 球距离球网像素中心线的偏移量。

---

### 💡 核心设计逻辑（开发者必读）

1.  **像素与物理双坐标制**：
    所有位置字段（`hitter_position`, `ball_position` 等）均同时保留了 `pixel`（用于在视频上画框）和 `court_m`（用于计算速度和跑动距离）。
    * *注意：`court_m` 的原点 (0,0) 通常设定在球场的一个角点或中心点。*

2.  **状态机驱动**：
    `shot_phase`（击球阶段）隐含在 `shot_index` 和 `is_likely_serve` 中。第一拍且符合发球动作的被标记为 `Serve`。

3.  **时延/间隔分析**：
    `prev_shot_gap_sec` 用于分析球员的反应时间或回合节奏。



---
