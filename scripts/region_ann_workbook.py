"""HTML helpers for the local region-annotation workbook."""

from __future__ import annotations

import html
import json


def radios(name: str, options: list[tuple[str, str]], checked: str) -> str:
    parts = []
    for value, label in options:
        mark = " checked" if value == checked else ""
        parts.append(
            f"<label><input type='radio' name='{html.escape(name)}' value='{html.escape(value)}'{mark}> {html.escape(label)}</label>"
        )
    return " ".join(parts)


def question_payload(rows: list[dict]) -> list[dict]:
    payload = []
    for row in rows:
        payload.append(
            {
                "sample_id": row["sample_id"],
                "query_id": row["query_id"],
                "line_index": row["line_index"],
                "query": row["query"],
                "pos_doc": row["pos_doc"],
                "pos_page": row["pos_page"],
                "page_png": f"pilot_materials/samples/{row['sample_id']}/page.png",
                "overlay_png": f"pilot_materials/samples/{row['sample_id']}/overlay.png",
                "card": f"pilot_materials/samples/{row['sample_id']}/card.md",
                "candidates": [
                    {
                        "box_id": int(box["box_id"]),
                        "bbox": [float(v) for v in box["bbox"]],
                        "type": box.get("type"),
                    }
                    for box in row["candidates"]
                ],
            }
        )
    return payload


