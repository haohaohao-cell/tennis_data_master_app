# CV 实验模块

本目录用于验证网球检测、主轨迹选择和轨迹优化。实验逻辑验证稳定后，再迁移到 `cv/` 对应生产模块。

输入视频放在 `cv/data/input/`，模型权重放在 `cv/models/weights/`，生成的 JSON、CSV、图片和视频统一写入 `cv/data/output/`。运行文件不提交到 Git。

## 模块与边界

| 顺序 | 模块                                     | 输入                | 输出                                  | 当前边界                                         |
| ---- | ---------------------------------------- | ------------------- | ------------------------------------- | ------------------------------------------------ |
| 1    | `generate_stable_court_roi_overlay.py` | 视频、球场检测权重  | ROI 首帧预览、overlay 视频            | 只生成并验证固定 ROI，尚未接入 TrackNet 候选评分 |
| 2    | `generate_ball_coords_json.ipynb`      | 视频、TrackNet 权重 | 每帧候选 JSON、候选图和 overlay 视频  | 保留每帧全部候选，不执行时序主轨迹选择           |
| 3    | Viterbi 主轨迹选择                       | 每帧候选、ROI       | 单一主球轨迹                          | 尚未实现                                         |
| 4    | `trajectory_optimization_lab.ipynb`    | 已确定的单一主轨迹  | 优化轨迹、诊断图、CSV 和 overlay 视频 | 只负责异常点剔除与补点，不负责从多球中选主球     |
| 5    | `generate_hit_points_json.ipynb`       | 优化后的单一轨迹    | 轨迹突变点                            | 后续实验                                         |

## 为什么按这个顺序

### 1. 先生成并验证场地 ROI

并排球场的视频中，TrackNet 可能同时检测到目标场地、隔壁场地和场边静止的球。ROI 用来提供“候选是否位于目标场地”的空间先验，后续可以降低 ROI 外候选的得分。场地检测可能受遮挡、机位和相机移动影响，因此必须先通过首帧预览和完整 overlay 视频人工确认 ROI，再把它用于候选评分。当前脚本只生成和验证 ROI，尚未接入 TrackNet。

### 2. 再保留每帧全部 TrackNet 候选

这一阶段的目标是保存检测证据，而不是提前决定哪个点是主球。过早只保留一个候选会丢失真实球，后续算法也无法纠正错误选择。因此 JSON 中的 `candidates` 保存每帧全部候选及置信度，供 Viterbi 综合时序信息选择。兼容字段 `pixel` 只是该帧置信度最高的候选，不是经过时序选择的主轨迹。

### 3. 用 Viterbi 选择单一主球轨迹

逐帧最高置信候选可能在主球、静止球、隔壁场球和误检之间切换。Viterbi 需要同时考虑 TrackNet 置信度、ROI、预测位置、速度和加速度连续性、静止惩罚及缺失状态，以整段路径总分选择同一个运动目标。只有完成这一步，后续轨迹优化的输入才具有明确的主球身份。该模块目前尚未实现。

Viterbi 完成前，多球练习视频仍可通过 `pixel` 跑通后续流程，但输出不能视为可靠的主球轨迹，也不适合用来评价轨迹优化的准确性。

### 4. 对单一主轨迹剔除异常点并补点

即使已经选定主球，TrackNet 仍可能产生短时漏检、坐标尖刺和局部偏移。因此需要用运动连续性和 RANSAC 识别异常点，并在可信区间内补齐缺失坐标。这一步不再处理“哪个球是主球”的问题，否则无法判断错误来自主轨迹选择还是异常点优化。

### 5. 检测突变点并分段拟合

一次击球或落地会改变球的速度和方向，使整段轨迹不再服从同一个二次函数。如果跨越突变点直接执行 RANSAC，拟合曲线会在事件附近产生偏差，还可能把真实转向当作异常点删除。因此先定位轨迹突变点，以它们作为分段边界，再对每段连续运动分别拟合。当前 `generate_hit_points_json.ipynb` 只负责寻找分段边界，不判断突变属于击球还是落地。

## 最短运行流程

从仓库根目录运行。准备 Python 3.11 环境及 notebook、PyTorch、OpenCV 等项目依赖后，将视频和权重放到上述目录。

1. 生成并人工检查场地 ROI：

   ```bash
   python cv/experiments/generate_stable_court_roi_overlay.py \
     --input cv/data/input/match01.mp4
   ```

   默认生成 `match01_court_roi_first_frame.jpg` 和 `match01_court_roi_overlay.mp4`。
2. 启动 Jupyter：

   ```bash
   python -m jupyter lab
   ```

   运行 `generate_ball_coords_json.ipynb`。将 `INPUT_VIDEO_PATH` 指向输入视频；调试时可设置 `MAX_FRAMES = 300`，完整运行时设为 `None`。
3. 运行 `trajectory_optimization_lab.ipynb` 前，将 `MATCH_FRAMES_PATH` 改为上一步生成的 JSON，例如：

   ```python
   MATCH_FRAMES_PATH = CV_OUTPUT_DIR / "match01_ball_coords_raw.json"
   ```

   多球视频可以用于调试流程；只有输入已是单一主轨迹，或标准单球片段中已人工确认 `pixel` 始终对应主球时，才能用输出评价轨迹优化效果。

以 `match01.mp4` 为例，主要输出统一带有输入视频名：

- `match01_ball_coords_raw.json`
- `match01_ball_coords_raw_overlay.mp4`
- `match01_ball_coords_trajectory.png`
- `match01_xy_function_coordinates.png`
- `match01_ransac_trajectory_overlay.mp4`

现有缺陷、待开发项和验收测试见 [ISSUES.md](ISSUES.md)。

## 其他实验

| 文件 | 用途 |
| --- | --- |
| `generate_ball_candidates_json.ipynb` | 旧版多候选提取与可视化参考 |
