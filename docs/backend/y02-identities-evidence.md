# Y02：影片身份、豆瓣适配与证据契约

更新：2026-10-26（北京时间）。基线 `c6ac7df`，分支 `feat/y02-movie-identities-evidence`。这是实现及自测交接记录，未代签 PionneerZ 或 C 的评审。

2026-10-31 恢复与核对：本记录从当前分支 `e60f603` 恢复。Y02提交 `e891591` 尚未合入 `origin/main`；主分支缺少本记录不是删除决议。主分支已通过 `0e2a54c` / PR #6 接入其他成员的模型与LangGraph MVP，当前分支尚未包含该代码。原文中“未见C01交付”属于10月26日探测时快照；现在模型部分已有交付，但TMDB真实覆盖与C02第二独立评价源仍无对应实现证据。复用范围和剩余缺口见[三人台账的Git核对](../三人开发任务台账.md#2026-10-31--git-提交核对与后端复用清单)。本次未重跑联网探测。

## 当前结论

Y02 的离线适配器、身份映射与兼容契约已实现；真实数据出口及三方契约冻结尚未通过。Y01 之前的“已完成（受限）/受限通过”表述应纠正为“已执行探测，自动评价获取未通过”。

2026-10-26 复测使用 Before Sunrise (1995)、Little Women (2019)、Anora (2024)。9 次真实 HTTP 请求，不重试、不跟随安全验证跳转、不登录。身份搜索 3/3 返回200，得到候选 `1296339`、`26348103`、`36195543`；每个片名与年份只有一个匹配，但仍待独立身份核验。详情及评论共6次请求全部302至 `sec.douban.com/c`，状态 `access_limited`。评分、评论摘录、全文和可用引用均未取得；本轮429为0、超时为0，不能由此推断没有限流。

上次详情页使用无末尾斜杠的网址，301只是补斜杠；本次改用规范路径，才确认后续安全验证。上次脚本缺少 `--live`、歧义时选首条、请求计数按样本数估算、只统计搜索超时等问题均已修复，新增离线回归。历史报告备份在本地忽略目录 `artifacts/local-backup/`，未改写历史证据。

当前进程未配置 `TMDB_READ_TOKEN`；既有 TMDB 探测器返回 `NOT_CONFIGURED`，没有发起请求。主仓库未见可识别的 C01/TMDB 实测和 C02 独立评价源交付，未伪造中文/长尾覆盖率或外部ID映射成功。

## 已交付行为

- `scripts/douban_adapter.py`：标题/别名标准化与精确年份候选筛选；同名翻拍、无年份、多候选不自动确认；规范的详情/评论路径；403/418/429、安全验证、超时、HTTP错误、解析错误与预算耗尽分别记录。一次请求失败也计入预算，未请求不计数。只记录重定向目标的主机/路径，丢弃查询参数及原始错误信息。
- 评分解析仅支持与请求 subject ID 一致的 Movie JSON-LD；短评解析保留作者、评论ID、原始URL、采集时间，粒度为 `excerpt`。没有实现长评全文获取；影片简介不当作评价摘要。解析器只通过人工构造的合成HTML回归，实际评分/评论页面解析仍待网络可达后的验证。
- 评论剧透等级默认 `unknown`，使用依据 `unverified`，不能进入要求安全证据的默认推荐理由；不因拿到HTML而自动标记可发布或“全网共识”。独立来源组保持未知，评分和评论不会因此变为两个独立源。
- `scripts/movie_identity.py`：确认映射时保留现有 `itunes:` 主ID、片名、时长、海报、导演；不直接改成豆瓣ID，不以同名同年自动归并；同一provider出现冲突必须先解决。此函数接收受信任的核验结果，不向客户端开放“自行确认”权限，也未实现持久化登记（属Y03）。
- `scripts/s0_contracts.py`：`Movie.external_ids`、`Evidence.granularity/author/source_content_id/independent_source_group/usage_basis`、`SourceEvidenceResult`、`RecommendationResponse.source_results` 为兼容增量；原有响应和合成样例仍合法。无新必填客户端字段；原`0.1.0`契约与旧入口保留。若客户端固定旧Schema且禁止额外字段，需同步本次生成Schema/类型后部署。
- 共享来源状态为 `ok`、`no_results`、`not_configured`、`access_limited`、`timeout`、`parse_error`、`upstream_error`、`budget_exhausted`、`ambiguous`；缓存状态为 `none/fresh/stale`。`ok`仅表示取得材料，不代表多源核验、授权或完整覆盖；部分成功可带缺口警告。适配器自身无缓存，TTL实施留给Y04。
- `contracts/adapter-examples/` 为单独的合成适配器样例，不加入片库或真实服务回退；`s0_check`校验这些样例。导出新增 `source-evidence-result.schema.json`，真实OpenAPI、推荐响应Schema与前端生成类型同步更新。

