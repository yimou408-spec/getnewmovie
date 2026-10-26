# M02：最小接口约定与机器样例

日期：2026-10-26。9条通俗样例已获用户确认。本文件确定后续 M03–M07 的实现目标；当前在线 API 和页面行为尚未改变。

## 文件入口

- 人工阅读：[MVP输入输出样例](MVP输入输出样例.md)。
- 机器读取：[9条输入、上下文、预期结果与完整合成响应](../contracts/mvp/intent-cases.json)。
- 目标模型输出的 JSON Schema：[intent-decision.schema.json](../contracts/mvp/intent-decision.schema.json)。
- 类型与离线检查：[mvp_intent_contracts.py](../scripts/mvp_intent_contracts.py)。
- 行为检查：[test_mvp_intent_contracts.py](../tests/test_mvp_intent_contracts.py)。

所有电影、证据、会话ID和确认ID都是人工合成。`execution_status=not_run_against_agent` 明确表示这些是目标样例，不是模型实测结果，禁止拿样例电影作为真实目录回退。

## 模型只返回理解结果

```json
{
  "action": "recommend",
  "updates": {
    "genres": ["喜剧"],
    "moods": ["轻松解压"],
    "max_runtime_minutes": 120,
    "exclude_genres": ["恐怖"]
  },
  "conflicts": [],
  "unhandled": []
}
```

模型不能返回电影名单、评分、URL或长期写入操作，类型校验拒绝这类额外字段。影片及证据始终由真实目录工具提供。

| 字段 | 约定 |
|---|---|
| action | `recommend`首次推荐；`refine`补充条件；`reroll`换组；`reset`重新开始 |
| updates | 复用现有 Constraints；只发送本轮提到的字段，未发送表示保留；显式空列表表示清除对应列表，时长为null表示解除时长限制 |
| conflicts | 需要用户选择的矛盾，最多两项 |
| unhandled | 暂不能执行的条件，最多两项；确认后只按可执行条件继续，不把它们标成已满足 |

实现时必须使用 `updates.model_dump(exclude_unset=True)` 取得更新，不能将默认空值展开后覆盖旧条件。列表更新表示更新后的完整列表；例如追加排除时，工作流结合上下文形成完整排除列表。

`action` 是工作流内部决策，当前不是在线推荐请求新增字段。自然语言由模型识别动作；已有换组按钮继续使用现有 `constraints.exclude_movie_ids`。重新开始可由前端新建会话并清空本次筛选实现，不需要为此新增端点。

## 请求、上下文和响应如何衔接

机器样例每条包含：

| 部分 | 用途 |
|---|---|
| request | 按当前 RecommendationRequest 校验的请求；零输入时填入固定探索文字，满足现有 query 非空要求 |
| context | 服务端或测试维护的上一轮条件、已展示ID；不是在线请求字段，不允许模型凭空生成 |
| expected_intent | 期望模型/按钮归一化后的内部动作与条件更新 |
| expected_constraints | 更新完毕后交给代码筛选的完整条件 |
| response | 按当前 RecommendationResponse 校验的完整合成响应；用于核对ready、empty及needs_clarification的结构 |

首次推荐在本次点选条件基础上应用更新；补充条件/换组从上一轮条件继续。换组额外排除本次已展示电影。reset清空筛选、未完成确认与本次排除，保留独立片单/比较。

示例：E05的输入是“改成90分钟以内”，更新只有 `max_runtime_minutes=90`，最终条件仍包含喜剧、轻松、排除恐怖。E06继续这些条件并加入已展示ID。E09响应为空并解释原因，不自行放宽。

存在冲突或未支持项时，使用现有 `needs_clarification`、`questions`、`clarification_id` 和确认提交结构，最多两个问题；确认前不查询最终候选。E03的选项分别决定保留恐怖或排除恐怖，冲突解决后才进入真实查询。确认ID由服务端生成，样例中的固定ID只用于说明结构。

### 解析方式的接入约定

当前 `Interpretation.method` 只允许 `rules-v1`。后续接入模型时在共享类型中增加 `llm-v1`，由实际执行路径填写；规则回退仍是 `rules-v1`，附上降级说明，不能仅改显示文字。

M02暂不对在线 API 增加尚未实现的能力声明或字段。M06实施接线时必须从共享类型重新导出 OpenAPI/Schema，再生成前端类型，M07同步展示。模型内部决策 Schema单独保存在 `contracts/mvp/`，不混入现有在线 Schema。

## 本轮校验方式

在仓库根目录，使用已安装项目依赖的 Python：

```powershell
python -m scripts.mvp_intent_contracts
python -m pytest tests/test_mvp_intent_contracts.py -q
```

修改目标模型输出类型后重新导出：

```powershell
python -m scripts.mvp_intent_contracts --export-schema
```

本机也可用 `artifacts/preview-venv/Scripts/python.exe`。若临时目录不可写，给 pytest 指定项目忽略目录下的专用 `--basetemp=artifacts/pytest-mvp`。

这些检查验证请求/响应结构、补充条件不丢失、冲突与确认一致、禁止模型编造额外字段，以及9条规格完整。它们不执行真实模型或在线Agent；M03验证模型，M05/M06验证工作流，最终页面验收另行记录。

## 接下来从哪里继续

M03直接复用 `IntentDecision` 和它的Schema编写提示词与适配器，不再另创一套字段。先以HTTPX测试替身返回E02的理解结果，验证解析；再做一次有限额度的真实请求，记录实际模型、结束原因、耗时和用量。模型理解结果通过不等于实际推荐链路已经完成。
