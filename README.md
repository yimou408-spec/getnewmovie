# 今晚看什么 · getnewmovie

零输入开始，或点选心情、类型和时长，在真实电影目录中选择、核对来源、加入本次片单及比较。React / TypeScript / Vite 前端随系统切换明暗主题，支持桌面与手机视口。

## 前端、验收与团队进度

- **[打开真实前端预览](https://standards-float-heather-promotional.trycloudflare.com/)**：本轮有效至 **2026-10-23 12:50 北京时间**，非永久部署；中断或到期后的重启方法见报告。
- **[最新验收报告与三人进度对齐](docs/frontend/acceptance-20261023.md)**：直接阅读，无需下载 Actions 压缩包。列明版本、真实操作、CI 证据、未通过项和每位组员待交付事项。
- [PR #4](https://github.com/yimou408-spec/getnewmovie/pull/4) · [云端预览运行](https://github.com/yimou408-spec/getnewmovie/actions/runs/39898294228) · [前端详细文档](docs/frontend/README.md)

**当前尚未达到完整商业级验收。** 已验证真实片库与规则选片；本轮仍有海报加载超时、本机运行工具缺失、最新版本全量验收及跨人联调/评审待完成。旧版本 220 项浏览器通过记录不能代替最新提交签收。请先按报告对齐，勿把计划或自测记为三方完成。

## 运行真实前端与 API

需要 Python 3.11+、Node.js 24，无需 TMDB 密钥。后端需能访问 Apple 美国区公开电影数据。

在仓库根目录构建并同源启动：

~~~powershell
python -m pip install -r requirements-s0.txt
cd web/app
npm ci
npm run build
cd ../..
python -m uvicorn scripts.movie_preview:app --host 127.0.0.1 --port 8000
~~~

打开 http://127.0.0.1:8000/，健康状态 http://127.0.0.1:8000/api/health。只发布前端构建目录与 API，支持子页面刷新；不发布仓库文件。这是复现说明，不表示当前用户电脑服务已恢复。

开发模式在根目录启动 API：

~~~powershell
python -m uvicorn scripts.movie_server:app --host 127.0.0.1 --port 8000
~~~

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
- 自然语言**规则解析与交互澄清已实现**：识别常见类型、心情、时长、年代和排除。冲突或不能执行的要求先确认，再查询片库。心情是类型/简介词法推断，不代表观众口碑或喜爱概率。
- 原始来源、采集时间、事实与推断分开显示。数据缓存约 30 分钟；评分、影评及地区观看渠道未取得时明确未知，商店链接不是直接播放。
- 基础资料比较、本次片单与隐藏/撤销反馈可用；只保存在当前页面，刷新清空。账号、持久化、长期记忆、DeepSeek 通用模型解析、LangGraph 主图、真实多源口碑尚待集成与验收。
- 和家人会限定家庭/动画，适龄仍需自行核对；其他同行选项仅记录情境。尚无真实用户研究或优于豆瓣的效果证据。

## 三人分工与计划

由 PionneerZ、yimou408-spec、2284266609-code 协作；以 [任务台账](docs/三人开发任务台账.md) 和 [本轮对齐清单](docs/frontend/acceptance-20261023.md#10-月-23-日三人对齐清单) 区分实现、自测、联调和交叉评审。

- [限期开发实施计划：10/29 目标、10/31 最晚](docs/限期开发实施计划_20261029.md)
- [开发执行与准备清单](docs/开发执行计划与准备清单.md)
- [产品功能与架构基线](docs/产品功能与架构基线.md)
- [工具复用调研](docs/工具复用调研.md)
- [推荐质量与后端方向](docs/frontend/recommendation-quality.md) · [素材来源](docs/frontend/assets.md)

历史 [S0 启动包](docs/s0/README.md) 仅用于离线契约和合成实验，不能作为产品真实数据验收。原始录音及访谈文本不纳入仓库。[原计划](docs/开发计划.md) · [TDD 清单](docs/TDD验收与任务清单.md)
