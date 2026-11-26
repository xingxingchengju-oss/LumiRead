export const chapters = [
  { id: "top", label: "概览" },
  { id: "sensing", label: "学习感知" },
  { id: "explore", label: "佩戴方式" },
  { id: "construction", label: "佩戴结构" },
  { id: "specifications", label: "价格" },
] as const;

export type Chapter = (typeof chapters)[number]["id"];
export type ScrollTrack = { progress: number; redraw?: () => void };
export type Wear = "open" | "blue" | "clip";
export const choices: { id: Wear; label: string; detail: string }[] = [
  {
    id: "open",
    label: "无镜片",
    detail: "一体镜保留所有感知窗口，镜圈内侧的眼动模组随镜框佩戴。",
  },
  {
    id: "blue",
    label: "防蓝光无度数镜片",
    detail: "同一副镜框配透明平光镜片。转到斜角，可以看见淡紫色镀膜。",
  },
  {
    id: "clip",
    label: "夹片款",
    detail: "弹簧夹口咬合镜框上沿，硅胶垫贴住两侧，继续使用自己的镜片。",
  },
];

export const parts = {
  lens: { name: "镜片", text: "选择佩戴方式。" },
  tof: {
    name: "ToF 距离传感器",
    text: "鼻梁中央的窗口估计镜框到前方读写目标的距离。持续靠近时，学习助手可提醒坐远一些。",
  },
  light: {
    name: "环境光传感器",
    text: "传感器测量读写环境的明暗，读数取自佩戴位置。光线持续偏暗时，学习助手提示检查桌面照明。",
  },
  camera: {
    name: "作业摄像头",
    text: "双击任一侧镜腿的触控区，前向镜头拍下眼前的作业。镜头旁的指示灯随拍摄亮起。",
  },
  "temple-right": {
    name: "右镜腿",
    text: "透过烟灰色外壳，可以看到主板、惯性传感器和无线天线。点主板可进一步放大。",
  },
  "temple-left": {
    name: "左镜腿",
    text: "电池沿镜腿纵向布置，底部的金属触点连接充电底座。",
  },
  board: {
    name: "主板与处理器",
    text: "右镜腿里的电路板连接前向镜头、眼动摄像头和传感器，汇集采样并连接学习助手。",
  },
  battery: {
    name: "可充电电池",
    text: "左镜腿内的电池为镜框和镜腿里的电路供电，与右侧主板分置。",
  },
  eye: {
    name: "内向眼动模组",
    text: "左右镜圈各有一枚朝向眼睛的摄像头，旁边是近红外补光。概念设计将双眼注视方向与头动、前向画面对齐，用于区分阅读、视频与休息。",
  },
  imu: {
    name: "六轴惯性传感器",
    text: "右侧主板采集头部加速度与角速度。结合前向画面估计头动，还需时间同步与佩戴标定。",
  },
  touch: {
    name: "镜腿触控区",
    text: "两侧镜腿各有一段带细纹的触控区。用同一侧连续轻点两次触发拍摄，手机演示采用相同的双击动作。",
  },
  charge: {
    name: "充电触点",
    text: "左镜腿下方的一对触点接通充电底座，为镜腿内的电池补充电量。",
  },
  radio: {
    name: "无线天线",
    text: "折线形天线沿右侧主板末端布置，透过聚合物镜腿完成配对与传图。",
  },
  clamp: {
    name: "弹簧夹扣",
    text: "弹簧夹口绕过原有镜框上沿，前后硅胶垫压紧镜框，给转轴留出活动空间。",
  },
  button: {
    name: "顶部功能按键",
    text: "夹片顶部的实体键用于触发拍摄和配对，凸起的细纹便于手指定位。",
  },
  "clip-core": {
    name: "夹片内部",
    text: "传感器主板与薄型电池并排放在可拆机身内。天线靠近非金属窗口，弹簧转轴位于电池后方。",
  },
} as const;

export type Part = keyof typeof parts;
export type Selection = { part: Part };
export const isPart = (s: unknown): s is Part =>
  typeof s === "string" && Object.hasOwn(parts, s);
export const sensors: Part[] = ["tof", "light", "camera"];
type Group = { title: string; items: Part[] };
const sensing: Group = { title: "纸面与光线", items: sensors };
const wearGroup: Group = { title: "佩戴方式", items: ["lens"] };
const frameGroups: Group[] = [
  sensing,
  { title: "阅读识别", items: ["eye", "imu"] },
  {
    title: "镜腿与内部",
    items: [
      "temple-right",
      "board",
      "radio",
      "temple-left",
      "battery",
      "charge",
      "touch",
    ],
  },
  wearGroup,
];
const clipGroups: Group[] = [
  sensing,
  {
    title: "夹装模块",
    items: ["clamp", "clip-core", "button", "charge", "radio"],
  },
  wearGroup,
];
export const partGroups = (clip: boolean) => (clip ? clipGroups : frameGroups);
export function interactivePart(raw: string, clip: boolean): Part | undefined {
  const id =
    raw === "led"
      ? "camera"
      : raw === "pad"
        ? "clamp"
        : raw === "shell"
          ? "clip-core"
          : raw;
  if (isPart(id) && partGroups(clip).some((g) => g.items.includes(id)))
    return id;
}
export function explanation(id: Part, clip: boolean) {
  if (clip) {
    if (id === "tof")
      return "模块正面的测距窗口估计镜框到前方读写目标的距离。持续偏近时，学习助手可提醒拉开距离。";
    if (id === "camera")
      return "按下顶部实体键，前向镜头记录纸面，镜头旁的指示灯随拍摄亮起。题目交由学习助手识别与讲解。";
    if (id === "radio")
      return "天线位于夹片端部的非金属窗口内侧，用于配对与传图。";
    if (id === "charge")
      return "夹片底部的金属触点接通充电底座，为可拆模块内的电池充电。";
  }
  return parts[id].text;
}
export function exposedShell(id: Part | undefined, clip: boolean) {
  if (clip) return id === "clip-core" ? "shell" : null;
  if (id === "board" || id === "imu" || id === "radio" || id === "temple-right")
    return "temple-right";
  if (id === "battery" || id === "temple-left") return "temple-left";
  return null;
}
export function markers(
  chapter: Chapter,
  clip: boolean,
  focused: boolean,
): Part[] {
  if (focused || chapter === "specifications") return [];
  if (chapter === "sensing") return sensors;
  if (chapter === "construction")
    return clip ? ["clip-core", "clamp"] : ["temple-right", "eye"];
  return ["lens"];
}
export function posterKey(
  wear: Wear,
  chapter: Chapter,
  selected: Selection | null,
) {
  const clip = wear === "clip",
    model = clip ? "clip" : "frame",
    part = selected?.part;
  if (part && part !== "lens") {
    const view =
      part === "temple-right"
        ? "board"
        : part === "temple-left"
          ? "battery"
          : part;
    return view === "clip-core" ? "clip-inside" : model + "-" + view;
  }
  if (!part && chapter === "construction")
    return clip ? "clip-inside" : "frame-inside";
  return wear === "open" ? "frame-open" : model;
}
export const wholePosters = new Set([
  "frame",
  "frame-open",
  "clip",
  "frame-inside",
]);
