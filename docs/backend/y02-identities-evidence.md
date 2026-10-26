# Y02：影片身份、豆瓣适配与证据契约

更新：2026-10-26（北京时间）。基线 `c6ac7df`，分支 `feat/y02-movie-identities-evidence`。这是实现及自测交接记录，未代签 PionneerZ 或 C 的评审。

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
