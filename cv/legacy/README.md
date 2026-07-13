# Legacy 模块

保存已经停用的旧版端到端推理，主要用于结果对照和旧调用兼容。

- `run_inference.py`：旧流程的完整实现。
- 新代码入口：`cv.pipeline.run_inference_v2`。
- 旧命令仍可通过 `python -m cv.scripts.run_inference` 调用。

不要在这里开发新功能；确认不再需要兼容后才能删除旧实现。
