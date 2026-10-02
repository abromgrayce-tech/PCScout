"""Unified requirements, products, offers and category-specific PC attributes."""

from typing import Literal, TypeAlias

from pydantic import Field, RootModel, model_validator

from ..models import StrictModel


ProductCategory: TypeAlias = Literal[
    "cpu", "gpu", "motherboard", "memory", "ssd", "hdd", "psu", "case",
    "cooler", "monitor", "keyboard", "mouse", "laptop", "desktop",
    "network_card", "other",
]
Currency: TypeAlias = Literal["CNY", "USD"]
AttributeValue: TypeAlias = str | int | float | bool | list[str] | list[int]


class Budget(StrictModel):
    min_price: float | None = Field(default=None, ge=0)
    max_price: float | None = Field(default=None, ge=0)
    currency: Currency = "USD"

    @model_validator(mode="after")
    def validate_range(self):
        if (self.min_price is not None and self.max_price is not None
                and self.min_price > self.max_price):
            raise ValueError("min_price 不能大于 max_price")
        return self


class PCCompatibilityContext(StrictModel):
    existing_cpu_socket: str | None = None
    existing_memory_type: str | None = None
    existing_psu_wattage: int | None = Field(default=None, gt=0)
    case_max_gpu_length_mm: float | None = Field(default=None, gt=0)
    case_max_cooler_height_mm: float | None = Field(default=None, gt=0)
    motherboard_form_factor: str | None = None
    available_pcie_version: str | None = None


class HardwareConstraint(StrictModel):
    """Machine-checkable hard requirement extracted from the user's wording."""

    field: str = Field(min_length=1)
    operator: Literal["eq", "gte", "lte", "contains", "not_contains"]
    value: str | int | float | bool
    source_text: str = Field(min_length=1)


class ProductRequirement(StrictModel):
    """Trusted representation parsed from the user's natural-language request."""

    category: ProductCategory
    category_name: str | None = None
    budget: Budget | None = None
    quantity: int = Field(default=1, ge=1)
    use_cases: list[str] = Field(default_factory=list)
    required_features: list[str] = Field(default_factory=list)
    preferred_features: list[str] = Field(default_factory=list)
    excluded_features: list[str] = Field(default_factory=list)
    hard_constraints: list[HardwareConstraint] = Field(default_factory=list)
    compatibility: PCCompatibilityContext = Field(default_factory=PCCompatibilityContext)

    @model_validator(mode="after")
    def validate_other_name(self):
        if self.category == "other" and not self.category_name:
            raise ValueError("category=other 时必须保留 category_name")
        return self


class CPUAttributes(StrictModel):
    socket: str | None = None
    cores: int | None = Field(default=None, gt=0)
    threads: int | None = Field(default=None, gt=0)
    base_clock_ghz: float | None = Field(default=None, gt=0)
    boost_clock_ghz: float | None = Field(default=None, gt=0)
    tdp_w: int | None = Field(default=None, gt=0)
    integrated_graphics: bool | None = None


class GPUAttributes(StrictModel):
    gpu_chipset: str | None = None
    vram_gb: int | None = Field(default=None, gt=0)
    memory_type: str | None = None
    length_mm: float | None = Field(default=None, gt=0)
    slot_width: float | None = Field(default=None, gt=0)
    recommended_psu_w: int | None = Field(default=None, gt=0)
    hdmi_ports: int | None = Field(default=None, ge=0)
    displayport_ports: int | None = Field(default=None, ge=0)


class MotherboardAttributes(StrictModel):
    socket: str | None = None
    chipset: str | None = None
    memory_type: Literal["DDR4", "DDR5"] | None = None
    memory_slots: int | None = Field(default=None, gt=0)
    max_memory_gb: int | None = Field(default=None, gt=0)
    form_factor: Literal["ATX", "Micro-ATX", "Mini-ITX", "E-ATX"] | None = None
    wifi: bool | None = None
    bluetooth: bool | None = None
    pcie_x16_slots: int | None = Field(default=None, ge=0)
    m2_slots: int | None = Field(default=None, ge=0)
    sata_ports: int | None = Field(default=None, ge=0)


class MemoryAttributes(StrictModel):
    memory_type: Literal["DDR4", "DDR5"] | None = None
    total_capacity_gb: int | None = Field(default=None, gt=0)
    module_count: int | None = Field(default=None, gt=0)
    speed_mts: int | None = Field(default=None, gt=0)
    cas_latency: int | None = Field(default=None, gt=0)
    ecc: bool | None = None


class SSDAttributes(StrictModel):
    capacity_gb: int | None = Field(default=None, gt=0)
    interface: Literal["SATA", "PCIe 3.0", "PCIe 4.0", "PCIe 5.0"] | None = None
    form_factor: str | None = None
    read_speed_mbps: int | None = Field(default=None, gt=0)
    write_speed_mbps: int | None = Field(default=None, gt=0)


