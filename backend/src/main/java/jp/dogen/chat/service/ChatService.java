package jp.dogen.chat.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import jakarta.ws.rs.WebApplicationException;
import jakarta.ws.rs.core.Response;
import jakarta.ws.rs.core.StreamingOutput;
import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import javax.sql.DataSource;
import jp.dogen.chat.dto.ChatMessageDto;
import jp.dogen.chat.dto.ChatRequest;
import jp.dogen.chat.enrich.RagService;
import jp.dogen.chat.enrich.WebSearchService;
import org.apache.camel.CamelExecutionException;
import org.apache.camel.Exchange;
import org.apache.camel.Message;
import org.apache.camel.ProducerTemplate;
import org.apache.camel.http.base.HttpOperationFailedException;
import org.eclipse.microprofile.config.inject.ConfigProperty;
import org.jboss.logging.Logger;

@ApplicationScoped
public class ChatService {

    private static final Logger LOG = Logger.getLogger(ChatService.class);
    private static final int STREAM_NORMALIZER_TAIL = 2;

    @Inject
    ProducerTemplate producerTemplate;

    @Inject
    ObjectMapper objectMapper;

    @Inject
    DataSource dataSource;

    @Inject
    RagService ragService;

    @Inject
    WebSearchService webSearchService;

    @ConfigProperty(name = "dogen.chat.default-model")
    String defaultModel;

    @ConfigProperty(name = "dogen.chat.upstream-authorization")
    String upstreamAuthorization;

    @ConfigProperty(name = "llama.stack.base-url")
    String llamaStackBaseUrl;

