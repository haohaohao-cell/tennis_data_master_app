# CV 兼容脚本

本目录只保留公共入口、CLI 包装和历史导入兼容模块，业务实现位于 `cv` 下的领域包。

- `run_inference_v2.py`: 稳定推理入口，转发到 `cv.pipeline.inference`。
- `db_operations.py`: 稳定数据库入口，转发到 `cv.persistence.repository`。
- 其他文件用于保持原有命令与导入路径可用。

不要在兼容模块中添加算法逻辑。
