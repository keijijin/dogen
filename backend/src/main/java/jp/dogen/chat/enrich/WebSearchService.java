package jp.dogen.chat.enrich;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Optional;
import org.eclipse.microprofile.config.inject.ConfigProperty;
import org.jboss.logging.Logger;

@ApplicationScoped
public class WebSearchService {

    private static final Logger LOG = Logger.getLogger(WebSearchService.class);

    private static final URI TAVILY = URI.create("https://api.tavily.com/search");

    @Inject
    ObjectMapper objectMapper;

    @ConfigProperty(name = "dogen.chat.web-search.enabled")
    boolean enabled;

    @ConfigProperty(name = "dogen.chat.web-search.max-results")
    int maxResults;

    @ConfigProperty(name = "dogen.chat.web-search.api-key")
    Optional<String> apiKey;

    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(8)).build();

    public String buildContextBlock(String userQuery) {
        String key = apiKey.orElse("").trim();
        if (!enabled || key.isBlank() || userQuery == null || userQuery.isBlank()) {
            return "";
        }
        int n = maxResults > 0 && maxResults <= 10 ? maxResults : 4;
        try {
            ObjectNode body = objectMapper.createObjectNode();
            body.put("api_key", key);
            body.put("query", userQuery);
            body.put("max_results", n);
            body.put("include_answer", true);
            String json = objectMapper.writeValueAsString(body);
            HttpRequest req = HttpRequest.newBuilder(TAVILY)
                    .timeout(Duration.ofSeconds(12))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(json, StandardCharsets.UTF_8))
                    .build();
            HttpResponse<String> res = http.send(req, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            if (res.statusCode() >= 400) {
                LOG.warnf("Tavily HTTP %s", res.statusCode());
                return "";
            }
            JsonNode root = objectMapper.readTree(res.body());
            StringBuilder sb = new StringBuilder();
            if (root.has("answer") && root.get("answer").isTextual()) {
                sb.append("要約: ").append(root.get("answer").asText()).append("\n\n");
            }
            JsonNode results = root.get("results");
            if (results != null && results.isArray()) {
                for (JsonNode r : results) {
                    String title = r.has("title") ? r.get("title").asText() : "";
                    String url = r.has("url") ? r.get("url").asText() : "";
                    String content = r.has("content") ? r.get("content").asText() : "";
                    if (!title.isBlank() || !content.isBlank()) {
                        sb.append("- ")
                                .append(title)
                                .append(" ")
                                .append(url)
                                .append("\n  ")
                                .append(content)
                                .append("\n");
                    }
                }
            }
            String out = sb.toString().trim();
            return out.isEmpty() ? "" : out;
        } catch (Exception e) {
            LOG.warn("web search failed", e);
            return "";
        }
    }
}