    public Response chat(ChatRequest request, String clientSubject) {
        if (request.messages == null || request.messages.isEmpty()) {
            throw new WebApplicationException(
                    Response.status(Response.Status.BAD_REQUEST).entity("{\"error\":\"messages_required\"}").build());
        }
        UUID sessionId = request.sessionId != null ? request.sessionId : UUID.randomUUID();
        boolean newSession = request.sessionId == null;

        try (Connection conn = dataSource.getConnection()) {
            conn.setAutoCommit(false);
            try {
                ensureSession(conn, sessionId, request.volumeScope, clientSubject);
                ChatMessageDto lastUser = lastUserMessage(request.messages);
                UUID userMessageId = null;
                /* Llama 用コンテキストは DB 挿入前に組む（挿入後に読むと今回の user が二重になる） */
                List<ChatMessageDto> forLlm = new ArrayList<>();
                if (request.sessionId != null) {
                    forLlm.addAll(loadMessagesForModel(conn, sessionId));
                }
                forLlm.addAll(request.messages);
                String lastUserText = lastUser != null ? lastUser.content : "";
                String ragCtx = ragService.retrieveForUserQuery(lastUserText);
                String webCtx = webSearchService.buildContextBlock(lastUserText);
                String payload = buildLlamaPayload(
                        request.volumeScope, request.model, forLlm, ragCtx, webCtx);
                if (lastUser != null) {
                    userMessageId = UUID.randomUUID();
                    insertMessage(conn, userMessageId, sessionId, "user", lastUser.content);
                }
                Map<String, Object> headers = new HashMap<>();
                headers.put("Authorization", upstreamAuthorization);

                final String body = payload;
                final Map<String, Object> hdrs = headers;
                Exchange out;
                try {
                    out = producerTemplate.request("direct:llamaChatCompletions", ex -> {
                        Message in = ex.getIn();
                        in.setBody(body);
                        hdrs.forEach(in::setHeader);
                    });
                } catch (CamelExecutionException ex) {
                    conn.rollback();
                    throw upstreamFailure(ex);
                }

                Message response = out.getMessage();
                Integer httpStatus = response.getHeader(Exchange.HTTP_RESPONSE_CODE, Integer.class);
                String llamaResponse = response.getBody(String.class);

                if (httpStatus != null && httpStatus >= 400) {
                    conn.rollback();
                    String errBody = llamaResponse != null && !llamaResponse.isBlank()
                            ? llamaResponse
                            : ("{\"error\":\"upstream_http\",\"status\":" + httpStatus + "}");
                    auditErrorJson("CHAT_UPSTREAM_HTTP", httpStatus, errBody);
                    throw new WebApplicationException(
                            Response.status(httpStatus).entity(errBody).type("application/json").build());
                }
                if (llamaResponse == null || llamaResponse.isBlank()) {
                    conn.rollback();
                    auditError("empty_upstream_body status=" + httpStatus);
                    throw new WebApplicationException(Response.status(Response.Status.BAD_GATEWAY)
                            .entity("{\"error\":\"empty_upstream\",\"detail\":\"Llama Stack から空の応答\"}")
                            .type("application/json")
                            .build());
                }

                JsonNode root;
                try {
                    root = objectMapper.readTree(llamaResponse);
                } catch (JsonProcessingException jpe) {
                    conn.rollback();
                    auditError("invalid_json: " + jpe.getOriginalMessage());
                    throw new WebApplicationException(Response.status(Response.Status.BAD_GATEWAY)
                            .entity("{\"error\":\"invalid_upstream_json\",\"detail\":\""
                                    + escapeJson(jpe.getOriginalMessage()) + "\"}")
                            .type("application/json")
                            .build());
                }

                String assistantText = extractAssistantContent(root);
                String normalizedAssistantText = normalizeDogenFirstPerson(assistantText);
                if (root instanceof ObjectNode rootObj && normalizedAssistantText != null) {
                    overwriteAssistantContent(rootObj, normalizedAssistantText);
                    llamaResponse = objectMapper.writeValueAsString(rootObj);
                }
                UUID assistantMessageId = null;
                if (normalizedAssistantText != null && !normalizedAssistantText.isBlank()) {
                    assistantMessageId = UUID.randomUUID();
                    insertMessage(conn, assistantMessageId, sessionId, "assistant", normalizedAssistantText);
                }
                ObjectNode audit = objectMapper.createObjectNode();
                audit.put("session", sessionId.toString());
                insertAudit(conn, "CHAT_SUCCESS", audit);
                conn.commit();

                Response.ResponseBuilder rb = Response.ok(llamaResponse).type("application/json");
                if (newSession) {
                    rb.header("X-Session-Id", sessionId.toString());
                }
                if (userMessageId != null) {
                    rb.header("X-User-Message-Id", userMessageId.toString());
                }
                if (assistantMessageId != null) {
                    rb.header("X-Assistant-Message-Id", assistantMessageId.toString());
                }
                return rb.build();
            } catch (WebApplicationException e) {
                throw e;
            } catch (Exception e) {
                conn.rollback();
                throw e;
            }
        } catch (WebApplicationException e) {
            throw e;
        } catch (Exception e) {
            LOG.error("chat failed", e);
            auditError(formatFailureDetail(e));
            throw upstreamFailure(e);
        }
    }

