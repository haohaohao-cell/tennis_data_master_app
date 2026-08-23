import type { Href } from "expo-router";

import type { MessageUserSummary, NotificationTarget } from "@/api/messages";

export type NotificationRouteIntent =
  | { kind: "navigate"; href: Href }
  | { kind: "request_view" }
  | { kind: "none" };

export function resolveNotificationRoute(
  target: NotificationTarget,
  actor: MessageUserSummary | null,
): NotificationRouteIntent {
  switch (target.type) {
    case "user_profile":
      return {
        kind: "navigate",
        href: {
          pathname: "/user/[id]",
          params: {
            avatar: actor?.avatar_path ?? "",
            id: target.user_id,
            name: actor?.nickname ?? "网球用户",
          },
        },
      };
    case "post_detail":
      return {
        kind: "navigate",
        href: { pathname: "/post/[id]", params: { id: target.post_id } },
      };
    case "post_comments":
      return {
        kind: "navigate",
        href: { pathname: "/post/[id]", params: { focus: "comments", id: target.post_id } },
      };
    case "message_request":
      return { kind: "request_view" };
    case "chat":
      return {
        kind: "navigate",
        href: { pathname: "/chat/[id]", params: { id: target.conversation_id } },
      };
    case "activity_detail":
      return {
        kind: "navigate",
        href: { pathname: "/activity/[id]", params: { id: target.activity_id } },
      };
    case "coach_identity":
      return { kind: "navigate", href: "/profile/coach-apply" };
    case "lesson_detail":
    case "none":
      return { kind: "none" };
  }
}
