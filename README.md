# getnewmovie

个性化电影推荐 Agent。当前本地fork仍包含早期S0和规划文档；主仓库已有真实目录和产品前端，新增Agent能力按当前实施计划推进。

- [当前限期开发实施计划：10月29日目标、10月31日最晚、三人逐日分工](docs/限期开发实施计划_20261029.md)
- [三人开发任务台账：工时、前置、交付和验收](docs/三人开发任务台账.md)
- [开发前准备清单：环境、账号、数据和测试准备](docs/开发执行计划与准备清单.md)
- [已确认的产品功能与架构基线](docs/产品功能与架构基线.md)
- [工具复用调研：现成组件、官方来源与许可限制](docs/工具复用调研.md)
- [S0启动包：三人任务、接口、原型、实验脚本与运行方式](docs/s0/README.md)

本轮已只读核对主仓库main的8f9f486：已有React前端、真实Apple电影目录、筛选、排序、比较和相应测试，本地尚未合并该快照。自然语言、豆瓣/多源评价、LangGraph与长期记忆仍待实现。下方命令为当前本地S0合成Mock入口，同步主仓库后产品运行方式以其现有说明为准。原始录音及访谈文本不纳入仓库。

当前确定使用DeepSeek Flash（`deepseek-flash`），由PionneerZ、yimou408-spec、2284266609-code三人协作。主仓库为[yimou408-spec/getnewmovie](https://github.com/yimou408-spec/getnewmovie)；当前origin所在仓库为2284266609-code的fork，开发后通过PR合入主仓库。

```powershell
python -m pip install -r requirements-s0.txt
python -m scripts.s0_check
python -m uvicorn scripts.s0_mock_server:app --host 127.0.0.1 --port 8000
```

原型：`http://127.0.0.1:8000/`；接口文档：`http://127.0.0.1:8000/docs`。
