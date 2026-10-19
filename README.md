# getnewmovie

今晚看什么 · 私人选片室。零输入开始，或点选心情、类型与时长，在真实电影中挑选、核对来源、加入本次片单及对比。界面随系统切换明暗主题，支持桌面与手机视口。

## 运行

需要 Python 3.11+、Node.js 24。无需 API 密钥；后端访问 Apple 美国区公开电影榜单及影片查询接口。

```powershell
python -m pip install -r requirements-s0.txt
python -m uvicorn scripts.movie_server:app --host 127.0.0.1 --port 8000
```

第二个终端：

```powershell
cd web/app
npm ci
npm run dev
```

打开 `http://127.0.0.1:5173/`。接口文档 `http://127.0.0.1:8000/docs`。资料源不可用时显示错误，不会使用合成影片补齐。

## 当前范围

- 真实目录为 Apple **美国区当前电影分类榜单**，不是全量电影库；搜索使用来源原文片名，覆盖当前分类榜单。
- 类型同组选项取并集，心情与类型交叉匹配，再结合简介关键词、类型与导演差异安排候选。支持年代、严格片长、榜单顺序，以及会话内持续排除和撤销。心情为规则推断，未经主观推荐质量验证。片长使用影片查询的 `trackTimeMillis` 向上取整，绝不用 RSS 预告片时长。
- 每次最多展示 3 部，显示实际查得及匹配数量；可以换一组，排除已经展示的影片。
- 资料缓存 30 分钟，保留来源与采集时间。缺失评分与地区观看渠道显示未知，商店链接不是直接播放。
- 自由文字理解、影评、中文片名翻译、模型个性化推荐、账号、云端片单和长期记忆尚未实现。其他同行选项只记录情境；和家人筛选家庭/动漫类别，但不保证适龄。

[前端设计、运行及验收](docs/frontend/README.md) · [真实片库验收记录](docs/frontend/live-catalog-acceptance.md) · [素材来源](docs/frontend/assets.md)

历史 S0 合成 Mock 仅保留用于离线契约实验和测试，产品入口及浏览器验收不使用该服务。[原计划](docs/开发计划.md) · [TDD 清单](docs/TDD验收与任务清单.md) · [S0 实验](docs/s0/README.md)
