# -*- coding: utf-8 -*-
"""Batch-level coverage summary for aggregate stock reports.

This module deliberately wraps the public pipeline class instead of changing
analysis, LLM parsing, scoring, or decision logic.  Failed analyses remain
excluded from investment conclusions; the aggregate report only discloses how
many requested targets produced valid results.
"""

from __future__ import annotations

from typing import Any, List, Optional


_PATCH_MARKER = "_batch_report_summary_patch_v1"


def _effective_target_count(stock_codes: List[str], analysis_targets: Optional[List[Any]]) -> int:
    """Mirror pipeline pre-run filtering for unsupported and duplicate targets."""
    if analysis_targets is None or len(analysis_targets) != len(stock_codes):
        return len(stock_codes)

    # Import lazily so importing this helper does not pull in the analysis stack.
    from src.services.stock_list_parser import ParseStatus

    seen_identities = set()
    count = 0
    for code, target in zip(stock_codes, analysis_targets):
        if target is not None and target.asset_type == ParseStatus.UNSUPPORTED:
            continue
        identity = (
            target.canonical_id
            if target is not None and target.asset_type == ParseStatus.INDEX
            else code
        )
        if identity in seen_identities:
            continue
        seen_identities.add(identity)
        count += 1
    return count


def _summary_lines(pipeline: Any, results: List[Any], requested: int) -> List[str]:
    success = len(results)
    if requested < success:
        return []
    failed = requested - success
    success_rate = (success / requested * 100.0) if requested else 0.0

    language = "zh"
    if results:
        language = str(getattr(results[0], "report_language", None) or "zh").strip().lower()
    if language not in {"zh", "en", "ko"}:
        language = str(getattr(getattr(pipeline, "config", None), "report_language", "zh") or "zh").strip().lower()

    if language == "en":
        return [
            f"> 📋 Requested **{requested}** stocks | ✅ Succeeded **{success}** | ⚠️ Failed **{failed}** | Success rate **{success_rate:.1f}%**",
            f"> Investment conclusions below are based only on the **{success}** successful results.",
        ]
    if language == "ko":
        return [
            f"> 📋 분석 요청 **{requested}**종목 | ✅ 성공 **{success}** | ⚠️ 실패 **{failed}** | 성공률 **{success_rate:.1f}%**",
            f"> 아래 투자 판단 통계는 유효한 결과가 생성된 **{success}**종목만 포함합니다.",
        ]
    return [
        f"> 📋 本次计划分析 **{requested}** 只 | ✅成功 **{success}** | ⚠️失败 **{failed}** | 成功率 **{success_rate:.1f}%**",
        f"> 下方买入/观望/卖出等投资结论仅统计成功生成有效结果的 **{success}** 只股票。",
    ]


def _inject_summary(report: str, summary_lines: List[str]) -> str:
    if not summary_lines:
        return report
    lines = str(report or "").splitlines()
    insert_at = 0
    if lines and lines[0].lstrip().startswith("#"):
        insert_at = 1
        while insert_at < len(lines) and not lines[insert_at].strip():
            insert_at += 1
    payload = [*summary_lines, ""]
    lines[insert_at:insert_at] = payload
    return "\n".join(lines)


def patch_pipeline_module(module: Any) -> None:
    """Replace ``module.StockAnalysisPipeline`` with a reporting-only subclass."""
    base = getattr(module, "StockAnalysisPipeline", None)
    if base is None or getattr(base, _PATCH_MARKER, False):
        return

    class StockAnalysisPipeline(base):
        """Original pipeline plus truthful requested/succeeded/failed reporting."""

        def run(
            self,
            stock_codes=None,
            dry_run: bool = False,
            send_notification: bool = True,
            merge_notification: bool = False,
            current_time=None,
            analysis_targets=None,
        ):
            if stock_codes is None:
                self.config.refresh_stock_list()
                effective_codes = list(self.config.stock_list or [])
            else:
                effective_codes = list(stock_codes)

            self._batch_report_requested_count = _effective_target_count(
                effective_codes,
                analysis_targets,
            )
            self._batch_report_success_count = None

            return super().run(
                stock_codes=effective_codes,
                dry_run=dry_run,
                send_notification=send_notification,
                merge_notification=merge_notification,
                current_time=current_time,
                analysis_targets=analysis_targets,
            )

        def _save_local_report(self, results, report_type=None):
            # The base pipeline calls this once with the complete successful set
            # before aggregate notifications are generated.
            self._batch_report_success_count = len(results)
            if report_type is None:
                return super()._save_local_report(results)
            return super()._save_local_report(results, report_type)

        def _generate_aggregate_report(self, results, report_type):
            report = super()._generate_aggregate_report(results, report_type)
            requested = getattr(self, "_batch_report_requested_count", None)
            full_success = getattr(self, "_batch_report_success_count", None)
            if not isinstance(requested, int) or requested < 0:
                return report
            # Grouped e-mail reports contain a subset of the successful results;
            # never stamp the full-batch denominator onto a subgroup report.
            if isinstance(full_success, int) and len(results) != full_success:
                return report
            return _inject_summary(report, _summary_lines(self, list(results), requested))

    setattr(StockAnalysisPipeline, _PATCH_MARKER, True)
    StockAnalysisPipeline.__name__ = "StockAnalysisPipeline"
    StockAnalysisPipeline.__qualname__ = "StockAnalysisPipeline"
    StockAnalysisPipeline.__module__ = module.__name__
    module.StockAnalysisPipeline = StockAnalysisPipeline
