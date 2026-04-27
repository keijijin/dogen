package jp.dogen.chat.api;

import io.quarkus.security.identity.SecurityIdentity;
import jakarta.inject.Inject;
import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import jp.dogen.chat.dto.ChatRequest;
import jp.dogen.chat.dto.FeedbackRequest;
import jp.dogen.chat.service.ChatService;
import jp.dogen.chat.service.FeedbackService;

@Path("/api/v1")
@Produces(MediaType.APPLICATION_JSON)
@Consumes(MediaType.APPLICATION_JSON)
public class ChatResource {

    @Inject
    ChatService chatService;

    @Inject
    FeedbackService feedbackService;

    @Inject
    SecurityIdentity securityIdentity;

    @POST
    @Path("/chat")
    public Response chat(ChatRequest body) {
        return chatService.chat(body, clientSubject());
    }

    @POST
    @Path("/chat/stream")
    @Produces("text/event-stream")
    public Response chatStream(ChatRequest body) {
        return chatService.chatStream(body, clientSubject());
    }

    @POST
    @Path("/feedback")
    public Response feedback(FeedbackRequest body) {
        feedbackService.record(body);
        return Response.accepted().entity("{\"status\":\"accepted\"}").build();
    }

    @GET
    @Path("/health")
    public String health() {
        return "{\"status\":\"UP\"}";
    }

    private String clientSubject() {
        if (securityIdentity == null || securityIdentity.isAnonymous()) {
            return null;
        }
        return securityIdentity.getPrincipal().getName();
    }
}
