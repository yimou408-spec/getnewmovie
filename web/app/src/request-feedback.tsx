import { CircleAlert } from "lucide-react";
import { ApiError } from "./domain";

export function ErrorNotice({
  error,
  retry,
}: {
  error: Error;
  retry?: () => void;
}) {
  const cancelled = error instanceof ApiError && error.kind === "cancelled";
  const canRetry = retry && (!(error instanceof ApiError) || error.retryable);
  return (
    <div
      role={cancelled ? "status" : "alert"}
      className={`notice ${cancelled ? "" : "error"}`}
    >
      <CircleAlert aria-hidden="true" />
      <div>
        <strong>{error.message}</strong>
        {error instanceof ApiError && error.trace && (
          <small>请求编号：{error.trace}</small>
        )}
        {canRetry && (
          <button type="button" className="button quiet" onClick={retry}>
            重新尝试
          </button>
        )}
      </div>
    </div>
  );
}
