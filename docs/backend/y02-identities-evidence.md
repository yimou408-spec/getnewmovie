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

交付代码`d2fe338`已推送，评审入口为[PR #7](https://github.com/yimou408-spec/getnewmovie/pull/7)，目标main，等待独立主审。云端[后端检查](https://github.com/yimou408-spec/getnewmovie/actions/runs/41189032534)与[前端检查](https://github.com/yimou408-spec/getnewmovie/actions/runs/41189032572)均在运行任何步骤前被GitHub拒绝启动；检查注释为“The job was not started because recent account payments have failed or your spending limit needs to be increased.”。账号Billing & plans恢复后再重跑，不能把这两条标作代码测试失败或CI通过。未修改账号付款/限额设置。

## 2026-11-01：TMDB 单样本真实访问通过

- 用户在自己的PowerShell窗口配置`TMDB_READ_TOKEN`并运行单样本探测；本次读取本地忽略报告`artifacts/s0/tmdb-report.json`核对，采集时间为北京时间2026-11-01 17:18。共2次真实请求、1部详情、0错误；《重庆森林》(1994)返回候选`tmdb:11104`、中文片名、102分钟时长、11个关键词及6个别名。
- 结果仍为`candidate_unverified`，需独立核对影片身份；CN地区观看渠道未知，不能解释为没有观看渠道。未修改`data/s0/tmdb_samples.json`的`pending_review`，未登记确认映射，也未接入生产推荐或认定多源评价验收通过。
- 接续检查：当前代理进程和Windows用户级环境变量均未取得非空`TMDB_READ_TOKEN`。因此未发起新的三样本请求；用户窗口中的配置不能由本次结果推断为其他进程可见。未读取或输出令牌内容。
- 下一步：在用户已配置令牌的同一PowerShell运行`python -m scripts.s0_probe_tmdb --live --limit 3 --max-requests 6 --output artifacts/s0/tmdb-20261101-three-samples.json`，最多6次请求。三样本仅验证中文资料及字段可达性；身份核对、翻拍/同名消歧和生产接线另行验收。

### 三样本探测结果（北京时间17:21）

- 已读取用户运行的`artifacts/s0/tmdb-20261101-three-samples.json`：3条样本、5次真实请求、0错误，预算未耗尽；本次代理未额外联网请求。
- 《重庆森林》(1994)候选`tmdb:11104`，102分钟、6个别名；《花样年华》(2000)候选`tmdb:843`，99分钟、15个别名。两者均取得中文详情，仍为待独立核验候选，不能以两条详情推断片库总体覆盖率。
- 《千与千寻》(2001)检索返回`129`和`535075`两个候选。探测器按歧义规则停止获取其详情，没有自动选择首条，因此仅有2条详情、共5次请求；这是消歧保护生效，不是API认证或网络失败。尚未核查两个候选各自的内容及类型。
- 3条观看渠道状态均为unknown，其中第三条未进行详情查询，不能当作三个已核验影片都没有CN渠道。下一步核对两个候选的原名、导演、年份和作品类型，并为最终映射留证据；三条样本继续保持`pending_review`。生产TMDB适配与第二独立评价源仍未完成。

### 《千与千寻》身份人工确认（2026-11-01）

- 核验者：用户（项目持有人），在本次会话中明确确认第一个候选为目标电影，第二个候选为拍摄《千与千寻》的纪录片。候选URL分别为`https://www.themoviedb.org/movie/129`与`https://www.themoviedb.org/movie/535075`。这是用户人工核验依据，代理未独立访问网页复核导演等字段。
- 已将`data/s0/tmdb_samples.json`的M03设置为`expected_tmdb_id=129`、`reference_status=human_verified`；M01/M02及其他未核验样本继续保持`pending_review`。原探测报告保留不变，不将历史ambiguous结果改写成成功，也未创建与Apple主ID的生产映射。
- 下一步先按已确认参考ID重跑三样本探测，获取M03详情并确认`matches_reference`。随后实现TMDB生产资料适配、受控身份映射与缓存/预算接线，再验收中文资料和来源显示；独立评价源及口碑综合另行完成，不能以本次人工确认代替。

## 2026-11-01：TMDB 资料适配接入推荐

- 用户已持久保存令牌，本轮从Windows用户环境安全传入子进程，未输出或写入仓库。启动服务使用进程变量`TMDB_READ_TOKEN`；`MOVIE_TMDB_LIVE=0`可禁用，默认有令牌即启用。这两个变量不自动读取`.env`，已运行的服务需重启。
- 新增`scripts/tmdb_adapter.py`，只对确认的数字ID请求`/3/movie/{id}`，最多一次HTTP，无重试/跳转；只取中文片名、原名、年份、时长和最多5个别名作为metadata证据，不取简介、影评、评分、海报或观看渠道。来源URL、采集时间、内容ID和provider_terms依据随证据保留；按[TMDB FAQ](https://developer.themoviedb.org/docs/faq)用于有署名的非商业原型，不声明商业授权。
- `EvidenceService`按已有确认映射接入TMDB，复用30分钟持久缓存、fresh/stale状态及全请求预算/时限。将已确认链接附加到请求内候选，保留Apple主ID、原片名、时长、排序和硬筛选；不修改共享目录。没有映射不搜索，候选映射不请求，禁用或缺令牌会显示未配置。
- 当前未创建真实Apple↔TMDB生产映射。《千与千寻》的人工确认仅核验TMDB查询种子；本轮Apple US直接搜索未取得候选，首次通过旧搜索入口触发榜单回退后被3次预算阻断，因此没有据此创建映射。后续必须核对真实Apple ID、导演、年份及作品类型后登记，不以片名/年份直接自动确认。
- 复现配置：启动后端前在进程设置令牌，构建/启动沿用README。独立核验跨源身份后使用现有命令`python -m scripts.backend_admin map --movie-id itunes:实际核验主ID --provider tmdb --external-id 实际核验TMDB_ID --basis human_verified --confirmed`。样本的`expected_tmdb_id`不会自动导入数据库。
- 已核对[官方署名要求](https://www.themoviedb.org/about/logos-attribution)，保存其官方原始SVG为`web/app/public/tmdb-logo.svg`，关于页和取得TMDB资料的来源面板显示标识及“This product uses the TMDB API but is not endorsed or certified by TMDB.”。未改变接口类型；现有JSON Schema/OpenAPI/TS生成链继续复用。

### 真实结果与数据质量

- 按用户确认参考ID重新运行三样本探测，报告`artifacts/s0/tmdb-20261101-confirmed-three.json`：6次请求、3条详情、0错误、0歧义；M03为matches_reference且无需再次人工核验，M01/M02仍待核验。探测器只验证API字段可达，不代表资料可直接发布。
- 该报告中M03的中文title实际包含广告网址；本轮另取TMDB英文资料核对到原名及导演Hayao Miyazaki，但没有修改上游内容，也未把污染中文片名替换为已验证资料。适配器对名称字段进行NFKC标准化并拒绝明显网址、标记、控制字符及过长内容；不保证识别所有上游错误。必需片名异常时返回parse_error且不发布/缓存正文，异常可选别名忽略。
- 新适配器真实复验`artifacts/s0/tmdb-20261101-adapter-smoke.json`：共3次HTTP；重庆森林、花样年华各取得1条资料，千与千寻的污染片名被拒绝（parse_error、0证据）。报告仅存状态、计数及固定警告，不复制污染正文。无模型调用、无豆瓣调用、无个人数据库写入。
- 剩余：真实Apple跨源映射登记与真实推荐联合验收、污染字段上游恢复后的复验、第二独立评价源与口碑综合、M11真实模型验收、M12独立环境/最终签收。三条CN渠道仍未知。

### 本轮工程验收

- TDD：新增后端测试先因`scripts.tmdb_adapter`缺失收集失败；页面署名测试先因组件未实现失败，随后实现通过。新增20条后端用例覆盖同片绑定、候选/缺映射不请求、HTTP错误/超时、广告污染、别名边界、缓存过期、禁用与共享目录不被修改；全量`python -m scripts.s0_check`最终186项通过。
- 前端Vitest39项通过，`types:check`生成一致性、生产构建及`format:check`通过；契约类型无变化，未手改生成文件。
- 新增`tests/tmdb.spec.ts`明确使用离线合成资料；Chrome桌面/手机、明/暗四组合4/4通过，Axe检查和横向无溢出通过，约2.9分钟。测试仅验证本轮资料面板、署名、图标加载及关于页，不替代真实多源或模型验收，也未重跑历史全量228项。
- 已查看桌面浅色及手机深色截图，文字与标识可读；截图在本地忽略目录`artifacts/tmdb-ui/`，测试服务独立绑定8011、模型/豆瓣禁用，未占用原预览端口。无新依赖，代码尚未提交/推送。

## 2026-11-01：两组真实映射登记与推荐联合验收

用户明确要求继续核验并登记映射及真实联调。本节更新上节“尚未创建真实映射”的阶段快照，不代签用户人工核验或其他成员评审。

### 映射依据（代理多字段核验）

| Apple主ID/来源 | TMDB ID/来源 | 核验结果 |
|---|---|---|
| [1886817811](https://itunes.apple.com/us/movie/the-legend-of-hei-ii/id1886817811) · The Legend of Hei II | [1144107](https://www.themoviedb.org/movie/1144107) · 罗小黑战记2 / The Legend of Hei 2 | 2025年、动画、Apple导演MTJJ & Jie GU与TMDB的MTJJ/Gu Jie对应；英文资料119分钟与Apple119分钟一致，随后中文资料120分钟。英文别名包含The Legend of Hei II；确认对应同一影片，保留两源时长差异。 |
| [1806410314](https://itunes.apple.com/us/movie/vampire-hunter-d-dubbed/id1806410314) · Vampire Hunter D (Dubbed) | [9463](https://www.themoviedb.org/movie/9463) · 吸血鬼猎人D | 1985年、动画、导演Toyoo Ashida完全一致；英文标题对应，Apple81分钟与TMDB英文80/中文82分钟接近。Apple是配音发行条目，TMDB为作品级ID，未宣称音轨/剪辑版完全相同；硬过滤仍采用Apple81分钟。 |

- 暂缓`itunes:1583335569`↔`tmdb:212162`（魔法少女小圆 叛逆的物语）：片名、2013年和117分钟一致，但Apple导演Akiyuki Shimbou与TMDB Director记录Yukihiro Miyamoto不同。尚未独立核对职务差异，不登记，不因单个搜索结果直接确认。
- 原始精选元数据与核验决定保留于本地忽略目录`artifacts/tmdb-mapping/apple-candidates.json`、`tmdb-candidates.json`、`verified-mappings.json`；核验者为Codex代理，非人工签收。Apple发现3次HTTP，TMDB候选检索/英文详情6次、中文适配复查2次，无自动重试。
- 为准确记录上述依据，给`ExternalMovieIdentity.basis`追加`multi_field_verified`，与`human_verified`、`provider_mapping`区分；不是开放客户端自助确认接口。`backend_admin map --basis`同步支持该值，Pydantic重新导出OpenAPI/响应Schema及前端TS类型。严格旧客户端须同步新枚举后使用。
- 登记前创建本机数据库备份`artifacts/backups/pre-tmdb-map-20261101-180134.sqlite3`，随后向默认`artifacts/state/movie.sqlite3`登记上述两组映射，完整性检查ok、schema v3；未修改个人偏好/已看记录或覆盖已有映射。

已核对上述证据后，其他环境可使用：

```powershell
python -m scripts.backend_admin map --movie-id itunes:1886817811 --provider tmdb --external-id 1144107 --basis multi_field_verified --confirmed
python -m scripts.backend_admin map --movie-id itunes:1806410314 --provider tmdb --external-id 9463 --basis multi_field_verified --confirmed
python -m scripts.tmdb_acceptance --live --movie-id itunes:1886817811 --movie-id itunes:1806410314
```

### 真实推荐与页面结果

- 新增`scripts/tmdb_acceptance.py`：必须`--live`、非空进程令牌及1–3个已确认映射Apple ID才请求；以真实Apple目录/仓储/TMDB适配执行两次watchlist推荐。无模型、无豆瓣、无身份创建或个人记忆写入；只更新资料缓存。报告在Git忽略路径，默认`artifacts/tmdb-mapping/recommendation-smoke.json`。
- 本次两源真实API联合验收8项全部通过：两次HTTP200、确认映射候选、fresh缓存、同片metadata证据、无评分/影评、Apple资料稳定、第二次零HTTP、未使用记忆。第一次共4次上游请求（2次Apple lookup、2次TMDB详情），第二次0次。这个结果验证上述两组，不证明全片库覆盖或推荐质量。
- 本机同源预览独立启动于`http://127.0.0.1:8012/`，使用已登记数据库及TMDB令牌，禁用模型和豆瓣。Chrome桌面浅色/手机深色2/2真实页面通过：点选动画与榜单顺序、确认The Legend of Hei II候选、打开来源面板、核对中文资料与两源链接；Axe及无横向溢出通过。截图[桌面浅色](../frontend/screenshots/tmdb-20261101/desktop-light-live.png)、[手机深色](../frontend/screenshots/tmdb-20261101/mobile-dark-live.png)保留真实metadata，无令牌或个人材料；本机临时Playwright配置/脚本在`artifacts/tmdb-mapping/`。
- TDD：先以失败测试复现basis枚举缺失和验收模块缺失，再实现；最终`s0_check`189项通过，前端39项、生产构建及格式检查通过。生成文件由工具重建，不手改Schema/TS；本轮未重复历史全量浏览器228项。未提交/推送。
- 后续仍缺：更多映射与批量消歧、千与千寻污染字段复验、独立评价源/口碑综合、真实模型M11、独立环境M12及签收。上述两源仅为影片资料，不能标成“真实多源评价已完成”。

### 联调验收脚本异常补测

- 用户确认“不支持该模型”的报错来自当前对话界面并要求继续测试；本次仅检查电影项目配置完整性（无模型配置），未发模型请求、未修改对话服务或模型设置。
- 按TDD追加7项用例：无令牌/无映射数据库/无已确认映射时零网络，HTTP失败、非法JSON、缺失响应字段、空证据、错片、错误TMDB内容ID不通过。复现验收器直接抛JSON/字段异常及内容ID不一致误判通过后修复：先按RecommendationResponse校验响应，额外绑定source_content_id与已确认外部ID及来源URL；异常标失败，不写原始错误正文。合计9项验收脚本测试通过。
- 最终`s0_check`196项通过，契约检查通过；本次仅后端验收器改动，无前端变更，沿用上一节39项单测及真实页面证据。
- 修复后真实复验报告`artifacts/tmdb-mapping/recommendation-smoke-negative-fix.json`，新增响应契约检查后9项全部通过；两次请求上游计数为2/0（两部Apple lookup；TMDB资料命中先前缓存），零模型/豆瓣请求。保留前次4/0冷TMDB缓存结果，不用本次缓存复验冒充新采集。

## 2026-11-01：影评获取增量与最终验收复查

- 用户要求“先提交并推送，再把验收完成”。已先提交并推送`fd28138`至`origin/feat/backend-persistence-evidence`，远程哈希复查一致；无关`.vscode/`保持未跟踪。本节记录其后的增量，未把缺配置或访问失败项目填成通过。
- 官方依据：[影评接口](https://developer.themoviedb.org/reference/movie-reviews)、[API条款](https://www.themoviedb.org/documentation/api/terms-of-use)、[非商业使用与署名FAQ](https://developer.themoviedb.org/docs/faq)，本轮均HTTP200。现有署名继续有效。非商业原型有限摘录标记provider_terms，不代表商业授权。
- 新增`scripts/tmdb_reviews.py`与`MOVIE_TMDB_REVIEWS_LIVE=1`可选接线；需进程`TMDB_READ_TOKEN`，且`MOVIE_TMDB_LIVE`未关闭。默认不取影评，只对已确认TMDB映射请求英文第一页，一次HTTP、最多3条、600字符/条，无重试/跳转。与metadata使用不同来源名`TMDB Reviews`和缓存键，复用30分钟TTL及共享预算。
- 校验影片ID、24位内容ID、固定原文URL、作者及纯文本范围；拒绝含HTML/链接/控制字符的材料，去重，不读取用户头像/个人主页/个人评分。保留作者、内容ID、采集时间、原文链接和excerpt粒度；独立来源组为空、spoiler_level=unknown，不能进入默认推荐理由。页面显示作者和“原文摘录”，主动展开后才显示正文；来源能力状态只表示配置了实现，不保证每片上游可用。

### 样本、映射与真实结果

- 英文影评10部覆盖探索（每片1次HTTP，首屏，不存正文）：TMDB 11104、843、129、550、155、238、27205、496243共8部有记录；1144107和9463两部为0，保留缺失分母。报告`artifacts/tmdb-mapping/review-discovery.json`仅存ID/作者/URL/字符数；没有据此推断独立原创、低剧透或创建Apple映射。重庆森林/花样年华的Apple US直接搜索仍空；火影忍者317442可核对作品资料但影评0，均未为凑覆盖登记。
- 《黑天鹅》Apple [407742758](https://itunes.apple.com/us/movie/black-swan/id407742758)与TMDB [44214](https://www.themoviedb.org/movie/44214)：同名、2010年、导演Darren Aronofsky一致，Apple109分钟、TMDB108分钟；确认作品级对应，仍保留Apple硬过滤字段。核验者为Codex代理，basis=multi_field_verified。精选资料保留`artifacts/tmdb-mapping/drama-identity-candidates.json`与`black-swan-identity.json`；登记前备份`artifacts/backups/pre-review-map-20261101.sqlite3`，没有改动个人偏好。
- 真实取得1条BonStevenson影评，内容ID`5da63e4ee6d3cc0015abbbf4`，原文[链接](https://www.themoviedb.org/review/5da63e4ee6d3cc0015abbbf4)，摘录320字符。仅证明这个作者样本可取得，不确认独立原创，不概括全网口碑。正文只按原型缓存策略本机保存，验收报告不写claim字段。
- `tmdb_acceptance --reviews`9项通过：HTTP、响应契约、映射候选、影评覆盖/缓存、同片作者与原文URL绑定、未推断剧透/独立性、未进入默认理由、第二次零HTTP、未用记忆。报告`artifacts/tmdb-mapping/review-recommendation-smoke.json`；首次3次HTTP（Apple详情/TMDB资料/影评各1），第二次0次。
- Chrome桌面浅色与手机深色真实页面2/2通过：影片详情加入片单、从片单推荐、来源面板核对影评作者、正文默认隐藏、主动展开/收起、原文链接与署名、Axe及无横向溢出。截图[桌面](../frontend/screenshots/tmdb-20261101/desktop-light-review-live.png)、[手机](../frontend/screenshots/tmdb-20261101/mobile-dark-review-live.png)已查看，截图正文收起。测试Chrome先卡本地导航，使用本次测试进程`--no-proxy-server`后恢复，未更改系统代理；初次脚本未展开筛选面板导致按钮定位失败，修正后完成真实链路。临时脚本/配置在`artifacts/tmdb-mapping/review-ui.*`。预览8013独立启动、模型/豆瓣禁用。

复现（核对映射依据后，使用自己的Python）：

```powershell
python -m scripts.backend_admin map --movie-id itunes:407742758 --provider tmdb --external-id 44214 --basis multi_field_verified --confirmed
python -m scripts.tmdb_acceptance --live --reviews --movie-id itunes:407742758 --output artifacts/tmdb-mapping/review-recommendation-smoke.json
# 真实页面需在启动进程额外设置；变更后重启后端
$env:MOVIE_TMDB_REVIEWS_LIVE = '1'
```

### 未通过条件与接续

- 豆瓣本轮显式live复验9次HTTP：3个身份候选、6次安全验证跳转、0评分/0影评，报告`artifacts/douban/final-20261101-report.json`。未绕过限制；没有真实豆瓣评价材料，故“豆瓣＋独立第二来源对照”、观点共识/分歧综合及10部同片评价验收未通过。需要来源方允许的实际可用数据通路；不以TMDB metadata、两个站点或两个用户名代替独立评价证明。
- M11：项目`.env`、当前进程及Windows User均未检测到完整LLM_BASE_URL/LLM_MODEL/LLM_API_KEY；运行`mvp_probe_model --live --case E02 --max-requests 1`返回NOT_CONFIGURED，零模型HTTP。已请用户本机配置，密钥无需发聊天；配置到齐后先限1次E02，再做真实冲突确认、失败恢复及记忆启用/关闭/改删与refine/reroll联动，记录请求与响应model。现阶段无法完成真实模型验收。
- M12：同机测试不代替另一成员/另一主机复现或最终人工签收。此次GitHub公开API查询仓库Actions返回404（无认证），没有新的CI通过结论；之前账户计费限制保留为历史问题，不能据旧报错误判本次CI状态。
- 本轮无新增依赖或契约字段变化；TDD先见缺模块/缺验收函数/缺作者UI与health能力失败，再实现。最终自动检查记录追加在下方；通过范围为工程、TMDB单源影评获取和本机真实页面，完整产品验收仍未通过。

最终工程结果：`python -m scripts.s0_check` **220 passed**（示例、30+30种子、契约与后端测试）；前端 **40 passed**，`npm run build`、`format:check`、`types:check`均通过；`git diff --check`通过，数据库integrity=ok/schema=3。真实影评推荐9项、Chrome页面2项通过，零付费模型HTTP。测试与截图对应本节代码增量；临时报告和数据库未纳入Git。完整验收结论：**未达到**，剩余条件为真实模型配置及M11实测、豆瓣可用且可引用的评价通路、独立性核验与口碑对照、M12独立复现/签收。
