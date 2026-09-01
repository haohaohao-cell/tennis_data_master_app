import type { BusinessObjectCard } from "@/api/messages";

export type BusinessObjectCardDisplayState =
  | "active"
  | "archived"
  | "deleted"
  | "unavailable"
  | "denied"
  | "not_found"
  | "unsupported";

export type BusinessObjectCardDestination =
  | { pathname: "/activity/[id]"; params: { id: string } }
  | { pathname: "/post/[id]"; params: { id: string } }
  | null;

export type MessageBusinessObjectCardModel = {
  destination: BusinessObjectCardDestination;
  displayState: BusinessObjectCardDisplayState;
  icon: "document-text-outline" | "fitness-outline" | "school-outline" | "videocam-outline" | "analytics-outline" | "alert-circle-outline";
  label: string;
  summary: string | null;
  title: string | null;
};

function displayStateForCard(card: BusinessObjectCard): BusinessObjectCardDisplayState {
  if (card.state === "unsupported") return "unsupported";
  if (card.object_state === "deleted") return "deleted";
  if (card.access === "denied") return "denied";
  if (card.access === "not_found") return "not_found";
  if (card.object_state === "archived") return "archived";
  if (card.object_state === "unavailable" || card.state === "unavailable" || !card.can_preview) return "unavailable";
  return "active";
}

function destinationForCard(card: BusinessObjectCard): BusinessObjectCardDestination {
  if (!card.can_open) return null;
  if (card.object_type === "tennis_activity") {
    return { pathname: "/activity/[id]", params: { id: card.object_id } };
  }
  if (card.object_type === "social_post") {
    return { pathname: "/post/[id]", params: { id: card.object_id } };
  }
  return null;
}

function cardLabel(objectType: string): string {
  switch (objectType) {
    case "tennis_activity": return "网球活动";
    case "lesson": return "课程";
    case "video": return "训练视频";
    case "analysis": return "分析";
    case "social_post": return "动态";
    default: return "业务内容";
  }
}

function cardIcon(objectType: string): MessageBusinessObjectCardModel["icon"] {
  switch (objectType) {
    case "tennis_activity": return "fitness-outline";
    case "lesson": return "school-outline";
    case "video": return "videocam-outline";
    case "analysis": return "analytics-outline";
    case "social_post": return "document-text-outline";
    default: return "alert-circle-outline";
  }
}

export function messageBusinessObjectCardModel(card: BusinessObjectCard): MessageBusinessObjectCardModel {
  const displayState = displayStateForCard(card);
  const destination = destinationForCard(card);
  const canShowContent = card.can_preview && ["active", "archived"].includes(displayState);
  return {
    destination,
    displayState,
    icon: cardIcon(card.object_type),
    label: cardLabel(card.object_type),
    summary: canShowContent ? card.safe_summary ?? card.summary : null,
    title: canShowContent ? card.title : null,
  };
}

export function messageBusinessObjectCardStateLabel(state: BusinessObjectCardDisplayState): string {
  switch (state) {
    case "archived": return "已归档";
    case "deleted": return "对象已删除";
    case "denied": return "无权访问";
    case "not_found": return "引用已失效";
    case "unsupported": return "当前版本暂不支持";
    case "unavailable": return "暂不可用";
    default: return "";
  }
}