def build_workbook(rows: list[dict]) -> str:
    bool_opts = [("null", "未填"), ("true", "是"), ("false", "否")]
    status_opts = [
        ("pending", "pending 不确定/未完成"),
        ("labeled", "labeled 已选出证据框"),
        ("skipped", "skipped 候选无法覆盖证据"),
    ]
    blocks = [
        "<!DOCTYPE html>",
        "<html lang='zh-CN'><head><meta charset='utf-8'>",
        "<title>ArxivQA region-ann-v0 本地标注</title>",
        "<style>",
        "body{font-family:sans-serif;max-width:1100px;margin:24px auto;line-height:1.45}",
        "img{max-width:100%;height:auto;border:1px solid #ccc}",
        "table{border-collapse:collapse;margin:8px 0 16px;width:100%}",
        "td,th{border:1px solid #bbb;padding:4px 8px;font-size:14px}",
        ".warn{background:#fff3cd;padding:12px}",
        ".sticky{position:sticky;top:0;background:#fff;border-bottom:1px solid #ddd;padding:12px 0;z-index:2}",
        "section{border-top:2px solid #333;padding-top:16px;margin-top:24px}",
        ".ok{color:#0a7;white-space:pre-wrap}",
        ".err{color:#b00;white-space:pre-wrap}",
        "label{margin-right:12px}",
        "</style></head><body>",
        "<div class='sticky'>",
        "<h1>40 题本地标注工作簿（region-ann-v0）</h1>",
        "<p class='warn'>浏览器<strong>不会</strong>写回仓库里的 jsonl。每次填完必须点「导出 JSONL」下载，再手动保存为 ",
        "<code>experiments/region_annotation/labels_annotator_A.jsonl</code> 或 ",
        "<code>labels_annotator_B.jsonl</code>。不要改 template 或 manifest。不要打开另一位标注者的文件。不自动推荐框。</p>",
        "<p>标注者：<select id='session-annotator'><option value=''>请选择</option><option value='A'>A</option><option value='B'>B</option></select>",
        " <button type='button' id='btn-import'>导入已有 JSONL</button>",
        " <input id='file-import' type='file' accept='.jsonl,application/jsonl,text/plain' hidden>",
        " <button type='button' id='btn-check'>本页校验</button>",
        " <button type='button' id='btn-export'>导出 JSONL</button></p>",
        "<pre id='io-status'></pre>",
        "</div>",
        "<p>协议：<code>experiments/region_annotation/annotation_protocol_v0.md</code>。协议版本仍是 <code>region-ann-v0</code>，本页只把规则写清楚，不改版本号。</p>",
        "<ul>",
        "<li><strong>不确定</strong>：看不准该选哪些框。保持 <code>pending</code>，在备注写原因。不要勾「无合适候选」，不要猜框。</li>",
        "<li><strong>候选无法覆盖证据</strong>：看完全部框后，现有候选都盖不住答案。勾「无合适候选」，状态变为 <code>skipped</code>。</li>",
        "<li><code>full</code>：该框单独已经盖住答题所需证据。</li>",
        "<li><code>partial</code>：该框只盖住一部分，需要和其他已选框一起看。</li>",
        "</ul>",
    ]
    for index, row in enumerate(rows, start=1):
        sid = html.escape(row["sample_id"])
        query = html.escape(str(row["query"]))
        rel = f"samples/{row['sample_id']}"
        blocks.append(f"<section id='{sid}' data-sample-id='{sid}'>")
        blocks.append(f"<h2>{index}/40 {sid}</h2>")
        blocks.append("<ul>")
        blocks.append(f"<li>query_id: <code>{html.escape(str(row['query_id']))}</code></li>")
        blocks.append(f"<li>line_index: <code>{html.escape(str(row['line_index']))}</code></li>")
        blocks.append(f"<li>pos_doc: <code>{html.escape(str(row['pos_doc']))}</code></li>")
        blocks.append(f"<li>pos_page: <code>{html.escape(str(row['pos_page']))}</code></li>")
        blocks.append("</ul>")
        blocks.append(f"<p><strong>题目</strong>：{query}</p>")
        blocks.append(f"<p>正页</p><p><img src='{rel}/page.png' alt='{sid} page'></p>")
        blocks.append(f"<p>候选框叠图（数字 = box_id）</p><p><img src='{rel}/overlay.png' alt='{sid} overlay'></p>")
        blocks.append(
            "<table><tr><th>选择</th><th>box_id</th><th>type</th><th>x1</th><th>y1</th><th>x2</th><th>y2</th><th>cover</th></tr>"
        )
        for box in row["candidates"]:
            bid = int(box["box_id"])
            x1, y1, x2, y2 = box["bbox"]
            btype = html.escape(str(box.get("type") or ""))
            blocks.append(
                "<tr>"
                f"<td><input class='box-check' id='box-{sid}-{bid}' type='checkbox' value='{bid}'></td>"
                f"<td>{bid}</td><td>{btype}</td>"
                f"<td>{float(x1):.3f}</td><td>{float(y1):.3f}</td>"
                f"<td>{float(x2):.3f}</td><td>{float(y2):.3f}</td>"
                f"<td><select class='cover-level' id='cover-{sid}-{bid}'>"
                "<option value=''>未填</option><option value='full'>full</option><option value='partial'>partial</option>"
                "</select></td></tr>"
            )
        blocks.append("</table>")
        blocks.append(
            f"<p><label><input class='nc-check' id='nc-{sid}' data-sample-id='{sid}' type='checkbox'> "
            "无合适候选（现有框都盖不住证据）</label></p>"
        )
        blocks.append(f"<p>no_candidate：{radios(f'ncflag-{sid}', bool_opts, 'null')}</p>")
        blocks.append(f"<p>cover_ok 已选框合在一起够不够答题：{radios(f'coverok-{sid}', bool_opts, 'null')}</p>")
        blocks.append(f"<p>cross_box 证据跨多个已选框：{radios(f'cross-{sid}', bool_opts, 'null')}</p>")
        blocks.append(f"<p>状态：{radios(f'status-{sid}', status_opts, 'pending')}</p>")
        blocks.append(f"<p>备注 remark（不确定时必填原因）<br><textarea id='remark-{sid}' rows='3' cols='80'></textarea></p>")
        blocks.append("<p>本页没有预选框。导出前请再点一次「本页校验」。</p>")
        blocks.append("</section>")
    payload = json.dumps(question_payload(rows), ensure_ascii=False)
    blocks.append(f"<script id='pilot-questions' type='application/json'>{payload}</script>")
    blocks.append("<script src='workbook.js'></script>")
    blocks.append("</body></html>")
    return "\n".join(blocks) + "\n"
