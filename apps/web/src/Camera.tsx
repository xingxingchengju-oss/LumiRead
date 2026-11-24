import { useEffect, useRef, useState } from "react";
import { api, message } from "./api";
import { SensorPanel } from "./glass/SensorPanel";
import { DoubleTap, type TapSide } from "./glass/doubleTap";

type Photo = { file: Blob; key: string } & (
  | { source: "camera" | "native_camera" }
  | { source: "double_tap"; side: TapSide }
);
export function Camera({ sid, silent }: { sid: string; silent: boolean }) {
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const generation = useRef(0);
  const picker = useRef<HTMLInputElement>(null);
  const [live, setLive] = useState(false);
  const taps = useRef(new DoubleTap());
  const finder = useRef<HTMLDivElement>(null);
  const [photo, setPhoto] = useState<Photo | null>(null),
    [preview, setPreview] = useState("");
  const [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false);
  const [confirmed, setConfirmed] = useState(false),
    [failed, setFailed] = useState(false);
  const locked = useRef(false),
    reupload = useRef<AbortController | null>(null);
  const muted = useRef(silent);
  muted.current = silent;
  const currentPhoto = useRef(photo);
  currentPhoto.current = photo;

  function stop() {
    taps.current.reset();
    generation.current++;
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
    if (video.current) video.current.srcObject = null;
    setLive(false);
  }
  useEffect(() => {
    if (silent) {
      stop();
      reupload.current?.abort();
      currentPhoto.current = null;
      setPhoto(null);
      setFailed(false);
      setNotice("入校静音已开启");
    }
  }, [silent]);
  useEffect(() => {
    const hide = () => {
      if (document.hidden) stop();
    };
    const interrupt = (event: PointerEvent) => {
      if (
        !event.isPrimary ||
        !(event.target instanceof Element) ||
        !finder.current?.contains(event.target) ||
        !event.target.closest("[data-tap-side]")
      )
        taps.current.reset();
    };
    document.addEventListener("pointerdown", interrupt, true);
    document.addEventListener("visibilitychange", hide);
    window.addEventListener("pagehide", stop);
    return () => {
      document.removeEventListener("pointerdown", interrupt, true);
      document.removeEventListener("visibilitychange", hide);
      window.removeEventListener("pagehide", stop);
      stop();
      reupload.current?.abort();
    };
  }, [sid]);
  useEffect(() => {
    if (!photo) {
      setPreview("");
      return;
    }
    const url = URL.createObjectURL(photo.file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [photo]);
  async function start() {
    if (muted.current || locked.current) return;
    stop();
    setNotice("");
    locked.current = true;
    setBusy(true);
    const stamp = generation.current;
    try {
      if (!navigator.mediaDevices?.getUserMedia)
        throw new Error("实时取景需要受信任的 HTTPS。也可使用下方的系统相机。");
      const rear: MediaTrackConstraints & { zoom: { ideal: number } } = {
        facingMode: { exact: "environment" },
        width: { ideal: 2560 },
        height: { ideal: 1920 },
        zoom: { ideal: 1 },
      };
      const next = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: rear,
      });
      if (stamp !== generation.current || muted.current || !video.current) {
        next.getTracks().forEach((t) => t.stop());
        return;
      }
      stream.current = next;
      const track = next.getVideoTracks()[0];
      track?.addEventListener(
        "ended",
        () => {
          if (stamp === generation.current) {
            stop();
            setNotice("取景已中断，可以重新开启摄像头。");
          }
        },
        { once: true },
      );
      const actual = track?.getSettings().facingMode;
      if (actual && actual !== "environment")
        throw new Error("当前设备未提供后置摄像头，可使用系统相机。");
      video.current.srcObject = next;
      await video.current.play();
      if (stamp === generation.current && !muted.current) setLive(true);
    } catch (e) {
      if (stamp === generation.current) {
        stop();
        setNotice(message(e));
      }
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }
  async function send(item: Photo) {
    setFailed(false);
    setNotice("正在上传作业照片…");
    const body = new FormData();
    body.set("photo", item.file, "worksheet.jpg");
    body.set("source", item.source);
    if (item.source === "double_tap") body.set("tap_side", item.side);
    body.set("idem", item.key);
    body.set("phone_confirmed", String(confirmed));
    const controller = new AbortController();
    reupload.current = controller;
    try {
      await api("/sessions/" + sid + "/captures", {
        method: "POST",
        body,
        signal: controller.signal,
      });
      if (!muted.current) {
        currentPhoto.current = null;
        setPhoto(null);
        setNotice("照片已送达，家长端可查看批改进度。");
      }
    } catch (e) {
      if (!muted.current && !controller.signal.aborted) {
        currentPhoto.current = item;
        setPhoto(item);
        setFailed(true);
        setNotice("照片上传失败，可重试。" + message(e));
      }
    } finally {
      if (reupload.current === controller) reupload.current = null;
    }
  }
  async function snap(side?: TapSide) {
    taps.current.reset();
    const v = video.current;
    if (
      !v?.videoWidth ||
      muted.current ||
      locked.current ||
      currentPhoto.current ||
      !live
    )
      return;
    locked.current = true;
    setBusy(true);
    setNotice("");
    const stamp = generation.current;
    try {
      const c = document.createElement("canvas");
      c.width = v.videoWidth;
      c.height = v.videoHeight;
      const context = c.getContext("2d");
      if (!context) throw new Error("无法抓拍，请使用系统相机。");
      context.drawImage(v, 0, 0);
      const blob = await new Promise<Blob | null>((resolve) =>
        c.toBlob(resolve, "image/jpeg", 0.94),
      );
      if (stamp !== generation.current || muted.current) return;
      if (!blob) throw new Error("照片生成失败，请重拍。");
      const item: Photo = {
        file: blob,
        ...(side
          ? { source: "double_tap" as const, side }
          : { source: "camera" as const }),
        key: crypto.randomUUID(),
      };
      if (side) {
        await send(item);
      } else {
        currentPhoto.current = item;
        setPhoto(item);
      }
    } catch (e) {
      if (!muted.current) setNotice(message(e));
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }
  async function upload() {
    if (!photo || muted.current || locked.current) return;
    locked.current = true;
    setBusy(true);
    setNotice("");
    try {
      await send(photo);
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }
  return (
    <section className="camera glass-camera">
      <header className="section-title">
        <h1>作业取景</h1>
        <span className="status">
          {live ? "摄像头开启" : silent ? "入校静音" : "摄像头关闭"}
        </span>
      </header>
      <div className="viewfinder" ref={finder} aria-label="后摄作业取景框">
        <video
          ref={video}
          playsInline
          muted
          aria-label="摄像头预览"
          hidden={!live || !!photo}
        />
        {photo && preview ? (
          <img src={preview} alt="待上传的作业照片" />
        ) : (
          !live && <p>将整张作业纸平放在镜头前</p>
        )}
        {live &&
          !photo &&
          (["left", "right"] as const).map((side) => {
            const label = side === "left" ? "左镜框" : "右镜框";
            return (
              <div
                key={side}
                data-tap-side={side}
                className="glass-touch-rail"
                role="group"
                aria-label={label + "双击区"}
                onPointerDown={(event) => {
                  if (muted.current || locked.current || currentPhoto.current) {
                    taps.current.reset();
                    return;
                  }
                  if (taps.current.begin(side, event.nativeEvent))
                    event.currentTarget.setPointerCapture(event.pointerId);
                }}
                onPointerMove={(event) => taps.current.move(event.nativeEvent)}
                onPointerCancel={() => taps.current.reset()}
                onLostPointerCapture={(event) =>
                  taps.current.lost(event.pointerId)
                }
                onPointerUp={(event) => {
                  const rect = event.currentTarget.getBoundingClientRect();
                  if (
                    event.clientX < rect.left ||
                    event.clientX > rect.right ||
                    event.clientY < rect.top ||
                    event.clientY > rect.bottom
                  ) {
                    taps.current.reset();
                    return;
                  }
                  if (taps.current.end(side, event.nativeEvent))
                    void snap(side);
                }}
              >
                <span>{label}</span>
                <strong>双击</strong>
              </div>
            );
          })}
      </div>
      {live && !photo && (
        <p className="glass-rail-hint">
          连续轻点同一侧镜框两下，即可拍照并上传。
        </p>
      )}
      <label className="check">
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
        />
        本次由本人使用 iPhone 16 Pro Max 现场拍摄
      </label>
      <div className="actions">
        {photo ? (
          <>
            <button disabled={busy || silent} onClick={upload}>
              {failed ? "重试上传" : "上传并批改"}
            </button>
            <button
              className="outline"
              disabled={busy}
              onClick={() => {
                currentPhoto.current = null;
                setPhoto(null);
                setFailed(false);
                setNotice("");
              }}
            >
              重拍
            </button>
          </>
        ) : (
          <>
            {live ? (
              <>
                <button disabled={busy || silent} onClick={() => snap()}>
                  拍下作业
                </button>
                <button className="outline" onClick={stop}>
                  关闭摄像头
                </button>
              </>
            ) : (
              <button disabled={busy || silent} onClick={() => start()}>
                开启摄像头
              </button>
            )}
            <button
              className="outline"
              disabled={busy || silent}
              onClick={() => picker.current?.click()}
            >
              使用系统相机
            </button>
          </>
        )}
      </div>
      <input
        hidden
        ref={picker}
        type="file"
        accept="image/*"
        capture="environment"
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file && !muted.current && !locked.current) {
            const item: Photo = {
              file,
              source: "native_camera",
              key: crypto.randomUUID(),
            };
            currentPhoto.current = item;
            setFailed(false);
            setPhoto(item);
            setNotice("");
          }
        }}
      />
      <p role="status">{notice}</p>
      <SensorPanel
        key={sid}
        sid={sid}
        video={video}
        active={live && !photo}
        silent={silent}
      />
    </section>
  );
}
