# 自主购物 Agent 架构

主 Agent 每轮调用大模型并输出 `MainAgentDecision`，自主选择购物、评分、推荐或结束。
Conditional Edge 执行这个选择；本地规则只校验数据前置条件和最大步骤数。

| 子 Agent | 私有 State | LLM 工作 | 主图得到的结果 |
|---|---|---|---|
| Shopping | 检索计划、数据库原始记录 | 规划检索、抽取分类参数 | products、search_summary |
| Scoring | 需求、候选及评分过程 | 硬条件判断和统一评分 | scoring_result |
| Recommendation | 需求、商品、评分 | 排序、理由和取舍 | recommendation |

## 混合评分

`hardware_scoring.py` 在本地确定性计算硬件条件 70 分。主板固定使用 Socket 20、
内存类型 15、预算 15、规格 10、其他兼容性 10；其他品类使用兼容性 30、预算 15、
必需规格 15、排除条件 10。任意已声明硬条件失败都会设置 `passed=false`。

只有硬件条件通过的商品才发送给 LLM。LLM 只返回用途匹配 15、用户偏好 10、其他
主观需求 5，共 30 分。Python 最后验证并计算：

```text
total_score = hardware_score + soft_score
```

因此模型不能修改硬件得分、淘汰原因或 100 分总分公式。

需求层使用统一 `ProductRequirement`，明确区分 required、preferred、excluded
features，并以 `PCCompatibilityContext` 保存 CPU 插槽、内存类型、电源功率、
机箱限长/限高、主板尺寸和 PCIe 版本。

商品层使用统一 `Product` 外壳和 `MerchantOffer` 报价。模型验证器根据 category
把 attributes 解析成对应专属模型并检查类型一致性，例如 motherboard 只能使用
`MotherboardAttributes`，不能混入 GPU 字段。未知长尾类别使用
`other + category_name + OtherAttributes`。所有大模型结果仍经过本地 Pydantic 校验。

`ProductSearchBackend` 是唯一搜索边界。默认 `JsonlProductSearchBackend` 将本地
10,000 条商品加载为轻量词法索引，并按标题、特征、描述、规格和分类进行排序。
以后可以替换成 SQL、向量库或商品 API，而不修改 Agent 拓扑。
