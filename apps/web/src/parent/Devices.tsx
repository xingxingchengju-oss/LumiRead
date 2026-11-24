import { useState, useCallback, useEffect } from "react";
import { api, json, message, type Snapshot } from "../api";
export function Devices({
  sid,
  snap,
  setError,
  onSilent,
}: {
  sid: string;
  snap: Snapshot;
  setError: (s: string) => void;
  onSilent: (v: boolean) => void;
}) {
  const [parentInvite, setParentInvite] = useState<{
    url: string;
    code: string;
  } | null>(null);
  const [inv, setInv] = useState<{ url: string; code: string } | null>(null),
    [busy, setBusy] = useState(true);
  const [setup, setSetup] = useState<{
    mode: "lan" | "public";
    public_unavailable: boolean;
    certificate: string | null;
    fingerprint: string | null;
  } | null>(null);
  const fetchInvite = useCallback(
    () =>
      api<{ url: string; code: string }>(
        "/sessions/" + sid + "/invites",
        json("POST", { role: "glasses" }),
      ),
    [sid],
  );
  useEffect(() => {
    let active = true;
    async function loadSetup() {
      try {
        const data = await api<NonNullable<typeof setup>>(
          "/sessions/" + sid + "/phone-setup",
        );
        if (!active) return;
        setSetup(data);
        if (data.mode === "public") {
          const invitation = await fetchInvite();
          if (active) setInv(invitation);
        }
      } catch (e) {
        if (active) setError(message(e));
      } finally {
        if (active) setBusy(false);
      }
    }
    void loadSetup();
    return () => {
      active = false;
    };
  }, [sid, fetchInvite, setError]);
  async function invite() {
    setBusy(true);
    try {
      setInv(await fetchInvite());
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  async function privacy() {
    if (!snap) return;
    setBusy(true);
    try {
      await api(
        "/sessions/" + sid + "/settings",
        json("PATCH", { silent: !snap.silent }),
      );
      onSilent(!snap.silent);
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <aside>
      <section className="paper">
        <h2>眼镜连接</h2>
        {setup?.public_unavailable && (
          <p role="status">
            公网隧道未连通，当前二维码仅限局域网。请将手机和 Mac
            连到同一可互访的网络。
          </p>
        )}
        <p>
          {setup?.mode === "public"
            ? "公网拍摄入口已开启。手机使用 4G、5G 或 Wi-Fi 均可扫码。"
            : "使用 iPhone 相机扫描一次性二维码。"}
        </p>
        <button onClick={invite} disabled={busy}>
          {inv ? "更新配对码" : "生成配对码"}
        </button>
        {inv && (
          <div className="pair-card">
            <img
              src={
                "/api/v1/sessions/" +
                sid +
                "/qr?code=" +
                encodeURIComponent(inv.code)
              }
              alt="虚拟眼镜配对二维码"
            />
            <a href={inv.url}>打开手机配对链接</a>
            <p>有效期 30 分钟，使用后失效。</p>
          </div>
        )}
        {setup?.mode === "public" && (
          <details className="setup">
            <summary>首次连接 iPhone</summary>
            <ol>
              <li>用 iPhone 相机扫上方配对码，在 Safari 打开。</li>
              <li>
                点「开启摄像头」并允许访问。公网地址使用受信任的 HTTPS
                证书，可直接拍摄。
              </li>
              <li>
                连点取景框同一侧的镜框两下即可拍照并上传。想先检查照片，可点「拍下作业」预览。批改结果会出现在这台
                Mac 上。
              </li>
            </ol>
            <p>
              如果 Mac
              换网，请等隧道重新连接。重启公网演示后，刷新家长页并生成新码。
            </p>
          </details>
        )}
        {setup?.certificate && (
          <details className="setup">
            <summary>首次连接 iPhone</summary>
            <ol>
              <li>
                <strong>连接同一网络。</strong> Mac 和 iPhone 连同一 Wi-Fi，
                或让 Mac 连这台 iPhone 的个人热点。用热点时，手机显示 4G 或 5G
                属于正常现象。
              </li>
              <li>
                <strong>用 iPhone 下载证书。</strong> 在手机的 Safari
                地址栏输入下方完整地址， 打开后点「允许 / Allow」。
                <a className="certificate-url" href={setup.certificate}>
                  {setup.certificate}
                </a>
              </li>
              <li>
                <strong>安装描述文件。</strong> 打开「设置 / Settings」，点
                「已下载描述文件 / Profile Downloaded」，选择 LumiRead Local
                Demo CA， 点「安装 / Install」。也可以从「通用 / General → VPN
                与设备管理 / VPN &amp; Device Management」进入。
              </li>
              <li>
                <strong>启用证书信任。</strong> 在「通用 / General → 关于本机 /
                About」底部打开 「证书信任设置 / Certificate Trust
                Settings」，打开 LumiRead Local Demo CA 的开关，点「继续 /
                Continue」。如果只看到 Trust Store Version 和 Trust Asset
                Version，先返回上一步完成安装，再回来打开开关。
              </li>
              <li>
                <strong>扫码开启摄像头。</strong> 在家长页生成配对码，用 iPhone
                相机扫码， 在 Safari
                点「开启摄像头」并允许访问。配对码已用或过期时，在同一场次点「更新配对码」再扫。
              </li>
            </ol>
            <p>
              <strong>换了热点，扫码后一直白屏？</strong> 对照 Safari 地址栏和
              Mac 当前的局域网
              IP。「更新配对码」会沿用服务启动时的地址。如果还是旧 IP， 在 Mac
              项目目录运行 <code>make stop</code>，再运行 <code>make demo</code>
              。 确认启动信息中的手机地址是新 IP，刷新家长页并重新生成配对码。
            </p>
            <p>本机证书 SHA-256</p>
            <code>{setup.fingerprint}</code>
          </details>
        )}
      </section>
      {setup && setup.mode === "lan" && (
        <details className="paper setup">
          <summary>配对另一台家长设备</summary>
          <button
            className="outline"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                setParentInvite(
                  await api<{ url: string; code: string }>(
                    "/sessions/" + sid + "/invites",
                    json("POST", { role: "parent" }),
                  ),
                );
              } catch (e) {
                setError(message(e));
              } finally {
                setBusy(false);
              }
            }}
          >
            生成家长配对邀请
          </button>
          {parentInvite && (
            <div className="pair-card">
              <img
                alt="家长设备配对二维码"
                src={
                  "/api/v1/sessions/" +
                  sid +
                  "/qr?code=" +
                  encodeURIComponent(parentInvite.code)
                }
              />
              <a href={parentInvite.url}>家长配对链接</a>
              <p>一次性使用，有效期 30 分钟。</p>
            </div>
          )}
        </details>
      )}
      <section className="paper">
        <h2>入校静音</h2>
        <p>
          {snap?.silent
            ? "已开启，摄像头和抓拍均已关闭。"
            : "开启后，配对设备会停止取景和拍照。"}
        </p>
        <button className="outline" disabled={!snap || busy} onClick={privacy}>
          {snap?.silent ? "解除静音" : "开启静音"}
        </button>
      </section>
    </aside>
  );
}
