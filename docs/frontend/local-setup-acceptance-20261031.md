# 本机展示版验收（2026-10-31）

本轮以主分支 `68ff223` 为基础整合免密钥演示，保留团队最新的 LangGraph、本次上下文、资料来源与影片身份核对功能。默认使用真实 Apple 公开电影资料和真实本机 Qwen2.5-1.5B-Instruct Q4_K_M，无需 TMDB token 或云模型密钥。

## 2026-11-01 · GitHub 全新副本与一键启动验收

从 GitHub 直接克隆分支 `feat/final-mvp-demo-20261031`，目录包含中文和空格。首次启动前不存在 `.env`、`.venv`、`node_modules`、前端构建或项目缓存；启动进程的 PATH 仅保留 Windows 自带目录，无法找到 Python、py、Node、npm 或 uv，并清除模型、TMDB 和 Python 配置变量。下载使用这台机器已有的网络通路，没有复制原项目的环境或模型文件。验证源码为 `6f46348`，最后的测试等待修正为 `0173e5d`，后续仅更新交接文档。

启动器自动安装项目内 uv 0.9.8、Python 3.13.9 和 Node.js 24.11.1，核对工具及模型 SHA256；Python 依赖使用带哈希的锁文件，前端按 package-lock 的变化重装。工具解压中断后，只有完整解压并写入校验标记才算已安装；新增离线回归覆盖这种恢复情形。无需管理员权限、系统 Python/Node 或 API 密钥，不修改全局配置。

| 检查 | 结果 | 本机证据（`artifacts/local-model/`） |
| --- | --- | --- |
| 全新副本后端 / S0 门禁 | Python 3.13.9 下184项通过，样例与契约通过 | `portable-fresh-s0.log`、`portable-fresh-runtime.json` |
| 原工作区前端 | 34项单测、类型、生产构建、格式通过，使用项目内 Node 24.11.1 | `portable-frontend-test.log`、`portable-frontend-build.log`、`portable-frontend-types-check.log`、`portable-frontend-format-check.log` |
| 全新副本 Chrome | 桌面/窄屏、明/暗四种布局，共12项通过：真实目录、海报、来源、片单、比较、系统主题、键盘、真实模型理解及90分钟补充 | `portable-fresh-chrome.log` |
| 缓存重启 | 不重复下载工具、依赖或模型；真实模型流程四种布局均通过 | `portable-warm-ready.json`、`portable-warm-start.log`、`portable-warm-chrome-corrected.log` |
| 新下载模型独立启动 | 新副本的 llama.cpp 和 GGUF 在临时18183端口完成真实 Chat Completions 调用，随后停止该临时进程 | `portable-fresh-model-independent.json` |

新副本完整下载并校验了约1.1 GB权重与运行时。页面流程按启动器设计复用了18181端口上已存在且匹配的健康模型；该实例保持运行。为排除依赖原副本的疑问，又单独运行新下载的可执行文件及权重，得到真实非空响应。没有将复用旧进程描述为新进程启动成功。

缓存重启首轮测试曾误取首页零输入后台响应，实际文字请求已经返回 `llm-v1`；已让测试等待初始目录完成，再观察提交请求，四种布局复验通过。初次失败日志及 trace 保留为 `portable-warm-chrome.log`、`portable-warm-initial-failure-trace.zip`，不计入通过数。上表12项与重启4项存在流程重叠，不与下方历史60项相加。

这是同一台 Windows 机器上全新 GitHub 副本和受限启动环境的实际复现，未模拟另一台实体硬件或其他操作系统。首次仍需要能够访问下载站点和 Apple 的网络；再次启动复用文件。共享源码中的启动器、锁文件和说明足以重新安装，不依赖忽略目录中这台电脑的现有文件。

## 2026-10-31 · 整合版历史验证

