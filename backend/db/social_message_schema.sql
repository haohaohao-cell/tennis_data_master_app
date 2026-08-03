-- Incremental schema for social relationships, conversations, and notifications.
-- This file is safe to run against existing development databases.

CREATE TABLE IF NOT EXISTS user_follows (
    follow_id TEXT PRIMARY KEY,
    follower_user_id TEXT NOT NULL,
    following_user_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'canceled')),
    source TEXT CHECK (source IS NULL OR length(source) <= 50),
    followed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    canceled_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (follower_user_id <> following_user_id),
    CHECK (status = 'active' OR canceled_at IS NOT NULL),
    FOREIGN KEY (follower_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (following_user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_social_stats (
    user_id TEXT PRIMARY KEY,
    follower_count INTEGER NOT NULL DEFAULT 0 CHECK (follower_count >= 0),
    following_count INTEGER NOT NULL DEFAULT 0 CHECK (following_count >= 0),
    friend_count INTEGER NOT NULL DEFAULT 0 CHECK (friend_count >= 0),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_blocks (
    user_block_id TEXT PRIMARY KEY,
    blocker_user_id TEXT NOT NULL,
    blocked_user_id TEXT NOT NULL,
    reason TEXT CHECK (reason IS NULL OR length(reason) <= 255),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    CHECK (blocker_user_id <> blocked_user_id),
    FOREIGN KEY (blocker_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (blocked_user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_privacy_settings (
    user_id TEXT PRIMARY KEY,
    direct_message_policy TEXT NOT NULL DEFAULT 'friends'
        CHECK (direct_message_policy IN ('everyone', 'following', 'friends')),
    allow_message_requests INTEGER NOT NULL DEFAULT 1 CHECK (allow_message_requests IN (0, 1)),
    default_post_visibility TEXT NOT NULL DEFAULT 'public'
        CHECK (default_post_visibility IN ('private', 'friends', 'followers', 'public')),
    show_profile_to_strangers INTEGER NOT NULL DEFAULT 1 CHECK (show_profile_to_strangers IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS social_post_stats (
    social_post_id TEXT PRIMARY KEY,
    like_count INTEGER NOT NULL DEFAULT 0 CHECK (like_count >= 0),
    comment_count INTEGER NOT NULL DEFAULT 0 CHECK (comment_count >= 0),
    favorite_count INTEGER NOT NULL DEFAULT 0 CHECK (favorite_count >= 0),
    share_count INTEGER NOT NULL DEFAULT 0 CHECK (share_count >= 0),
    view_count INTEGER NOT NULL DEFAULT 0 CHECK (view_count >= 0),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (social_post_id) REFERENCES social_posts(social_post_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS post_reactions (
    reaction_id TEXT PRIMARY KEY,
    social_post_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    reaction_type TEXT NOT NULL DEFAULT 'like'
        CHECK (reaction_type IN ('like')),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'canceled')),
    source TEXT CHECK (source IS NULL OR length(source) <= 50),
    reacted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    canceled_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (status = 'active' OR canceled_at IS NOT NULL),
    FOREIGN KEY (social_post_id) REFERENCES social_posts(social_post_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS post_favorites (
    favorite_id TEXT PRIMARY KEY,
    social_post_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'canceled')),
    source TEXT CHECK (source IS NULL OR length(source) <= 50),
    favorited_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    canceled_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (status = 'active' OR canceled_at IS NOT NULL),
    FOREIGN KEY (social_post_id) REFERENCES social_posts(social_post_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS post_comments (
    comment_id TEXT PRIMARY KEY,
    social_post_id TEXT NOT NULL,
    author_user_id TEXT NOT NULL,
    parent_comment_id TEXT,
    root_comment_id TEXT,
    content TEXT CHECK (content IS NULL OR length(content) <= 2000),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'deleted', 'hidden')),
    source TEXT CHECK (source IS NULL OR length(source) <= 50),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    CHECK (parent_comment_id IS NULL OR parent_comment_id <> comment_id),
    CHECK (root_comment_id IS NULL OR root_comment_id <> comment_id),
    CHECK (status <> 'active' OR content IS NOT NULL),
    CHECK (status = 'active' OR deleted_at IS NOT NULL),
    FOREIGN KEY (social_post_id) REFERENCES social_posts(social_post_id) ON DELETE CASCADE,
    FOREIGN KEY (author_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (parent_comment_id) REFERENCES post_comments(comment_id),
    FOREIGN KEY (root_comment_id) REFERENCES post_comments(comment_id)
);

CREATE TABLE IF NOT EXISTS user_post_views (
    user_post_view_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    social_post_id TEXT NOT NULL,
    first_viewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_viewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    first_view_source TEXT CHECK (first_view_source IS NULL OR length(first_view_source) <= 50),
    last_view_source TEXT CHECK (last_view_source IS NULL OR length(last_view_source) <= 50),
    view_count INTEGER NOT NULL DEFAULT 1 CHECK (view_count >= 1),
    total_dwell_time_ms INTEGER NOT NULL DEFAULT 0 CHECK (total_dwell_time_ms >= 0),
    last_dwell_time_ms INTEGER NOT NULL DEFAULT 0 CHECK (last_dwell_time_ms >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, social_post_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (social_post_id) REFERENCES social_posts(social_post_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_post_hides (
    user_post_hide_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    social_post_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'canceled')),
    source TEXT CHECK (source IS NULL OR length(source) <= 50),
    reason TEXT CHECK (reason IS NULL OR length(reason) <= 255),
    hidden_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    canceled_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (status = 'active' OR canceled_at IS NOT NULL),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (social_post_id) REFERENCES social_posts(social_post_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chat_conversations (
    conversation_id TEXT PRIMARY KEY,
    conversation_type TEXT NOT NULL
        CHECK (conversation_type IN ('direct', 'group')),
    group_type TEXT CHECK (
        group_type IN ('friend_group', 'lesson_group', 'training_group', 'coach_course_group', 'custom')
        OR group_type IS NULL
    ),
    direct_pair_key TEXT CHECK (direct_pair_key IS NULL OR length(direct_pair_key) <= 100),
    title TEXT CHECK (title IS NULL OR length(title) <= 120),
    avatar_path TEXT,
    created_by_user_id TEXT,
    context_type TEXT CHECK (
        context_type IN ('lesson', 'tennis_activity', 'video', 'social_post', 'custom')
        OR context_type IS NULL
    ),
    context_id TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived', 'deleted')),
    last_message_id TEXT,
    last_message_seq INTEGER NOT NULL DEFAULT 0 CHECK (last_message_seq >= 0),
    last_message_preview TEXT CHECK (last_message_preview IS NULL OR length(last_message_preview) <= 255),
    last_message_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    CHECK (
        (conversation_type = 'direct' AND direct_pair_key IS NOT NULL AND group_type IS NULL)
        OR (conversation_type = 'group' AND direct_pair_key IS NULL)
    ),
    CHECK ((context_type IS NULL AND context_id IS NULL) OR (context_type IS NOT NULL AND context_id IS NOT NULL)),
    FOREIGN KEY (created_by_user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS chat_messages (
    message_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    message_seq INTEGER NOT NULL CHECK (message_seq >= 1),
    sender_user_id TEXT,
    sender_type TEXT NOT NULL DEFAULT 'user'
        CHECK (sender_type IN ('user', 'system', 'ai', 'admin')),
    message_type TEXT NOT NULL DEFAULT 'text'
        CHECK (message_type IN (
            'text',
            'image',
            'video',
            'audio',
            'file',
            'post_share',
            'video_share',
            'activity_share',
            'lesson_share',
            'analysis_card',
            'system_event',
            'custom'
        )),
    text_content TEXT CHECK (text_content IS NULL OR length(text_content) <= 5000),
    payload_json TEXT,
    target_object_type TEXT CHECK (
        target_object_type IN ('user', 'video', 'social_post', 'tennis_activity', 'lesson', 'analysis', 'custom')
        OR target_object_type IS NULL
    ),
    target_object_id TEXT,
    context_object_type TEXT CHECK (
        context_object_type IN ('video', 'social_post', 'tennis_activity', 'lesson', 'custom')
        OR context_object_type IS NULL
    ),
    context_object_id TEXT,
    reply_to_message_id TEXT,
    client_message_id TEXT CHECK (client_message_id IS NULL OR length(client_message_id) <= 120),
    status TEXT NOT NULL DEFAULT 'sent'
        CHECK (status IN ('sent', 'revoked', 'deleted')),
    sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    CHECK (sender_type <> 'user' OR sender_user_id IS NOT NULL),
    CHECK (message_type <> 'text' OR text_content IS NOT NULL),
    CHECK ((target_object_type IS NULL AND target_object_id IS NULL) OR (target_object_type IS NOT NULL AND target_object_id IS NOT NULL)),
    CHECK ((context_object_type IS NULL AND context_object_id IS NULL) OR (context_object_type IS NOT NULL AND context_object_id IS NOT NULL)),
    FOREIGN KEY (conversation_id) REFERENCES chat_conversations(conversation_id) ON DELETE CASCADE,
    FOREIGN KEY (sender_user_id) REFERENCES users(user_id),
    FOREIGN KEY (reply_to_message_id) REFERENCES chat_messages(message_id)
);

CREATE TABLE IF NOT EXISTS post_shares (
    post_share_id TEXT PRIMARY KEY,
    social_post_id TEXT NOT NULL,
    shared_by_user_id TEXT NOT NULL,
    share_target_type TEXT NOT NULL
        CHECK (share_target_type IN ('conversation', 'user', 'external', 'copy_link')),
    target_user_id TEXT,
    conversation_id TEXT,
    message_id TEXT,
    channel TEXT CHECK (channel IS NULL OR length(channel) <= 50),
    payload_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        (
            share_target_type = 'conversation'
            AND conversation_id IS NOT NULL
            AND target_user_id IS NULL
        )
        OR (
            share_target_type = 'user'
            AND target_user_id IS NOT NULL
            AND conversation_id IS NULL
        )
        OR (
            share_target_type IN ('external', 'copy_link')
            AND target_user_id IS NULL
            AND conversation_id IS NULL
        )
    ),
    FOREIGN KEY (social_post_id) REFERENCES social_posts(social_post_id) ON DELETE CASCADE,
    FOREIGN KEY (shared_by_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (target_user_id) REFERENCES users(user_id),
    FOREIGN KEY (conversation_id) REFERENCES chat_conversations(conversation_id),
    FOREIGN KEY (message_id) REFERENCES chat_messages(message_id)
);

CREATE TABLE IF NOT EXISTS chat_conversation_members (
    conversation_member_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    member_role TEXT NOT NULL DEFAULT 'member'
        CHECK (member_role IN ('owner', 'admin', 'member', 'coach', 'student')),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'left', 'removed')),
    joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    left_at TEXT,
    last_read_message_id TEXT,
    last_read_message_seq INTEGER NOT NULL DEFAULT 0 CHECK (last_read_message_seq >= 0),
    last_read_at TEXT,
    unread_count INTEGER NOT NULL DEFAULT 0 CHECK (unread_count >= 0),
    muted_until TEXT,
    pinned_at TEXT,
    archived_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    CHECK (status = 'active' OR left_at IS NOT NULL),
    FOREIGN KEY (conversation_id) REFERENCES chat_conversations(conversation_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (last_read_message_id) REFERENCES chat_messages(message_id)
);

CREATE TABLE IF NOT EXISTS chat_message_requests (
    message_request_id TEXT PRIMARY KEY,
    requester_user_id TEXT NOT NULL,
    recipient_user_id TEXT NOT NULL,
    conversation_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'accepted', 'declined', 'blocked', 'canceled')),
    request_message TEXT CHECK (request_message IS NULL OR length(request_message) <= 500),
    source TEXT CHECK (source IS NULL OR length(source) <= 50),
    requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    responded_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (requester_user_id <> recipient_user_id),
    CHECK (status = 'pending' OR responded_at IS NOT NULL OR status = 'canceled'),
    FOREIGN KEY (requester_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (recipient_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (conversation_id) REFERENCES chat_conversations(conversation_id)
);

CREATE TABLE IF NOT EXISTS chat_message_attachments (
    attachment_id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL,
    attachment_type TEXT NOT NULL
        CHECK (attachment_type IN ('image', 'video', 'audio', 'file', 'object_card', 'data_card', 'link')),
    media_path TEXT,
    thumbnail_path TEXT,
    mime_type TEXT CHECK (mime_type IS NULL OR length(mime_type) <= 100),
    file_size_bytes INTEGER CHECK (file_size_bytes IS NULL OR file_size_bytes >= 0),
    duration_ms INTEGER CHECK (duration_ms IS NULL OR duration_ms >= 0),
    width_px INTEGER CHECK (width_px IS NULL OR width_px > 0),
    height_px INTEGER CHECK (height_px IS NULL OR height_px > 0),
    object_type TEXT CHECK (
        object_type IN ('user', 'video', 'social_post', 'tennis_activity', 'lesson', 'analysis', 'custom')
        OR object_type IS NULL
    ),
    object_id TEXT,
    payload_json TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0 CHECK (sort_order >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((object_type IS NULL AND object_id IS NULL) OR (object_type IS NOT NULL AND object_id IS NOT NULL)),
    FOREIGN KEY (message_id) REFERENCES chat_messages(message_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notification_events (
    notification_event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL
        CHECK (event_type IN (
            'follow',
            'post_like',
            'post_comment',
            'comment_reply',
            'mention',
            'video_shared',
            'ai_analysis_completed',
            'lesson_created',
            'lesson_updated',
            'coach_application_reviewed',
            'system_announcement',
            'custom'
        )),
    category TEXT NOT NULL DEFAULT 'system'
        CHECK (category IN ('interaction', 'system', 'ai', 'coach', 'lesson')),
    actor_user_id TEXT,
    object_type TEXT CHECK (
        object_type IN ('user', 'video', 'social_post', 'comment', 'tennis_activity', 'lesson', 'coach_application', 'analysis', 'custom')
        OR object_type IS NULL
    ),
    object_id TEXT,
    context_type TEXT CHECK (
        context_type IN ('video', 'social_post', 'tennis_activity', 'lesson', 'custom')
        OR context_type IS NULL
    ),
    context_id TEXT,
    title TEXT CHECK (title IS NULL OR length(title) <= 120),
    body TEXT CHECK (body IS NULL OR length(body) <= 500),
    deep_link TEXT CHECK (deep_link IS NULL OR length(deep_link) <= 255),
    payload_json TEXT,
    dedup_key TEXT CHECK (dedup_key IS NULL OR length(dedup_key) <= 160),
    aggregation_key TEXT CHECK (aggregation_key IS NULL OR length(aggregation_key) <= 160),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((object_type IS NULL AND object_id IS NULL) OR (object_type IS NOT NULL AND object_id IS NOT NULL)),
    CHECK ((context_type IS NULL AND context_id IS NULL) OR (context_type IS NOT NULL AND context_id IS NOT NULL)),
    FOREIGN KEY (actor_user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS user_notifications (
    user_notification_id TEXT PRIMARY KEY,
    notification_event_id TEXT NOT NULL,
    recipient_user_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'visible'
        CHECK (status IN ('visible', 'deleted')),
    priority TEXT NOT NULL DEFAULT 'normal'
        CHECK (priority IN ('normal', 'high')),
    delivered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    seen_at TEXT,
    read_at TEXT,
    dismissed_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    FOREIGN KEY (notification_event_id) REFERENCES notification_events(notification_event_id) ON DELETE CASCADE,
    FOREIGN KEY (recipient_user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_inbox_counters (
    user_id TEXT PRIMARY KEY,
    unread_direct_message_count INTEGER NOT NULL DEFAULT 0 CHECK (unread_direct_message_count >= 0),
    unread_group_message_count INTEGER NOT NULL DEFAULT 0 CHECK (unread_group_message_count >= 0),
    unread_notification_count INTEGER NOT NULL DEFAULT 0 CHECK (unread_notification_count >= 0),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS content_reports (
    content_report_id TEXT PRIMARY KEY,
    reporter_user_id TEXT NOT NULL,
    target_type TEXT NOT NULL
        CHECK (target_type IN ('user', 'social_post', 'post_comment', 'chat_message', 'chat_conversation', 'video')),
    target_id TEXT NOT NULL,
    reason_type TEXT NOT NULL
        CHECK (reason_type IN ('spam', 'harassment', 'inappropriate', 'fraud', 'privacy', 'other')),
    reason_text TEXT CHECK (reason_text IS NULL OR length(reason_text) <= 1000),
    source TEXT CHECK (source IS NULL OR length(source) <= 50),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'reviewing', 'resolved', 'rejected')),
    reviewer_user_id TEXT,
    reviewed_at TEXT,
    resolution_note TEXT CHECK (resolution_note IS NULL OR length(resolution_note) <= 1000),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (reporter_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (reviewer_user_id) REFERENCES users(user_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_follows_active_pair
    ON user_follows(follower_user_id, following_user_id)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_user_follows_follower_created
    ON user_follows(follower_user_id, followed_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_follows_following_created
    ON user_follows(following_user_id, followed_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_follows_mutual_lookup
    ON user_follows(following_user_id, follower_user_id, status);

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_blocks_active_pair
    ON user_blocks(blocker_user_id, blocked_user_id)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_user_blocks_blocked
    ON user_blocks(blocked_user_id, blocker_user_id)
    WHERE deleted_at IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_post_reactions_active_user_post_type
    ON post_reactions(user_id, social_post_id, reaction_type)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_post_reactions_post_active
    ON post_reactions(social_post_id, reaction_type, status, reacted_at DESC);

CREATE INDEX IF NOT EXISTS idx_post_reactions_user_created
    ON post_reactions(user_id, reacted_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_post_favorites_active_user_post
    ON post_favorites(user_id, social_post_id)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_post_favorites_post_active
    ON post_favorites(social_post_id, status, favorited_at DESC);

CREATE INDEX IF NOT EXISTS idx_post_favorites_user_created
    ON post_favorites(user_id, favorited_at DESC);

CREATE INDEX IF NOT EXISTS idx_post_comments_post_status_created
    ON post_comments(social_post_id, status, created_at ASC, comment_id ASC);

CREATE INDEX IF NOT EXISTS idx_post_comments_parent_created
    ON post_comments(parent_comment_id, created_at ASC, comment_id ASC);

CREATE INDEX IF NOT EXISTS idx_post_comments_root_created
    ON post_comments(root_comment_id, created_at ASC, comment_id ASC);

CREATE INDEX IF NOT EXISTS idx_post_comments_author_created
    ON post_comments(author_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_social_post_stats_updated
    ON social_post_stats(updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_post_views_user_last_viewed
    ON user_post_views(user_id, last_viewed_at DESC, social_post_id DESC);

CREATE INDEX IF NOT EXISTS idx_user_post_views_post
    ON user_post_views(social_post_id, last_viewed_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_post_hides_active_pair
    ON user_post_hides(user_id, social_post_id)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_user_post_hides_user_hidden
    ON user_post_hides(user_id, hidden_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_conversations_direct_pair
    ON chat_conversations(direct_pair_key)
    WHERE conversation_type = 'direct'
      AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_chat_conversations_context
    ON chat_conversations(context_type, context_id);

CREATE INDEX IF NOT EXISTS idx_chat_conversations_last_message
    ON chat_conversations(last_message_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_members_conversation_user_active
    ON chat_conversation_members(conversation_id, user_id)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_chat_members_user_status
    ON chat_conversation_members(user_id, status, pinned_at DESC, archived_at, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_chat_members_user_unread
    ON chat_conversation_members(user_id, unread_count);

CREATE INDEX IF NOT EXISTS idx_chat_members_conversation
    ON chat_conversation_members(conversation_id, status);

CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_message_requests_pending_pair
    ON chat_message_requests(requester_user_id, recipient_user_id)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_chat_message_requests_recipient_status
    ON chat_message_requests(recipient_user_id, status, requested_at DESC);

CREATE INDEX IF NOT EXISTS idx_chat_message_requests_requester_status
    ON chat_message_requests(requester_user_id, status, requested_at DESC);

CREATE INDEX IF NOT EXISTS idx_chat_message_requests_conversation
    ON chat_message_requests(conversation_id)
    WHERE conversation_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_messages_conversation_seq
    ON chat_messages(conversation_id, message_seq);

CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_messages_client_message
    ON chat_messages(sender_user_id, client_message_id)
    WHERE client_message_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_post_shares_post_created
    ON post_shares(social_post_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_post_shares_user_created
    ON post_shares(shared_by_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_post_shares_conversation
    ON post_shares(conversation_id, created_at DESC)
    WHERE conversation_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation_created
    ON chat_messages(conversation_id, message_seq DESC);

CREATE INDEX IF NOT EXISTS idx_chat_messages_sender_created
    ON chat_messages(sender_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_chat_messages_target_object
    ON chat_messages(target_object_type, target_object_id);

CREATE INDEX IF NOT EXISTS idx_chat_attachments_message_sort
    ON chat_message_attachments(message_id, sort_order);

CREATE INDEX IF NOT EXISTS idx_chat_attachments_object
    ON chat_message_attachments(object_type, object_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_notification_events_dedup
    ON notification_events(dedup_key)
    WHERE dedup_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_notification_events_object
    ON notification_events(object_type, object_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_notification_events_actor_created
    ON notification_events(actor_user_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_notifications_recipient_event
    ON user_notifications(recipient_user_id, notification_event_id);

CREATE INDEX IF NOT EXISTS idx_user_notifications_recipient_unread
    ON user_notifications(recipient_user_id, read_at, created_at DESC)
    WHERE status = 'visible' AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_user_notifications_recipient_created
    ON user_notifications(recipient_user_id, created_at DESC)
    WHERE status = 'visible' AND deleted_at IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_content_reports_active_reporter_target
    ON content_reports(reporter_user_id, target_type, target_id)
    WHERE status IN ('pending', 'reviewing');

CREATE INDEX IF NOT EXISTS idx_content_reports_target_created
    ON content_reports(target_type, target_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_content_reports_status_created
    ON content_reports(status, created_at DESC);

CREATE TRIGGER IF NOT EXISTS trg_user_follows_set_updated_at
AFTER UPDATE ON user_follows
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE user_follows
    SET updated_at = CURRENT_TIMESTAMP
    WHERE follow_id = OLD.follow_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_user_social_stats_set_updated_at
AFTER UPDATE ON user_social_stats
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE user_social_stats
    SET updated_at = CURRENT_TIMESTAMP
    WHERE user_id = OLD.user_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_user_blocks_set_updated_at
AFTER UPDATE ON user_blocks
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE user_blocks
    SET updated_at = CURRENT_TIMESTAMP
    WHERE user_block_id = OLD.user_block_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_user_privacy_settings_set_updated_at
AFTER UPDATE ON user_privacy_settings
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE user_privacy_settings
    SET updated_at = CURRENT_TIMESTAMP
    WHERE user_id = OLD.user_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_social_post_stats_set_updated_at
AFTER UPDATE ON social_post_stats
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE social_post_stats
    SET updated_at = CURRENT_TIMESTAMP
    WHERE social_post_id = OLD.social_post_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_post_reactions_set_updated_at
AFTER UPDATE ON post_reactions
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE post_reactions
    SET updated_at = CURRENT_TIMESTAMP
    WHERE reaction_id = OLD.reaction_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_post_favorites_set_updated_at
AFTER UPDATE ON post_favorites
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE post_favorites
    SET updated_at = CURRENT_TIMESTAMP
    WHERE favorite_id = OLD.favorite_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_post_comments_set_updated_at
AFTER UPDATE ON post_comments
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE post_comments
    SET updated_at = CURRENT_TIMESTAMP
    WHERE comment_id = OLD.comment_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_user_post_views_set_updated_at
AFTER UPDATE ON user_post_views
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE user_post_views
    SET updated_at = CURRENT_TIMESTAMP
    WHERE user_post_view_id = OLD.user_post_view_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_user_post_hides_set_updated_at
AFTER UPDATE ON user_post_hides
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE user_post_hides
    SET updated_at = CURRENT_TIMESTAMP
    WHERE user_post_hide_id = OLD.user_post_hide_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_chat_conversations_set_updated_at
AFTER UPDATE ON chat_conversations
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE chat_conversations
    SET updated_at = CURRENT_TIMESTAMP
    WHERE conversation_id = OLD.conversation_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_chat_members_set_updated_at
AFTER UPDATE ON chat_conversation_members
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE chat_conversation_members
    SET updated_at = CURRENT_TIMESTAMP
    WHERE conversation_member_id = OLD.conversation_member_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_chat_message_requests_set_updated_at
AFTER UPDATE ON chat_message_requests
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE chat_message_requests
    SET updated_at = CURRENT_TIMESTAMP
    WHERE message_request_id = OLD.message_request_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_chat_messages_set_updated_at
AFTER UPDATE ON chat_messages
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE chat_messages
    SET updated_at = CURRENT_TIMESTAMP
    WHERE message_id = OLD.message_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_user_notifications_set_updated_at
AFTER UPDATE ON user_notifications
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE user_notifications
    SET updated_at = CURRENT_TIMESTAMP
    WHERE user_notification_id = OLD.user_notification_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_user_inbox_counters_set_updated_at
AFTER UPDATE ON user_inbox_counters
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE user_inbox_counters
    SET updated_at = CURRENT_TIMESTAMP
    WHERE user_id = OLD.user_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_content_reports_set_updated_at
AFTER UPDATE ON content_reports
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE content_reports
    SET updated_at = CURRENT_TIMESTAMP
    WHERE content_report_id = OLD.content_report_id;
END;
