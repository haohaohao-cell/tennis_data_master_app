# CV 模块

## 稳定接口

- `cv.pipeline.run_inference_v2`: 后端推理入口。
- `cv.cli.inference`: 唯一的生产命令行入口；`cv.scripts.run_inference_v2` 仅保留兼容调用。
- `cv.scripts.db_operations.TennisAnalysisRepository`: SQLite 访问入口。

`cv/scripts` 是兼容层，不应继续放置业务实现。新增代码按职责放入 `pipeline`、`segmentation`、`builders`、`tracking`、`court`、`events`、`analytics`、`persistence`、`visualization` 或 `io`。

## 约束

- 不从内部领域包反向导入 `cv.scripts`。
- 路径统一来自 `cv.config`，不要修改 `sys.path` 或依赖当前工作目录。
- 运行输入输出使用 `cv/data/input` 和 `cv/data/output`。
- 模型实现放在 `cv/models`，notebook 放在 `cv/experiments`。
- shots、points 和 match_frames 的公共字段属于兼容契约。
