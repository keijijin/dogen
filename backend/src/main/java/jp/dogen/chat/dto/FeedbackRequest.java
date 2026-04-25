package jp.dogen.chat.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.util.UUID;

@JsonIgnoreProperties(ignoreUnknown = true)
public class FeedbackRequest {

    public UUID messageId;
    public short rating;
    public String comment;
}
