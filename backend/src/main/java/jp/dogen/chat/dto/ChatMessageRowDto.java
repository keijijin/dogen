package jp.dogen.chat.dto;

import java.util.UUID;

/** 永続化済みメッセージ行（GET /api/v1/sessions/{id}/messages） */
public class ChatMessageRowDto {

    public UUID id;
    public String role;
    public String content;
    public String createdAt;
}
