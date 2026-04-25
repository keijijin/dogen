package jp.dogen.chat.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.util.List;
import java.util.UUID;

@JsonIgnoreProperties(ignoreUnknown = true)
public class ChatRequest {

    /** 省略時は新規セッションとして扱い、応答ヘッダ X-Session-Id で返す */
    public UUID sessionId;

    public String volumeScope;
    public String model;
    public List<ChatMessageDto> messages;
}
