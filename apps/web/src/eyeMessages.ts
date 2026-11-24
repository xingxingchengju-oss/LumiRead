export const distanceNotice = "离作业有点近，稍微坐远一点";
export const brightnessNotice = "桌面有点暗，试试开灯或挪到亮一点的地方";

export function distanceState(estimate: number | null) {
  if (estimate === null) return "暂时无法估计";
  return estimate < 33 ? "可能过近" : "距离合适";
}
