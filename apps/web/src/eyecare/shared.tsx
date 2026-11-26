import { useResource } from "../parent/data";

const updates = new EventTarget();
export function usePublic<T>(path: string) {
  return useResource<T>(path, updates, "");
}
export function Loading({
  error,
  reload,
}: {
  error: string;
  reload: () => void;
}) {
  return error ? (
    <p role="alert">
      {error} <button onClick={reload}>重试</button>
    </p>
  ) : (
    <p role="status">正在读取记录…</p>
  );
}
export const duration = (t: number) => {
  const s = Math.max(0, Math.floor(t));
  return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
};