| 检查 | 结果 | 本机证据（项目根目录下） |
| --- | --- | --- |
| 后端全量离线测试 | 180 通过 | `artifacts/local-model/mvp-backend-all.log` |
| S0 离线门禁 | 样例、种子、契约及 180 项测试通过 | `python -m scripts.s0_check` |
| 前端单元测试 | 34 通过 | `artifacts/local-model/mvp-frontend-unit-final.log` |
| 类型与生产构建 | 通过，OpenAPI 与 TS 类型重新生成 | `artifacts/local-model/mvp-build-final.log` |
| Chrome 核心、真实模型及配置 | 四种布局共 48 个不同场景通过 | `mvp-chrome-core.log`、`mvp-chrome-mobile.log`、`mvp-chrome-tmdb-corrected.log`，均在 `artifacts/local-model/` |
| Chrome 冲突确认 | 文字/点选条件两种选择，四种布局共 8 项通过 | `artifacts/local-model/mvp-chrome-conflict.log` |
| Chrome 双重故障恢复 | 四种布局共 4 项通过；故意使 TMDB 鉴权与模型服务不可用，仍查询并渲染真实 Apple 电影，继续补充条件也保留前次类型和排除项 | `artifacts/local-model/mvp-chrome-fault.log` |

共 60 个不同 Chrome 场景通过，包含桌面/窄屏、明/暗主题、来源面板、详情、片单、对比、筛选、真实模型条件提取和 90 分钟补充、可见错误、海报重试、键盘及系统主题立即切换。真实本机模型测试明确断言 `llm-v1`；模型故障测试明确断言 `rules-v1`。TMDB 界面适配测试使用明确标注的离线合成响应，不能解释为真实 TMDB 联网通过。

首轮 TMDB 界面测试因新版入口和折叠资料区而失败；修正操作路径后又发现 TMDB 海报错误走 Apple 专用代理，已改用经域名校验的 TMDB 图片 URL。四种布局均复验通过；保留初次失败日志，没有把失败或跳过统计为通过。核心批次跳过的故障场景已在专用故障服务实际通过。

测试使用独立 Chrome 上下文，结束后关闭。窄屏为移动视口及触控模拟，非实体手机验收。自动 axe 检查不代表完整人工无障碍认证。前一版 92 项后端/68 项浏览器记录属于旧分支历史，本轮不混用其计数。

## 对应本机展示的六组流程

1. 零输入进入真实片库，候选保留原始影片身份和来源。
2. 自然语言提取类型、心情、时长与排除项，结果经代码严格筛选。
3. 文字与点选冲突先确认，按实际选择执行；不支持的条件明确提示。
4. 本次上下文支持继续调整时长、换组、重新开始，模型失败后仍可继续。
5. 打开详情与来源、加入片单、加入对比、隐藏及撤销，状态限于本次会话。
6. 可选源、模型、海报及请求异常时提供可见反馈，已有真实结果保留，可重试。

共享截图：[桌面真实模型](screenshots/final-local-20261031/desktop-light-real-model-results.png)、[暗色桌面](screenshots/final-local-20261031/desktop-dark-real-model-results.png)、[窄屏](screenshots/final-local-20261031/mobile-light-real-model-results.png)、[双重故障恢复](screenshots/final-local-20261031/mobile-dark-real-source-recovery.png)、[接入状态](screenshots/final-local-20261031/desktop-light-real-model-setup.png)。

## 启动与边界

从 GitHub 获取源码后，在 Windows 10/11 x64 上双击项目根目录 `start-demo.cmd`，等待自动安装、构建和浏览器打开 `http://127.0.0.1:8000/`；保留终端运行。无需预装 Python/Node 或填写密钥。首次需下载工具、依赖和约1.1 GB本机模型并校验，建议预留6 GB磁盘空间；中断后再次启动可续传，后续复用缓存。已有服务占用8000时用 `start-demo.cmd --port 8001`，不停止已有程序。详细排错见[本地演示说明](../local-demo.md)。

本机课堂展示和全新 GitHub 副本复现已验证；另一台实体电脑尚未实测。真实 TMDB 和可选云模型未联网验收，但均不影响默认流程。Apple 美国区资料不保证中国区渠道或全片库覆盖；评分缺失保持未知。所有资料源均不可用时显示可重试错误，不编造电影。

多源口碑、长期记忆、账号和正式公网部署属于已暂缓范围。页面片单与比较刷新后清空，本次理解上下文在服务进程内。不要将本机展示通过描述为这些扩展功能已交付。
