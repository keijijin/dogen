package jp.dogen.chat.service;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import jakarta.ws.rs.NotFoundException;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Timestamp;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import javax.sql.DataSource;
import jp.dogen.chat.dto.ChatMessageRowDto;
import jp.dogen.chat.dto.SessionSummaryDto;

@ApplicationScoped
public class SessionService {

    private static final int DEFAULT_LIMIT = 80;

    @Inject
    DataSource dataSource;

    public List<SessionSummaryDto> listRecent(int limit, String clientSubject) throws Exception {
        int cap = limit > 0 && limit <= 200 ? limit : DEFAULT_LIMIT;
        boolean anon = clientSubject == null || clientSubject.isBlank();
        String sql =
                anon
                        ? """
                SELECT s.id, s.created_at, s.volume_scope,
                       (SELECT COUNT(*)::int FROM chat_message m WHERE m.session_id = s.id) AS msg_count,
                       (SELECT m.content FROM chat_message m WHERE m.session_id = s.id
                        ORDER BY m.created_at DESC LIMIT 1) AS last_content
                FROM chat_session s
                WHERE s.client_subject IS NULL
                ORDER BY COALESCE(
                    (SELECT MAX(m.created_at) FROM chat_message m WHERE m.session_id = s.id),
                    s.created_at
                ) DESC
                LIMIT ?
                """
                        : """
                SELECT s.id, s.created_at, s.volume_scope,
                       (SELECT COUNT(*)::int FROM chat_message m WHERE m.session_id = s.id) AS msg_count,
                       (SELECT m.content FROM chat_message m WHERE m.session_id = s.id
                        ORDER BY m.created_at DESC LIMIT 1) AS last_content
                FROM chat_session s
                WHERE s.client_subject = ?
                ORDER BY COALESCE(
                    (SELECT MAX(m.created_at) FROM chat_message m WHERE m.session_id = s.id),
                    s.created_at
                ) DESC
                LIMIT ?
                """;
        try (Connection conn = dataSource.getConnection();
                PreparedStatement ps = conn.prepareStatement(sql)) {
            if (anon) {
                ps.setInt(1, cap);
            } else {
                ps.setString(1, clientSubject);
                ps.setInt(2, cap);
            }
            try (ResultSet rs = ps.executeQuery()) {
                List<SessionSummaryDto> out = new ArrayList<>();
                while (rs.next()) {
                    SessionSummaryDto row = new SessionSummaryDto();
                    row.id = rs.getObject("id", UUID.class);
                    row.createdAt = toIso(rs.getTimestamp("created_at"));
                    row.volumeScope = rs.getString("volume_scope");
                    row.messageCount = rs.getInt("msg_count");
                    String last = rs.getString("last_content");
                    row.preview = summarize(last);
                    out.add(row);
                }
                return out;
            }
        }
    }

    public List<ChatMessageRowDto> listMessages(UUID sessionId, String clientSubject) throws Exception {
        if (!sessionOwned(sessionId, clientSubject)) {
            throw new NotFoundException("session not found");
        }
        String sql =
                "SELECT id, role, content, created_at FROM chat_message WHERE session_id = ? ORDER BY created_at ASC";
        try (Connection conn = dataSource.getConnection();
                PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setObject(1, sessionId);
            try (ResultSet rs = ps.executeQuery()) {
                List<ChatMessageRowDto> out = new ArrayList<>();
                while (rs.next()) {
                    ChatMessageRowDto m = new ChatMessageRowDto();
                    m.id = rs.getObject("id", UUID.class);
                    m.role = rs.getString("role");
                    m.content = rs.getString("content");
                    m.createdAt = toIso(rs.getTimestamp("created_at"));
                    out.add(m);
                }
                return out;
            }
        }
    }

    private boolean sessionOwned(UUID id, String clientSubject) throws Exception {
        boolean anon = clientSubject == null || clientSubject.isBlank();
        String sql =
                anon
                        ? "SELECT 1 FROM chat_session WHERE id = ? AND client_subject IS NULL"
                        : "SELECT 1 FROM chat_session WHERE id = ? AND client_subject = ?";
        try (Connection conn = dataSource.getConnection();
                PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setObject(1, id);
            if (!anon) {
                ps.setString(2, clientSubject);
            }
            try (ResultSet rs = ps.executeQuery()) {
                return rs.next();
            }
        }
    }

    private static String toIso(Timestamp ts) {
        if (ts == null) {
            return null;
        }
        return ts.toInstant().toString();
    }

    private static String summarize(String s) {
        if (s == null || s.isBlank()) {
            return "";
        }
        String t = s.replace('\n', ' ').trim();
        return t.length() > 120 ? t.substring(0, 117) + "…" : t;
    }
}
