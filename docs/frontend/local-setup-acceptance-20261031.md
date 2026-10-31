# 本机展示版验收（2026-10-31）

本轮以主分支 `68ff223` 为基础整合免密钥演示，保留团队最新的 LangGraph、本次上下文、资料来源与影片身份核对功能。默认使用真实 Apple 公开电影资料和真实本机 Qwen2.5-1.5B-Instruct Q4_K_M，无需 TMDB token 或云模型密钥。

## 当前版本验证

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

在项目根目录双击 `start-demo.cmd`，终端出现地址后打开 `http://127.0.0.1:8000/`；保留终端运行。首次启动下载约 1.1 GB 本机模型并校验 SHA256。最终 ZIP 已包含构建、模型、运行时与许可，可运行 `start-demo.cmd --no-build`。新电脑仍需 Windows x64、Python 3.11+ 以及安装依赖、访问 Apple 的网络。

本机课堂展示范围已验证。另一台物理电脑的首次安装尚未执行；源码与启动器不等于独立免安装 EXE。真实 TMDB 和可选云模型未联网验收，但均不影响默认流程。Apple 美国区资料不保证中国区渠道或全片库覆盖；评分缺失保持未知。所有资料源均不可用时显示可重试错误，不编造电影。

多源口碑、长期记忆、账号和正式公网部署属于已暂缓范围。页面片单与比较刷新后清空，本次理解上下文在服务进程内。不要将本机展示通过描述为这些扩展功能已交付。
