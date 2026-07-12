# 轨迹实验说明

本目录用于调试网球轨迹、击球点和落点检测。实验依赖 `cv` 包中的模型与工具，生成的中间文件统一写入 `cv/data/output/`；该目录是运行时目录，不纳入 Git。

## 推荐启动顺序

请在仓库根目录启动 Jupyter，确保 notebook 可以导入 `cv`：

```bash
jupyter lab
```

然后按以下顺序运行 notebook。每个 notebook 都应从上到下执行，后一个 notebook 依赖前一个 notebook 生成的文件。

### 1. 提取和清理初始坐标

文件：`generate_ball_coords_json.ipynb`

这个 notebook 使用 TrackNet 对视频逐帧检测网球，生成候选点并选择一条时间上连续的主球轨迹。处理重点包括：

- 从三帧输入中提取网球候选坐标和置信度；
- 过滤明显不可能的候选点和噪声；
- 在同一画面存在多个候选点时，选择更符合时间连续性的主球轨迹；
- 过滤其他场地或画面中非当前比赛网球的候选点，为后续轨迹拟合保留更干净的输入。

主要输出：

- `cv/data/output/ball_coords_raw.json`
- `cv/data/output/ball_coords_match_frames.json`
- `cv/data/output/ball_coords_raw_overlay.mp4`
- `cv/data/output/ball_candidates_overlay.mp4`

先检查 overlay 视频，确认保留下来的坐标基本对应当前场地的网球，再进入下一步。

### 2. 初步 RANSAC 轨迹处理

文件：`trajectory_optimization_lab.ipynb`

这个 notebook 读取第一步的坐标，对整段轨迹进行初步 RANSAC/二次曲线拟合，并对缺失点进行初步补点。它的主要用途是：

- 观察原始轨迹中的离群点和缺失区间；
- 用抛物线模型估计相邻帧之间的合理轨迹；
- 生成后续事件检测可以使用的初步轨迹候选。

主要输出通常包括：

- `cv/data/output/winransac_initial_trajectory_candidate.csv`
- `cv/data/output/winransac_trajectory_candidate.csv`
- 对应的轨迹可视化或调试结果。

这一步的结果是初步结果，不应被理解为最终的完整轨迹。特别是击球和落点附近可能仍然存在较大残差。

### 3. 检测突变点并按轨迹分段

文件：`generate_hit_points_json.ipynb`

这个 notebook 在原始轨迹或初步 RANSAC 轨迹上检测击球点和落点等突变点，并将候选点聚合成最终的事件点。检测逻辑主要比较当前坐标与前后窗口均值的变化，识别运动方向或速度发生明显变化的帧。

它随后以这些事件点作为轨迹边界，对每一段轨迹单独执行 RANSAC，并进行段内补点。主要输出包括：

- `cv/data/output/hit_points_mean_reversal.json`
- `cv/data/output/winransac_segmented_trajectory_candidate.csv`
- `cv/data/output/hit_points_mean_reversal_overlay.mp4`

## 为什么不能直接对整段轨迹做 RANSAC

网球轨迹在两个连续事件之间通常可以近似为一段较平滑的二次曲线。但击球和落点会造成轨迹的突变：

- 击球时，球的速度和方向发生变化；
- 落地时，球的垂直运动和水平运动状态发生变化；
- 两个事件前后的轨迹不属于同一个简单的二次函数。

因此，如果把包含击球点、落点的整段轨迹直接交给 RANSAC，单个模型需要同时解释多个不同运动阶段。结果通常会出现以下问题：

- 突变点被误判为离群点；
- 拟合曲线在事件附近偏离真实轨迹；
- 补点会跨越事件边界，产生不符合物理运动的坐标；
- 一个阶段的曲线会影响另一个阶段的拟合参数。

当前方案是先检测事件，再将每两个相邻事件之间的轨迹视为独立片段，最后对每个片段分别进行 RANSAC。这样每个模型只需要拟合一个相对连续的运动阶段，能够更稳定地完成离群点过滤和缺失点补全，同时保留击球点和落点本身作为轨迹边界。

## 调试与参数实验

文件：`testransac.ipynb`

这个 notebook 用于独立测试 RANSAC 参数、拟合效果和轨迹可视化。它不是主流程的必需步骤。建议在主流程产物已经生成后，用它比较不同阈值、迭代次数和补点策略，再将确认后的参数同步回主 notebook。

## 运行注意事项

- 运行前确认 `cv/models/weights/model_best.pt` 存在；模型权重默认不纳入 Git，需要在本地准备。
- 修改 notebook 中的视频路径、输入 JSON 路径或输出路径时，优先使用 `cv.config` 中的目录配置。
- 如果第一步的候选点明显包含其他场地网球或大量噪声，不要直接调高 RANSAC 阈值；应先检查候选筛选和主轨迹选择。
- 如果第二步的整段拟合在击球或落点附近残差很大，这是预期现象，应继续执行第三步的事件分段处理。
- 每次重新运行时，建议清理或确认 `cv/data/output/` 中的旧 CSV/JSON，避免 notebook 读取到上一次实验的结果。
