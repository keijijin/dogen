package jp.dogen.chat.enrich;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import java.util.ArrayList;
import java.util.List;
import org.apache.camel.CamelExecutionException;
import org.apache.camel.Exchange;
import org.apache.camel.Message;
import org.apache.camel.ProducerTemplate;
import org.eclipse.microprofile.config.inject.ConfigProperty;
import org.jboss.logging.Logger;

@ApplicationScoped
public class EmbeddingsClient {

    private static final Logger LOG = Logger.getLogger(EmbeddingsClient.class);

    @Inject
    ProducerTemplate producerTemplate;

    @Inject
    ObjectMapper objectMapper;

    @ConfigProperty(name = "dogen.chat.rag.embedding-model")
    String embeddingModel;

    @ConfigProperty(name = "dogen.chat.upstream-authorization")
    String upstreamAuthorization;

    /**
     * OpenAI 互換の batched input。失敗時は空リスト。
     */
    public List<double[]> embedBatch(List<String> texts) {
        if (texts == null || texts.isEmpty()) {
            return List.of();
        }
        ObjectNode root = objectMapper.createObjectNode();
        root.put("model", embeddingModel);
        ArrayNode inputs = objectMapper.createArrayNode();
        for (String t : texts) {
            inputs.add(t == null ? "" : t);
        }
        root.set("input", inputs);
        try {
            String body = objectMapper.writeValueAsString(root);
            Exchange out = producerTemplate.request("direct:llamaEmbeddings", ex -> {
                Message in = ex.getIn();
                in.setBody(body);
                in.setHeader("Authorization", upstreamAuthorization);
            });
            Message response = out.getMessage();
            Integer httpStatus = response.getHeader(Exchange.HTTP_RESPONSE_CODE, Integer.class);
            String raw = response.getBody(String.class);
            if (httpStatus != null && httpStatus >= 400) {
                LOG.warnf("embeddings HTTP %s: %s", httpStatus, truncate(raw, 200));
                return List.of();
            }
            if (raw == null || raw.isBlank()) {
                return List.of();
            }
            JsonNode tree = objectMapper.readTree(raw);
            JsonNode data = tree.get("data");
            if (data == null || !data.isArray()) {
                return List.of();
            }
            List<double[]> rows = new ArrayList<>();
            for (int i = 0; i < texts.size(); i++) {
                rows.add(null);
            }
            int implicit = 0;
            for (JsonNode row : data) {
                int idx = row.has("index") ? row.get("index").asInt() : implicit++;
                if (idx < 0 || idx >= rows.size()) {
                    continue;
                }
                JsonNode emb = row.get("embedding");
                if (emb == null || !emb.isArray()) {
                    rows.set(idx, new double[0]);
                } else {
                    double[] v = new double[emb.size()];
                    for (int i = 0; i < emb.size(); i++) {
                        v[i] = emb.get(i).asDouble();
                    }
                    rows.set(idx, v);
                }
            }
            for (int i = 0; i < rows.size(); i++) {
                if (rows.get(i) == null) {
                    rows.set(i, new double[0]);
                }
            }
            return rows;
        } catch (CamelExecutionException e) {
            LOG.warn("embeddings camel failure", e);
            return List.of();
        } catch (Exception e) {
            LOG.warn("embeddings parse failure", e);
            return List.of();
        }
    }

    public double[] embedOne(String text) {
        List<double[]> r = embedBatch(List.of(text == null ? "" : text));
        return r.isEmpty() ? new double[0] : r.get(0);
    }

    private static String truncate(String s, int n) {
        if (s == null) {
            return "";
        }
        return s.length() <= n ? s : s.substring(0, n);
    }
}