## 复现

默认不联网；脚本不读取 `.env`。真实报告只保存状态、计数、候选元数据及URL，不保存原始HTML、评论文本、Cookie或密钥。

```powershell
python -m scripts.douban_probe
# 退出2，零HTTP请求
$env:DOUBAN_PROBE_NETWORK='direct'
python -m scripts.douban_probe --live --max-requests 9 --timeout 8 --output artifacts/douban/y02-direct-report.json
# 退出1：已经执行，但自动评价未通过
python -m scripts.s0_probe_tmdb --live --limit 3 --max-requests 8
# 当前退出2：TMDB_READ_TOKEN未配置，零请求
python -m scripts.s0_check
cd web/app
npm ci --ignore-scripts --no-audit --no-fund
npm run types:generate
npm test
npm run build
```

显式代理模式需设置 `DOUBAN_PROBE_NETWORK=proxy` 并传 `--proxy`；报告不保存代理地址。本次只复测direct，未扩大网络探测。

## 验证与剩余工作

按TDD先运行新增测试：模块/类型不存在导致2个收集错误；随后用例复现缺少联网开关、错误URL、重复映射、未定义来源状态及空评论与解析失败混淆；实现后通过。Python合计89项通过，前端34项通过，Schema导出检查及生产构建通过。第一次构建发现新增usage_basis被类型生成器当必填，已改为可选空值，并在豆瓣适配器明确填unverified；保留旧样例后重新生成类型、构建通过。未开展新的浏览器视觉验收，因为本次没有修改界面。

本轮未将豆瓣适配器接入 `/recommendations`，健康声明仍为 `ratings=false/reviews=false`；不会在Apple catalog锁内运行新增影评请求。先有独立确认的影片映射和真实证据通路，再由Y04/Y05接入生产推荐服务。

剩余出口：可用豆瓣评价通路及使用条件、TMDB配置与真实字段覆盖核查、C01/C02交付、同片第二独立源、P/C共同评审和前端真实响应联调。上述就绪前 Y02 保持进行中，不能以离线测试代替G2真实多源出口。

## 2026-10-26：保存并同步主仓库

Y02 改动先保存为本地提交 `e891591`，随后重新 fetch 并将最新 `origin/main`（`182a6c0`，PR #5）合入当前分支，合并提交为 `05ba67e`；没有文本冲突。保留了主仓库的首页、海报代理与回归更新。

合并后 `python -m scripts.s0_check` 通过，Python 94 项；前端 Vitest 34 项通过，`types:check`、`format:check`、生产构建及契约导出检查通过。Windows 检出的 CRLF 曾导致格式检查失败，转为 LF 后通过，Git 规范化后没有内容差异。

