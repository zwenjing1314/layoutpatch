# route-v2 外部测试来源与数据分工补充核实

> 本文件仅补充外部来源与只读验收证据。依据用户最新指示，另一个模型的现有代码、协议、data-roles-v1 划分和 regions-v1 产物保持原样，以其数据分工为标准；不生成替代划分。
> 非模型效果实验，不登记新的 EXP，不训练、不评分。运行结果补充在本文下方。

## 本轮补充命令登记

用户要求不改另一个模型的产物，本轮不修改其 `docs/02-commands.md`，仅在此登记新增补充检查。所有命令从项目根目录执行。

```powershell
uv run --offline --no-sync ruff check scripts/seal_route_v2_data.py
uv run --offline --no-sync pytest tests/datasets/test_route_v2_split.py tests/datasets/test_identity_verification.py tests/datasets/test_internal_identity.py
uv run --offline --no-sync python scripts/seal_route_v2_data.py
```

- 输入：现有划分/区域产物、身份审计报告、官方固定版本数据与已获取来源快照。只读校验，模型不加载。
- 输出：`experiments/route_v2_data/v1/` 的外部测试元数据清单、哈希回执和只读核查；原始网页/标注快照归档至 `artifacts/route_v2_data/source_archive_v1/`（不进Git）。不写原划分/区域产物。
- 验证：重建划分只写临时目录，逐字节对比既有proof；对源文件复核SHA256；外部1623题完整保留；核验训练页面排除标记。预计约1分钟。
- 失败处理：停止封存，不自动修改既有输入或换seed；已存在补充目录只验证相同内容，不覆盖。

## 结果

补充检查进行中；不把运行前的预期写作通过结果。
