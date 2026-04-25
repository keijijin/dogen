(function () {
  var API_BASE = window.DOGEN_CHAT_API_BASE || "http://127.0.0.1:8081";
  var TOKEN_KEY = "dogen_bearer_token";
  function bearer() {
    var t = null;
    try {
      t = localStorage.getItem(TOKEN_KEY);
    } catch (e) {}
    return t && t.trim() ? "Bearer " + t.trim() : "Bearer fake";
  }
  var form = document.getElementById("chat-form");
  var out = document.getElementById("chat-out");
  var err = document.getElementById("chat-err");
  var sessionHint = document.getElementById("session-hint");
  if (!form || !out) return;

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    err.textContent = "";
    out.textContent = "送信中…";
    var q = document.getElementById("chat-q").value;
    var vol = document.getElementById("chat-vol").value.trim();
    var body = {
      messages: [{ role: "user", content: q }],
    };
    if (vol) body.volumeScope = vol;

    fetch(API_BASE + "/api/v1/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: bearer(),
      },
      body: JSON.stringify(body),
    })
      .then(function (res) {
        var sid = res.headers.get("X-Session-Id");
        var uid = res.headers.get("X-User-Message-Id");
        var aid = res.headers.get("X-Assistant-Message-Id");
        if (sid || uid || aid) {
          sessionHint.textContent =
            [sid && "セッション: " + sid, uid && "ユーザー発話ID: " + uid, aid && "応答ID: " + aid]
              .filter(Boolean)
              .join(" · ");
        }
        return res.text().then(function (t) {
          if (!res.ok) {
            throw new Error(res.status + " " + t);
          }
          return t;
        });
      })
      .then(function (text) {
        try {
          var j = JSON.parse(text);
          out.textContent = JSON.stringify(j, null, 2);
        } catch (e) {
          out.textContent = text;
        }
      })
      .catch(function (e) {
        out.textContent = "";
        var hint =
          e.message ||
          "通信に失敗しました。`backend` で `mvn quarkus:dev` を起動し、Llama Stack（8321）と OpenAI キーを確認してください。";
        if (e.message === "Failed to fetch") {
          hint +=
            " API が起動しているか（`8081`）、URL が `http://…` でブロックされていないか確認してください。CORS で落ちる場合は `application.yaml` の `quarkus.http.cors` を確認（Compose は `%compose` で全オリジン許可）。";
        }
        err.textContent = hint;
      });
  });
})();
