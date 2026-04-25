package jp.dogen.chat.api;

import io.quarkus.security.identity.SecurityIdentity;
import jakarta.inject.Inject;
import jakarta.ws.rs.DefaultValue;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.PathParam;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.QueryParam;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.NotFoundException;
import jakarta.ws.rs.core.Response;
import java.util.UUID;
import jp.dogen.chat.service.SessionService;

@Path("/api/v1/sessions")
@Produces(MediaType.APPLICATION_JSON)
public class SessionResource {

    @Inject
    SessionService sessionService;

    @Inject
    SecurityIdentity securityIdentity;

    @GET
    public Response list(@QueryParam("limit") @DefaultValue("80") int limit) {
        try {
            return Response.ok(sessionService.listRecent(limit, clientSubject())).build();
        } catch (Exception e) {
            return Response.serverError()
                    .entity("{\"error\":\"sessions_list_failed\"}")
                    .type(MediaType.APPLICATION_JSON)
                    .build();
        }
    }

    @GET
    @Path("/{id}/messages")
    public Response messages(@PathParam("id") UUID id) {
        try {
            return Response.ok(sessionService.listMessages(id, clientSubject())).build();
        } catch (NotFoundException e) {
            return Response.status(Response.Status.NOT_FOUND)
                    .entity("{\"error\":\"session_not_found\"}")
                    .type(MediaType.APPLICATION_JSON)
                    .build();
        } catch (Exception e) {
            return Response.serverError()
                    .entity("{\"error\":\"messages_list_failed\"}")
                    .type(MediaType.APPLICATION_JSON)
                    .build();
        }
    }

    private String clientSubject() {
        if (securityIdentity == null || securityIdentity.isAnonymous()) {
            return null;
        }
        return securityIdentity.getPrincipal().getName();
    }
}
