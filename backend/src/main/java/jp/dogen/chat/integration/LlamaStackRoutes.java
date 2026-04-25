package jp.dogen.chat.integration;

import io.quarkus.arc.Unremovable;
import jakarta.enterprise.context.ApplicationScoped;
import org.apache.camel.Exchange;
import org.apache.camel.builder.RouteBuilder;
import org.eclipse.microprofile.config.inject.ConfigProperty;

/**
 * Llama Stack の OpenAI 互換 <code>/v1/chat/completions</code> へ中継する。
 */
@ApplicationScoped
@Unremovable
public class LlamaStackRoutes extends RouteBuilder {

    @ConfigProperty(name = "llama.stack.base-url")
    String llamaStackBaseUrl;

    @Override
    public void configure() {
        // throwExceptionOnFailure=false で 4xx/5xx も本文を返し、ChatService でステータス判定する
        String completions = llamaStackBaseUrl.replaceAll("/$", "")
                + "/v1/chat/completions?bridgeEndpoint=true&throwExceptionOnFailure=false";

        from("direct:llamaChatCompletions")
                .routeId("llama-chat-completions")
                .setHeader(Exchange.HTTP_METHOD, constant("POST"))
                .setHeader(Exchange.CONTENT_TYPE, constant("application/json"))
                .choice()
                .when(header("Authorization").isNull())
                .setHeader("Authorization", constant("Bearer fake"))
                .end()
                .to(completions);

        String embeddings =
                llamaStackBaseUrl.replaceAll("/$", "")
                        + "/v1/embeddings?bridgeEndpoint=true&throwExceptionOnFailure=false";
        from("direct:llamaEmbeddings")
                .routeId("llama-embeddings")
                .setHeader(Exchange.HTTP_METHOD, constant("POST"))
                .setHeader(Exchange.CONTENT_TYPE, constant("application/json"))
                .choice()
                .when(header("Authorization").isNull())
                .setHeader("Authorization", constant("Bearer fake"))
                .end()
                .to(embeddings);
    }
}
