"""M4 audit CLI: machine gate (audit.json) + >=20 overlays for human check.

用法（登记于 docs/02-commands.md）：
    uv run python scripts/run_phase1b_audit.py            # 机器门限 + 20 张叠图
输出：
    artifacts/audit/mmdocir_evaluation/audit.json         机器门限数值
    artifacts/audit/mmdocir_evaluation/overlays/*.jpg     人工抽查叠图
判据（PAPER_SPEC 第 6 节）：越界率 < 1%；无页级覆盖为 0 的异常页；叠图人工点头。
"""

from __future__ import annotations

import typer

from layoutpatch.evaluation.audit import audit_nodes_table, write_audit_json
from layoutpatch.evaluation.audit_overlays import generate_overlays
from layoutpatch.paths import artifacts_dir

app = typer.Typer(help="Phase 1B coordinate audit.")


@app.command()
def main(
    limit_pages: int | None = typer.Option(None, help="Optional page limit for a quick scan."),
) -> None:
    out_dir = artifacts_dir() / "audit" / "mmdocir_evaluation"
    audits, report = audit_nodes_table(limit_pages=limit_pages)
    audit_path = write_audit_json(audits, report, out_dir)
    overlays, missing = generate_overlays()
    typer.echo(f"audit.json: {audit_path}")
    typer.echo(
        f"pages={report.pages_audited} regions={report.total_regions} "
        f"oob={report.out_of_bounds_regions} (ratio={report.out_of_bounds_ratio:.4f}) "
        f"coverage_mean={report.coverage_mean:.4f} zero_pages={len(report.pages_zero_coverage)}"
    )
    typer.echo(f"gate: oob_pass={report.gate_oob_pass} zero_page_pass={report.gate_zero_page_pass} all_pass={report.gate_all_pass}")
    typer.echo(f"overlays: {len(overlays)} written, {len(missing)} missing page images")
    if missing:
        typer.echo(f"missing page ids: {missing[:10]}")


if __name__ == "__main__":
    app()