浏览器首次运行误复用了另一项目占用的 5173 端口，已停止该轮，保留原项目进程。随后使用忽略目录中的临时配置，以 5174 启动本项目，8000 启动独立后端，禁用已有服务复用。回归发现两处上游测试假设失效：冷启动目录超过默认 5 秒等待；从详情返回后未展开条件面板便点击隐藏按钮。先复现失败，再将首次目录等待设为 50 秒（客户端请求超时为 45 秒），并补充展开面板操作。修正后完整重跑 Chrome 桌面/手机、明/暗四组合，**224/224 通过，用时 12.6 分钟**。真实目录测试遵守上游限流等待；合成证据用例仍明确为离线场景。

本次浏览器报告位于本地忽略路径 `artifacts/merge-main/playwright-report/index.html`；临时配置位于 `artifacts/merge-main/playwright.config.ts`，不作为共享配置发布。测试自动覆盖的历史截图已恢复，未将机器相关截图混入提交。本轮通过不改变自动豆瓣评价获取未通过、Y02 尚待真实多源验收的结论。

## 2026-10-31：与主分支 MVP 整合

- 基线：Y02分支 `e60f603` 与主分支 `1d4d46f`；文档核对先保存为 `33d5b28`，代码合并为 `4e16081`。保留双方契约增量与实现，无文本冲突。
- 重新导出6份JSON Schema/OpenAPI并生成TS类型，无内容变化；当前合并后 `python -m scripts.s0_check` 为142项通过，前端单元34项通过，类型生成一致性和生产构建通过。
- 格式检查发现工作区3个前端文件换行不符合Prettier；规范化 `App.tsx`、`request-feedback.test.tsx`、`service-status.tsx` 后全仓前端格式检查通过。Git规范化后无内容差异，没有新增前端行为改动。
- 真实模型和豆瓣没有在本轮重新调用；Y02仍是离线实现交付，真实数据出口、独立来源与三方签收待完成。原任务剩余项见[三人任务台账](../三人开发任务台账.md)。
- 合并后的浏览器离线兼容回归：Chrome桌面/手机、明/暗四组合52/52通过，用时2.1分钟，覆盖S0六状态、0–3部与缺省字段、多平台来源展示、比较证据快照及非法评分引用拒绝。本轮仅运行 `--grep OFFLINE`，不是全量真实上游或模型验收；测试服务进程显式禁用模型配置，无付费模型调用。
- 本机浏览器报告在忽略路径 `artifacts/merge-main/y02-report/index.html`，截图在 `artifacts/merge-main/y02-screenshots/`；本地路径不是其他协作者可访问的共享证据。远程结果以合入后GitHub Actions为准。

## 2026-10-31：Y03–Y08 后端增量与验收

本轮从主分支 `68ff223` 创建 `feat/backend-persistence-evidence`。范围为原三人计划中可解除联调阻塞的后端持久化、反馈/记忆、证据服务基础和运行约束；不把历史MVP签收扩大为完整多源产品签收。原10月26日“未接入数据库/反馈”保留为历史快照，以本节为准。

### 实现与接口交接

