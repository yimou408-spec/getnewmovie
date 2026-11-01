import Ajv from "ajv";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ArrowLeft, ExternalLink } from "lucide-react";
import schema from "../../../contracts/generated/configuration-response.schema.json";
import type { components } from "./generated/api";
import { api } from "./domain";
import { ErrorNotice } from "./request-feedback";
import "./runtime-setup.css";

type Configuration = components["schemas"]["RuntimeConfiguration"];
const valid = new Ajv({ strict: false }).compile<Configuration>(schema);
const labels = {
  not_configured: "未配置",
  incomplete: "配置不完整",
  invalid: "配置格式无效",
  configured: "已填写 · 待联网验证",
};

export function RuntimeSetup() {
  const query = useQuery({
    queryKey: ["runtime-configuration"],
    queryFn: async ({ signal }) => {
      const raw = await api("/configuration", { signal });
      if (!valid(raw))
        throw new Error("配置状态返回格式不完整，请更新服务后重试。");
      return raw;
    },
    retry: false,
  });
  return (
    <>
      <div className="page-heading">
        <Link to="/" className="back-link">
          <ArrowLeft size={16} />
          回选片室
        </Link>
        <h1>本机运行配置</h1>
        <p>本机模型配合真实电影榜单即可演示，TMDB 和云模型均为可选接入。</p>
      </div>
      {query.isPending && <p role="status">正在读取配置状态…</p>}
      {query.error && (
        <ErrorNotice
          error={query.error}
          retry={() => {
            void query.refetch();
          }}
        />
      )}
      {query.data && (
        <section className="setup-summary" aria-labelledby="setup-status-title">
          <div className="setup-summary-heading">
            <h2 id="setup-status-title">当前配置状态</h2>
            <button
              className="button secondary"
              disabled={query.isFetching}
              onClick={() => {
                void query.refetch();
              }}
            >
              {query.isFetching ? "读取中…" : "刷新状态"}
            </button>
          </div>
          <p>
            当前片库：
            <strong>
              {query.data.catalog_provider === "tmdb"
                ? "TMDB"
                : "Apple 美国区公开榜单"}
            </strong>{" "}
            · 文字解析：
            <strong>
              {query.data.intent_method === "llm-v1"
                ? query.data.model_location === "local"
                  ? "本机 Qwen 模型"
                  : "云模型"
                : "本地规则"}
            </strong>
          </p>
          <div className="setup-cards">
            {(
              [
                ["tmdb", "TMDB 电影资料（可选）"],
                [
                  "llm",
                  query.data.model_location === "local"
                    ? "本机模型"
                    : "模型解析",
                ],
              ] as const
            ).map(([key, title]) => (
              <article key={key}>
                <h3>{title}</h3>
                <p
                  className={
                    query.data[key].state === "invalid" ||
                    query.data[key].state === "incomplete"
                      ? "setup-warning"
                      : ""
                  }
                >
                  {key === "tmdb" && query.data.catalog_provider === "apple"
                    ? query.data.catalog_fallback_active
                      ? "TMDB 暂时不可用，已启用 Apple 真实榜单"
                      : "当前使用 Apple 真实榜单，无需 TMDB token"
                    : key === "llm" && query.data[key].live_verified
                      ? "已完成真实模型调用"
                      : key === "llm" &&
                          query.data.model_location === "local" &&
                          query.data[key].state === "configured"
                        ? "本机模型已接入 · 待实际调用"
                        : labels[query.data[key].state]}
                </p>
                {(query.data[key].missing ?? []).length > 0 &&
                  !(
                    key === "tmdb" && query.data.catalog_provider === "apple"
                  ) && (
                    <p className="muted">
                      待填写：{(query.data[key].missing ?? []).join("、")}
                    </p>
                  )}
                <p className="muted">
                  {key === "llm" && query.data.model_name
                    ? `模型：${query.data.model_name}。`
                    : ""}
                  {key === "llm" && query.data.model_location === "local"
                    ? "观影文字在本机处理，不需要 API 密钥。"
                    : "本页不显示密钥；填写配置不代表调用成功。"}
                  {query.data[key].verified_at
                    ? ` 最近成功调用：${new Date(query.data[key].verified_at).toLocaleString()}。`
                    : ""}
                </p>
              </article>
            ))}
          </div>
        </section>
      )}
      <section className="setup-guide" aria-labelledby="setup-guide-title">
        <h2 id="setup-guide-title">直接运行本地演示</h2>
        <ol>
          <li>
            <strong>先运行演示。</strong>双击项目根目录{" "}
            <code>start-demo.cmd</code>
            ，等待构建完成。首次会下载约 1.1 GB 的本地 Qwen
            模型并校验文件，之后复用本机文件。
            浏览器将打开本地页面；关闭前保留终端窗口。电影榜单仍需能联网访问
            Apple。
          </li>
          <li>
            <strong>输入观影想法并核对条件。</strong>
            本机 Qwen
            只提取类型、年代、心情和时长等条件，电影资料来自真实片库。遇到冲突会先请你确认。
            本地模型不是 DeepSeek；原定 DeepSeek 接口保留为可选云接入。
          </li>
        </ol>
        <details>
          <summary>可选：改用 TMDB 或云模型</summary>
          <p>
            仅在需要更换资料源或使用团队的云模型时，填写根目录 .env
            并重启演示。现有文件不会被启动器覆盖。
          </p>
          <ol>
            <li>
              <strong>TMDB 使用只读 API token。</strong>用项目持有人的 TMDB
              账号，在 API 设置中申请 <em>API Read Access Token</em>，填写到{" "}
              <code>TMDB_READ_TOKEN</code>。这是 API
              访问凭据，不是网站登录密码，也不是 v3 API Key。
              <a
                href="https://www.themoviedb.org/settings/api"
                target="_blank"
                rel="noopener noreferrer"
              >
                打开 TMDB API 设置{" "}
                <ExternalLink size={13} aria-label="新窗口打开" />
              </a>
            </li>
            <li>
              <strong>模型使用服务商 API 凭据。</strong>填写{" "}
              <code>LLM_BASE_URL</code>、<code>LLM_MODEL</code>、
              <code>LLM_API_KEY</code>。地址为 HTTPS、兼容 Chat Completions 的
              API 根路径，程序会追加 <code>/chat/completions</code>
              。模型名称沿用团队选择，按服务商账号实际权限填写。使用模型时，观影描述会发送给该服务商，可能产生
              API 费用。
            </li>
            <li>
              <strong>完成联网检查。</strong>
              先在命令行运行对应的只读探测，再回页面查找、筛选并核对电影。已填写不代表凭据有效、模型质量合格或当前网络可用。
            </li>
          </ol>
          <div className="setup-command">
            <code>
              .venv\Scripts\python.exe -m scripts.s0_probe_tmdb --live
            </code>
            <code>
              .venv\Scripts\python.exe -m scripts.s0_probe_model --live
            </code>
          </div>
          <p className="muted">
            密钥不要发到聊天或提交 Git。TMDB 未配置时默认用 Apple；已选择 TMDB
            后若发生鉴权、限流或连接故障，会切换到 Apple
            并标明实际来源。未完整配置模型或模型调用失败时使用规则解析，未识别条件仍需确认，也可继续点选选片。
          </p>
        </details>
        <Link to="/about">查看功能与数据边界</Link>
      </section>
    </>
  );
}
