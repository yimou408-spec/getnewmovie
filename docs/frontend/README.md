# 产品前端与验收记录

本次交付是可运行的 S0 产品前端。交互按正式软件产品标准实现，后端仍是合成 Mock，不能把固定样例结果当作真实推荐或正式商业服务。

## 设计与功能

产品暂名“今晚看什么 · 私人选片室”。围绕“零输入开始或点选偏好 → 核对少量候选 → 查看理由与来源 → 保存或对比”组织页面。采用宽幅海岸列车摄影、36–80px 大标题、瓷白/墨蓝底色及琥珀操作色；主视觉之后是选片区与六个一键场景。桌面内容区最大 1800px，手机独立排版，320px 下约束字段改为单列。没有授权电影海报时使用明确的文字占位。[视觉方案](visual-redesign.md)与[摄影来源及许可证](assets.md)均随仓库交付。

- 选片：默认不要求输入文字；“什么都行，直接看看”立即提交。可点选 6 种心情、10 种类型、4 种同行方式与常用时长，也可直接选择六个场景并提交。文字补充、精确时长与地区默认收起。另有从本次片单选、已知道片名两个入口，保留各自草稿。
- 确认：同名作品展示年份与资料，用户确认后才提交 `movie_id`。
- 候选：评分保留原量表、来源、样本数；展示推荐理由、安全证据、数据模式、跟踪编号及渠道未知状态。缺失信息不填造。
- 片单：确认影片后加入，仅存当前 React 页面内存，刷新清空；移出与清空可以在当前提示内撤销。
- 对比：2–3 部影片调用后端对比接口，横向比较已返回的资料；窄屏表格局部滚动，支持键盘焦点。
- 偏好与隐私：禁用尚未接入的长期记忆，说明服务端删除与本地清空的区别。
- 故障：加载、空结果、澄清、降级、超时、未配置、网络失败、无效契约、影片 404 和页面 404；失败保留原输入和上次候选，不自动重试请求。
- 外观：全站 `prefers-color-scheme`，系统切换立即生效，没有独立的页面主题开关。包含键盘跳转、焦点、减少动画和触控目标。

## 接口与能力边界

| 能力 | 本次接入 | 仍未实现或限制 |
| --- | --- | --- |
| 推荐 | `POST /recommendations`，六种 S0 联调状态；成功状态展示三部不同的合成影片 | 固定样例，偏好虽已提交，但不参与匹配、筛选或排序；不会真正理解约束、片单或已确认影片 |
| 影片检索与详情 | `GET /movies`、`GET /movies/{id}` | 仅五部虚构影片，没有真实目录、海报或剧情 |
| 对比 | `POST /comparisons` | 基础资料，不产生智能比较结论 |
| 评分与证据 | 原样展示契约字段，校验安全证据关联 | 评分为合成数据；`.invalid` 占位地址不可点击 |
| 片单与反馈 | 当前会话片单；隐藏本次候选 | 没有服务端 CRUD、同步或反馈学习 |
| 用户与长期记忆 | 所有请求 `memory_enabled: false` | 没有登录、记忆、偏好持久化、导出或服务端删除 |
| 观看渠道 | 明确显示未知 | 没有实时可用性或地区版权查询 |

页面顶部、候选、隐私与关于页均保留上述边界。联调场景选择器只用于 S0；接入真实服务时应连同数据授权、鉴权、运营观测和错误策略一起重新验收，不应直接去掉提示作为上线完成。

## 工程结构

保留现有 Python/S0 栈与旧线框。新前端使用项目计划中的 React、TypeScript、Vite；Radix 提供 Tabs/Checkbox 行为，TanStack Query 管理请求状态，React Router 管理路由，Lucide 提供图标。

- `web/app/src/App.tsx`：应用路由与流程。
- `web/app/src/styles.css`：共享视觉变量、系统主题及响应式布局。
- `web/app/src/domain.ts`：请求构造、AJV 契约校验、安全来源地址与错误映射。
- `web/app/src/generated/api.d.ts`：由仓库 OpenAPI 生成，不手工维护。
- `web/app/tests/acceptance.spec.ts`：真实 Chrome/S0 HTTP 集成验收；网络与无效响应测试额外使用明确的浏览器故障注入。

推荐请求及响应使用仓库生成的 JSON Schema，并额外检查候选状态、评分量表、唯一身份及安全证据关联。没有改动后端接口、业务模型或原有实验脚本。没有把输入、片单或反馈写入浏览器持久化存储。

## 本地运行与验证

在仓库根目录：

```powershell
python -m pip install -r requirements-s0.txt
python -m uvicorn scripts.s0_mock_server:app --host 127.0.0.1 --port 8000
```

在第二个终端：

```powershell
cd web/app
npm ci
npm run dev
```

入口 `http://127.0.0.1:5173/`；Vite 将 `/api` 转发到本地 8000 服务。浏览器请求没有绕过实际 HTTP 接口。

验证命令（前端目录）：

```powershell
npm test
npm run build
npm run format:check
npm run types:check
npm run test:e2e
```

本地端到端测试使用安装的 Google Chrome；没有 Chrome 时先安装。测试可启动服务，也会复用正在运行的本地服务。Python 不在 PATH 时把 `PYTHON` 设置为对应 Python 可执行文件绝对路径。根目录回归命令为 `python -m scripts.s0_check`。

