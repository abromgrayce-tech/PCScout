# PCScout（电脑智选助手）

PCScout 是一个基于 LangGraph 的自主式电脑商品选购 Agent。它将商品检索、硬件条件
评分和推荐解释分开处理，并用共享主状态协调三个拥有私有状态的子 Agent。

原固定工作流已改为一个自主主 Agent 和三个调用大模型的子 Agent：

```text
START → main_agent (LLM)
           ├─→ shopping_agent       ─┐
           ├─→ scoring_agent        ─┼→ main_agent
           ├─→ recommendation_agent ─┘
           └─→ END
```

用户自然语言统一解析为 `ProductRequirement`，其中预算使用 `Budget`，已有硬件和
尺寸限制使用结构化 `PCCompatibilityContext`。所有检索结果使用统一的
`Product + MerchantOffer` 外壳；`Product.attributes` 则根据 category 强制使用
CPU、GPU、主板、内存、SSD、HDD、电源、机箱、散热、显示器、键鼠、笔记本、
整机或网卡对应的 Attributes Schema。长尾商品使用 `other + category_name`。

主 Agent 使用 `MainAgentState`；三个子 Agent 分别使用自己的私有 State。检索计划、
数据库原始记录等中间数据不会进入主 State。

评分采用固定 100 分制：Python 根据预算、规格和硬件兼容性确定性计算 70 分，LLM
只负责用途匹配 15 分、偏好满足 10 分和其他主观需求 5 分。硬件条件不通过的商品
直接淘汰，LLM 无权修改硬件分或淘汰结论。

默认数据库路径为 `data/computer_products_10000.jsonl`，由构建脚本从 Amazon Reviews
2023 Electronics 元数据筛选 10,000 条电脑商品。由于上游数据没有明确的再分发许可，
生成后的数据库和原始 Parquet 缓存不会提交到 GitHub；仓库只保留可复现构建脚本与
生成元数据。使用数据前请自行阅读上游数据集条款。

Graph 默认使用 `JsonlProductSearchBackend` 直接检索该文件。也可以实现
`ProductSearchBackend.search(plan)` 并注入其他数据库：

```python
graph = build_graph(search_backend=my_backend)
```

## 快速开始

安装运行依赖：

```powershell
python -m pip install -r requirements.txt
```

首次克隆后，安装额外的数据处理依赖并构建本地数据库：

```powershell
python -m pip install -r requirements-data.txt
python scripts\build_computer_catalog.py
```

设置大模型服务。不要把真实 API Key 写入代码或提交到 Git：

```powershell
$env:DASHSCOPE_API_KEY="你的 API Key"
$env:SHOPPING_AGENT_BASE_URL="你的 OpenAI 兼容接口 /v1 地址"
$env:SHOPPING_AGENT_MODEL="qwen3.7-plus"
```

运行 Agent 或测试：

```powershell
python agent.py "预算2500元，买27英寸4K非曲面显示器"
python -m pytest -q
```

## 数据来源

构建脚本使用 [Amazon Reviews 2023](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023)
的 Electronics 商品元数据。数据库只用于本地研究和实验；数据权利与使用限制以
上游说明为准。
