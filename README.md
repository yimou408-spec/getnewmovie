# 今晚看什么 · getnewmovie

从真实电影目录中选择、核对来源、加入本次片单和比较。React / TypeScript / Vite 前端支持独立页面、桌面与手机视口，随系统切换明暗主题；FastAPI 与前端可在本机同一端口运行。

## 本机展示

需要 Windows 10/11 x64 和可访问下载站点、资料源的网络。本分支已整合一键启动、模型理解、条件确认、真实目录、匿名长期偏好与已看；真实多源口碑仍待完成。队友下载完整源码后，在仓库根目录双击 `start-demo.cmd`，或运行：

```powershell
.\start-demo.cmd
```

无需预装 Python、Node 或填写 API 密钥。启动器将固定版本的 Python 3.13.9、Node.js 24.11.1 和 uv 0.9.8 安装到项目目录，按锁文件安装依赖、构建前端，打开 http://127.0.0.1:8000/；不需要管理员权限，不修改系统 PATH、代理或执行策略。默认使用 **Apple 美国区真实电影榜单 + 本机 Qwen2.5-1.5B-Instruct Q4_K_M**。首次需下载约 1.1 GB 模型及运行环境、依赖，请保留足够磁盘空间并等待终端进度；中断后再次双击可继续。后续复用本机文件，`git pull` 更新依赖后自动重装对应版本。保留终端窗口，按 Ctrl+C 停止本次演示及它创建的模型进程。端口被占用时保留已有服务，可运行 `start-demo.cmd --port 8001`。

本机模型通过 llama.cpp 运行，只监听回环地址。模型提取受限条件，主分支已有的 **LangGraph** 负责理解、确认、真实目录筛选与本次上下文；电影事实与排序由目录和代码提供。模型下载、启动、请求失败或提取未通过条件核对时，使用规则解析并显示说明；未识别要求仍需确认。可选 TMDB 失败时切换至 Apple 真实资料。所有资料源均失败时保留已有结果并显示可重试错误，不用合成电影补齐。

选片 `/`、片单 `/watchlist`、对比 `/compare`、影片 `/film/:movieId`、偏好 `/preferences`、接入状态 `/about`、配置指引 `/setup` 均可独立打开或刷新。API 文档位于 `/docs`。

- [本地运行与排错](docs/local-demo.md)
- [本轮免密钥交付与展示验收](docs/frontend/local-setup-acceptance-20261031.md)
- [MVP任务状态和工作记录](docs/MVP开发工作记录.md)
- [MVP输入输出与最小接口约定](docs/MVP最小接口约定.md)

## 可选配置