- `app/services/storage.py`：SQLite版本迁移（当前v3）、事务、外键级联、偏好乐观版本、反馈event_id幂等与冲突、受控撤销、过期会话清理、备份及完整性检查；同一外部ID不能归属两个主影片。`create_app(repository=...)`可注入临时数据库，旧`scripts.movie_server`入口保留。
- `POST /identities`返回一次性匿名Bearer凭据，数据库只存SHA-256摘要。它是本机浏览器能力令牌，不是账号登录、多人认证或跨设备恢复；服务仍只绑定127.0.0.1。`POST /sessions`可绑定该身份。
- `GET/PUT/DELETE /me/preferences`：写入需`confirmed=true`和`expected_version`，保存支持的明确偏好；排除影片、同行、原始文字不能写长期偏好。删除偏好清空并关闭记忆；`GET/DELETE /me/seen`管理已看；`DELETE /me/data?confirmed=true`删除身份及关联偏好、已看、反馈、会话。旧令牌失效，不从旧上下文恢复。
- `POST /feedback`：`seen/unseen`为明确确认的长期已看状态；`dismiss/restore`只影响指定会话；`undo`使用`target_event_id`，不覆盖同片的后续修改。每个身份已看、每个会话临时排除上限400，防止超过推荐契约的排除容量。并发重复event_id只写一次；同ID不同payload返回409。接口只存确认ID和动作，不存用户原文。
- 推荐的双开关：服务端偏好enabled与请求`memory_enabled=true`同时成立才读取长期记录；本次条件覆盖历史，模型明确清空的字段在连续调整中仍保持清空；长期记忆不写回临时条件。已看参与硬排除。保存/删除期间版本变化使旧推荐返回409，不能提交旧状态结果。
- `app/services/evidence.py`：仅对独立确认的外部映射调用适配器；持久TTL缓存、fresh/stale语义、更新失败保留原采集时间；统一`source_results`输出。来源域名数量不等于独立性，独立publisher组保持来源声明，不从URL臆造。没有使用依据的正文/评分不会存库或发布。当前生产只可显式启用既有豆瓣适配器，没有第二独立源实现。
- `app/services/budget.py`、`request_limits.py`：同请求共享最多20次HTTP、3次搜索、45秒响应时限；失败请求计数，缓存命中不计，目录/模型/豆瓣/海报共用预算；等待目录锁也受剩余时间限制。无自动重试。超时返回504，阻塞工作线程可能继续到当前底层调用退出，但不能把迟到结果写回图会话/当成成功响应；单次HTTP超时取剩余预算。不是任意Python函数的强制终止机制。
- `X-Trace-ID`及`X-Upstream-Calls`响应头与脱敏路由日志：只含路由模板、状态、计数、耗时，无Bearer、query、用户文字或外部URL。个人数据接口`Cache-Control: no-store`。JSON/OpenAPI/TS类型均由Pydantic重新生成。
- 前端偏好页：明确同意后创建匿名身份并启用记忆；保存当前点选、关闭/启用、清空偏好、已看移除及全部数据二次确认删除。候选“确认已看并保存”连接真实反馈API；失败不假报成功。原本次片单、对比、临时隐藏继续保留页面内存语义。逐来源缺失/失败/缓存状态在候选中显示。

### 配置、启动、备份与恢复

默认数据库为忽略路径`artifacts/state/movie.sqlite3`。可在**进程环境**设置`MOVIE_DB_PATH`改为其他绝对路径；该变量和`MOVIE_DOUBAN_LIVE`不自动读取.env。模型配置仍按README从根目录.env读取。依赖没有新增顶层包，复用FastAPI的AnyIO及Python标准库SQLite。

```powershell
python -m pip install -r requirements-s0.txt
python -m scripts.backend_admin check
cd web/app
npm ci
npm run build
cd ../..
python -m uvicorn scripts.movie_preview:app --host 127.0.0.1 --port 8000
```

备份输出必须为不存在的新路径，不会覆盖已有备份；数据库和备份含个人记录，保留在Git忽略目录：

```powershell
python -m scripts.backend_admin backup --output artifacts/backups/movie-20261031.sqlite3
python -m scripts.backend_admin --database artifacts/backups/movie-20261031.sqlite3 check
```

恢复时先停止本项目服务，**把`MOVIE_DB_PATH`指向已检查的备份副本**后重新启动，不覆盖原库；先验证偏好/已看隔离和数据版本。备份早于删除操作时会保留历史数据，恢复后须重新执行需保留的删除，不宣称备份具备远程撤销机制。

已独立核验影片身份后，管理员可本机登记映射（不能仅凭同名同年或候选搜索结果执行）：

```powershell
python -m scripts.backend_admin map --movie-id itunes:实际主ID --provider douban --external-id 实际核验ID --basis human_verified --confirmed
```

只有存在确认映射，且在启动进程显式设置`$env:MOVIE_DOUBAN_LIVE='1'`，推荐才会发豆瓣请求；该开关不绕过安全验证，也不授予正文存储/发布权限。缺配置/映射显示not_configured；未确认映射显示ambiguous，禁止自动选首条。

