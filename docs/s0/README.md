# S0 数据与接口可行性：启动包

对应[开发计划](../开发计划.md)第7节S0，建议2–3个团队工作日。本目录只覆盖第一阶段，不将模拟接口视为推荐产品已完成。

## 交付与责任

| 交付 | 负责人 | 文件/入口 | 当前状态 |
|---|---|---|---|
| 交互规格及可运行线框 | A | [交互与验收](交互与验收.md)、`web/s0/index.html` | 已创建，待三人评审 |
| API/Schema/错误状态 | B | [接口契约](接口契约.md)、`contracts/generated/` | 可导出并自动检查 |
| 共享Mock及本地服务 | B，A/C使用 | `contracts/examples/`、`scripts/s0_mock_server.py` | 离线合成数据 |
| 数据源可行性实验 | B | `scripts/s0_probe_tmdb.py`、`data/s0/tmdb_samples.json` | 脚本就绪，真实接入待运行 |
| 数据许可登记 | B | [数据与许可清单](数据与许可清单.md) | 已登记已知信息及未知项 |
| 模型接口小实验 | C，B协作 | `scripts/s0_probe_model.py` | 一次固定输入调用，真实实验待运行 |
| 30条匿名合成任务与评估脚本 | C | `data/s0/eval_tasks.json`、`scripts/s0_evaluate.py` | 20条开发、10条保留；非真实用户偏好答案 |
| 检查记录与退出条件 | B/C，A复核 | [验收记录](验收记录.md) | 离线检查可运行，S0整体待验收 |

## 安装与离线检查

在仓库根目录使用Python 3.11+：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-s0.txt
.\.venv\Scripts\python -m scripts.s0_export_contracts
.\.venv\Scripts\python -m scripts.s0_check
```

已有兼容依赖时可直接使用`python`。导出脚本从Pydantic模型生成JSON Schema和OpenAPI；修改契约时一起更新导出结果、样例和测试。CI仅运行离线检查。

启动可运行线框/Mock：

```powershell
python -m uvicorn scripts.s0_mock_server:app --host 127.0.0.1 --port 8000
```

打开`http://127.0.0.1:8000/`体验线框，`/docs`查看接口。只绑定本机，模拟服务不含认证、数据库、真实LLM或外部数据调用。所有请求均带`X-Data-Mode: synthetic`响应头。原型与Mock同源，无需另配CORS。

## 真实实验

环境变量文件（包括`.env.example`）仅保留本地，由Git忽略，不上传仓库。所需变量名：TMDB使用`TMDB_READ_TOKEN`及可选的`WATCH_REGION`（默认CN）；模型使用`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`。脚本**不自动读取.env**，可在终端设置环境变量；Key只通过环境传入，不作为命令行参数、日志或报告内容。不要把密钥值写进提交。缺少配置返回退出码2且不请求网络。

TMDB默认只查3个样本、最多8次HTTP请求；搜索与详情各算一次，失败也占预算，不自动重试：

```powershell
python -m scripts.s0_probe_tmdb --live --limit 3 --max-requests 8 --region CN
```

逐批覆盖30部时显式扩大到`--limit 30 --max-requests 60`。参考片名/年份目前均待核验，未填TMDB ID；候选数量不为1时不会自动选首条。一条结果也仅是待确认候选。报告保留缺失率、分母、身份歧义、地区覆盖和时延，不验证是否真的可播放。`matches_reference`仅表示符合输入参考ID，参考未人工确认时仍标待核验。

模型实验使用环境中的`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`。基础URL需为HTTPS，例如供应商的`https://host/v1`；脚本调用其`/chat/completions`，不适用于其他协议，单次请求也可能收费：

```powershell
python -m scripts.s0_probe_model --live
```

只检查“100分钟以内、不要恐怖”固定合成输入的解析，不上传访谈或用户数据，不代表模型选片质量。当前不指定供应商、价格和已验证模型。

## 离线评估

推荐实现/实验程序后续生成JSON数组：`[{"task_id":"S0-01","response":{...}}]`，其中response符合契约。每次必须覆盖指定split的所有任务，重复、缺失、额外任务都会失败。

```powershell
python -m scripts.s0_evaluate --predictions artifacts/s0/predictions.json --split dev
```

当前尚无推荐实现，也没有伪造一份全部通过的预测。脚本只检查结构、状态和已标注硬条件，并将人工检查项列为manual_checks_pending；主题真伪、严重剧透、记忆写入、主观愿看仍需独立测试或人工评审，不能据自动检查声称已验证。这批任务是可公开的回归起点，后续模型调优后需补充未见任务，公开的holdout不保证盲测。

退出码：0为本次检查/实验完成且无自动错误；1为检查失败、上游错误或预算不足；2为参数错误或未配置/未启用联网。TMDB命中或单次模型解析成功不等于S0整体通过。

生成报告默认写到`artifacts/s0/`，已被Git忽略。审查后将不含敏感字段的结论填写[验收记录](验收记录.md)，不自动提交原始响应。
