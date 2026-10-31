# 产品前端

保留 React / TypeScript / Vite、Radix Tabs/Checkbox、TanStack Query、React Router、Lucide。沿用宽幅海岸列车摄影、清晰点选分组及系统明暗主题。默认不需要文字输入，支持六种心情、十种分类、三档时长、六个快捷场景，以及已知片名和本次片单选片。

## 运行与验证

根目录安装 `requirements-s0.txt`，运行 `python -m uvicorn scripts.movie_server:app --host 127.0.0.1 --port 8000`。前端目录运行 `npm ci`、`npm run dev`。入口 `http://127.0.0.1:5173/`，Vite 把 `/api` 转发给 8000。无需配置密钥。`/health` 应报告 `real-catalog` 和 `synthetic_fallback: false`。

根目录：`python -m scripts.s0_check` 会检查契约及全部离线后端测试；`python -m scripts.movie_live_check` 是明确需要联网的真实片库筛选验收，并将完整响应写入忽略目录 `artifacts/live-catalog/`。Apple 请求预算为每进程每分钟 20 次，工具达到预算后等待下一个窗口，不绕过限流。

前端目录：`npm test`、`npm run build`、`npm run format:check`、`npm run types:check`、`npm run test:e2e`。类型从真实服务 OpenAPI 生成。联网端到端测试先核对服务身份，再连接真实片库；明确命名为 `OFFLINE` 的证据契约用例使用合成数据，故障用例注入失败或错误契约，均不算真实口碑数据验收。CI 也访问真实上游，其失败可能意味着外部网络/源服务不可用，不以合成数据隐藏失败。

本机使用 Google Chrome，四个项目覆盖桌面 1440×1000、手机 390×844，各自浅色和深色；另验证 1920 和 320 宽度。包括实际 HTTP 请求、偏好筛选、严格时长、空结果、换一组、海报、来源、检索确认、片单、对比、主题即时切换、键盘及错误保留。axe 自动规则不是完整人工无障碍认证。手机为移动视口及触控模拟，未测试实体手机或 Safari。

## 实现与边界

- `scripts/movie_catalog.py`：固定 Apple HTTPS 源、ID 校验、超时、速率预算、有限缓存及真实资料归一化。海报只接受 Apple 图片域名，链接只接受 Apple 商店域名。
- `scripts/movie_sources.py` 与 `scripts/movie_server.py`：真实目录、规则筛选、身份查询和比较；可选 TMDB 失败时切换至 Apple 真实资料并提示，所有来源失败返回可读错误，没有合成回退。
- `src/App.tsx`：自然语言、澄清、点选、请求快照、候选、片单、对比及能力状态；`src/domain.ts` 校验请求响应，未知字段不编造。
- `src/evidence.tsx`：每部电影的证据面板，分别展示原平台评分、量表、票数、采集时间、原始链接、来源观点和推荐推断；没有取得的评分与观点保持未知。比较页保留勾选时的理由和证据快照，换组不会悄悄替换。
- `scripts/movie_model.py` 与 `scripts/movie_intent.py`：本机 Qwen 提取有限条件，保留可选云模型接口；请求失败时规则解析兜底。常见类型、时长、年代和排除条件实际参与筛选；文字与点选冲突及无法执行的要求先确认，最多两项交互澄清，页面注明实际解析方法。
- `scripts/movie_ranking.py`：确定性的内容线索排序与类型/导演多样性；支持保留来源顺序。权重是启发式规则，未拟合个人喜爱概率，也没有评分替代品。
- 心情先按类型映射，再按简介关键词辅助排序。同组 OR，类型、心情类别、时长、年代、排除列表交叉匹配。未知时长/年份不进入对应限定结果。最多展示三部，换一组累计排除；“这次不想看”会在后续新请求中持续排除，可撤销，刷新清空。
- 片单、反馈、备注和对比只在页面内存中；刷新清空。备注暂不参与匹配，页面直接说明。匿名解析会话在服务进程内保存约30分钟，不是账号或长期记忆。本机小模型只提取有限条件；Apple 没有提供评分/影评或地区渠道数据。
- Apple 美国区榜单可能包含预售影片，商店链接不是可观看保证。动画选项对应 Apple Anime；家庭对应 Kids & Family，适龄需要用户核对。

## 部署

构建 `web/app/dist` 后，由部署方提供 HTTPS、静态路由回退，以及同源 `/api/*` 到后端的反向代理；`vite preview` 不提供生产 API 代理。后端应单进程运行以共享当前内存缓存和速率预算。多进程或多实例部署前需集中缓存/限流。本次未部署公网、未作生产负载或 Core Web Vitals 验收；商业发布前仍需单独核对数据服务条款、适用地区和运营要求。

[最新证据展示与验收](p03-20261023.md) · [操作、演示和联调清单](handoff-20261023.md) · [自然语言验收](p02-20261022.md) · [历史真实片库验收](live-catalog-acceptance.md) · [推荐质量与后端方向](recommendation-quality.md) · [素材来源](assets.md) · [视觉方案（历史记录）](visual-redesign.md)