GitHub Actions 的前端工作流安装 Playwright Chromium，在 Linux 上执行同一套四项目验收并保留报告。CI 使用 Chromium，本机实际验收使用 Google Chrome，两者不混称。

## 构建与部署

`npm run build` 生成 `web/app/dist`；依赖锁文件已提交，应用代码、验证器、框架依赖分包。没有外链字体或虚构的电影图片。

部署方需要提供：

1. 同源 `/api/*` 转发到后端，移除 `/api` 前缀；当前 Vite 代理只在开发时生效，`vite preview` 不提供后端生产代理。
2. 静态资源服务，以及应用路径回退到 `index.html`，保证直接访问 `/film/...`、`/compare` 等路由有效。
3. HTTPS、与后端一致的数据模式及错误响应；推荐响应和用户数据不能当作公共缓存。

本次未部署公网、未接入真实数据源或模型，也未测量生产流量下的 Core Web Vitals。上线前仍需完成真实后端与素材授权、隐私流程、设备兼容、性能及可用性验收。

## 实际验收

验收日期：2026-10-19。本机 Windows、Google Chrome 155.0.8059.80，桌面 1440×1000，另检查 1920×1080 和 2560×1080；手机视口 390×844，另检查 320×720。手机验收使用真实 Chrome 的移动视口与触控模拟，未声称完成实体 iPhone/Android 或 Safari 验收。

| 环境 | 核心工作流 | 服务状态及身份确认 | 系统主题与键盘 | 网络失败与会话边界 |
| --- | --- | --- | --- | --- |
| 桌面浅色 | 通过 | 通过 | 通过 | 通过 |
| 桌面深色 | 通过 | 通过 | 通过 | 通过 |
| 手机浅色 | 通过 | 通过 | 通过 | 通过 |
| 手机深色 | 通过 | 通过 | 通过 | 通过 |

核心工作流包括实际 HTTP 推荐、请求参数、核对来源、片单、真实对比接口、清空与撤销。自动检查文档无横向溢出；axe 在首页、候选、对比及关于页检查 WCAG 2/2.1/2.2 A/AA 相关规则。自动规则通过不等于完整的人工读屏或合规认证。

最终本地结果：24 项浏览器验收、5 项前端单元测试、32 项后端测试全部通过；生产构建、生成类型一致性、格式和差异检查通过。覆盖零输入请求、点选参数、键盘选择、重置、场景一键提交、三部独立候选及明确的固定样例说明；同时保留宽屏、摄影加载、错误状态和隐私流程检查。后端测试有一条原有 Starlette/httpx 弃用提示，无测试失败。生产构建的三个 JavaScript 分包约为 45.0 / 134.8 / 332.5 kB（未压缩）；尚未做线上性能测量。

单元测试覆盖零输入默认请求、偏好参数、三部独立合成候选、响应契约、安全来源、已确认身份、时长与禁用记忆。本轮先建立零输入与多候选失败用例，再完成实现并通过。后端保留原 S0 契约回归，并验证固定样例不能冒充满足个性化约束的推荐。

截图目录为 [`screenshots/`](screenshots/)，包含旧线框基线与 22 张最终验收截图：四种环境的首页、点选区、候选、对比，1920/2560 宽屏明暗主题，以及 320px 手机明暗主题。截图来自端到端测试当前运行，可复现，不是静态设计稿。人工复核桌面与手机的构图、点选区、候选和比较视图；三部候选在宽屏并排、手机单列。

| 截图 | 浅色 | 深色 |
| --- | --- | --- |
| 桌面首页 | [查看](screenshots/desktop-light-home.png) | [查看](screenshots/desktop-dark-home.png) |
| 桌面点选 | [查看](screenshots/desktop-light-choices.png) | [查看](screenshots/desktop-dark-choices.png) |
| 桌面候选 | [查看](screenshots/desktop-light-result.png) | [查看](screenshots/desktop-dark-result.png) |
| 1920 宽屏 | [查看](screenshots/desktop-light-1920.png) | [查看](screenshots/desktop-dark-1920.png) |
| 2560 宽屏 | [查看](screenshots/desktop-light-2560.png) | [查看](screenshots/desktop-dark-2560.png) |
| 手机首页 | [查看](screenshots/mobile-light-home.png) | [查看](screenshots/mobile-dark-home.png) |
| 手机点选 | [查看](screenshots/mobile-light-choices.png) | [查看](screenshots/mobile-dark-choices.png) |
| 320 窄屏 | [查看](screenshots/mobile-light-320.png) | [查看](screenshots/mobile-dark-320.png) |
| 手机候选 | [查看](screenshots/mobile-light-result.png) | [查看](screenshots/mobile-dark-result.png) |
| 手机对比 | [查看](screenshots/mobile-light-compare.png) | [查看](screenshots/mobile-dark-compare.png) |

## 本次使用的 skills

- `software-product-frontend`：产品层级、真实状态、组件复用和 Chrome 验收。
- `frontend-design`：影像优先的视觉方向、大屏构图、排版和响应式设计。
- `web-design-guidelines`：基于当前官方规则复核表单、焦点、交互与可访问性。
- `vercel-react-best-practices`：React 状态、请求、依赖与构建检查。
- `webapp-testing`：Playwright 工作流、截图、异常路径及浏览器回归。

这些是实施方法，运行项目不需要安装 Codex skills。
