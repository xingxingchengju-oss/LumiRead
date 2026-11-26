import type { Part } from "./product";

type Annotation = { anchor: string; text: string; below?: boolean };
export type StructureStep = {
  part: Part;
  view: string;
  cover?: string;
  location: string;
  title: string;
  description: string;
  labels?: Annotation[];
};

export const frameSteps: StructureStep[] = [
  {
    part: "touch",
    view: "frame-touch",
    location: "右镜腿外侧",
    title: "手指碰到哪里",
    description:
      "两侧镜腿各有一段细纹触控区。连续轻点同一侧两次，就能让前向相机拍下作业。",
  },
  {
    part: "board",
    view: "frame-board",
    cover: "frame-closed",
    location: "右镜腿内部",
    title: "右镜腿里有什么",
    description:
      "处理器汇集采样，六轴惯性传感器记录头动。靠近镜腿末端的折线形天线负责无线连接。",
    labels: [
      { anchor: "radio", text: "天线" },
      { anchor: "processor", text: "处理器", below: true },
      { anchor: "imu", text: "惯性传感器" },
    ],
  },
  {
    part: "battery",
    view: "frame-battery",
    location: "左镜腿内部",
    title: "电从哪里来",
    description:
      "薄型电池沿左镜腿铺开。下方一对金属触点与底座接合，为电池充电。",
    labels: [
      { anchor: "battery", text: "电池" },
      { anchor: "charge", text: "充电触点", below: true },
    ],
  },
  {
    part: "eye",
    view: "frame-eye",
    location: "镜圈内侧",
    title: "眼镜怎样看向眼睛",
    description:
      "左右镜圈各有一枚朝向眼睛的摄像头，旁边的两点是近红外补光。概念设计将眼动与头动、前向画面同步。",
  },
];

export const clipSteps: StructureStep[] = [
  {
    part: "clamp",
    view: "clip-clamp",
    location: "镜框上沿",
    title: "夹片怎样戴稳",
    description:
      "弹簧夹扣跨过原有镜框的上沿，前后两片硅胶垫从两侧夹紧，让镜片留在原位。",
  },
  {
    part: "button",
    view: "clip-button",
    location: "夹片顶部",
    title: "按哪里拍作业",
    description:
      "摸到凸起的按键后轻按一次，前向相机便拍下纸面，镜头旁的指示灯随拍摄亮起。",
  },
  {
    part: "clip-core",
    view: "clip-inside",
    cover: "clip-closed",
    location: "夹片机身内部",
    title: "机身里怎样排布",
    description:
      "主板与薄型电池并排装在夹片里，避开后方的弹簧转轴。天线藏在端部的非金属窗口内侧。",
    labels: [
      { anchor: "pcb", text: "主板" },
      { anchor: "cell", text: "电池", below: true },
      { anchor: "radio", text: "天线窗口" },
    ],
  },
  {
    part: "charge",
    view: "clip-charge",
    location: "夹片底部",
    title: "怎样充电",
    description: "底部的两枚金属触点对齐充电底座，电流由这里进入夹片内的电池。",
  },
];
