package jp.dogen.chat.api;

import static io.restassured.RestAssured.given;
import static org.hamcrest.CoreMatchers.containsString;

import io.quarkus.test.junit.QuarkusTest;
import org.junit.jupiter.api.Test;

@QuarkusTest
class HealthTest {

    @Test
    void healthReturnsUp() {
        given().when().get("/api/v1/health").then().statusCode(200).body(containsString("UP"));
    }
}
