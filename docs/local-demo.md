# 本地演示、凭据与排错

## 不配置密钥也能演示

队友从 GitHub 拉取代码或解压源码，在 Windows 10/11 x64 上双击项目根目录 `start-demo.cmd`。无需预装 Python/Node，无需管理员权限或 API 密钥。首次自动下载固定版本的 uv 0.9.8、Python 3.13.9、Node.js 24.11.1，按 `requirements-demo.lock` 与 `web/app/package-lock.json` 安装依赖，再下载约 1.1 GB 的本机 Qwen 模型并构建页面。请等待终端进度，浏览器在准备完成后打开。工具与模型均核对官方 SHA256，Python 依赖核对锁定哈希，npm 使用锁文件的完整性信息。

运行环境位于忽略的 `artifacts/bootstrap/`、`.venv/`，模型位于 `artifacts/local-model/`；不修改系统 PATH、代理或执行策略。首次安装需要网络和额外磁盘空间，建议至少预留 6 GB；再次双击会复用下载与环境。拉取新代码后，Python 按锁文件安装，前端锁文件有变化时自动重装，避免沿用旧依赖。退出时 Ctrl+C；启动器仅停止自己创建的模型进程。

默认使用 Apple 美国区公开榜单和本机 Qwen2.5-1.5B-Instruct，需要可访问 Apple 的网络。可演示零输入选片、条件筛选、真实模型提取条件与澄清、影片详情、来源核对、当前片单、对比和主题跟随系统。页面均可直接刷新。TMDB 与云模型账号均非前置条件。

8000 已占用时启动器不会停止已有程序；运行 `start-demo.cmd --port 8001`。服务仅监听本机 `127.0.0.1`，未部署到公网。换电脑后从 GitHub 获取源码并双击启动器，不能只复制浏览器地址；也不要复制其他电脑的 `.venv` 或 `node_modules`。

## TMDB token 怎么取得

