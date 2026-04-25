package jp.dogen.chat.service;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import jakarta.ws.rs.WebApplicationException;
import jakarta.ws.rs.core.Response;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.util.UUID;
import javax.sql.DataSource;
import jp.dogen.chat.dto.FeedbackRequest;

@ApplicationScoped
public class FeedbackService {

    @Inject
    DataSource dataSource;

    public void record(FeedbackRequest req) {
        if (req.messageId == null) {
            throw new WebApplicationException(
                    Response.status(Response.Status.BAD_REQUEST).entity("{\"error\":\"messageId_required\"}").build());
        }
        try (Connection conn = dataSource.getConnection()) {
            String sql = "INSERT INTO user_feedback (id, message_id, rating, comment) VALUES (?, ?, ?, ?)";
            try (PreparedStatement ps = conn.prepareStatement(sql)) {
                ps.setObject(1, UUID.randomUUID());
                ps.setObject(2, req.messageId);
                ps.setShort(3, req.rating);
                ps.setString(4, req.comment);
                ps.executeUpdate();
            }
        } catch (Exception e) {
            throw new WebApplicationException(
                    e,
                    Response.status(Response.Status.INTERNAL_SERVER_ERROR)
                            .entity("{\"error\":\"feedback_failed\"}")
                            .build());
        }
    }
}