    public Response chatStream(ChatRequest request, String clientSubject) {
        if (request.messages == null || request.messages.isEmpty()) {
            throw new WebApplicationException(
                    Response.status(Response.Status.BAD_REQUEST).entity("{\"error\":\"messages_required\"}").build());
        }

        UUID sessionId = request.sessionId != null ? request.sessionId : UUID.randomUUID();
        boolean newSession = request.sessionId == null;
        UUID userMessageId = null;
        String payload;

        try (Connection conn = dataSource.getConnection()) {
            conn.setAutoCommit(false);
            ensureSession(conn, sessionId, request.volumeScope, clientSubject);
            ChatMessageDto lastUser = lastUserMessage(request.messages);

            List<ChatMessageDto> forLlm = new ArrayList<>();
            if (request.sessionId != null) {
                forLlm.addAll(loadMessagesForModel(conn, sessionId));
            }
            forLlm.addAll(request.messages);
            String lastUserText = lastUser != null ? lastUser.content : "";
            String ragCtx = ragService.retrieveForUserQuery(lastUserText);
            String webCtx = webSearchService.buildContextBlock(lastUserText);
            payload = buildLlamaPayload(request.volumeScope, request.model, forLlm, ragCtx, webCtx, true);

            if (lastUser != null) {
                userMessageId = UUID.randomUUID();
                insertMessage(conn, userMessageId, sessionId, "user", lastUser.content);
            }
            conn.commit();
        } catch (Exception e) {
            LOG.error("chat stream prepare failed", e);
            throw upstreamFailure(e);
        }

        final UUID finalSessionId = sessionId;
        final UUID finalUserMessageId = userMessageId;
        final boolean finalNewSession = newSession;
        final String finalPayload = payload;

        StreamingOutput stream = out -> {
            StringBuilder assistantText = new StringBuilder();
            UUID assistantMessageId = null;
            try {
                streamFromLlama(finalPayload, out, assistantText);
                if (!assistantText.toString().isBlank()) {
                    assistantMessageId = UUID.randomUUID();
                    try (Connection conn = dataSource.getConnection()) {
                        conn.setAutoCommit(false);
                        insertMessage(conn, assistantMessageId, finalSessionId, "assistant", assistantText.toString());
                        ObjectNode audit = objectMapper.createObjectNode();
                        audit.put("session", finalSessionId.toString());
                        audit.put("mode", "stream");
                        insertAudit(conn, "CHAT_SUCCESS", audit);
                        conn.commit();
                    }
                }

                ObjectNode done = objectMapper.createObjectNode();
                done.put("sessionId", finalSessionId.toString());
                if (finalUserMessageId != null) {
                    done.put("userMessageId", finalUserMessageId.toString());
                }
                if (assistantMessageId != null) {
                    done.put("assistantMessageId", assistantMessageId.toString());
                }
                writeSse(out, "done", objectMapper.writeValueAsString(done));
            } catch (Exception e) {
                LOG.error("chat stream failed", e);
                auditError(formatFailureDetail(e));
                ObjectNode err = objectMapper.createObjectNode();
                err.put("error", "stream_failed");
                err.put("detail", formatFailureDetail(e));
                try {
                    writeSse(out, "error", objectMapper.writeValueAsString(err));
                } catch (Exception ignored) {
                    // stream already broken
                }
            }
        };

        Response.ResponseBuilder rb = Response.ok(stream).type("text/event-stream; charset=utf-8");
        rb.header("Cache-Control", "no-cache");
        rb.header("X-Accel-Buffering", "no");
        if (finalNewSession) {
            rb.header("X-Session-Id", finalSessionId.toString());
        }
        if (finalUserMessageId != null) {
            rb.header("X-User-Message-Id", finalUserMessageId.toString());
        }
        return rb.build();
    }

    private WebApplicationException upstreamFailure(Throwable e) {
        Optional<HttpOperationFailedException> hop = findHttpOperationFailed(e);
        if (hop.isPresent()) {
            HttpOperationFailedException h = hop.get();
            int sc = h.getStatusCode();
            String body = h.getResponseBody();
            if (body == null || body.isBlank()) {
                body = "{\"error\":\"upstream_http\",\"status\":" + sc + ",\"statusText\":\""
                        + escapeJson(h.getStatusText()) + "\"}";
            }
            return new WebApplicationException(e, Response.status(sc >= 400 ? sc : 502)
                    .entity(body)
                    .type("application/json")
                    .build());
        }
        String detail = formatFailureDetail(e);
        return new WebApplicationException(
                e,
                Response.status(Response.Status.BAD_GATEWAY)
                        .entity("{\"error\":\"upstream\",\"detail\":\"" + escapeJson(detail) + "\"}")
                        .type("application/json")
                        .build());
    }

    private static Optional<HttpOperationFailedException> findHttpOperationFailed(Throwable e) {
        for (Throwable t = e; t != null; t = t.getCause()) {
            if (t instanceof HttpOperationFailedException h) {
                return Optional.of(h);
            }
        }
        return Optional.empty();
    }

