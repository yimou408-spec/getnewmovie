# 今晚看什么 · getnewmovie

从真实电影目录中选择、核对来源、加入本次片单和比较。React / TypeScript / Vite 前端支持独立页面、桌面与手机视口，随系统切换明暗主题；FastAPI 与前端可在本机同一端口运行。

## 本机展示

需要 Windows 10/11 x64 和可访问下载站点、资料源的网络。队友从 GitHub 拉取代码或解压源码后，在仓库根目录双击 **`start-demo.cmd`**，或运行：

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

启动器只在根目录 `.env` 不存在时创建本机模板，不覆盖已有云模型配置。环境变量优先。`.env` 和模型文件均被 Git 忽略；配置页仅返回状态，不返回密钥。默认演示不依赖以下可选服务。

| 配置项 | 用途 |
| --- | --- |
| `MOVIE_MODEL_BACKEND` | `local` 启用内置本机模型；清空且无云配置时使用规则模式 |
| `MOVIE_CATALOG_PROVIDER` | `auto`、`apple` 或 `tmdb`；auto 仅在 token 非空时选择 TMDB |
| `TMDB_READ_TOKEN` | 项目自有 TMDB API Read Access Token，非网站登录密码 |
| `LLM_BASE_URL` | 服务商提供的 HTTPS、兼容 Chat Completions 的 API 根路径 |
| `LLM_MODEL` | 团队选定且该账号有权限使用的准确模型标识 |
| `LLM_API_KEY` | 同一服务商的 API 密钥 |

云模型使用团队已有 MVP 适配器，只有配置云服务后才发送观影描述并可能产生费用。默认本机模型不等同于 DeepSeek，也不保证理解复杂描述。Qwen 模型使用 Apache-2.0，llama.cpp 使用 MIT；安装器核对官方文件 SHA256，交付包附许可证。

```powershell
.venv\Scripts\python.exe -m scripts.movie_demo --check
```

以上命令仅显示脱敏状态，不请求资料源。已配置不等于联网通过；配置页显示当前进程实际模型调用成功的时间。可选 TMDB 与云模型不作为默认本机演示的验收前置条件。

## 当前 MVP 的边界

- 支持零输入探索、自然语言条件、冲突确认、本次条件补充、换组、隐藏/撤销、片单和 2–3 部影片比较。心情是软偏好，类型、年代、片长和排除由代码严格筛选。
- Apple 候选来自美国区当前分类榜单；搜索使用来源原文片名，不是全量片库。TMDB 热门查询单次最多核对 8 部；两种 ID 保留各自来源，不互相冒充。
- 资料缓存约 30 分钟，显示来源、原始采集时间和事实/推断差别。Apple 未取得评分、影评和地区播放渠道时保持未知；商店链接不是直接播放。TMDB 评分保留量表与投票数。
- 片单和隐藏反馈在页面内存中，刷新清空；匿名条件上下文有时限，不是长期记忆。多源口碑、数据库长期记忆、账号、正式公网部署仍属后续范围。Y02 离线豆瓣适配器及身份契约已保留，不表示真实豆瓣联网接通。
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

[前端文档](docs/frontend/README.md) · [素材来源](docs/frontend/assets.md) · [S0合成实验](docs/s0/README.md)。原始录音、访谈文本、密钥及本机模型文件不纳入 Git；合成实验不作为真实电影验收。