class HDDAttributes(StrictModel):
    capacity_gb: int | None = Field(default=None, gt=0)
    interface: Literal["SATA", "SAS"] | None = None
    form_factor: str | None = None
    rpm: int | None = Field(default=None, gt=0)
    cache_mb: int | None = Field(default=None, ge=0)


class PSUAttributes(StrictModel):
    wattage: int | None = Field(default=None, gt=0)
    efficiency_rating: str | None = None
    modular: Literal["non-modular", "semi-modular", "fully-modular"] | None = None
    atx_version: str | None = None


class CaseAttributes(StrictModel):
    supported_motherboard_sizes: list[str] = Field(default_factory=list)
    max_gpu_length_mm: int | None = Field(default=None, gt=0)
    max_cpu_cooler_height_mm: int | None = Field(default=None, gt=0)
    psu_form_factor: str | None = None
    radiator_support_mm: list[int] = Field(default_factory=list)


class CoolerAttributes(StrictModel):
    cooler_type: Literal["air", "liquid"] | None = None
    supported_sockets: list[str] = Field(default_factory=list)
    height_mm: float | None = Field(default=None, gt=0)
    radiator_size_mm: int | None = Field(default=None, gt=0)
    tdp_capacity_w: int | None = Field(default=None, gt=0)


class MonitorAttributes(StrictModel):
    screen_size_inch: float | None = Field(default=None, gt=0)
    resolution: str | None = None
    refresh_rate_hz: int | None = Field(default=None, gt=0)
    panel_type: str | None = None
    response_time_ms: float | None = Field(default=None, ge=0)
    hdr: bool | None = None
    adaptive_sync: list[str] = Field(default_factory=list)
    curved: bool | None = None
    usb_c_power_w: int | None = Field(default=None, ge=0)


class KeyboardAttributes(StrictModel):
    layout: str | None = None
    form_factor: str | None = None
    switch_type: str | None = None
    connection_types: list[str] = Field(default_factory=list)
    hot_swappable: bool | None = None
    has_numpad: bool | None = None


class MouseAttributes(StrictModel):
    connection_types: list[str] = Field(default_factory=list)
    max_dpi: int | None = Field(default=None, gt=0)
    weight_g: float | None = Field(default=None, gt=0)
    button_count: int | None = Field(default=None, gt=0)
    handedness: Literal["left", "right", "ambidextrous"] | None = None


class LaptopAttributes(StrictModel):
    cpu_model: str | None = None
    gpu_model: str | None = None
    ram_gb: int | None = Field(default=None, gt=0)
    storage_gb: int | None = Field(default=None, gt=0)
    screen_size_inch: float | None = Field(default=None, gt=0)
    resolution: str | None = None
    weight_kg: float | None = Field(default=None, gt=0)
    battery_wh: float | None = Field(default=None, gt=0)
    operating_system: str | None = None


class DesktopAttributes(StrictModel):
    cpu_model: str | None = None
    gpu_model: str | None = None
    ram_gb: int | None = Field(default=None, gt=0)
    storage_gb: int | None = Field(default=None, gt=0)
    psu_wattage: int | None = Field(default=None, gt=0)
    operating_system: str | None = None


class NetworkCardAttributes(StrictModel):
    interface: str | None = None
    ethernet_speed_gbps: float | None = Field(default=None, gt=0)
    wifi_standard: str | None = None
    bluetooth_version: str | None = None


class OtherAttributes(RootModel[dict[str, AttributeValue]]):
    """Controlled long-tail fallback; values remain JSON primitives/lists."""


ProductAttributes: TypeAlias = (
    CPUAttributes | GPUAttributes | MotherboardAttributes | MemoryAttributes
    | SSDAttributes | HDDAttributes | PSUAttributes | CaseAttributes
    | CoolerAttributes | MonitorAttributes | KeyboardAttributes | MouseAttributes
    | LaptopAttributes | DesktopAttributes | NetworkCardAttributes | OtherAttributes
)

ATTRIBUTE_MODELS: dict[str, type[StrictModel] | type[OtherAttributes]] = {
    "cpu": CPUAttributes, "gpu": GPUAttributes, "motherboard": MotherboardAttributes,
    "memory": MemoryAttributes, "ssd": SSDAttributes, "hdd": HDDAttributes,
    "psu": PSUAttributes, "case": CaseAttributes, "cooler": CoolerAttributes,
    "monitor": MonitorAttributes, "keyboard": KeyboardAttributes, "mouse": MouseAttributes,
    "laptop": LaptopAttributes, "desktop": DesktopAttributes,
    "network_card": NetworkCardAttributes, "other": OtherAttributes,
}


class MerchantOffer(StrictModel):
    merchant: str = Field(min_length=1)
    price: float | None = Field(default=None, ge=0)
    currency: Currency = "USD"
    in_stock: bool | None = None
    url: str | None = None
    shipping_cost: float | None = Field(default=None, ge=0)


