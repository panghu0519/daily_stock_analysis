from types import SimpleNamespace

from src.batch_report_summary import patch_pipeline_module


class _BasePipeline:
    def __init__(self):
        self.config = SimpleNamespace(stock_list=[], report_language="zh")
        self.saved_report = None

    def run(
        self,
        stock_codes=None,
        dry_run=False,
        send_notification=True,
        merge_notification=False,
        current_time=None,
        analysis_targets=None,
    ):
        results = [SimpleNamespace(code=str(i), report_language="zh") for i in range(10)]
        self._save_local_report(results, "simple")
        return results

    def _save_local_report(self, results, report_type="simple"):
        self.saved_report = self._generate_aggregate_report(results, report_type)
        return "report.md"

    def _generate_aggregate_report(self, results, report_type):
        return (
            "# 🎯 日报\n\n"
            f"> 共分析 **{len(results)}** 只股票 | 🟢买入:0 🟡观望:{len(results)} 🔴卖出:0\n"
        )


def _patched_pipeline():
    module = SimpleNamespace(StockAnalysisPipeline=_BasePipeline, __name__="fake_pipeline")
    patch_pipeline_module(module)
    return module.StockAnalysisPipeline()


def test_batch_summary_reports_requested_success_failed_counts():
    pipeline = _patched_pipeline()
    results = pipeline.run(stock_codes=[f"{i:06d}" for i in range(21)])

    assert len(results) == 10
    assert "本次计划分析 **21** 只" in pipeline.saved_report
    assert "✅成功 **10**" in pipeline.saved_report
    assert "⚠️失败 **11**" in pipeline.saved_report
    assert "成功率 **47.6%**" in pipeline.saved_report
    assert "仅统计成功生成有效结果的 **10** 只股票" in pipeline.saved_report
    assert "🟡观望:10" in pipeline.saved_report


def test_all_success_reports_zero_failures():
    pipeline = _patched_pipeline()
    pipeline.run(stock_codes=[f"{i:06d}" for i in range(10)])

    assert "本次计划分析 **10** 只" in pipeline.saved_report
    assert "✅成功 **10**" in pipeline.saved_report
    assert "⚠️失败 **0**" in pipeline.saved_report
    assert "成功率 **100.0%**" in pipeline.saved_report


def test_group_report_does_not_reuse_full_batch_denominator():
    pipeline = _patched_pipeline()
    results = pipeline.run(stock_codes=[f"{i:06d}" for i in range(21)])

    subgroup = pipeline._generate_aggregate_report(results[:3], "simple")
    assert "本次计划分析 **21** 只" not in subgroup
    assert "共分析 **3** 只股票" in subgroup
