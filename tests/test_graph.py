import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from pydantic import ValidationError

from shopping_agent.graph import build_graph
from shopping_agent.hardware_scoring import score_hardware_requirements
from shopping_agent.schemas.autonomous import MainAgentDecision, SearchPlan
from shopping_agent.schemas.computer_products import (
    Budget, HardwareConstraint, MerchantOffer, MonitorAttributes,
    MotherboardAttributes, PCCompatibilityContext, Product, ProductBatch,
    ProductRequirement, RecommendationItem, RecommendationResult,
    SoftPreferenceScore, SoftScoringResult,
)
from shopping_agent.search_backend import (
    DEFAULT_CATALOG_PATH, JsonlProductSearchBackend, RawProductRecord,
)


class FakeBackend:
    def __init__(self):
        self.plan = None

    def search(self, plan):
        self.plan = plan
        return [RawProductRecord(source_id="db-1", raw_text="Test 27in 4K monitor, 1999 CNY")]


class FakeInvoker:
    def __init__(self):
        self.main_round = 0

    def __call__(self, _system, _user, model):
        if model is MainAgentDecision:
            self.main_round += 1
            if self.main_round == 1:
                return MainAgentDecision(
                    next_agent="shopping_agent", reason="需要先检索",
                    search_query="27英寸 4K 显示器",
                    request=ProductRequirement(
                        category="monitor", budget=Budget(max_price=2500, currency="CNY"),
                        use_cases=["office"], preferred_features=["色彩准确"],
                        hard_constraints=[
                            HardwareConstraint(field="screen_size_inch", operator="eq", value=27, source_text="27英寸"),
                            HardwareConstraint(field="resolution", operator="contains", value="3840x2160", source_text="4K"),
                            HardwareConstraint(field="curved", operator="eq", value=False, source_text="不要曲面屏"),
                        ],
                    ),
                )
            actions = {2: "scoring_agent", 3: "recommendation_agent", 4: "finish"}
            return MainAgentDecision(next_agent=actions[self.main_round], reason="继续任务")
        if model is SearchPlan:
            return SearchPlan(category="monitor", query="27 inch 4k monitor", limit=5)
        if model is ProductBatch:
            return ProductBatch(products=[Product(
                product_id="p1", category="monitor", name="Test Monitor", brand="Test",
                attributes=MonitorAttributes(screen_size_inch=27, resolution="3840x2160", curved=False),
                offers=[MerchantOffer(merchant="Test Shop", price=1999, currency="CNY")],
                source="fake database",
            )])
        if model is SoftScoringResult:
            return SoftScoringResult(scores=[SoftPreferenceScore(
                product_id="p1", use_case_score=12, preference_score=7,
                subjective_score=3, total_score=22,
                evidence=["适合办公"], confidence=.9,
            )], summary="软偏好评分完成")
        if model is RecommendationResult:
            return RecommendationResult(
                status="complete", summary="推荐 p1",
                items=[RecommendationItem(rank=1, product_id="p1",
                                          reason="满足需求", tradeoffs=[])],
            )
        raise AssertionError(model)


