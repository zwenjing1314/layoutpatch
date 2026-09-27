# 编码探针（2026-09-26）

> 只批探针，不批全量。本页不是开训许可。未启动 `scripts/train_phase2r.py`，未读 `test_eval`，未改 `recall_layout`，未下载新模型。

## 1. 去重页数口径

范围都是 `train_fit` + `train_dev` 的正页 + 负页。两套数差在文档名怎么切，不在页图有没有。

| 口径 | 去重页 | 怎么切文档名 | 状态 |
| --- | ---: | --- | --- |
| 旧 | 55894 | `Path.stem`：从最后一个点截断 | 作废，不再使用 |
| 现行 | 63064 | 只去掉结尾 `.pdf`，大小写不敏感 | 本页唯一计数 |

`Path.stem` 会把带点的文档名切短。`1308.1101` 变成 `1308`，不同文档并成同一个键，去重页被少计。现行口径不切这个点。页图在 `data/raw/mmdocir_train/hf_hub/parquet/`，7 个 parquet 都在。

| 项 | 数 |
| --- | ---: |
| 去重页 | 63064 |
| 候选框 | 647553 |
| 0 框页 | 42 |

分域命中页 / 框 / 0 框页：ArxivQA 8344 / 66501 / 3，DUDE 3782 / 29859 / 21，MP-DocVQA 4927 / 38982 / 13，SciQAG 4438 / 46728 / 0，SlideVQA 13300 / 60555 / 4，TAT-DQA 6102 / 57149 / 1，Wiki-ss 22171 / 347779 / 0。七域相加 63064，与去重页一致。

## 2. 20 页探针

用现有 `ColPaliPageRetriever`，模型名仍是 `vidore/colpali`。`vidore/colpali` 是适配器，本来没有 `config.json`。基座在 `vidore/colpaligemma-3b-mix-448-base`，`adapter_config.json` 已指向它。没有新写 `from_pretrained` 路径，没有设挡住基座的离线开关。

20 页取自 `ArxivQA_filter.parquet` 前 20 行，页图在 `artifacts/probe/encode20/page_00.jpg` 到 `page_19.jpg`。向量在 `artifacts/probe/encode20/cache/`，20 个 `.pt`。未写入正式缓存 `artifacts/colpali/`。

计时含模型加载，见 `artifacts/probe/encode20/timing.json`。batch=1，与评测编码同口径。

| 项 | 值 |
| --- | --- |
| 20 页耗时 | 77.91 秒 |
| 每页 | 3.896 秒 |
| 峰值显存 | 8697185280 字节，8.10 GiB（`torch.cuda.max_memory_allocated`） |
| 向量形状 | 20 页均为 `[1031, 128]` |
| 外推全量 | 63064 × 3.896 秒 = 245682 秒 = 68.24 小时。超过 6 小时。 |

## 3. 范围收缩（train_fit，未编码）

只计 `train_fit`。`train_dev` 不编码。题必须正页和负页都至少有 1 个框，0 框页排除。文档名只去掉结尾 `.pdf`。对齐用 jsonl 的 `line_index`，不用会撞号的 `query_id`。

| 项 | 数 |
| --- | ---: |
| train_fit 题 | 57062 |
| 正负页都至少 1 框 | 57012 |
| 这些题的去重页 | 58515 |
| 外推 | 58515 × 3.896 秒 = 63.33 小时 |

63.33 小时超过 12 小时。未编码。等改范围。未写入 `artifacts/colpali/mmdocir_train/`。

## 4. 按域（未编码）

母集是上一节 57012 题。页按域内去重。七域页数相加 58515，与上一节去重页一致，域间没有共用页。外推仍是 3.896 秒/页。未编码。

| 域 | 题数 | 去重页 | 外推小时 |
| --- | ---: | ---: | ---: |
| ArxivQA | 9241 | 7112 | 7.70 |
| DUDE | 2312 | 3330 | 3.60 |
| MP-DocVQA | 5565 | 4487 | 4.86 |
| SciQAG | 4316 | 4269 | 4.62 |
| SlideVQA | 10399 | 11934 | 12.92 |
| TAT-DQA | 12781 | 5513 | 5.97 |
| Wiki-ss | 12398 | 21870 | 23.67 |

推荐 `ArxivQA`。它是不超过 12 小时里页数最多的单域，整域编码，不把同一文档的页切开。`SlideVQA` 12.92 小时，`Wiki-ss` 23.67 小时，都不进。等批准后再编码。

## 5. 停

全量 68.24 小时不批。收缩后 63.33 小时仍超 12 小时，不编码。不开训，不下载，不读 `test_eval`。

外推超过 6 小时。不开全量，不开训，不读 `test_eval`，不下载。
