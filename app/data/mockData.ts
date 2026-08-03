import type { ImageSourcePropType } from "react-native";

export const tennisImages = {
  courtPractice: require("../assets/images/content/court-practice.png"),
  matchEvening: require("../assets/images/content/match-evening.png"),
  serveSession: require("../assets/images/content/serve-session.png"),
} satisfies Record<string, ImageSourcePropType>;

export type Activity = {
  id: string;
  title: string;
  type: "比赛" | "训练" | "课程" | "视频";
  time: string;
  location: string;
  description: string;
  image: ImageSourcePropType;
  metrics: Array<{ label: string; value: string; unit?: string }>;
};

export const activities: Activity[] = [
  {
    id: "match-001",
    title: "周末双打练习赛",
    type: "比赛",
    time: "今天 19:30",
    location: "滨江网球中心 3 号场",
    description: "第二盘发球局稳定很多，反拍防守还有继续整理的空间。",
    image: tennisImages.matchEvening,
    metrics: [
      { label: "时长", value: "96", unit: "min" },
      { label: "制胜分", value: "18" },
      { label: "一发率", value: "62", unit: "%" },
    ],
  },
  {
    id: "drill-serve",
    title: "一发节奏训练",
    type: "训练",
    time: "昨天 16:10",
    location: "城市运动公园",
    description: "保留抛球高度，先把身体重心和挥拍节奏稳定下来。",
    image: tennisImages.serveSession,
    metrics: [
      { label: "发球", value: "84", unit: "次" },
      { label: "进区率", value: "71", unit: "%" },
      { label: "平均速度", value: "138", unit: "km/h" },
    ],
  },
  {
    id: "baseline-002",
    title: "底线多拍对拉",
    type: "训练",
    time: "周三 08:40",
    location: "星河网球馆",
    description: "正手连续性不错，移动到位后击球质量明显更稳。",
    image: tennisImages.courtPractice,
    metrics: [
      { label: "回合", value: "42", unit: "拍" },
      { label: "稳定度", value: "86", unit: "%" },
      { label: "训练量", value: "2.1", unit: "h" },
    ],
  },
];

export const socialPosts = [
  {
    id: "post-1",
    activityId: "baseline-002",
    author: "林安",
    level: "NTRP 3.5",
    time: "18 分钟前",
    text: "今天把底线节奏放慢了一点，连续对拉终于能多坚持几拍。",
    image: tennisImages.courtPractice,
    likes: 128,
    comments: 16,
    saves: 21,
  },
  {
    id: "post-2",
    activityId: "match-001",
    author: "陈一鸣",
    level: "NTRP 4.0",
    time: "1 小时前",
    text: "夜场双打，网前处理比上周更果断。下一次想专门练接发。",
    image: tennisImages.matchEvening,
    likes: 87,
    comments: 9,
    saves: 12,
  },
  {
    id: "post-3",
    activityId: "drill-serve",
    author: "周晴",
    level: "NTRP 3.0",
    time: "今天 09:22",
    text: "发球课后的小目标：抛球不追球，先把动作做完整。",
    image: tennisImages.serveSession,
    likes: 54,
    comments: 5,
    saves: 8,
  },
];

export const nearbyPlayers = [
  { id: "near-1", name: "许航", distance: "0.8 km", level: "NTRP 3.0" },
  { id: "near-2", name: "Mia", distance: "1.4 km", level: "NTRP 3.5" },
  { id: "near-3", name: "赵予", distance: "2.1 km", level: "NTRP 4.0" },
  { id: "near-4", name: "Wen", distance: "3.6 km", level: "初学进阶" },
];

export const trainingEntries = [
  { label: "比赛", icon: "trophy-outline" },
  { label: "训练", icon: "fitness-outline" },
  { label: "课程", icon: "school-outline" },
  { label: "视频", icon: "videocam-outline" },
] as const;

export const createActions = [
  {
    kind: "publish_post",
    label: "发布动态",
    icon: "create-outline",
    subtitle: "发布到社区 Post，不创建 Activity",
  },
  {
    kind: "upload_video",
    label: "上传视频",
    icon: "cloud-upload-outline",
    subtitle: "保存为带视频的 Tennis Activity",
  },
  {
    kind: "record_match",
    label: "记录比赛",
    icon: "trophy-outline",
    subtitle: "无视频也能保存比赛 Activity",
  },
  {
    kind: "record_training",
    label: "记录训练",
    icon: "barbell-outline",
    subtitle: "无视频也能保存训练 Activity",
  },
] as const;

export const notifications = [
  { id: "n1", title: "陈一鸣评论了你的训练动态", time: "5 分钟前", detail: "这组正手节奏很稳。" },
  { id: "n2", title: "课程提醒", time: "今天 15:00", detail: "明晚 19:30 发球专项课。" },
  { id: "n3", title: "训练报告已生成", time: "昨天", detail: "底线多拍对拉的概览可查看。" },
];

export const chats = [
  { id: "c1", name: "周教练", message: "下节课我们先看发球抛球。", time: "12:40" },
  { id: "c2", name: "双打小队", message: "周六下午有人约球吗？", time: "昨天" },
  { id: "c3", name: "林安", message: "视频我已经发你了。", time: "周二" },
];

export type Student = {
  id: string;
  name: string;
  level: string;
  lastLesson: string;
  lessons: number;
  focus: string;
  note: string;
};

export const students: Student[] = [
  {
    id: "stu-1",
    name: "林安",
    level: "NTRP 3.5",
    lastLesson: "昨天 18:30",
    lessons: 18,
    focus: "正手稳定性",
    note: "击球点更靠前后，连续性明显提升。",
  },
  {
    id: "stu-2",
    name: "许航",
    level: "NTRP 3.0",
    lastLesson: "周三 20:00",
    lessons: 9,
    focus: "发球节奏",
    note: "抛球高度需要保持一致，先减少发力变化。",
  },
  {
    id: "stu-3",
    name: "赵予",
    level: "NTRP 4.0",
    lastLesson: "上周日 09:00",
    lessons: 26,
    focus: "接发站位",
    note: "面对二发可以更主动压上，提升回球深度。",
  },
];

export const coachCourses = [
  { id: "course-1", title: "发球专项小课", time: "明天 19:30", students: "许航 / Mia" },
  { id: "course-2", title: "青少年底线稳定性", time: "周六 10:00", students: "林安" },
];

export const pendingVideos = [
  { id: "video-1", title: "许航一发训练", time: "今天上传", length: "00:42" },
  { id: "video-2", title: "林安正手移动", time: "昨天上传", length: "01:16" },
];
