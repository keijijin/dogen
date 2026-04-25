package jp.dogen.chat.dto;

import java.util.UUID;

/** セッション一覧用（GET /api/v1/sessions） */
public class SessionSummaryDto {

    public UUID id;
    public String createdAt;
    public String volumeScope;
    public int messageCount;
    public String preview;
}
