/**
 * ブラウザ完結の OIDC Authorization Code + PKCE（ディスカバリ利用）。
 * 依存: window.DOGEN_OIDC（oidc-config.js）
 */
(function (global) {
  var STORAGE_ACCESS = "dogen_bearer_token";
  var STORAGE_REFRESH = "dogen_refresh_token";
  var STORAGE_ID = "dogen_id_token";
  var SS_VERIFIER = "dogen_oidc_code_verifier";
  var SS_STATE = "dogen_oidc_state";
  var SS_NEXT = "dogen_oidc_next";

  function cfg() {
    return global.DOGEN_OIDC || {};
  }

  function b64url(buf) {
    var bin = "";
    var bytes = new Uint8Array(buf);
    for (var i = 0; i < bytes.byteLength; i++) {
      bin += String.fromCharCode(bytes[i]);
    }
    return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  function randomVerifier() {
    var arr = new Uint8Array(48);
    crypto.getRandomValues(arr);
    return b64url(arr);
  }

  function randomState() {
    var arr = new Uint8Array(16);
    crypto.getRandomValues(arr);
    return b64url(arr);
  }

  function sha256base64url(verifier) {
    return crypto.subtle
      .digest("SHA-256", new TextEncoder().encode(verifier))
      .then(function (hash) {
        return b64url(hash);
      });
  }

  function trimSlash(u) {
    return u ? u.replace(/\/+$/, "") : "";
  }

  /** HTTPS ページから http の Issuer を取ると Mixed Content で fetch が失敗する */
  function normalizeAuthority(authority) {
    if (!authority) return authority;
    try {
      if (String(global.location.protocol) === "https:" && /^http:\/\//i.test(authority)) {
        return authority.replace(/^http:\/\//i, "https://");
      }
    } catch (e) {}
    return authority;
  }

  function fetchJsonCors(url, init) {
    var base = {
      mode: "cors",
      credentials: "omit",
      cache: "no-store",
    };
    var opts = init ? Object.assign({}, base, init) : base;
    return fetch(url, opts).catch(function (e) {
      var m = (e && e.message) || String(e);
      if (m === "Failed to fetch" || (e && e.name === "TypeError")) {
        throw new Error(
          "IdP への接続に失敗しました（Failed to fetch）。HTTPS の整合やキャッシュのほか、ブラウザの追跡防止(ITP)でクロスサイト fetch が遮断されている可能性があります。OpenShift では deploy/openshift/09-configure-oidc.sh による同一オリジン /auth/kc/ 中継を有効にしてください。"
        );
      }
      throw e;
    });
  }

  function redirectUri() {
    var c = cfg();
    var path = c.redirect_path || "/auth/callback.html";
    return new URL(path, global.location.origin).href;
  }

  function postLogoutUri() {
    var c = cfg();
    var path = c.post_logout_redirect_path || "/";
    return new URL(path, global.location.origin).href;
  }

  function discoveryUrl(authority) {
    return trimSlash(normalizeAuthority(authority)) + "/.well-known/openid-configuration";
  }

  /**
   * OpenShift 等: well-known は同一オリジン `/auth/kc/` 経由で取得し、
   * fetch が必要なエンドポイントだけ Keycloak 公開 URL → プロキシ URL に差し替える（authorization はフル遷移のまま）。
   */
  function rewriteKeycloakFetchEndpoints(meta, c) {
    var pub = trimSlash(normalizeAuthority(c.keycloak_public_origin || ""));
    var prx = trimSlash(c.browser_oidc_proxy_prefix || "");
    if (!pub || !prx) return meta;
    function rep(u) {
      if (!u || typeof u !== "string") return u;
      if (u.indexOf(pub) === 0) return prx + u.substring(pub.length);
      return u;
    }
    var keys = [
      "token_endpoint",
      "revocation_endpoint",
      "introspection_endpoint",
      "device_authorization_endpoint",
      "end_session_endpoint",
    ];
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i];
      if (meta[k]) meta[k] = rep(meta[k]);
    }
    return meta;
  }

  function fetchDiscovery(authority) {
    var a = normalizeAuthority(authority);
    return fetchJsonCors(discoveryUrl(a))
      .then(function (r) {
        if (!r.ok) throw new Error("OpenID 設定の取得に失敗しました (" + r.status + ")");
        return r.json();
      })
      .then(function (meta) {
        return rewriteKeycloakFetchEndpoints(meta, cfg());
      });
  }

  global.DogenOidc = {
    isEnabled: function () {
      var c = cfg();
      return !!(c.enabled === true && c.authority && c.client_id);
    },

    getAccessToken: function () {
      try {
        return global.localStorage.getItem(STORAGE_ACCESS);
      } catch (e) {
        return null;
      }
    },

    clearTokens: function () {
      try {
        global.localStorage.removeItem(STORAGE_ACCESS);
        global.localStorage.removeItem(STORAGE_REFRESH);
        global.localStorage.removeItem(STORAGE_ID);
      } catch (e) {}
    },

    parseIdPayload: function () {
      try {
        var id = global.localStorage.getItem(STORAGE_ID);
        if (!id) return null;
        var parts = id.split(".");
        if (parts.length < 2) return null;
        var json = parts[1].replace(/-/g, "+").replace(/_/g, "/");
        var pad = json.length % 4;
        if (pad) json += "====".slice(0, 4 - pad);
        var bin = atob(json);
        return JSON.parse(bin);
      } catch (e) {
        return null;
      }
    },

    startLogin: function () {
      var c = cfg();
      if (!this.isEnabled()) {
        return Promise.reject(new Error("OIDC が無効か、設定が不足しています"));
      }
      var self = this;
      return fetchDiscovery(c.authority).then(function (meta) {
        var authEp = meta.authorization_endpoint;
        if (!authEp) throw new Error("authorization_endpoint がありません");
        var verifier = randomVerifier();
        return sha256base64url(verifier).then(function (challenge) {
          var state = randomState();
          try {
            global.sessionStorage.setItem(SS_VERIFIER, verifier);
            global.sessionStorage.setItem(SS_STATE, state);
            if (c.save_return_path !== false) {
              global.sessionStorage.setItem(SS_NEXT, global.location.pathname + global.location.search + global.location.hash);
            } else {
              global.sessionStorage.removeItem(SS_NEXT);
            }
          } catch (e) {}

          var params = new URLSearchParams();
          params.set("client_id", c.client_id);
          params.set("response_type", "code");
          params.set("scope", c.scope || "openid profile email");
          params.set("redirect_uri", redirectUri());
          params.set("state", state);
          params.set("code_challenge", challenge);
          params.set("code_challenge_method", "S256");
          global.location.href = authEp + "?" + params.toString();
        });
      });
    },

    /**
     * コールバックページで呼び出す。トークン保存後、戻り先 URL を返す。
     */
    completeLoginFromCurrentUrl: function () {
      var c = cfg();
      var params = new URLSearchParams(global.location.search);
      var err = params.get("error");
      if (err) {
        var desc = params.get("error_description") || err;
        return Promise.reject(new Error(desc));
      }
      var code = params.get("code");
      var state = params.get("state");
      if (!code || !state) {
        return Promise.reject(new Error("code または state がありません"));
      }
      var savedState = null;
      var verifier = null;
      try {
        savedState = global.sessionStorage.getItem(SS_STATE);
        verifier = global.sessionStorage.getItem(SS_VERIFIER);
      } catch (e) {}
      if (!verifier || state !== savedState) {
        return Promise.reject(new Error("state が一致しません。もう一度ログインしてください"));
      }

      return fetchDiscovery(c.authority).then(function (meta) {
        var tokenEp = meta.token_endpoint;
        if (!tokenEp) throw new Error("token_endpoint がありません");

        var body = new URLSearchParams();
        body.set("grant_type", "authorization_code");
        body.set("client_id", c.client_id);
        body.set("code", code);
        body.set("redirect_uri", redirectUri());
        body.set("code_verifier", verifier);

        return fetchJsonCors(tokenEp, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: body.toString(),
        }).then(function (r) {
          return r.text().then(function (t) {
            var j;
            try {
              j = JSON.parse(t);
            } catch (e) {
              throw new Error("トークン応答が JSON ではありません");
            }
            if (!r.ok) {
              throw new Error(j.error_description || j.error || "トークン取得に失敗しました");
            }
            if (!j.access_token) throw new Error("access_token がありません");
            try {
              global.localStorage.setItem(STORAGE_ACCESS, j.access_token);
              if (j.refresh_token) global.localStorage.setItem(STORAGE_REFRESH, j.refresh_token);
              if (j.id_token) global.localStorage.setItem(STORAGE_ID, j.id_token);
              global.sessionStorage.removeItem(SS_VERIFIER);
              global.sessionStorage.removeItem(SS_STATE);
            } catch (e) {}
            var next = "/";
            try {
              next = global.sessionStorage.getItem(SS_NEXT) || "/";
              global.sessionStorage.removeItem(SS_NEXT);
            } catch (e2) {}
            if (!next || next.indexOf("/") !== 0) next = "/";
            if (next === "/auth/callback.html") next = "/";
            return next;
          });
        });
      });
    },

    logout: function () {
      var idToken = null;
      try {
        idToken = global.localStorage.getItem(STORAGE_ID);
      } catch (e) {}
      var c = cfg();
      if (!c.authority) {
        this.clearTokens();
        global.location.href = postLogoutUri();
        return Promise.resolve();
      }
      return fetchDiscovery(c.authority)
        .then(function (meta) {
          var end = meta.end_session_endpoint;
          var post = postLogoutUri();
          global.DogenOidc.clearTokens();
          if (end && idToken) {
            var sep = end.indexOf("?") >= 0 ? "&" : "?";
            global.location.href =
              end +
              sep +
              "id_token_hint=" +
              encodeURIComponent(idToken) +
              "&post_logout_redirect_uri=" +
              encodeURIComponent(post);
            return;
          }
          global.location.href = post;
        })
        .catch(function () {
          global.DogenOidc.clearTokens();
          global.location.href = postLogoutUri();
        });
    },
  };
})(window);
