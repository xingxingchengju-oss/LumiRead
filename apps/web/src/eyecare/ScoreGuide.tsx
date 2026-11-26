import { useLayoutEffect, useRef } from "react";
import type { components } from "../../../../packages/contracts/types";
import "./score-guide.css";

type Policy = components["schemas"]["ScorePolicy"];
const cover = new URL("./reading-break.jpg", import.meta.url).href;
const categoryNames = {
  phone: "手机阅读",
  video: "所有设备看视频",
  tablet: "平板阅读",
  computer: "电脑阅读",
  paper: "纸质阅读",
  other_text: "物体文字阅读",
};

function Articles({ policy }: { policy: Policy }) {
  return (
    <section className="sg-articles" aria-labelledby="sg-articles-title">
      <h3 id="sg-articles-title">用眼科普</h3>
      <details>
        <summary>同样读半小时，手机、平板和纸书有什么不同？</summary>
        <div className="sg-article-body">
          <p>
            一项研究请 90 人分别用手机、平板和纸张阅读同样长的时间。其中有 30 名
            10–18 岁的青少年，平均年龄约 13 岁。每次阅读 30
            分钟后，他们给眼睛干涩、视物模糊等感受打分。
          </p>
          <table>
            <caption>青少年组的眼部不适问卷得分</caption>
            <thead>
              <tr>
                <th scope="col">阅读媒介</th>
                <th scope="col">平均值 ± 标准差</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <th scope="row">手机</th>
                <td>38.40 ± 10.50</td>
              </tr>
              <tr>
                <th scope="row">平板</th>
                <td>25.17 ± 10.70</td>
              </tr>
              <tr>
                <th scope="row">纸张</th>
                <td>11.87 ± 6.98</td>
              </tr>
            </tbody>
          </table>
          <p>
            这组青少年读手机后的平均不适评分最高，因此 LumiRead
            把手机阅读的提醒放在较早一档。
            表中的标准差反映同组读者之间的差异。研究只测量了半小时后的感受，6–9
            岁孩子的个人疲劳变化仍需单独研究。
          </p>
          <p>
            LumiRead 从学习用屏建议的 30～40
            分钟中，取较早的时点提醒手机读者，取中点提醒平板和电脑读者。
            纸书和物体文字参照连续读写 40
            分钟的建议。录像难以区分学习视频和娱乐视频，所有视频统一按较早一档提醒，带字幕的视频也算在内。
            电脑和视频的具体提醒时间属于项目设定。
          </p>
          <a
            href="https://doi.org/10.4274/gulhane.galenos.2025.34711"
            target="_blank"
            rel="noreferrer"
          >
            研究原文与表 3 · Gülhane Medical Journal，2026
          </a>
        </div>
      </details>
      <details>
        <summary>专注看屏幕时，我们会少眨多少次眼？</summary>
        <div className="sg-article-body">
          <p>
            每眨一次眼，眼泪就会重新铺展在眼球表面。一项实验用眼动设备观察了 36
            名 6–15 岁儿童。他们交谈时平均每分钟眨眼 20.8
            次，开始玩手机游戏的第一分钟降至 8.9 次。
          </p>
          <p>
            在随后一小时的游戏中，眨眼频率持续偏低。孩子们在游戏结束后报告了更多眼部不适。
            这个例子说明，换一种任务，眨眼习惯也会变。录像里的阅读时长和个人实际的干涩感，需要分别观察。
          </p>
          <a
            href="https://pubmed.ncbi.nlm.nih.gov/35668140/"
            target="_blank"
            rel="noreferrer"
          >
            阅读学龄儿童手机游戏研究 · Eye，2023
          </a>
        </div>
      </details>
      <details>
        <summary>什么时候抬头，什么时候休息十分钟？</summary>
        <div className="sg-article-body">
          <p>
            写作业或读书约 20 分钟，可以抬起头，找一个约 6 米以外的物体，看至少
            20 秒。 国家卫健委还建议，使用屏幕学习 30～40 分钟后，休息远眺 10
            分钟。连续读写宜控制在 40
            分钟以内。中小学生出于娱乐等非学习目的使用屏幕，单次宜控制在 15
            分钟以内。
          </p>
          <p>
            在回放里，放下手机走开后，系统可以记录阅读和视频的中断。是否实际望向远处，需要自己判断。
            LumiRead 给短暂停顿留出 {policy.rest_grace_seconds}{" "}
            秒缓冲，再逐秒扣分，让满分经过
            {policy.full_rest_seconds / 60}{" "}
            分钟连续休息回到零。下降的数值用于安排下一次提醒。
          </p>
          <a
            href="https://www.nhc.gov.cn/fys/c100078/202307/a210193cfd774009a1db0399d713fec9.shtml"
            target="_blank"
            rel="noreferrer"
          >
            国家卫健委《防控儿童青少年近视核心知识十条》
          </a>
          <a
            href="https://www.nhc.gov.cn/jkj/c100063/201808/0449e83bf5d040a7b257387db8cf24a7.shtml"
            target="_blank"
            rel="noreferrer"
          >
            八部门《综合防控儿童青少年近视实施方案》
          </a>
        </div>
      </details>
    </section>
  );
}

