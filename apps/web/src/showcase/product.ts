export const chapters = [
  { id: "top", label: "概览" },
  { id: "explore", label: "佩戴方式" },
  { id: "sensing", label: "学习感知" },
  { id: "construction", label: "佩戴结构" },
  { id: "specifications", label: "价格" },
] as const;

export type Chapter = (typeof chapters)[number]["id"];
export type Wear = "open" | "blue" | "clip";
export const choices: { id: Wear; label: string; detail: string }[] = [
  { id: "open", label: "无镜片", detail: "保留一体镜框与内置传感器。" },
  {
    id: "blue",
    label: "防蓝光无度数镜片",
    detail: "透明平光镜片，斜光下可见淡淡的镀膜反光。",
  },
  {
    id: "clip",
    label: "夹片款",
    detail: "把智能模块夹在自己的眼镜上，继续使用原有镜片。",
  },
];

export const parts = {
  lens: { name: "镜片", text: "选择适合自己的佩戴方式。" },
  camera: {
    name: "作业摄像头",
    text: "镜头朝向眼前的纸面，拍下作业和题目，供学习助手识别与讲解。",
  },
  led: {
    name: "拍摄指示灯",
    text: "摄像头旁的指示灯显示拍摄状态，孩子和身边的人都能看见。",
  },
  tof: {
    name: "ToF 距离传感器",
    text: "鼻梁中央的小窗口测量眼睛到书本的距离。持续靠得太近时，学习助手会提醒调整坐姿。",
  },
  light: {
    name: "环境光传感器",
    text: "传感器测量读写环境的明暗。桌面光线偏低时，学习助手会提示开灯或挪到亮一点的地方。",
  },
  rim: {
    name: "烟灰半透明镜框",
    text: "全框板材包住镜片边缘，也把前部传感器收进上沿。烟灰色材质在侧光下透出内部轮廓。",
  },
  nose: {
    name: "硅胶鼻托",
    text: "两侧柔软的鼻托贴合鼻梁，支撑镜架，减少读写时向下滑动。",
  },
  hinge: {
    name: "轻量金属铰链",
    text: "哑金色转轴连接镜框和镜腿，打开时支撑镜架，收起时让镜腿折回内侧。",
  },
  "temple-right": {
    name: "右镜腿",
    text: "外壳下方是主板。把处理与通信电路放在右侧，可以腾出前框的空间。",
  },
  "temple-left": {
    name: "左镜腿",
    text: "电池藏在左侧镜腿，与另一侧的主板分开布置，让两侧的重量更均衡。",
  },
  board: {
    name: "主板与处理器",
    text: "右镜腿里的电路板连接摄像头和传感器，负责图像处理与数据通信。",
  },
  battery: {
    name: "可充电电池",
    text: "左镜腿内的电池为摄像头和传感器供电，与右侧主板分担整副眼镜的重量。",
  },
  ear: {
    name: "柔软防滑耳套",
    text: "柔软的耳套沿耳后弯曲，帮助镜架保持稳定，也让长时间佩戴时的接触更舒适。",
  },
  shell: {
    name: "镁合金机身",
    text: "轻量金属外壳包住夹片模块的传感器与电路。圆角贴近镜框上沿，减少突出感。",
  },
  button: {
    name: "顶部功能按键",
    text: "顶部凸起的实体按键便于凭触感定位，用于开关、触发拍摄和设备配对。",
  },
  clamp: {
    name: "弹簧夹扣",
    text: "打开夹口，沿镜框上沿放入，再松开夹扣。模块就能随原有眼镜一起佩戴。",
  },
  pad: {
    name: "夹口硅胶垫",
    text: "柔软的硅胶垫夹在金属件和镜框之间，帮助夹紧，也保护原有镜框的表面。",
  },
} as const;

export type Part = keyof typeof parts;
export type Point = [number, number, number];
export type Selection = { part: Part; point?: Point };
export const isPart = (value: unknown): value is Part =>
  typeof value === "string" && Object.hasOwn(parts, value);

type PartGroup = { title: string; items: Part[] };
export function partGroups(clip: boolean): PartGroup[] {
  const sensing: PartGroup = {
    title: "学习感知",
    items: ["camera", "tof", "light", "led"],
  };
  return clip
    ? [
        sensing,
        { title: "夹装模块", items: ["shell", "button", "clamp", "pad"] },
        { title: "佩戴方式", items: ["lens"] },
      ]
    : [
        sensing,
        { title: "镜框与佩戴", items: ["lens", "rim", "hinge", "nose", "ear"] },
        {
          title: "镜腿与内部",
          items: ["temple-right", "board", "temple-left", "battery"],
        },
      ];
}

export function explanation(part: Part, clip: boolean) {
  if (clip && part === "tof")
    return "模块正面的测距窗口朝向桌面，测量读写距离。持续靠书本太近时，学习助手会发出提醒。";
  return parts[part].text;
}

export function exposedTemple(part?: Part) {
  if (part === "board" || part === "temple-right") return "temple-right";
  if (part === "battery" || part === "temple-left") return "temple-left";
  return null;
}

export function markers(
  chapter: Chapter,
  clip: boolean,
  focused: boolean,
): Part[] {
  if (focused || chapter === "specifications") return [];
  if (chapter === "sensing") return ["camera", "tof", "light"];
  if (chapter === "construction")
    return clip ? ["clamp", "button"] : ["temple-left", "temple-right"];
  return ["lens"];
}
