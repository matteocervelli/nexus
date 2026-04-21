export interface ApiErrorDetail {
  status: number;
  message: string;
  detail?: unknown;
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;
  constructor({ status, message, detail }: ApiErrorDetail) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}
