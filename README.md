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
