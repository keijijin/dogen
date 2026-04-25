package jp.dogen.chat.enrich;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import java.sql.Array;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import javax.sql.DataSource;
import org.eclipse.microprofile.config.inject.ConfigProperty;
import org.jboss.logging.Logger;

@ApplicationScoped
public class RagService {

    private static final Logger LOG = Logger.getLogger(RagService.class);

    @Inject
    DataSource dataSource;

    @Inject
    EmbeddingsClient embeddingsClient;

    @ConfigProperty(name = "dogen.chat.rag.enabled")
    boolean ragEnabled;

    @ConfigProperty(name = "dogen.chat.rag.top-k")
    int topK;

    private final Object embedLock = new Object();

    public String retrieveForUserQuery(String userText) {
        if (!ragEnabled || userText == null || userText.isBlank()) {
            return "";
        }
        try {
            syncEmbeddingsIfNeeded();
            double[] q = embeddingsClient.embedOne(userText);
            if (q.length == 0) {
                return "";
            }
            List<Scored> scored = new ArrayList<>();
            try (Connection c = dataSource.getConnection()) {
                String sql = "SELECT id, volume_key, content, embedding FROM rag_chunk WHERE embedding IS NOT NULL";
                try (PreparedStatement ps = c.prepareStatement(sql);
                        ResultSet rs = ps.executeQuery()) {
                    while (rs.next()) {
                        double[] emb = readEmbedding(rs.getArray("embedding"));
                        if (emb.length != q.length || emb.length == 0) {
                            continue;
                        }
                        String vk = rs.getString("volume_key");
                        double sim = cosine(q, emb);
                        scored.add(new Scored(rs.getString("content"), vk, sim));
                    }
                }
            }
            int k = topK > 0 && topK <= 20 ? topK : 5;
            scored.sort(Comparator.comparingDouble((Scored s) -> s.score).reversed());
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < Math.min(k, scored.size()); i++) {
                Scored s = scored.get(i);
                sb.append("[").append(s.volumeKey).append("] ").append(s.content).append("\n\n");
            }
            return sb.toString().trim();
        } catch (Exception e) {
            LOG.warn("RAG retrieve failed", e);
            return "";
        }
    }

    private void syncEmbeddingsIfNeeded() throws Exception {
        synchronized (embedLock) {
            try (Connection c = dataSource.getConnection()) {
                List<Long> ids = new ArrayList<>();
                List<String> texts = new ArrayList<>();
                String sel = "SELECT id, content FROM rag_chunk WHERE embedding IS NULL";
                try (PreparedStatement ps = c.prepareStatement(sel);
                        ResultSet rs = ps.executeQuery()) {
                    while (rs.next()) {
                        ids.add(rs.getLong("id"));
                        texts.add(rs.getString("content"));
                    }
                }
                if (ids.isEmpty()) {
                    return;
                }
                List<double[]> vectors = embeddingsClient.embedBatch(texts);
                if (vectors.size() != ids.size()) {
                    LOG.warnf("RAG embed size mismatch ids=%d vec=%d", ids.size(), vectors.size());
                    return;
                }
                String upd = "UPDATE rag_chunk SET embedding = ?::float8[] WHERE id = ?";
                c.setAutoCommit(false);
                try (PreparedStatement ps = c.prepareStatement(upd)) {
                    for (int i = 0; i < ids.size(); i++) {
                        double[] v = vectors.get(i);
                        if (v.length == 0) {
                            continue;
                        }
                        Array arr = c.createArrayOf("float8", toDoubleObjectArray(v));
                        ps.setArray(1, arr);
                        ps.setLong(2, ids.get(i));
                        ps.executeUpdate();
                    }
                    c.commit();
                } catch (Exception e) {
                    c.rollback();
                    throw e;
                }
            }
        }
    }

    private static Double[] toDoubleObjectArray(double[] v) {
        Double[] o = new Double[v.length];
        for (int i = 0; i < v.length; i++) {
            o[i] = v[i];
        }
        return o;
    }

    private static double[] readEmbedding(Array sqlArray) throws Exception {
        if (sqlArray == null) {
            return new double[0];
        }
        Object o = sqlArray.getArray();
        if (o instanceof float[] f) {
            double[] v = new double[f.length];
            for (int i = 0; i < f.length; i++) {
                v[i] = f[i];
            }
            return v;
        }
        if (o instanceof Double[] d) {
            double[] v = new double[d.length];
            for (int i = 0; i < d.length; i++) {
                v[i] = d[i] != null ? d[i] : 0d;
            }
            return v;
        }
        if (o instanceof Number[] n) {
            double[] v = new double[n.length];
            for (int i = 0; i < n.length; i++) {
                v[i] = n[i] != null ? n[i].doubleValue() : 0d;
            }
            return v;
        }
        return new double[0];
    }

    private static double cosine(double[] a, double[] b) {
        double dot = 0, na = 0, nb = 0;
        for (int i = 0; i < a.length; i++) {
            dot += a[i] * b[i];
            na += a[i] * a[i];
            nb += b[i] * b[i];
        }
        double denom = Math.sqrt(na) * Math.sqrt(nb);
        return denom < 1e-9 ? 0 : dot / denom;
    }

    private record Scored(String content, String volumeKey, double score) { }
}