用项目持有人的 TMDB 账号打开 [API 设置](https://www.themoviedb.org/settings/api)，按网站流程申请 API 访问，找到 **API Read Access Token**，填入根目录 `.env` 的 `TMDB_READ_TOKEN=` 后面。

这不是网站密码，也不是 v3 API Key。本项目按 [官方认证说明](https://developer.themoviedb.org/docs/authentication-application) 通过 Authorization Bearer header 发送 token。助手没有可交付的共享 token。

`MOVIE_CATALOG_PROVIDER=auto` 在 token 非空时选择 TMDB，否则选 Apple。想保留 token 而演示 Apple，可写 `MOVIE_CATALOG_PROVIDER=apple`。TMDB 每次最多查询 8 部热门候选详情；中文名称、片长等可能缺失。页面保留来源、评分证据和官方署名，不将评分解释为个人喜爱概率。

## 本机模型

根目录 `.env` 中的 `MOVIE_MODEL_BACKEND=local` 启用内置模型。其他三个 `LLM_*` 字段留空即可，不需要 API 密钥。模型通过 llama.cpp 的 CPU 版本运行，监听本机 `127.0.0.1:18181`；文件及日志位于忽略的 `artifacts/local-model/`。不安装系统服务，不修改系统代理或其他项目。

下载来自 [Qwen 官方仓库](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF) 和 [llama.cpp 官方发布](https://github.com/ggml-org/llama.cpp/releases/tag/b12020)，权重与运行时固定版本并校验 SHA256。下载中断会保留完成的分段，再次运行可续传。下载或模型启动失败时仍启动前端，自动使用规则兜底；重新启动可重试安装。必要时可用 `MOVIE_DOWNLOAD_PROXY` 指定本机已有下载代理，不修改系统设置。

已有旧 `.env` 且三个云字段均为空时，可执行 `.venv\Scripts\python.exe -m scripts.movie_local --install --enable`。启用命令会保留原文件的其他内容；发现已有云模型配置时拒绝覆盖。本机已安装的演示不需要重新申请账号。

本机模型能力有限；提取结果还需通过规则校验，漏掉硬条件、增加未表达条件或混淆时长上下限时自动使用规则解析，页面注明实际方法。未支持的要求会澄清，影片事实与排序不交给模型生成。配置页只在当前进程实际调用并校验成功后，显示成功调用时间。

## 可选：云模型怎么配置

需要原定 DeepSeek 等云接入时，填写同一服务商提供的 `LLM_BASE_URL`、`LLM_MODEL` 和 `LLM_API_KEY`。云 base URL 必须为 HTTPS、兼容 Chat Completions 的根路径；程序追加 `/chat/completions`，勿重复填写该后缀。显式云配置优先于内置本机模式，模型标识沿用团队选择，以账号实际权限为准。

模型仅提取类型、心情、时长上限、同行、年代和排除类型，结果经过严格结构校验。每个新描述最多一次请求，输出预算 512 tokens、云端 20 秒/本机 30 秒超时；成功解析在当前进程缓存 30 分钟。影片、评分、来源证据不由模型生成。冲突和无法执行的要求进入澄清流程。

点选选片不调用模型。未启用模型或模型请求失败时使用规则，页面会直接提示本次使用规则；无法执行的要求仍需确认。失败后 30 秒内不重复等待该模型，之后允许再次尝试。只有云模型会向服务商发送观影描述并可能计费。配置页不主动调用付费 API，不把配置格式检查当作真实调用证明。

## 资料源故障恢复

默认 Apple 不依赖 TMDB。当已选择的 TMDB 缺少凭据、拒绝访问或暂时失败时，系统自动查询 Apple 的真实榜单、检索与详情，结果区直接提示切换来源。保留 Apple 原始影片 ID、链接、采集时间及评分缺失状态。TMDB 返回正常空结果时不会另换资料源；故障后 60 秒允许重新尝试 TMDB。已有不同来源的影片仍按自身 ID 查询详情，不混用身份。

所有资料源均不可用时，页面保留已经取得的候选并显示错误，可重试或修改条件。它不会将编造的影片、评分或成功状态当作真实结果。

## 保存并核对

启动器仅在 `.env` 不存在时创建空白模板。文件已被 Git 忽略；不要截图密钥、发聊天或提交 Git。终端环境变量优先于 `.env`。修改后重启本次演示，若未生效请检查终端是否仍有同名旧变量。

```powershell
.venv\Scripts\python.exe -m scripts.movie_demo --check
.venv\Scripts\python.exe -m scripts.mvp_probe_model --live --case E02 --max-requests 1
```

第一条只打印脱敏状态；第二条读取根目录`.env`或进程变量，显式调用一次云模型，可能计费，结果写入忽略的`artifacts/`。旧`s0_probe_*`仅读取进程变量，不会自动加载`.env`。探测通过后，仍需在网页实际提交文字、核对识别条件和影片来源。“已填写 · 待联网验证”不是联网验收结果。

## 常见故障

| 现象 | 处理 |
| --- | --- |
| 工具或依赖下载失败 | 检查能否访问 GitHub、nodejs.org、Python/PyPI 与 npm 下载源，再次双击；已完成的工具分段会保留，不需手动安装 Python/Node |
| `python` 打开 Windows 商店 | 双击 `start-demo.cmd`，它使用项目内的 Python；手动排错使用 `.venv\Scripts\python.exe` |
| 端口占用 | 保留已有服务，使用 `--port 8001` |
| TMDB 鉴权失败 | 核对 API Read Access Token、账号权限和旧环境变量，勿粘贴登录密码 |
| 网络或上游超时 | 检查资料源网络；页面显示错误，不用样例补齐 |
| 模型解析失败 | 核对根路径、模型标识、余额/权限及 API 支持，也可点选演示 |
| 严格筛选无结果 | 有限候选可能不匹配，可放宽条件；不代表全片库无此影片 |

匿名长期偏好与已看已接入本机 SQLite（默认 `artifacts/state/movie.sqlite3`，可用 `MOVIE_DB_PATH` 指定位置），需要用户明确启用/确认；偏好页支持关闭、修改及删除，删除全部个人数据后匿名凭据失效。不要把个人数据库、`.env` 或其他电脑的运行环境发给队友。页面片单与临时隐藏仍在刷新后清空。账号、云端片单、多源口碑综合和地区观看渠道尚未完成。TMDB 影评摘录需要单独启用并确认同片映射，不保证默认演示能取得影评。

## 本轮完整分支复现与签收

本轮完整代码已合入 `main`，包含一键启动、持久化、TMDB 资料/可选影评和模型冲突修复；`feat/backend-persistence-evidence` 保留整合开发记录。队友请从 GitHub 选择 `main` 后使用 Code → Download ZIP，完整解压再运行；也可使用 Git：

已完成云端验证的业务版本为 `7da4adf9af4e298a8d1cfef07bfd8650eb772393`：[固定版本ZIP](https://github.com/yimou408-spec/getnewmovie/archive/7da4adf9af4e298a8d1cfef07bfd8650eb772393.zip)。该版本后端离线检查、前端类型/单测/构建/格式及244项浏览器验收通过；8项需专用模型/故障环境的浏览器检查未在CI运行。后续仅补文档时可以使用最新 `main`，请保留实际版本记录。

```powershell
git clone --branch main https://github.com/yimou408-spec/getnewmovie.git
cd getnewmovie
git rev-parse HEAD
.\start-demo.cmd
```

记录完整提交哈希；浏览器打开后检查零输入推荐、文字与点选冲突两种选择、补充时长、换组、详情来源、片单/比较、临时隐藏撤销，以及匿名偏好/已看在刷新与服务重启后保留、关闭记忆和删除数据。需要测试真实云模型/TMDB时，由测试者在其本机配置凭据；不要复制或提交他人密钥。默认本机模型通过不等同于云模型或真实豆瓣通过。

请将操作系统、提交哈希、实际模型、启动结果、上述检查结果和失败截图/脱敏错误登记回现有工作记录，并由实际操作成员签收。首次下载约1.1 GB模型及工具，建议预留6 GB空间；另一台电脑签收和真实多源评价状态分别记录。

若已有旧副本且工作区没有未保存改动，可运行 `git switch main`、`git pull --ff-only origin main` 再启动；有本地改动时保留原副本，另建目录下载，避免覆盖。ZIP 下载者保留本次下载链接和 GitHub 页面显示的提交哈希。

## 口碑综合开发分支

2026-11-01最新调整：当前改为IMDb单平台影评目标，豆瓣/第二平台不再是验收前置。IMDb没有已启用的生产采集适配器；默认来源状态为`IMDb/not_configured`，注册IMDb影片映射不会发起HTTP或让`reviews`能力变成true。现有TMDB可选影评仅作为历史可用通路保留，不自动改标签或计作IMDb成功。先按[当前计划](限期开发实施计划_20261029.md#当前执行计划2026-11-01-imdb-单平台影评调整)核对正文产品、使用范围与字段，不要填一个假定存在的`IMDB_API_KEY`。

已实现`comparison_scope=single_platform`的站内材料对照及IMDb映射命令，详情和合成例子见[接口约定](MVP最小接口约定.md#imdb单平台影评接口2026-11-01)。不同作者账号不充当独立来源，也不代表全平台共识。真实素材及10片验收仍待完成；下方TMDB探测/审核操作保留，旧“豆瓣未通过”不再阻断当前交付。

`feat/evidence-opinion-synthesis` 新增来源面板的材料观点对照，范围和离线验收见[MVP最新记录](MVP开发工作记录.md#2026-11-01--口碑综合最小实现离线证据验收)。默认只处理已标记安全、可使用的影评受控短语；材料不足/独立性未知就明确降级。当前真实TMDB摘录为剧透未知、无独立组，豆瓣仍无可用评价，不会因此出现“真实多源已核验”。

默认不增加模型调用。若后续要验证远程模型辅助选择，在本机 `.env` 显式设置 `MOVIE_OPINIONS_MODEL=1` 并重启；会把合格影评片段发送给配置的服务商，每次推荐最多一次额外请求，可能计费。本轮未运行真实综合模型；本机Qwen及生产补查来源未接入。开启前仍需有安全且允许使用的材料；该开关不能解除豆瓣限制或自动核验作者独立性。

审核接线可显式设置进程变量 `$env:MOVIE_REVIEW_AUDIT_PATH = 'artifacts/opinions/review-audit.json'` 后重启（此项只读进程变量）。默认不开启。本地JSON登记格式见 `app/services/review_audit.py`：`version: 1`、`decisions`；每项记录影片/来源/证据ID、作者、URL、采集片段SHA-256、逐字连续摘录、剧透决定、审核者及human/agent身份、时间和理由。登记独立组还必须提供原创发布者、原始HTTPS链接和核验理由；不同用户名不能直接充数。登记文件只表达审核者决定，不自动证明其正确，也不提升使用许可。真实正文和审核文件保留在忽略的 `artifacts/`，不要提交。

审核覆盖当前引用片段，不覆盖整篇；上游片段、作者、URL或影片绑定变化时失效。原始采集缓存不保存审核覆盖层，因此删除决定可立即撤销，下次缓存命中也重新审核。失效/损坏文件不提升安全或独立性。复测采集和登记匹配可运行：

```powershell
python -m scripts.review_acceptance --live --tmdb-id 155 --audit artifacts/opinions/review-audit.json --output artifacts/opinions/review-acceptance.json
```

此命令读取根目录 `.env`/进程令牌，最多6个明确TMDB ID、每片一次HTTP，无模型调用；保留失败分母，报告省略正文。退出0仅表示该批采集成功，不表示豆瓣、第二独立平台、人工低剧透审核或完整多源验收通过。