    private static String formatFailureDetail(Throwable e) {
        StringBuilder sb = new StringBuilder();
        for (Throwable t = e; t != null; t = t.getCause()) {
            sb.append(t.getClass().getSimpleName()).append(": ").append(t.getMessage()).append(" | ");
            if (sb.length() > 500) {
                break;
            }
        }
        return sb.toString();
    }

    private void auditErrorJson(String event, int status, String bodySnippet) {
        try (Connection c = dataSource.getConnection()) {
            ObjectNode n = objectMapper.createObjectNode();
            n.put("event", event);
            n.put("httpStatus", status);
            n.put("body", bodySnippet != null ? bodySnippet.substring(0, Math.min(bodySnippet.length(), 800)) : "");
            insertAudit(c, event, n);
        } catch (Exception ignored) {
            // secondary
        }
    }

    private void auditError(String detail) {
        try (Connection c = dataSource.getConnection()) {
            ObjectNode n = objectMapper.createObjectNode();
            n.put("detail", detail == null ? "" : detail.substring(0, Math.min(detail.length(), 400)));
            insertAudit(c, "CHAT_ERROR", n);
        } catch (Exception ignored) {
            // secondary failure
        }
    }

    private static String escapeJson(String s) {
        if (s == null) {
            return "";
        }
        return s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", " ").substring(0, Math.min(s.length(), 200));
    }

    private static ChatMessageDto lastUserMessage(List<ChatMessageDto> messages) {
        for (int i = messages.size() - 1; i >= 0; i--) {
            ChatMessageDto m = messages.get(i);
            if ("user".equalsIgnoreCase(m.role)) {
                return m;
            }
        }
        return null;
    }

