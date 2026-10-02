"""Deterministic 70-point hardware and compatibility scoring."""

import json
import re
from typing import Any

from .schemas.computer_products import (
    HardwareCriterion, HardwareScore, Product, ProductRequirement,
)


def _canon(value: Any) -> str:
    text = str(value).lower()
    replacements = {
        "wi-fi": "wifi", "无线网络": "wifi", "蓝牙": "bluetooth",
        "非曲面": "flat", "直屏": "flat", "曲面": "curved",
        "英寸": "inch", "显存": "vram", "内存": "memory",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return re.sub(r"[^a-z0-9.+]+", "", text)


def _criterion(name: str, points: float, passed: bool, evidence: str) -> HardwareCriterion:
    return HardwareCriterion(
        criterion=name, score=points if passed else 0,
        max_score=points, passed=passed, evidence=evidence,
    )


def _product_facts(product: Product) -> str:
    return _canon(json.dumps(product.model_dump(mode="json"), ensure_ascii=False))


def _lookup(product: Product, field: str) -> Any:
    key = field.removeprefix("attributes.")
    attributes = product.attributes.model_dump(mode="python")
    if isinstance(attributes, dict) and key in attributes:
        return attributes[key]
    data = product.model_dump(mode="python")
    return data.get(key)


def _evaluate_constraint(product: Product, field: str, operator: str, expected: Any) -> tuple[bool, str]:
    actual = _lookup(product, field)
    if actual is None:
        return False, f"商品缺少 {field} 参数"
    try:
        if operator == "eq":
            if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
                passed = float(actual) == float(expected)
            else:
                passed = _canon(actual) == _canon(expected)
        elif operator == "gte":
            passed = float(actual) >= float(expected)
        elif operator == "lte":
            passed = float(actual) <= float(expected)
        elif operator == "contains":
            passed = _canon(expected) in _canon(actual)
        elif operator == "not_contains":
            passed = _canon(expected) not in _canon(actual)
        else:
            passed = False
    except (TypeError, ValueError):
        passed = False
    return passed, f"{field} 实际值={actual!r}，要求 {operator} {expected!r}"


def _specification_check(
    request: ProductRequirement, product: Product, *, include_excluded: bool = True
) -> tuple[bool, str]:
    facts = _product_facts(product)
    failures: list[str] = []
    applicable = [
        constraint for constraint in request.hard_constraints
        if include_excluded or constraint.operator != "not_contains"
    ]
    if applicable:
        for constraint in applicable:
            passed, evidence = _evaluate_constraint(
                product, constraint.field, constraint.operator, constraint.value
            )
            if not passed:
                failures.append(f"{constraint.source_text}（{evidence}）")
    else:
        for feature in request.required_features:
            normalized = _canon(feature)
            if normalized and normalized not in facts:
                failures.append(f"缺少必需规格：{feature}")
    if include_excluded:
        for feature in request.excluded_features:
            normalized = _canon(feature)
            if normalized and normalized in facts:
                failures.append(f"包含排除项：{feature}")
    if failures:
        return False, "；".join(failures)
    return True, "全部必需规格和排除条件均满足"


def _exclusion_check(request: ProductRequirement, product: Product) -> tuple[bool, str]:
    facts = _product_facts(product)
    failures = [
        f"包含排除项：{feature}" for feature in request.excluded_features
        if _canon(feature) and _canon(feature) in facts
    ]
    for constraint in request.hard_constraints:
        if constraint.operator != "not_contains":
            continue
        passed, evidence = _evaluate_constraint(
            product, constraint.field, constraint.operator, constraint.value
        )
        if not passed:
            failures.append(f"{constraint.source_text}（{evidence}）")
    return (False, "；".join(failures)) if failures else (True, "未命中排除条件")


def _budget_check(request: ProductRequirement, product: Product) -> tuple[bool, str]:
    budget = request.budget
    if budget is None:
        return True, "用户未设置预算限制"
    totals = []
    for offer in product.offers:
        if offer.currency != budget.currency or offer.price is None or offer.in_stock is False:
            continue
        totals.append(offer.price + (offer.shipping_cost or 0))
    if not totals:
        return False, f"没有 {budget.currency} 的有效报价"
    lowest = min(totals)
    if budget.min_price is not None and lowest < budget.min_price:
        return False, f"最低总价 {lowest} 低于下限 {budget.min_price}"
    if budget.max_price is not None and lowest > budget.max_price:
        return False, f"最低总价 {lowest} 超过上限 {budget.max_price}"
    return True, f"最低总价 {lowest} {budget.currency} 符合预算"


def _compatibility_checks(request: ProductRequirement, product: Product) -> list[tuple[bool, str]]:
    context = request.compatibility
    attrs = product.attributes.model_dump(mode="python")
    checks: list[tuple[bool, str]] = []
    if product.category == "gpu":
        required_psu = attrs.get("recommended_psu_w")
        if context.existing_psu_wattage is not None:
            checks.append((required_psu is not None and context.existing_psu_wattage >= required_psu,
                           f"现有电源={context.existing_psu_wattage}W，显卡建议={required_psu}W"))
        length = attrs.get("length_mm")
        if context.case_max_gpu_length_mm is not None:
            checks.append((length is not None and length <= context.case_max_gpu_length_mm,
                           f"机箱限长={context.case_max_gpu_length_mm}mm，显卡={length}mm"))
    elif product.category == "memory" and context.existing_memory_type is not None:
        actual = attrs.get("memory_type")
        checks.append((_canon(actual) == _canon(context.existing_memory_type),
                       f"现有内存类型={context.existing_memory_type}，商品={actual}"))
    elif product.category == "cooler":
        if context.existing_cpu_socket is not None:
            sockets = attrs.get("supported_sockets") or []
            checks.append((_canon(context.existing_cpu_socket) in _canon(sockets),
                           f"散热器支持插槽={sockets}"))
        if context.case_max_cooler_height_mm is not None:
            height = attrs.get("height_mm")
            checks.append((height is not None and height <= context.case_max_cooler_height_mm,
                           f"机箱限高={context.case_max_cooler_height_mm}mm，散热器={height}mm"))
    return checks


def _combined_check(checks: list[tuple[bool, str]], default: str) -> tuple[bool, str]:
    if not checks:
        return True, default
    return all(item[0] for item in checks), "；".join(item[1] for item in checks)


def _score_motherboard(request: ProductRequirement, product: Product) -> list[HardwareCriterion]:
    attrs = product.attributes.model_dump(mode="python")
    socket = request.compatibility.existing_cpu_socket
    socket_ok = socket is None or _canon(attrs.get("socket")) == _canon(socket)
    memory = request.compatibility.existing_memory_type
    memory_ok = memory is None or _canon(attrs.get("memory_type")) == _canon(memory)
    budget_ok, budget_evidence = _budget_check(request, product)
    specs_ok, specs_evidence = _specification_check(request, product)
    other_checks = []
    if request.compatibility.motherboard_form_factor is not None:
        actual = attrs.get("form_factor")
        other_checks.append((_canon(actual) == _canon(request.compatibility.motherboard_form_factor),
                             f"主板尺寸={actual}，要求={request.compatibility.motherboard_form_factor}"))
    if request.compatibility.available_pcie_version is not None:
        other_checks.append((False, "主板 Schema 尚无 PCIe 版本证据"))
    other_ok, other_evidence = _combined_check(other_checks, "未设置其他兼容性限制")
    return [
        _criterion("CPU Socket 匹配", 20, socket_ok,
                   "未指定 CPU Socket" if socket is None else f"商品={attrs.get('socket')}，要求={socket}"),
        _criterion("内存类型匹配", 15, memory_ok,
                   "未指定内存类型" if memory is None else f"商品={attrs.get('memory_type')}，要求={memory}"),
        _criterion("预算符合", 15, budget_ok, budget_evidence),
        _criterion("规格要求满足", 10, specs_ok, specs_evidence),
        _criterion("其他兼容性", 10, other_ok, other_evidence),
    ]


def score_hardware_requirements(request: ProductRequirement, product: Product) -> HardwareScore:
    """Return a deterministic score; no LLM is involved."""
    if product.category == "motherboard":
        criteria = _score_motherboard(request, product)
    else:
        compatibility_ok, compatibility_evidence = _combined_check(
            _compatibility_checks(request, product), "该品类没有额外兼容性限制"
        )
        budget_ok, budget_evidence = _budget_check(request, product)
        specs_ok, specs_evidence = _specification_check(
            request, product, include_excluded=False
        )
        excluded_ok, excluded_evidence = _exclusion_check(request, product)
        criteria = [
            _criterion("硬件兼容性", 30, compatibility_ok, compatibility_evidence),
            _criterion("预算符合", 15, budget_ok, budget_evidence),
            _criterion("必需规格", 15, specs_ok, specs_evidence),
            _criterion("排除条件", 10, excluded_ok,
                       excluded_evidence),
        ]
    failed = [item.evidence for item in criteria if not item.passed]
    return HardwareScore(
        total_score=sum(item.score for item in criteria),
        passed=not failed,
        rejection_reasons=failed,
        criteria=criteria,
    )
