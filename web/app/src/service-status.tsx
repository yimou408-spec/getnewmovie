import Ajv from "ajv";
import { useQuery } from "@tanstack/react-query";
import schema from "../../../contracts/generated/health-response.schema.json";
import { api } from "./domain";
import type { components } from "./generated/api";
import { ErrorNotice } from "./request-feedback";
import { TMDBAttribution } from "./evidence";

export type Health = components["schemas"]["HealthResponse"];
const valid = new Ajv({ strict: false }).compile<Health>(schema);
export function validateHealth(raw: unknown): Health {
  if (!valid(raw))
    throw new Error("服务声明与接口约定不一致，能力状态暂无法确认。");
  return raw;
}
const capabilities = [
  [
    "metadata",
    "影片资料",
    "片名、年份、类型、时长、导演与来源海报；字段仍可能缺失。",
  ],
  [
    "ratings",
    "口碑评分",
    "需要有明确来源、量表与证据的评分；电影资料不能代替评分。",
  ],
  [
    "reviews",
    "影评证据",
    "需要实际取得并标注来源的影评；外部搜索链接不能代替影评证据。",
  ],
  [
    "natural_language",
    "自然语言条件解析",
    "可用本机 Qwen 或配置的云模型提取受限条件，也保留规则模式。冲突和未识别条件需确认，电影事实与排序仍由片库和规则提供。",
  ],
  [
    "model_understanding",
    "模型理解与Agent工作流",
    "配置模型后接入自然语言理解、确认与本次条件调整；模型可用性以实际请求为准。",
  ],
  [
    "long_term_memory",
    "长期记忆",
    "偏好确认、读取、修改与删除；本次片单只在当前页面保留。",
  ],
  [
    "local_availability",
    "本地观看渠道",
    "按地区核实可观看渠道；商店资料链接不代表本地可播放。",
  ],
] as const;

export function ServiceStatusView({ health }: { health: Health }) {
  const trusted =
    health.service === "real-catalog" && !health.synthetic_fallback;
  return (
    <section aria-labelledby="service-status-title" className="service-status">
      <h2 id="service-status-title">当前服务声明</h2>
      <p className="muted">
        服务报告的资料源：{health.provider}
        。下表说明已实现的接口能力，不代表上游此刻可用，也不代表推荐质量已通过评估。
      </p>
      {!trusted && (
        <p className="notice">服务身份尚未核实，能力状态保持待确认。</p>
      )}
      <div
        className="table-scroll"
        role="region"
        aria-label="能力接入状态"
        tabIndex={0}
      >
        <table className="capabilities">
          <thead>
            <tr>
              <th scope="col">能力</th>
              <th scope="col">当前状态</th>
              <th scope="col">使用边界</th>
            </tr>
          </thead>
          <tbody>
            {capabilities.map(([key, title, detail]) => {
              const value = trusted ? health.capabilities?.[key] : undefined;
              return (
                <tr key={key}>
                  <th scope="row">{title}</th>
                  <td>
                    {value === true
                      ? "已接入"
                      : value === false
                        ? "未接入"
                        : "待确认"}
                  </td>
                  <td>{detail}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <TMDBAttribution />
    </section>
  );
}

export function useServiceHealth() {
  return useQuery({
    queryKey: ["service-capabilities"],
    queryFn: async () => validateHealth(await api("/health")),
    staleTime: 30000,
    retry: false,
  });
}

export function ServiceStatus() {
  const query = useServiceHealth();
  if (query.isPending) return <p role="status">正在读取服务声明…</p>;
  if (query.error)
    return (
      <>
        <ErrorNotice
          error={query.error}
          retry={() => {
            void query.refetch();
          }}
        />
        <p className="muted">
          服务声明读取失败，当前接入能力待确认；已有候选资料仍可查看。
        </p>
      </>
    );
  return <ServiceStatusView health={query.data} />;
}