class AutonomousGraphTests(unittest.TestCase):
    def test_main_agent_routes_three_private_state_subagents(self):
        backend = FakeBackend()
        result = build_graph(invoker=FakeInvoker(), search_backend=backend).invoke({
            "user_query": "2500元买27英寸4K非曲面显示器",
            "route_history": [], "errors": [], "step_count": 0,
        })
        self.assertEqual(result["recommendation"].items[0].product_id, "p1")
        score = result["scoring_result"].scores[0]
        self.assertEqual(score.hardware_score.total_score, 70)
        self.assertEqual(score.soft_score.total_score, 22)
        self.assertEqual(score.total_score, 92)
        self.assertEqual(result["route_history"], [
            "main→shopping_agent", "main→scoring_agent",
            "main→recommendation_agent", "main→finish",
        ])
        self.assertNotIn("search_plan", result)
        self.assertNotIn("raw_products", result)

    def test_requirement_uses_structured_compatibility(self):
        request = ProductRequirement(
            category="motherboard",
            budget=Budget(max_price=250, currency="USD"),
            use_cases=["gaming", "programming"],
            required_features=["DDR5"], preferred_features=["WiFi"],
            compatibility=PCCompatibilityContext(existing_cpu_socket="AM5"),
        )
        self.assertEqual(request.compatibility.existing_cpu_socket, "AM5")

    def test_motherboard_hardware_score_uses_fixed_70_point_policy(self):
        request = ProductRequirement(
            category="motherboard",
            budget=Budget(max_price=250, currency="USD"),
            compatibility=PCCompatibilityContext(
                existing_cpu_socket="AM5", existing_memory_type="DDR5"
            ),
            hard_constraints=[HardwareConstraint(
                field="wifi", operator="eq", value=True, source_text="必须有 WiFi"
            )],
        )
        product = Product(
            product_id="mb1", category="motherboard", name="B650 WiFi",
            attributes=MotherboardAttributes(
                socket="AM5", memory_type="DDR5", wifi=True, form_factor="ATX"
            ),
            offers=[MerchantOffer(merchant="shop", price=220, currency="USD")],
        )
        score = score_hardware_requirements(request, product)
        self.assertTrue(score.passed)
        self.assertEqual(score.total_score, 70)
        self.assertEqual(
            [(item.criterion, item.max_score) for item in score.criteria],
            [("CPU Socket 匹配", 20), ("内存类型匹配", 15),
             ("预算符合", 15), ("规格要求满足", 10), ("其他兼容性", 10)],
        )

    def test_hardware_budget_failure_cannot_be_overridden_by_llm(self):
        request = ProductRequirement(
            category="motherboard", budget=Budget(max_price=200, currency="USD")
        )
        product = Product(
            product_id="mb2", category="motherboard", name="Expensive board",
            attributes=MotherboardAttributes(),
            offers=[MerchantOffer(merchant="shop", price=300, currency="USD")],
        )
        score = score_hardware_requirements(request, product)
        self.assertFalse(score.passed)
        self.assertEqual(score.total_score, 55)
        self.assertTrue(any("超过上限" in reason for reason in score.rejection_reasons))

    def test_product_selects_attributes_from_category(self):
        product = Product.model_validate({
            "product_id": "mb001", "category": "motherboard",
            "name": "ASUS TUF Gaming B650-PLUS WIFI",
            "attributes": {"socket": "AM5", "memory_type": "DDR5", "wifi": True},
        })
        self.assertIsInstance(product.attributes, MotherboardAttributes)

    def test_wrong_category_attributes_are_rejected(self):
        with self.assertRaises(ValidationError):
            Product.model_validate({
                "product_id": "bad", "category": "motherboard", "name": "Bad",
                "attributes": {"vram_gb": 16},
            })

    def test_budget_range_is_validated(self):
        with self.assertRaises(ValidationError):
            Budget(min_price=300, max_price=200)

    def test_mutable_lists_are_not_shared(self):
        first = ProductRequirement(category="cpu")
        second = ProductRequirement(category="cpu")
        first.use_cases.append("gaming")
        self.assertEqual(second.use_cases, [])

    @unittest.skipUnless(DEFAULT_CATALOG_PATH.is_file(), "本地 10k 商品库尚未构建")
    def test_local_database_contains_10000_unique_computer_products(self):
        with DEFAULT_CATALOG_PATH.open("r", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]
        self.assertEqual(len(rows), 10_000)
        self.assertEqual(len({row["product_id"] for row in rows}), 10_000)
        self.assertTrue(all(row.get("category_hint") for row in rows))

    def test_local_database_search_prefers_requested_category(self):
        rows = [
            {"product_id": "gpu-1", "category_hint": "gpu",
             "title": "RTX graphics card", "features": ["gaming"]},
            {"product_id": "monitor-1", "category_hint": "monitor",
             "title": "RTX compatible monitor", "features": ["4K"]},
        ]
        with TemporaryDirectory() as directory:
            catalog = Path(directory) / "catalog.jsonl"
            catalog.write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            results = JsonlProductSearchBackend(catalog).search(
                SearchPlan(category="gpu", query="RTX graphics card", limit=1)
            )
        self.assertEqual(len(results), 1)
        self.assertEqual(json.loads(results[0].raw_text)["category_hint"], "gpu")


if __name__ == "__main__":
    unittest.main()
