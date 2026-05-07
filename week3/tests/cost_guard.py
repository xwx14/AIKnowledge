"""多 Agent 预算守卫：追踪 LLM 调用成本，预警/拦截预算超限。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


class BudgetExceededError(Exception):
    """预算超限异常。"""


@dataclass
class CostRecord:
    timestamp: str
    node_name: str
    prompt_tokens: int
    completion_tokens: int
    cost_yuan: float
    model: str


@dataclass
class CostGuard:
    budget_yuan: float = 1.0
    alert_threshold: float = 0.8
    input_price_per_million: float = 1.0
    output_price_per_million: float = 2.0
    _records: list[CostRecord] = field(default_factory=list, repr=False)

    @property
    def total_prompt_tokens(self) -> int:
        return sum(r.prompt_tokens for r in self._records)

    @property
    def total_completion_tokens(self) -> int:
        return sum(r.completion_tokens for r in self._records)

    @property
    def total_cost_yuan(self) -> float:
        return sum(r.cost_yuan for r in self._records)

    def record(self, node_name: str, usage: dict[str, int], model: str = "") -> None:
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        cost = (prompt_tokens / 1_000_000) * self.input_price_per_million + \
               (completion_tokens / 1_000_000) * self.output_price_per_million
        rec = CostRecord(
            timestamp=datetime.now().isoformat(),
            node_name=node_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_yuan=cost,
            model=model,
        )
        self._records.append(rec)

    def check(self) -> dict[str, Any]:
        total = self.total_cost_yuan
        ratio = total / self.budget_yuan if self.budget_yuan > 0 else 0.0

        if total > self.budget_yuan:
            raise BudgetExceededError(
                f"预算超限: ¥{total:.4f} > ¥{self.budget_yuan:.4f}"
            )

        if ratio >= self.alert_threshold:
            return {
                "status": "warning",
                "total_cost": total,
                "budget": self.budget_yuan,
                "usage_ratio": ratio,
                "message": f"接近预算上限 ({ratio:.0%})",
            }

        return {
            "status": "ok",
            "total_cost": total,
            "budget": self.budget_yuan,
            "usage_ratio": ratio,
            "message": "预算正常",
        }

    def get_report(self) -> dict[str, Any]:
        by_node: dict[str, dict[str, Any]] = {}
        for r in self._records:
            entry = by_node.setdefault(r.node_name, {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cost_yuan": 0.0,
                "calls": 0,
                "models": set(),
            })
            entry["prompt_tokens"] += r.prompt_tokens
            entry["completion_tokens"] += r.completion_tokens
            entry["cost_yuan"] += r.cost_yuan
            entry["calls"] += 1
            entry["models"].add(r.model)

        for entry in by_node.values():
            entry["models"] = sorted(entry["models"])

        return {
            "total_cost": self.total_cost_yuan,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_calls": len(self._records),
            "budget": self.budget_yuan,
            "usage_ratio": self.total_cost_yuan / self.budget_yuan if self.budget_yuan > 0 else 0.0,
            "by_node": by_node,
        }

    def save_report(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path else Path("cost_report.json")
        report = self.get_report()
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return target


if __name__ == "__main__":
    passed = 0
    failed = 0

    def assert_test(condition: bool, name: str) -> None:
        global passed, failed
        if condition:
            passed += 1
            print(f"  [PASS] {name}")
        else:
            failed += 1
            print(f"  [FAIL] {name}")

    print("=" * 60)
    print("CostGuard 测试")
    print("=" * 60)

    # --- 测试 1: 成本追踪正确 ---
    print("\n[测试1] 成本追踪正确")
    guard = CostGuard(budget_yuan=1.0, input_price_per_million=1.0, output_price_per_million=2.0)
    guard.record("analyze", {"prompt_tokens": 500_000, "completion_tokens": 200_000}, model="deepseek-chat")
    assert_test(guard.total_prompt_tokens == 500_000, "total_prompt_tokens == 500000")
    assert_test(guard.total_completion_tokens == 200_000, "total_completion_tokens == 200000")
    expected_cost = 500_000 / 1_000_000 * 1.0 + 200_000 / 1_000_000 * 2.0
    assert_test(abs(guard.total_cost_yuan - expected_cost) < 1e-9, f"total_cost_yuan == {expected_cost}")

    guard.record("review", {"prompt_tokens": 100_000, "completion_tokens": 50_000}, model="glm-4")
    assert_test(guard.total_prompt_tokens == 600_000, "累加后 total_prompt_tokens == 600000")
    expected_cost2 = expected_cost + 100_000 / 1_000_000 * 1.0 + 50_000 / 1_000_000 * 2.0
    assert_test(abs(guard.total_cost_yuan - expected_cost2) < 1e-9, f"累加后 total_cost_yuan == {expected_cost2}")

    # --- 测试 2: 预警阈值触发 ---
    print("\n[测试2] 预警阈值触发")
    guard2 = CostGuard(budget_yuan=1.0, alert_threshold=0.8, input_price_per_million=1.0, output_price_per_million=2.0)
    guard2.record("analyze", {"prompt_tokens": 400_000, "completion_tokens": 200_000})
    result = guard2.check()
    assert_test(result["status"] == "warning", f'status == "warning" (实际: {result["status"]})')
    assert_test(result["usage_ratio"] >= 0.8, f"usage_ratio >= 0.8 (实际: {result['usage_ratio']:.2%})")

    # --- 测试 3: 预算超限检测 ---
    print("\n[测试3] 预算超限检测")
    guard3 = CostGuard(budget_yuan=0.001, alert_threshold=0.8, input_price_per_million=1.0, output_price_per_million=2.0)
    guard3.record("analyze", {"prompt_tokens": 1_000_000, "completion_tokens": 500_000})
    try:
        guard3.check()
        assert_test(False, "应抛出 BudgetExceededError")
    except BudgetExceededError:
        assert_test(True, "抛出 BudgetExceededError")

    # --- 测试 4: 正常状态 ---
    print("\n[测试4] 正常状态")
    guard4 = CostGuard(budget_yuan=100.0, alert_threshold=0.8, input_price_per_million=1.0, output_price_per_million=2.0)
    guard4.record("collect", {"prompt_tokens": 1_000, "completion_tokens": 500})
    result4 = guard4.check()
    assert_test(result4["status"] == "ok", f'status == "ok" (实际: {result4["status"]})')

    # --- 测试 5: 报告生成 ---
    print("\n[测试5] 报告生成")
    guard5 = CostGuard(budget_yuan=1.0, input_price_per_million=1.0, output_price_per_million=2.0)
    guard5.record("analyze", {"prompt_tokens": 100_000, "completion_tokens": 50_000}, model="deepseek-chat")
    guard5.record("review", {"prompt_tokens": 80_000, "completion_tokens": 30_000}, model="glm-4")
    guard5.record("analyze", {"prompt_tokens": 60_000, "completion_tokens": 20_000}, model="deepseek-chat")
    report = guard5.get_report()
    assert_test(report["total_calls"] == 3, f"total_calls == 3 (实际: {report['total_calls']})")
    assert_test("analyze" in report["by_node"], "by_node 包含 analyze")
    assert_test("review" in report["by_node"], "by_node 包含 review")
    assert_test(report["by_node"]["analyze"]["calls"] == 2, "analyze 调用 2 次")
    assert_test(report["by_node"]["review"]["calls"] == 1, "review 调用 1 次")

    # --- 测试 6: 保存报告 ---
    print("\n[测试6] 保存报告")
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        tmp_path = f.name
    saved_path = guard5.save_report(tmp_path)
    assert_test(saved_path.exists(), "报告文件已创建")
    loaded = json.loads(saved_path.read_text(encoding="utf-8"))
    assert_test(loaded["total_calls"] == 3, "保存后 total_calls == 3")
    saved_path.unlink()

    print(f"\n{'=' * 60}")
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)