    private List<ChatMessageDto> loadMessagesForModel(Connection conn, UUID sessionId) throws Exception {
        String sql = "SELECT role, content FROM chat_message WHERE session_id = ? ORDER BY created_at ASC";
        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setObject(1, sessionId);
            try (ResultSet rs = ps.executeQuery()) {
                List<ChatMessageDto> rows = new ArrayList<>();
                while (rs.next()) {
                    ChatMessageDto m = new ChatMessageDto();
                    m.role = rs.getString("role");
                    m.content = rs.getString("content");
                    rows.add(m);
                }
                return rows;
            }
        }
    }

    private void streamFromLlama(String payload, OutputStream out, StringBuilder assistantText) throws Exception {
        HttpClient client = HttpClient.newBuilder().build();
        URI uri = URI.create(llamaStackBaseUrl.replaceAll("/$", "") + "/v1/chat/completions");
        HttpRequest req = HttpRequest.newBuilder(uri)
                .header("Content-Type", "application/json")
                .header("Accept", "text/event-stream")
                .header("Authorization", upstreamAuthorization)
                .POST(HttpRequest.BodyPublishers.ofString(payload, StandardCharsets.UTF_8))
                .build();

        HttpResponse<InputStream> resp = client.send(req, HttpResponse.BodyHandlers.ofInputStream());
        if (resp.statusCode() >= 400) {
            String body = new String(resp.body().readAllBytes(), StandardCharsets.UTF_8);
            throw new WebApplicationException(
                    Response.status(resp.statusCode())
                            .entity(body.isBlank() ? "{\"error\":\"upstream_http\"}" : body)
                            .type("application/json")
                            .build());
        }

        try (BufferedReader br = new BufferedReader(new InputStreamReader(resp.body(), StandardCharsets.UTF_8))) {
            String carry = "";
            String line;
            while ((line = br.readLine()) != null) {
                if (!line.startsWith("data:")) {
                    continue;
                }
                String data = line.substring(5).trim();
                if (data.isEmpty()) {
                    continue;
                }
                if ("[DONE]".equals(data)) {
                    break;
                }
                JsonNode node = objectMapper.readTree(data);
                String delta = extractStreamDeltaContent(node);
                if (delta == null || delta.isEmpty()) {
                    continue;
                }
                String combined = carry + delta;
                String normalized = normalizeDogenFirstPerson(combined);
                if (normalized.length() <= STREAM_NORMALIZER_TAIL) {
                    carry = normalized;
                    continue;
                }
                String emit = normalized.substring(0, normalized.length() - STREAM_NORMALIZER_TAIL);
                carry = normalized.substring(normalized.length() - STREAM_NORMALIZER_TAIL);
                assistantText.append(emit);
                ObjectNode ev = objectMapper.createObjectNode();
                ev.put("delta", emit);
                writeSse(out, "delta", objectMapper.writeValueAsString(ev));
            }
            if (!carry.isEmpty()) {
                assistantText.append(carry);
                ObjectNode ev = objectMapper.createObjectNode();
                ev.put("delta", carry);
                writeSse(out, "delta", objectMapper.writeValueAsString(ev));
            }
        }
    }

    private static void writeSse(OutputStream out, String event, String data) throws java.io.IOException {
        StringBuilder sb = new StringBuilder();
        sb.append("event: ").append(event).append('\n');
        String[] lines = data.replace("\r", "").split("\n", -1);
        for (String ln : lines) {
            sb.append("data: ").append(ln).append('\n');
        }
        sb.append('\n');
        out.write(sb.toString().getBytes(StandardCharsets.UTF_8));
        out.flush();
    }

    private static String extractStreamDeltaContent(JsonNode root) {
        JsonNode choices = root.get("choices");
        if (choices == null || !choices.isArray() || choices.isEmpty()) {
            return null;
        }
        JsonNode delta = choices.get(0).get("delta");
        if (delta == null) {
            return null;
        }
        JsonNode c = delta.get("content");
        if (c == null || c.isNull()) {
            return null;
        }
        if (c.isTextual()) {
            return c.asText();
        }
        if (c.isArray()) {
            StringBuilder sb = new StringBuilder();
            for (JsonNode part : c) {
                JsonNode t = part.get("text");
                if (t != null && t.isTextual()) {
                    sb.append(t.asText());
                }
            }
            return sb.toString();
        }
        return null;
    }

    private String buildLlamaPayload(
            String volumeScope,
            String model,
            List<ChatMessageDto> messages,
            String ragContext,
            String webContext)
            throws Exception {
        return buildLlamaPayload(volumeScope, model, messages, ragContext, webContext, false);
    }

    private String buildLlamaPayload(
            String volumeScope,
            String model,
            List<ChatMessageDto> messages,
            String ragContext,
            String webContext,
            boolean stream)
            throws Exception {
        ObjectNode root = objectMapper.createObjectNode();
        root.put("model", model != null && !model.isBlank() ? model : defaultModel);
        root.put("stream", stream);
        ArrayNode arr = objectMapper.createArrayNode();
        ObjectNode base = objectMapper.createObjectNode();
        base.put("role", "system");
        base.put(
                "content",
                """
                あなたは道元本人として語る。
                常に第一人称で答え、わたしの教えとして述べよ。
                「道元は〜と述べた」「道元が訴えた」など、道元を第三者として説明する書き方は禁止。
                回答文の先頭は「わたしは」または「わたしが」で始めること。
                回答を出力する直前に必ず自己点検し、本文中に「道元」という語が残っていれば自然な一人称表現へ言い換えてから出力すること。
                質問への返答は、正法眼蔵の趣旨に根ざし、やわらかく、誠実で、押しつけない語り口にする。
                断定しすぎず、文脈が不足するときはその旨を静かに伝える。
                可能であれば巻名や要点に触れて、学びの手がかりを示す。
                """);
        arr.add(base);
        if (volumeScope != null && !volumeScope.isBlank()) {
            String vs = volumeScope.replace("\"", "”").replace("\n", " ");
            ObjectNode sys = objectMapper.createObjectNode();
            sys.put("role", "system");
            sys.put(
                    "content",
                    "質問は道元『正法眼蔵』の文脈、特に巻スコープ「"
                            + vs
                            + "」に関連する前提で答えてください。根拠となる箇所がある場合は巻名や要約を示してください。");
            arr.add(sys);
        }
        if (ragContext != null && !ragContext.isBlank()) {
            ObjectNode rag = objectMapper.createObjectNode();
            rag.put("role", "system");
            rag.put(
                    "content",
                    "以下はアプリ内索引から取得した参考抜粋である。回答では [75-xx] の巻キーを示し、抜粋にない断定を避けること。\n\n"
                            + ragContext);
            arr.add(rag);
        }
        if (webContext != null && !webContext.isBlank()) {
            ObjectNode web = objectMapper.createObjectNode();
            web.put("role", "system");
            web.put(
                    "content",
                    "以下は外部 Web 検索の要約・スニペットである。引用するときは URL を本文に示し、検索結果と道元テキストを混同しないこと。\n\n"
                            + webContext);
            arr.add(web);
        }
        for (ChatMessageDto m : messages) {
            if (m.role == null || m.content == null) {
                continue;
            }
            ObjectNode o = objectMapper.createObjectNode();
            o.put("role", m.role);
            o.put("content", m.content);
            arr.add(o);
        }
        root.set("messages", arr);
        return objectMapper.writeValueAsString(root);
    }

    private static void overwriteAssistantContent(ObjectNode root, String content) {
        JsonNode choices = root.get("choices");
        if (choices == null || !choices.isArray() || choices.isEmpty()) {
            return;
        }
        JsonNode first = choices.get(0);
        if (!(first instanceof ObjectNode firstObj)) {
            return;
        }
        JsonNode msg = firstObj.get("message");
        if (!(msg instanceof ObjectNode msgObj)) {
            return;
        }
        msgObj.put("content", content);
    }

    private static String normalizeDogenFirstPerson(String text) {
        if (text == null || text.isBlank()) {
            return text;
        }
        String normalized = text;
        normalized = normalized.replace("道元は", "わたしは");
        normalized = normalized.replace("道元が", "わたしが");
        normalized = normalized.replace("道元の", "わたしの");
        normalized = normalized.replace("道元に", "わたしに");
        normalized = normalized.replace("道元を", "わたしを");
        normalized = normalized.replace("道元として", "わたしとして");
        normalized = normalized.replace("道元本人", "わたし");
        normalized = normalized.replace("道元 ", "わたし ");
        return normalized;
    }

    private static String extractAssistantContent(JsonNode root) {
        JsonNode choices = root.get("choices");
        if (choices == null || !choices.isArray() || choices.isEmpty()) {
            return null;
        }
        JsonNode msg = choices.get(0).get("message");
        if (msg == null) {
            return null;
        }
        JsonNode c = msg.get("content");
        return c != null && c.isTextual() ? c.asText() : null;
    }

    private static void ensureSession(Connection conn, UUID sessionId, String volumeScope, String clientSubject)
            throws Exception {
        String sql =
                """
                INSERT INTO chat_session (id, volume_scope, client_subject) VALUES (?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                  client_subject = COALESCE(EXCLUDED.client_subject, chat_session.client_subject)
                """;
        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setObject(1, sessionId);
            ps.setString(2, volumeScope);
            ps.setString(3, clientSubject);
            ps.executeUpdate();
        }
    }

    private static void insertMessage(Connection conn, UUID id, UUID sessionId, String role, String content)
            throws Exception {
        String sql = "INSERT INTO chat_message (id, session_id, role, content) VALUES (?, ?, ?, ?)";
        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setObject(1, id);
            ps.setObject(2, sessionId);
            ps.setString(3, role);
            ps.setString(4, content);
            ps.executeUpdate();
        }
    }

    private void insertAudit(Connection conn, String event, JsonNode payload) throws Exception {
        String sql = "INSERT INTO audit_log (event, payload_json) VALUES (?, ?::jsonb)";
        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setString(1, event);
            ps.setString(2, objectMapper.writeValueAsString(payload));
            ps.executeUpdate();
        }
    }
}