class Product(StrictModel):
    """One product shell whose attributes are selected by category."""

    product_id: str = Field(min_length=1)
    category: ProductCategory
    category_name: str | None = None
    brand: str | None = None
    model: str | None = None
    name: str = Field(min_length=1)
    description: str | None = None
    attributes: ProductAttributes
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0)
    offers: list[MerchantOffer] = Field(default_factory=list)
    source: str | None = None

    @model_validator(mode="before")
    @classmethod
    def parse_category_attributes(cls, value):
        if not isinstance(value, dict):
            return value
        category = value.get("category")
        attributes = value.get("attributes")
        model = ATTRIBUTE_MODELS.get(category)
        if model is not None and isinstance(attributes, dict):
            value = dict(value)
            value["attributes"] = model.model_validate(attributes)
        return value

    @model_validator(mode="after")
    def validate_category_attributes(self):
        expected = ATTRIBUTE_MODELS[self.category]
        if not isinstance(self.attributes, expected):
            raise ValueError(
                f"category={self.category} 必须使用 {expected.__name__}"
            )
        if self.category == "other" and not self.category_name:
            raise ValueError("category=other 时必须保留 category_name")
        return self


class ProductBatch(StrictModel):
    products: list[Product] = Field(default_factory=list)
    extraction_notes: list[str] = Field(default_factory=list)


class HardwareCriterion(StrictModel):
    criterion: str = Field(min_length=1)
    score: float = Field(ge=0)
    max_score: float = Field(gt=0)
    passed: bool
    evidence: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_range(self):
        if self.score > self.max_score:
            raise ValueError("hardware criterion score cannot exceed max_score")
        return self


class HardwareScore(StrictModel):
    total_score: float = Field(ge=0, le=70)
    max_score: float = Field(default=70, ge=70, le=70)
    passed: bool
    rejection_reasons: list[str] = Field(default_factory=list)
    criteria: list[HardwareCriterion]

    @model_validator(mode="after")
    def validate_hardware_total(self):
        if abs(sum(item.score for item in self.criteria) - self.total_score) > 1e-6:
            raise ValueError("硬件总分必须等于各项得分之和")
        if abs(sum(item.max_score for item in self.criteria) - 70) > 1e-6:
            raise ValueError("硬件评分项满分之和必须为 70")
        if self.passed and self.rejection_reasons:
            raise ValueError("硬件条件通过时不能包含淘汰原因")
        if not self.passed and not self.rejection_reasons:
            raise ValueError("硬件条件不通过时必须说明原因")
        return self


class SoftPreferenceScore(StrictModel):
    product_id: str = Field(min_length=1)
    use_case_score: float = Field(ge=0, le=15)
    preference_score: float = Field(ge=0, le=10)
    subjective_score: float = Field(ge=0, le=5)
    total_score: float = Field(ge=0, le=30)
    evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_soft_total(self):
        expected = self.use_case_score + self.preference_score + self.subjective_score
        if abs(expected - self.total_score) > 1e-6:
            raise ValueError("软偏好总分必须等于 15+10+5 三项得分之和")
        return self


class SoftScoringResult(StrictModel):
    scores: list[SoftPreferenceScore] = Field(default_factory=list)
    summary: str = ""


class ProductScore(StrictModel):
    product_id: str = Field(min_length=1)
    hard_constraints_met: bool
    rejection_reasons: list[str] = Field(default_factory=list)
    hardware_score: HardwareScore
    soft_score: SoftPreferenceScore
    total_score: float = Field(ge=0, le=100)
    max_score: float = Field(default=100, ge=100, le=100)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_consistency(self):
        expected = self.hardware_score.total_score + self.soft_score.total_score
        if abs(expected - self.total_score) > 1e-6:
            raise ValueError("最终得分必须等于硬件得分加软偏好得分")
        if self.hard_constraints_met != self.hardware_score.passed:
            raise ValueError("硬条件结论必须与 hardware_score 一致")
        if self.hard_constraints_met and self.rejection_reasons:
            raise ValueError("合格商品不能包含淘汰原因")
        if not self.hard_constraints_met and not self.rejection_reasons:
            raise ValueError("不合格商品必须包含淘汰原因")
        return self


class ScoringResult(StrictModel):
    scores: list[ProductScore] = Field(default_factory=list)
    scoring_summary: str = ""


class RecommendationItem(StrictModel):
    rank: int = Field(ge=1)
    product_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    tradeoffs: list[str] = Field(default_factory=list)


class RecommendationResult(StrictModel):
    status: Literal["complete", "no_match", "failed"]
    items: list[RecommendationItem] = Field(default_factory=list)
    summary: str
    no_match_reason: str | None = None

    @model_validator(mode="after")
    def validate_status(self):
        if self.status == "complete" and not self.items:
            raise ValueError("complete recommendation must contain items")
        if self.status != "complete" and self.items:
            raise ValueError("non-complete recommendation cannot contain items")
        return self


# State-facing names keep the graph independent from schema refactors.
ComputerShoppingRequest = ProductRequirement
ComputerProduct = Product