### 已执行验证与仍未通过项

- TDD：先添加仓储/API、证据/预算、页面组件测试，分别因待实现模块缺失失败；新增身份隔离、事务幂等、撤销、版本竞争、偏好删除/连续调整、防迟到响应与真实总时限等行为后实现通过。浏览器首轮因测试定位匹配两个status元素失败，改为精确反馈定位后重验通过。
- 最终开发环境后端166项、前端38项单测通过；Schema/机器规格、构建和格式检查通过。独立`artifacts/backend-venv`安装`requirements-s0.txt`后同样166项通过，`pip check`无损坏依赖。独立环境仍位于同一Windows主机，不代替另一人的环境复现。
- SQLite重启读取、v1→v2→v3迁移、备份副本完整性和偏好恢复已验证；本地CLI检查/备份/副本检查通过，原数据库未覆盖。临时状态与报告均在忽略目录。
- Chrome桌面/手机、明/暗四组完整回归228/228通过（10.1分钟），覆盖真实Apple、纯规则自然语言、来源面板、比较、故障恢复，以及明确标注的离线合成契约场景。最后补丁对记忆、连续请求、冲突确认及比较另跑24/24（1.5分钟）。记忆接口实际写临时SQLite；Axe及窄屏无横向溢出通过。历史截图的自动覆盖已恢复；新增[桌面浅色](../frontend/screenshots/backend-20261031/desktop-light-memory.png)与[手机深色](../frontend/screenshots/backend-20261031/mobile-dark-memory.png)只含测试状态，无令牌/个人材料。
- 首轮完整回归暴露旧断言仍期待记忆不可用、旧health固定行数和真实上游限流。测试现按明确授权按钮和逐能力行检查，限流等待一分钟后仅重试一次，未放宽生产限额。最终复核先用失败测试确认并修复：排除合计超500返回409；证据失败不提交未送达的Agent上下文；请求级评分不污染共享片库；另补旧v1库保留偏好迁移及失效匿名身份重新授权。
- `python -m scripts.backend_acceptance --live`及最终复验：真实Apple目录3次上游请求、3部候选，偏好硬过滤、已看跨会话排除、反馈幂等、删除/令牌撤销七项检查全部通过。没有模型调用；来源状态not_configured未伪装为多源成功。脱敏报告`artifacts/backend-acceptance/final-live-smoke.json`。
- 豆瓣显式复测9次请求：3个身份候选、6次安全验证重定向；评分0、短评0、全文0。`TMDB_READ_TOKEN`缺失，TMDB零请求；LLM配置缺失，本轮零付费模型请求。探测报告`artifacts/douban/20261031-development.json`；没有保存原HTML或评论正文。
- 剩余：豆瓣真实可用评价通路与使用条件、TMDB真实覆盖、第二独立评价源、口碑综合/低剧透真实验收、M11真实模型冲突/失败恢复、另一成员环境复现、P/C独立主审、最终签收与云端CI。不可把本轮工程实现标成原完整多源产品已经验收。

### 本轮验收范围与下次提醒

用户2026-10-31确认“暂时用离线，后续提醒我用真实模型验收”。本轮按离线工程验收交付，既有Apple真实冒烟作为附加证据；不再为本轮等待LLM/TMDB配置，也不把离线模型替身标成真实DeepSeek通过。

下一次继续开发或最终交付前，先提醒用户在本机配置`LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`（不发聊天），再明确运行`python -m scripts.mvp_probe_model --live --case E02 --max-requests 1`，以及同一版本的真实冲突确认、失败恢复、记忆开关/补充/换组与删除验收；记录实际响应模型及脱敏结果。TMDB另需进程变量`TMDB_READ_TOKEN`，豆瓣/第二源仍需真实可用通路。P/C独立评审与另一环境复现保留待办。
