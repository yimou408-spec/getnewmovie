# getnewmovie

个性化电影推荐 Agent，当前处于S0数据与接口可行性阶段。

- [开发计划：需求证据、核心/次核心范围、架构与里程碑](docs/开发计划.md)
- [TDD验收与任务清单：测试先行、故障与安全门禁](docs/TDD验收与任务清单.md)
- [工具复用调研：现成组件、官方来源与许可限制](docs/工具复用调研.md)
- [S0启动包：三人任务、接口、原型、实验脚本与运行方式](docs/s0/README.md)

S0包含可运行的合成Mock、交互线框、契约检查和实验脚本；产品推荐服务尚未实现，真实数据源与模型可行性待验证。原始录音及访谈文本不纳入仓库。

```powershell
python -m pip install -r requirements-s0.txt
python -m scripts.s0_check
python -m uvicorn scripts.s0_mock_server:app --host 127.0.0.1 --port 8000
```

原型：`http://127.0.0.1:8000/`；接口文档：`http://127.0.0.1:8000/docs`。

## 产品前端

新的响应式前端位于 `web/app`，支持选片、同名影片确认、本次片单、影片资料、对比、偏好与隐私说明。浅色与深色外观自动跟随系统。

需要 Python 3.11+、Node.js 24 与 npm。在上面的 Mock 服务保持运行时，另开终端：

```powershell
cd web/app
npm ci
npm run dev
```

打开 `http://127.0.0.1:5173/`。这是连接真实 S0 HTTP 接口的合成数据联调版；推荐模型、真实电影数据、账号、云端片单及长期记忆尚未实现。旧线框入口仍保留。

[前端设计、接入边界、部署与验收记录](docs/frontend/README.md)
