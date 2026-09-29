# 融合形状 smoke test

定向命令：`uv run pytest tests/retrieval/test_fusion_shapes.py -q`。结果：5 passed。

全仓命令：`./tasks.ps1 check`。结果：被既有 ruff 错误阻塞，pytest 未执行。本轮新增文件单独 ruff 通过，定向 mypy 通过。

既有错误，本轮未修改：
- `scripts/_encode_dude_train_dev.py:9`，I001。
- `scripts/_fill_mixed_missing_pages.py:6`，I001。
- `scripts/train_phase2r.py:196`、`:197`，F821，`query_vecs`。
- `scripts/train_phase2r.py:200`，F821，两处 `ranker`。
- `scripts/train_phase2r.py:319`，F841，`question`。
- `scripts/train_phase2r_arxivqa_notext.py:34`，F401，`QueryRecord`。
- `scripts/train_phase2r_arxivqa_notext.py:197`、`:198`，F821，`query_vecs`。
- `scripts/train_phase2r_arxivqa_notext.py:201`，F821，两处 `ranker`。
- `scripts/train_phase2r_arxivqa_notext.py:322`，F841，`question`。

输入输出形状：随机 `P:[2,8,128]`，输出 `[2,8,128]`。

空 patch 保持原值：是。

gate 初始值：bias=-3，`sigmoid(-3)=0.04742587357759476`。

参数量：nodes 63360，local fusion 82818，总计 146178。

随机输入未产生 NaN。

未进行训练。

test_eval 未读取。

显存仍未知。

正式训练未批准。