2026-10-31后端增量：已加入SQLite匿名身份、明确确认的偏好/已看、反馈幂等与撤销、数据删除、来源状态/TTL及请求预算。打开“偏好与隐私”选择是否启用，默认关闭；本次文字/片单/临时隐藏不会自动成为长期偏好。数据库默认位于忽略路径`artifacts/state/movie.sqlite3`。[接口、备份恢复及验收记录](docs/backend/y02-identities-evidence.md#2026-10-31y03y08-后端增量与验收)。豆瓣真实评价、第二独立评价源和完整最终验收仍未通过。

2026-11-01 TMDB资料增量：启动进程设置`TMDB_READ_TOKEN`后启用资料适配，`MOVIE_TMDB_LIVE=0`可关闭；这两个变量不自动读取`.env`，修改后需重启后端。仅对管理员已独立核验并登记的Apple↔TMDB映射取中文片名、原名、别名和时长，资料显示在来源面板；Apple主ID、片名及筛选依据保持原样。无映射时不会自动搜索或合并，显示未配置；异常片名会被拒绝。本机已登记罗小黑战记2、吸血鬼猎人D两组多字段核验映射，真实推荐及缓存联调通过；其他环境需按记录核验后登记。TMDB资料不等于独立影评、全量中文搜索或地区观看渠道。[配置、映射及真实验证](docs/backend/y02-identities-evidence.md#2026-11-01tmdb-资料适配接入推荐)。

2026-11-01影评增量：进程设置`MOVIE_TMDB_REVIEWS_LIVE=1`并配置上述TMDB令牌，可按已确认TMDB映射取得英文影评首屏，最多3条、每条最多600字符；默认不开启。保留作者和原文链接，可能剧透的正文需主动展开；不推断作者独立性，不作为默认推荐理由，不合成全网共识。已核验并登记《黑天鹅》`itunes:407742758`↔`tmdb:44214`；真实影评推荐9项及桌面/手机页面2项通过。豆瓣复验仍被安全验证阻断，模型配置仍缺失，因此完整最终验收尚未通过。[结果、配置和剩余条件](docs/backend/y02-identities-evidence.md#2026-11-01影评获取增量与最终验收复查)。

## 前端、验收与团队进度

2026-11-01模型验收更新：本机配置已生效；修复文字/点选冲突被模型混淆的问题，提示词升级`mvp-intent-v2`。真实DeepSeek＋Apple＋临时记忆17项接口检查、桌面/手机4项页面场景通过，本机M11已收口；超时恢复使用明确标记的本地故障注入。复现：`python -m scripts.mvp_acceptance --live --max-model-requests 4`。[模型验收记录](docs/MVP开发工作记录.md#2026-11-01--m11本机模型与交互验收收口)。另一环境签收与真实多源口碑仍待完成，旧服务需重启才读取新配置。

- **[打开真实前端预览](https://standards-float-heather-promotional.trycloudflare.com/)**：本轮有效至 **2026-10-23 12:50 北京时间**，非永久部署；中断或到期后的重启方法见报告。
- **[最新验收报告与三人进度对齐](docs/frontend/acceptance-20261023.md)**：直接阅读，无需下载 Actions 压缩包。列明版本、真实操作、CI 证据、未通过项和每位组员待交付事项。
- [PR #4](https://github.com/yimou408-spec/getnewmovie/pull/4) · [云端预览运行](https://github.com/yimou408-spec/getnewmovie/actions/runs/39898294228) · [前端详细文档](docs/frontend/README.md)

云模型使用团队已有 MVP 适配器，只有配置云服务后才发送观影描述并可能产生费用。默认本机模型不等同于 DeepSeek，也不保证理解复杂描述。Qwen 模型使用 Apache-2.0，llama.cpp 使用 MIT；安装器核对官方文件 SHA256，交付包附许可证。

```powershell
.venv\Scripts\python.exe -m scripts.movie_demo --check
```

以上命令仅显示脱敏状态，不请求资料源。已配置不等于联网通过；配置页显示当前进程实际模型调用成功的时间。可选 TMDB 与云模型不作为默认本机演示的验收前置条件。

## 当前 MVP 的边界

- 支持零输入探索、自然语言条件、冲突确认、本次条件补充、换组、隐藏/撤销、片单和 2–3 部影片比较。心情是软偏好，类型、年代、片长和排除由代码严格筛选。
- Apple 候选来自美国区当前分类榜单；搜索使用来源原文片名，不是全量片库。TMDB 热门查询单次最多核对 8 部；两种 ID 保留各自来源，不互相冒充。
- 资料缓存约 30 分钟，显示来源、原始采集时间和事实/推断差别。Apple 未取得评分、影评和地区播放渠道时保持未知；商店链接不是直接播放。TMDB 评分保留量表与投票数。
- 片单和临时隐藏在页面内存中，刷新清空；匿名条件上下文有时限。明确确认的偏好和已看使用匿名身份保存至本机 SQLite，支持关闭、改删与清空；不会自动同步其他设备。账号、正式公网部署和多源口碑仍待完成；豆瓣适配器与 TMDB 影评获取实现不等于真实多源评价验收通过。
- 已从 GitHub 全新克隆，在无可用系统 Python/Node、无密钥、无项目缓存的隔离启动环境完成首次安装、真实页面和缓存重启验收；范围为 Windows x64 课堂展示，另一台实体电脑及其他操作系统未实测。详见[复现验收](docs/frontend/local-setup-acceptance-20261031.md)。

## 开发与检查

```powershell
python -m pip install -r requirements-s0.txt
python -m pytest -q
python -m scripts.s0_check
python -m scripts.s0_export_contracts --check
cd web/app
npm ci
npm run build
npm test
npm run format:check
npx playwright test
```

分离开发：根目录运行 `python -m uvicorn scripts.movie_server:app --host 127.0.0.1 --port 8000`，另一终端在 `web/app` 运行 `npm run dev`，访问 http://127.0.0.1:5173/。Windows 浏览器验收优先使用本机 Chrome，可用 `MOVIE_DEMO_BASE_URL` 指定已启动的演示服务。

## 协作与历史资料

主仓库为 [yimou408-spec/getnewmovie](https://github.com/yimou408-spec/getnewmovie)，由 PionneerZ、yimou408-spec、2284266609-code 协作。当前缩减 MVP 范围以 [MVP工作记录](docs/MVP开发工作记录.md) 为准；[三人任务台账](docs/三人开发任务台账.md)、[10月23日验收](docs/frontend/acceptance-20261023.md)、[原限期计划](docs/限期开发实施计划_20261029.md) 保留历史事实，早期临时公网预览已过期。

另一个终端：

~~~powershell
cd web/app
npm ci
npm run dev
~~~

打开 http://127.0.0.1:5173/，Vite 将 /api 转发至后端；API 文档为 http://127.0.0.1:8000/docs。真实来源不可用时显示错误，不以合成电影补齐。

## 当前实现与边界

- Apple 美国区当前电影分类榜单与影片查询已接入，非全量片库；按来源原文片名查询并核对年份。最多展示三部，显示实际查得与匹配数量，可换组和排除。
- 类型、年代、片长、排除列表参与真实筛选；片长取影片查询的 trackTimeMillis 向上取整，不采用预告片长度。未知时长/年份不进入对应限制结果。
- 自然语言支持模型理解与LangGraph流程（需配置模型），未配置时沿用规则路径；可识别类型、心情、时长、年代和排除，冲突或不能执行的要求先确认。支持本次条件补充和换组，心情排序仍为词法推断，不代表口碑或喜爱概率。
- 原始来源、采集时间、事实与推断分开显示。数据缓存约 30 分钟；评分、影评及地区观看渠道未取得时明确未知，商店链接不是直接播放。
- 基础资料比较、本次片单与隐藏/撤销反馈只保存在页面，刷新清空。明确同意后可保存匿名身份、长期偏好与已看；关闭记忆不参与推荐，改删和全部数据删除可用。模型调用有上限；匿名短期上下文保留本次条件，刷新创建新会话。账号登录、跨设备恢复和真实多源口碑仍未接入。
- 和家人会限定家庭/动画，适龄仍需自行核对；其他同行选项仅记录情境。尚无真实用户研究或优于豆瓣的效果证据。

## 三人分工与计划

由 PionneerZ、yimou408-spec、2284266609-code 协作；以 [任务台账](docs/三人开发任务台账.md) 和 [本轮对齐清单](docs/frontend/acceptance-20261023.md#10-月-23-日三人对齐清单) 区分实现、自测、联调和交叉评审。

- [限期开发实施计划：10/29 目标、10/31 最晚](docs/限期开发实施计划_20261029.md)
- [开发执行与准备清单](docs/开发执行计划与准备清单.md)
- [产品功能与架构基线](docs/产品功能与架构基线.md)
- [工具复用调研](docs/工具复用调研.md)
- [推荐质量与后端方向](docs/frontend/recommendation-quality.md) · [素材来源](docs/frontend/assets.md)

历史 [S0 启动包](docs/s0/README.md) 仅用于离线契约和合成实验，不能作为产品真实数据验收。原始录音及访谈文本不纳入仓库。[原计划](docs/开发计划.md) · [TDD 清单](docs/TDD验收与任务清单.md)
