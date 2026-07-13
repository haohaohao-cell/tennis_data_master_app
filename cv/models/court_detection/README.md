# Court Detection 模型

此模块定义球场关键点检测网络。

- `ConvBlock`：卷积、激活和批归一化基础块。
- `BallTrackerNet`：编码器/解码器式热图网络；名称沿用旧代码，实际用于球场关键点。
- 输出通道数对应要预测的关键点热图数量，主流程使用 `out_channels=15`。

模型权重由 `cv.config.DEFAULT_COURT_MODEL_PATH` 指定，后处理和单应矩阵计算位于 `cv.court`。
