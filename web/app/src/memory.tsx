import { useEffect, useState } from "react";
import { api, ApiError } from "./domain";
import type { components } from "./generated/api";

type Preferences = components["schemas"]["PreferencesResponse"];
export type SavedChoices = Partial<components["schemas"]["MemoryPreferences"]>;
export function identityToken() {
  try {
    return localStorage.getItem("movie-identity");
  } catch {
    return null;
  }
}
export function identityHeaders(): HeadersInit {
  const token = identityToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
export async function sendFeedback(
  sessionId: string,
  action: "seen" | "unseen",
  movieId: string,
  eventId: string,
) {
  return api("/feedback", {
    method: "POST",
    headers: identityHeaders(),
    body: JSON.stringify({
      event_id: eventId,
      session_id: sessionId,
      action,
      movie_id: movieId,
      confirmed: true,
    }),
  });
}

export function MemorySettings({
  current,
  onChanged,
}: {
  current: SavedChoices;
  onChanged: (enabled: boolean) => void;
}) {
  const [token, setToken] = useState(identityToken);
  const [preferences, setPreferences] = useState<Preferences>();
  const [seen, setSeen] = useState<string[]>([]);
  const [consent, setConsent] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteConsent, setDeleteConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [message, setMessage] = useState("");

  async function load() {
    const [saved, watched] = await Promise.all([
      api<Preferences>("/me/preferences", { headers: identityHeaders() }),
      api<{ movie_ids: string[] }>("/me/seen", { headers: identityHeaders() }),
    ]);
    setPreferences(saved);
    setSeen(watched.movie_ids);
    onChanged(saved.enabled);
    return saved;
  }
  useEffect(() => {
    if (token) void work(load);
  }, [token]);
  async function work(task: () => Promise<unknown>) {
    setBusy(true);
    setError(undefined);
    setMessage("");
    try {
      await task();
    } catch (e) {
      if (
        e instanceof ApiError &&
        e.status === 401 &&
        e.code === "IDENTITY_REQUIRED"
      ) {
        localStorage.removeItem("movie-identity");
        setToken(null);
        setPreferences(undefined);
        setSeen([]);
        setConsent(false);
        setDeleting(false);
        setDeleteConsent(false);
        onChanged(false);
        setError("匿名身份已失效，请重新同意后建立身份。");
      } else {
        setError(e instanceof Error ? e.message : "操作失败，请重试。");
      }
    } finally {
      setBusy(false);
    }
  }
  async function write(enabled: boolean, choices = current) {
    const {
      genres,
      moods,
      exclude_genres,
      preferred_tags,
      max_runtime_minutes,
      era,
    } = choices;
    const clean = {
      genres,
      moods,
      exclude_genres,
      preferred_tags,
      max_runtime_minutes,
      era,
    };
    if (!preferences) throw new Error("请先刷新服务端记录。");
    const saved = await api<Preferences>("/me/preferences", {
      method: "PUT",
      headers: identityHeaders(),
      body: JSON.stringify({
        enabled,
        constraints: clean,
        confirmed: true,
        expected_version: preferences.version,
      }),
    });
    setPreferences(saved);
    onChanged(saved.enabled);
  }
  return (
    <section
      className="settings memory-settings"
      aria-label="长期偏好与已看管理"
      aria-busy={busy}
    >
      <section>
        <div>
          <h2>{preferences?.enabled ? "记忆已启用" : "长期记忆默认关闭"}</h2>
          <p>
            仅保存你明确确认的偏好与已看记录。本次文字、片单、对比和临时不想看不会成为长期偏好。匿名身份保存在此浏览器；没有账号登录或跨设备恢复。
          </p>
          {!token ? (
            <>
              <label>
                <input
                  type="checkbox"
                  checked={consent}
                  onChange={(e) => setConsent(e.target.checked)}
                />
                同意在本机保存匿名身份，并在服务端保存我确认的偏好与已看记录
              </label>
              <button
                className="button secondary"
                disabled={!consent || busy}
                onClick={() =>
                  void work(async () => {
                    const created = await api<{ identity_token: string }>(
                      "/identities",
                      { method: "POST" },
                    );
                    try {
                      localStorage.setItem(
                        "movie-identity",
                        created.identity_token,
                      );
                    } catch {
                      await api("/me/data?confirmed=true", {
                        method: "DELETE",
                        headers: {
                          Authorization: `Bearer ${created.identity_token}`,
                        },
                      });
                      throw new Error(
                        "浏览器未允许保存匿名身份；尚未启用记忆。",
                      );
                    }
                    const initial = await api<Preferences>("/me/preferences", {
                      headers: identityHeaders(),
                    });
                    const saved = await api<Preferences>("/me/preferences", {
                      method: "PUT",
                      headers: identityHeaders(),
                      body: JSON.stringify({
                        enabled: true,
                        constraints: {},
                        confirmed: true,
                        expected_version: initial.version,
                      }),
                    });
                    setPreferences(saved);
                    setToken(created.identity_token);
                    onChanged(true);
                  })
                }
              >
                建立匿名身份并启用记忆
              </button>
            </>
          ) : (
            <>
              <p>
                已保存类型：
                {preferences?.constraints.genres?.join("、") || "不限"}；心情：
                {preferences?.constraints.moods?.join("、") || "不限"}；时长：
                {preferences?.constraints.max_runtime_minutes ?? "不限"}。
              </p>
              <button
                className="button secondary"
                disabled={busy || !preferences}
                onClick={() =>
                  void work(async () => {
                    await write(
                      !preferences?.enabled,
                      preferences?.constraints as SavedChoices,
                    );
                    setMessage(
                      preferences?.enabled
                        ? "记忆已关闭，推荐不读取已保存记录"
                        : "记忆已启用",
                    );
                  })
                }
              >
                {preferences?.enabled ? "关闭记忆" : "启用已保存记忆"}
              </button>
              <button
                className="button secondary"
                disabled={busy || !preferences}
                onClick={() =>
                  void work(async () => {
                    await write(preferences?.enabled ?? false);
                    setMessage("长期偏好已保存");
                  })
                }
              >
                保存当前点选为长期偏好
              </button>
              <button
                className="button secondary"
                disabled={busy || !preferences}
                onClick={() =>
                  void work(async () => {
                    await api(
                      `/me/preferences?expected_version=${preferences!.version}&confirmed=true`,
                      { method: "DELETE", headers: identityHeaders() },
                    );
                    await load();
                    setMessage("长期偏好已清空，记忆已关闭");
                  })
                }
              >
                清空长期偏好并关闭记忆
              </button>
            </>
          )}
        </div>
      </section>
      {token && (
        <section>
          <div>
            <h2>已看记录</h2>
            <p>
              影片候选上的“确认已看并保存”会跨会话保留；开启记忆时参与排除。
            </p>
            {!seen.length ? (
              <p>还没有已看记录。</p>
            ) : (
              <ul>
                {seen.map((id) => (
                  <li key={id}>
                    {id}{" "}
                    <button
                      className="button text-button"
                      disabled={busy}
                      onClick={() =>
                        void work(async () => {
                          const session = await api<{ session_id: string }>(
                            "/sessions",
                            { method: "POST", headers: identityHeaders() },
                          );
                          await sendFeedback(
                            session.session_id,
                            "unseen",
                            id,
                            crypto.randomUUID(),
                          );
                          await load();
                          setMessage("已移除已看标记");
                        })
                      }
                    >
                      移除已看标记
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <button
              className="button secondary"
              disabled={busy}
              onClick={() => void work(load)}
            >
              刷新服务端记录
            </button>
          </div>
        </section>
      )}
      {token && (
        <section>
          <div>
            <h2>删除个人数据</h2>
            <p>
              删除服务端偏好、已看、反馈和所有关联会话，同时移除此浏览器匿名身份。
            </p>
            {!deleting ? (
              <button
                className="button secondary"
                disabled={busy}
                onClick={() => setDeleting(true)}
              >
                删除全部服务端个人数据
              </button>
            ) : (
              <div role="group" aria-label="确认删除个人数据">
                <label>
                  <input
                    type="checkbox"
                    checked={deleteConsent}
                    onChange={(e) => setDeleteConsent(e.target.checked)}
                  />
                  确认删除偏好、已看与会话，删除后无法撤销
                </label>
                <button
                  className="button secondary"
                  disabled={!deleteConsent || busy}
                  onClick={() =>
                    void work(async () => {
                      await api("/me/data?confirmed=true", {
                        method: "DELETE",
                        headers: identityHeaders(),
                      });
                      localStorage.removeItem("movie-identity");
                      setToken(null);
                      setPreferences(undefined);
                      setSeen([]);
                      setDeleting(false);
                      setDeleteConsent(false);
                      setConsent(false);
                      onChanged(false);
                      setMessage("服务端个人数据已删除，旧匿名身份已失效");
                    })
                  }
                >
                  确认删除全部个人数据
                </button>
                <button
                  className="button text-button"
                  disabled={busy}
                  onClick={() => {
                    setDeleting(false);
                    setDeleteConsent(false);
                  }}
                >
                  取消删除
                </button>
              </div>
            )}
          </div>
        </section>
      )}
      {busy && <p role="status">正在更新服务端记录…</p>}
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
    </section>
  );
}
