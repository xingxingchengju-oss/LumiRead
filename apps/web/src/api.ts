import type { components } from "../../../packages/contracts/types";
type Schemas = components["schemas"];
export type Session = Schemas["Session"];
export type Snapshot = Schemas["Snapshot"];
export type Item = Schemas["QuestionResult"];
export type Job = Schemas["Job"];
export type EventRow = Schemas["Event"];
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch("/api/v1" + path, {
    ...init,
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res
      .json()
      .then((x) => x.detail)
      .catch(() => null);
    throw new ApiError(
      res.status,
      typeof detail === "string" ? detail : "请求失败，请再试一次。",
    );
  }
  return res.status === 204 ? (undefined as T) : res.json();
}
export function localHost() {
  return ["localhost", "127.0.0.1", "[::1]"].includes(location.hostname);
}
export function json(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}
export function listen(
  sid: string,
  initial: number,
  changed: (e: EventRow) => void,
  connection: (s: string) => void,
) {
  let seq = initial,
    active = true,
    socket: WebSocket | null = null,
    retry = 0,
    poll = 0;
  const consume = (row: EventRow) => {
    if (active && row.seq > seq) {
      seq = row.seq;
      changed(row);
    }
  };
  const connect = () => {
    if (!active) return;
    socket = new WebSocket(
      (location.protocol === "https:" ? "wss://" : "ws://") +
        location.host +
        "/api/v1/sessions/" +
        sid +
        "/ws?after=" +
        seq,
    );
    socket.onopen = () => {
      if (active) {
        connection("实时连接");
        clearInterval(poll);
      }
    };
    socket.onmessage = (event) => consume(JSON.parse(event.data));
    socket.onclose = () => {
      if (!active) return;
      connection("重新连接中");
      const sync = () =>
        api<EventRow[]>("/sessions/" + sid + "/events?after=" + seq)
          .then((rows) => {
            if (active) {
              rows.forEach(consume);
              connection("轮询同步");
            }
          })
          .catch(() => {
            if (active) connection("等待连接");
          });
      clearInterval(poll);
      void sync();
      poll = window.setInterval(sync, 1500);
      retry = window.setTimeout(connect, 4000);
    };
  };
  connect();
  return () => {
    active = false;
    clearTimeout(retry);
    clearInterval(poll);
    socket?.close();
  };
}
export const message = (e: unknown) =>
  e instanceof Error ? e.message : "操作未完成，请重试。";

export type Hotspot = Schemas["Hotspot"];
export type Product = Schemas["Product"];
export type Catalog = Schemas["Catalog"];
export type Sample = Schemas["Sample"];
export type EyeAlert = Schemas["Alert"];
export type Mastery = Schemas["Mastery"];
export type Recommendation = Schemas["Exercise"];
export type Attempt = Schemas["PracticeResult"];
export type ArchivedItem = Schemas["Mistake"];
