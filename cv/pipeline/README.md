# Pipeline 模块

编排一次完整的视频分析，是后端调用 CV 能力的主要入口。

```python
from cv.pipeline import run_inference_v2

shots, points = run_inference_v2("match.mp4")
```

流程依次完成球场与球员检测、球跟踪、事件识别、统计计算、point 分段、坐标补全以及 shot/point 数据构建。默认只返回内存中的 `(shots, points)`；是否保存中间或最终 JSON 由参数控制。

模型路径集中在 `cv.config`，命令行入口位于 `cv.cli.inference`。
