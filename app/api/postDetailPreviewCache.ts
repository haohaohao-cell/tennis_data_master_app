import type { PostDetailResponse } from "@/api/posts";

const MAX_PREVIEW_COUNT = 20;
const PREVIEW_TTL_MS = 5 * 60 * 1000;

type CachedPostDetail = {
  detail: PostDetailResponse;
  storedAt: number;
};

const cachedDetails = new Map<string, CachedPostDetail>();

function pruneExpired(now: number) {
  for (const [postId, cached] of cachedDetails) {
    if (now - cached.storedAt > PREVIEW_TTL_MS) {
      cachedDetails.delete(postId);
    }
  }
}

function pruneOverflow() {
  while (cachedDetails.size > MAX_PREVIEW_COUNT) {
    const oldestKey = cachedDetails.keys().next().value;
    if (!oldestKey) {
      return;
    }
    cachedDetails.delete(oldestKey);
  }
}

export function primePostDetailPreview(detail: PostDetailResponse) {
  const now = Date.now();
  pruneExpired(now);
  cachedDetails.delete(detail.post.social_post_id);
  cachedDetails.set(detail.post.social_post_id, {
    detail,
    storedAt: now,
  });
  pruneOverflow();
}

/** Remove a deleted Post from the in-memory detail preview cache. */
export function clearPostDetailPreview(socialPostId: string) {
  cachedDetails.delete(socialPostId);
}

export function peekPostDetailPreview(socialPostId: string | null | undefined) {
  if (!socialPostId) {
    return null;
  }

  const cached = cachedDetails.get(socialPostId);
  if (!cached) {
    return null;
  }

  if (Date.now() - cached.storedAt > PREVIEW_TTL_MS) {
    cachedDetails.delete(socialPostId);
    return null;
  }

  return cached.detail;
}
