(function () {
  var API_BASE = window.DOGEN_CHAT_API_BASE || "http://127.0.0.1:8081";
  var TOKEN_KEY = "dogen_bearer_token";
  var TOKEN_ID_KEY = "dogen_id_token";
  function oidcEnabled() {
    var c = window.DOGEN_OIDC || {};
    return !!(c.enabled === true && c.authority && c.client_id);
  }
  function oidcRequiredForChat() {
    if (oidcEnabled()) return true;
    try {
      if (window.location.protocol !== "https:") return false;
      var b = window.DOGEN_CHAT_API_BASE;
      if (!b || !String(b).trim()) return false;
      var u = String(b).trim();
      if (!/^https:\/\//i.test(u)) return false;
      if (/^https:\/\/(127\.0\.0\.1|localhost)\b/i.test(u)) return false;
      return true;
    } catch (e) {
      return false;
    }
  }
  function rawAccessToken() {
    try {
      var t = localStorage.getItem(TOKEN_KEY);
      return t && t.trim() ? t.trim() : null;
    } catch (e) {
      return null;
    }
  }
  function rawTokenForApi() {
    var at = rawAccessToken();
    if (at) return at;
    try {
      var id = localStorage.getItem(TOKEN_ID_KEY);
      if (id && id.trim()) return id.trim();
    } catch (e) {}
    return null;
  }
  function bearer() {
    var tok = rawTokenForApi();
    if (oidcRequiredForChat()) {
      return tok ? "Bearer " + tok : null;
    }
    return tok ? "Bearer " + tok : "Bearer fake";
  }
  function apiAuthMessage(statusText) {
    var m = String(statusText || "");
    if (!oidcRequiredForChat()) return m;
    if ((/^401\b|^403\b/.test(m) || m.indexOf("401 ") === 0 || m.indexOf("403 ") === 0) && !rawTokenForApi()) {
      return "ログインが必要です。ナビの「ログイン」からサインインしてください。（" + m + "）";
    }
    if (/^401\b|^403\b/.test(m) || m.indexOf("401 ") === 0 || m.indexOf("403 ") === 0) {
      return "API がトークンを拒否しました。ログアウトして再度ログインしてください。（" + m + "）";
    }
    return m;
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

    var headers = { "Content-Type": "application/json" };
    var b = bearer();
    if (b) headers.Authorization = b;
    fetch(API_BASE + "/api/v1/chat", {
      method: "POST",
      headers: headers,
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
        err.textContent = apiAuthMessage(hint);
      });
  });
})();