export default function ScoreGuide({
  policy,
  activity,
  range,
  startScore,
  endScore,
  reason,
  onClose,
}: {
  policy: Policy;
  activity: string;
  range: string;
  startScore: string;
  endScore: string;
  reason: string;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useLayoutEffect(() => {
    if (dialog.current && !dialog.current.open) dialog.current.showModal();
  }, []);
  function readArticles() {
    const first = dialog.current?.querySelector<HTMLDetailsElement>(
      ".sg-articles details",
    );
    if (!first) return;
    first.open = true;
    first.querySelector("summary")?.focus({ preventScroll: true });
    first.scrollIntoView({ block: "start" });
  }
  return (
    <dialog
      ref={dialog}
      className="ec-score-guide"
      aria-labelledby="sg-title"
      onClose={onClose}
    >
      <header className="sg-header">
        <h2 id="sg-title">了解用眼提醒积分</h2>
        <button
          type="button"
          className="sg-close"
          aria-label="关闭积分说明"
          onClick={() => dialog.current?.close()}
        >
          ×
        </button>
      </header>
      <div className="sg-content">
        <section className="sg-context" aria-label="当前片段计分">
          <div>
            <small>当前片段 · {range}</small>
            <h3>{activity}</h3>
            <p className="sg-movement">
              <span aria-hidden="true">
                {startScore} <i>→</i> {endScore} <small>分</small>
              </span>
              <span className="sg-spoken">
                本段从 {startScore} 分到 {endScore} 分
              </span>
            </p>
            <p>{reason}</p>
          </div>
          <img
            src={cover}
            width="1280"
            height="720"
            alt="窗边书桌上的书和手机"
          />
        </section>
        <section className="sg-rules" aria-labelledby="sg-rules-title">
          <div className="sg-rules-heading">
            <h3 id="sg-rules-title">多久会提醒休息？</h3>
            <button type="button" onClick={readArticles}>
              阅读科普 <span aria-hidden="true">↓</span>
            </button>
          </div>
          <p>
            LumiRead 按活动时长累计分数，满 {policy.max_points}{" "}
            分提醒安排一次较长的休息。下表是项目选定的提醒时间。
          </p>
          <table aria-labelledby="sg-rules-title">
            <thead>
              <tr>
                <th scope="col">活动</th>
                <th scope="col">每 {policy.settlement_seconds} 个有效秒</th>
                <th scope="col">从零到满分</th>
              </tr>
            </thead>
            <tbody>
              {policy.tiers.map((tier) => (
                <tr key={tier.categories[0]}>
                  <th scope="row">
                    {tier.categories.map((category, i) => (
                      <span className="sg-category" key={category}>
                        {categoryNames[category]}
                        {i + 1 < tier.categories.length && "、"}
                      </span>
                    ))}
                  </th>
                  <td>+{tier.points_per_settlement} 分</td>
                  <td>{tier.minutes_to_reminder} 分钟</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>
            每档把 {policy.max_points} 分均分给该档的有效用眼时间。每凑满{" "}
            {policy.settlement_seconds}{" "}
            秒结算一次，跨片段保留余秒。切换媒介时，每秒仍按原片段的费率计算。
          </p>
          <p>
            <b>休息时</b>，连续前 {policy.rest_grace_seconds}{" "}
            秒保持分数，之后每秒减 {policy.rest_points_per_second}{" "}
            分。从满分连续休息 {policy.full_rest_seconds / 60} 分钟归零。
          </p>
          <p>
            <b>判断待定或缺数时</b>
            ，相应秒数冻结积分，并中断连续休息计时。确认阅读但媒介待定，阅读时长照计。
          </p>
        </section>
        <Articles policy={policy} />
      </div>
    </dialog>
  );
}
