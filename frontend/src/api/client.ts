export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// Gọi /api/v1... — lỗi theo contract {"error":{code,message}} (backend/app/api/errors.py)
export async function apiGet<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api/v1${path}`);
  } catch (e) {
    throw new ApiError(0, "network_error", e instanceof Error ? e.message : "mạng lỗi");
  }
  if (!res.ok) {
    let code = "http_error";
    let message = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { error?: { code?: string; message?: string } };
      if (body.error) {
        code = body.error.code ?? code;
        message = body.error.message ?? message;
      }
    } catch {
      // response không phải JSON — giữ default
    }
    throw new ApiError(res.status, code, message);
  }
  return (await res.json()) as T;
}
