(function () {
  var LS_KEY = "dogen_chat_session_id";
  var TOKEN_KEY = "dogen_bearer_token";
  function apiBase() {
    var b = null;
    try {
      b = window.DOGEN_CHAT_API_BASE;
    } catch (e) {}
    if (b && String(b).trim()) {
      var u = String(b).trim().replace(/\/+$/, "");
      try {
        if (window.location.protocol === "https:" && /^http:\/\/(127\.0\.0\.1|localhost)\b/i.test(u)) {
          return null;
        }
      } catch (e2) {}
      return u;
    }
    try {
      if (window.location.protocol === "https:") {
        return null;
      }
    } catch (e3) {}
    return "http://127.0.0.1:8081";
  }

  function misconfiguredApiBaseMessage() {
    return (
      "API の URL が未設定か、HTTPS ページから http://127.0.0.1 を指しています（ブラウザがブロックします）。OpenShift では ./deploy/openshift/07-patch-web-api-url.sh で runtime-config.js を更新し、ページを再読み込みしてください。"
    );
  }

  /** OIDC 有効（nav.js で oidc-config 読み込み済みであること） */
  function oidcEnabled() {
    var c = window.DOGEN_OIDC || {};
    return !!(c.enabled === true && c.authority && c.client_id);
  }

  /**
   * HTTPS の本番ドメインで API も https のとき、oidc-config.js が誤って enabled:false でも
   * compose,oidc の API には Bearer fake を送らない（403 の原因になる）。
   */
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

  var TOKEN_ID_KEY = "dogen_id_token";

  function rawAccessToken() {
    try {
      var t = localStorage.getItem(TOKEN_KEY);
      return t && t.trim() ? t.trim() : null;
    } catch (e) {
      return null;
    }
  }

  /** Bearer は access_token を優先。古い保存データ互換のため id_token もフォールバックで許可。 */
  function rawTokenForApi() {
    var at = rawAccessToken();
    if (at) return at;
    try {
      var id = localStorage.getItem(TOKEN_ID_KEY);
      if (id && id.trim()) return id.trim();
    } catch (e) {}
    return null;
  }

  /**
   * OIDC 有効時はアクセストークンが無いと Authorization を付けない（Bearer fake は 403 の原因になる）。
   * OIDC 無効時は従来どおり匿名で Bearer fake。
   */
  function bearer() {
    var tok = rawTokenForApi();
    if (oidcRequiredForChat()) {
      return tok ? "Bearer " + tok : null;
    }
    return tok ? "Bearer " + tok : "Bearer fake";
  }

  function headersJson() {
    var h = {
      Accept: "application/json",
      "Content-Type": "application/json",
    };
    var b = bearer();
    if (b) h.Authorization = b;
    return h;
  }

  function headersStreamJson() {
    var h = {
      Accept: "text/event-stream",
      "Content-Type": "application/json",
    };
    var b = bearer();
    if (b) h.Authorization = b;
    return h;
  }

  function headersGet() {
    var h = { Accept: "application/json" };
    var b = bearer();
    if (b) h.Authorization = b;
    return h;
  }

  function apiAuthMessage(statusText) {
    var m = String(statusText || "");
    if (!oidcRequiredForChat()) return m;
    if ((/^401\b|^403\b/.test(m) || m.indexOf("401 ") === 0 || m.indexOf("403 ") === 0) && !rawTokenForApi()) {
      return "ログインが必要です。ナビの「ログイン」からサインインしてください。（" + m + "）";
    }
    if (/^401\b|^403\b/.test(m) || m.indexOf("401 ") === 0 || m.indexOf("403 ") === 0) {
      return "API がトークンを拒否しました。ログアウトして再度ログインしてください。OpenShift では ./deploy/openshift/09-configure-oidc.sh を再実行し、API を再デプロイしたうえで試してください。（" + m + "）";
    }
    return m;
  }

  var root = document.createElement("div");
  root.id = "dogen-dock-root";
  root.setAttribute("aria-live", "polite");
  root.innerHTML =
    '<button type="button" id="dogen-dock-fab" aria-expanded="false" aria-controls="dogen-dock-panel">問答</button>' +
    '<div id="dogen-dock-panel" hidden role="dialog" aria-label="正法眼蔵問答">' +
    '  <div class="dogen-dock__head">' +
    '    <h2>問答 Bot</h2>' +
    '    <button type="button" id="dogen-dock-close" aria-label="閉じる">×</button>' +
    "  </div>" +
    '  <div class="dogen-dock__toolbar">' +
    '    <label class="visually-hidden" for="dogen-session-select">セッション</label>' +
    '    <select id="dogen-session-select" aria-label="保存済みセッション"></select>' +
    '    <button type="button" id="dogen-new-session">新規</button>' +
    "  </div>" +
    '  <div class="dogen-dock__toolbar" style="border-bottom: none; padding-top: 0">' +
    '    <label class="visually-hidden" for="dogen-dock-vol">巻スコープ</label>' +
    '    <input id="dogen-dock-vol" type="text" placeholder="巻スコープ（任意）例: 現成公案" />' +
    "  </div>" +
    '  <div id="dogen-messages"></div>' +
    '  <form id="dogen-dock-form">' +
    '    <label class="visually-hidden" for="dogen-dock-input">質問</label>' +
    '    <textarea id="dogen-dock-input" placeholder="質問を入力…" rows="3"></textarea>' +
    '    <button type="submit" id="dogen-dock-send">送信</button>' +
    "  </form>" +
    '  <div id="dogen-dock-err"></div>' +
    "</div>";

  if (!document.getElementById("dogen-dock-vis-style")) {
    var st = document.createElement("style");
    st.id = "dogen-dock-vis-style";
    st.textContent = ".visually-hidden{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}";
    document.head.appendChild(st);
  }
  document.body.appendChild(root);

  var fab = document.getElementById("dogen-dock-fab");
  var panel = document.getElementById("dogen-dock-panel");
  var closeBtn = document.getElementById("dogen-dock-close");
  var sel = document.getElementById("dogen-session-select");
  var newBtn = document.getElementById("dogen-new-session");
  var vol = document.getElementById("dogen-dock-vol");
  var messagesEl = document.getElementById("dogen-messages");
  var form = document.getElementById("dogen-dock-form");
  var input = document.getElementById("dogen-dock-input");
  var sendBtn = document.getElementById("dogen-dock-send");
  var errEl = document.getElementById("dogen-dock-err");

  var sessionId = null;

  function setSession(id) {
    sessionId = id || null;
    if (sessionId) {
      try {
        localStorage.setItem(LS_KEY, sessionId);
      } catch (e) {}
    } else {
      try {
        localStorage.removeItem(LS_KEY);
      } catch (e) {}
    }
    syncSelect();
  }

  function syncSelect() {
    var opts = sel.querySelectorAll("option[data-sid]");
    for (var i = 0; i < opts.length; i++) {
      opts[i].selected = sessionId && opts[i].value === sessionId;
    }
    if (!sessionId) {
      var blank = sel.querySelector("option[value='']");
      if (blank) blank.selected = true;
    }
  }

  function clearErr() {
    errEl.textContent = "";
  }

  function scrollMessages() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function isSafeLink(u) {
    return /^(https?:\/\/|mailto:)/i.test(u || "");
  }

  function renderMarkdownSafe(text) {
    var src = String(text || "");
    var blocks = [];
    src = src.replace(/```([\s\S]*?)```/g, function (_m, code) {
      var idx = blocks.length;
      blocks.push('<pre><code>' + escapeHtml(code) + "</code></pre>");
      return "%%CODEBLOCK_" + idx + "%%";
    });

    var html = escapeHtml(src);
    html = html.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, function (_m, label, url) {
      if (!isSafeLink(url)) return label;
      return '<a href="' + url + '" target="_blank" rel="noopener noreferrer">' + label + "</a>";
    });
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    html = html.replace(/\n/g, "<br>");
    html = html.replace(/%%CODEBLOCK_(\d+)%%/g, function (_m, i) {
      return blocks[Number(i)] || "";
    });
    return html;
  }

  function setAssistantBody(bodyEl, text) {
    bodyEl.classList.add("dogen-msg__body--md");
    bodyEl.innerHTML = renderMarkdownSafe(text);
  }

  function createBubble(role, text) {
    var div = document.createElement("div");
    div.className = "dogen-msg dogen-msg--" + (role === "user" ? "user" : "assistant");
    var span = document.createElement("span");
    span.className = "dogen-msg__meta";
    span.textContent = role === "user" ? "あなた" : "応答";
    div.appendChild(span);
    var body = document.createElement("div");
    if (role === "assistant") setAssistantBody(body, text);
    else body.textContent = text;
    div.appendChild(body);
    messagesEl.appendChild(div);
    scrollMessages();
    return { root: div, body: body };
  }

  function appendBubble(role, text) {
    createBubble(role, text);
  }

  function clearMessages() {
    messagesEl.innerHTML = "";
  }

  function renderHistory(rows) {
    clearMessages();
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      if (r.role && r.content) appendBubble(r.role, r.content);
    }
    scrollMessages();
  }

  function fetchJSON(url, options) {
    var o = Object.assign(
      { mode: "cors", credentials: "omit", cache: "no-store" },
      options || {}
    );
    return fetch(url, o).then(function (res) {
      return res.text().then(function (t) {
        if (!res.ok) throw new Error(res.status + " " + t);
        try {
          return JSON.parse(t);
        } catch (e) {
          return t;
        }
      });
    });
  }

  function parseSseBlock(block) {
    var lines = String(block || "").replace(/\r/g, "").split("\n");
    var event = "message";
    var dataLines = [];
    for (var i = 0; i < lines.length; i++) {
      var ln = lines[i];
      if (ln.indexOf("event:") === 0) {
        event = ln.substring(6).trim() || "message";
      } else if (ln.indexOf("data:") === 0) {
        dataLines.push(ln.substring(5).trim());
      }
    }
    var raw = dataLines.join("\n");
    var parsed = null;
    if (raw) {
      try {
        parsed = JSON.parse(raw);
      } catch (e) {
        parsed = { raw: raw };
      }
    }
    return { event: event, data: parsed };
  }

  function streamChat(base, body, assistantBody) {
    return fetch(base + "/api/v1/chat/stream", {
      method: "POST",
      mode: "cors",
      credentials: "omit",
      cache: "no-store",
      headers: headersStreamJson(),
      body: JSON.stringify(body),
    }).then(function (res) {
      var sidHeader = res.headers.get("X-Session-Id");
      if (sidHeader) setSession(sidHeader);
      if (!res.ok) {
        return res.text().then(function (t) {
          throw new Error(res.status + " " + t);
        });
      }
      if (!res.body || !res.body.getReader) {
        return res.text().then(function (t) {
          setAssistantBody(assistantBody, t || "（ストリーミング非対応の応答）");
          scrollMessages();
        });
      }
      var reader = res.body.getReader();
      var decoder = new TextDecoder();
      var buf = "";
      var acc = "";
      var gotDelta = false;

      function handleBlock(block) {
        if (!block || !block.trim()) return;
        var evt = parseSseBlock(block);
        if (evt.event === "delta" && evt.data && typeof evt.data.delta === "string") {
          acc += evt.data.delta;
          gotDelta = true;
          setAssistantBody(assistantBody, acc);
          scrollMessages();
        } else if (evt.event === "done" && evt.data) {
          if (evt.data.sessionId) setSession(evt.data.sessionId);
        } else if (evt.event === "error") {
          var detail = (evt.data && (evt.data.detail || evt.data.error)) || "stream error";
          throw new Error(String(detail));
        }
      }

      function pump() {
        return reader.read().then(function (r) {
          if (r.done) {
            if (buf.trim()) handleBlock(buf);
            if (!gotDelta) throw new Error("stream_no_delta");
            return { mode: "stream", hasDelta: true };
          }
          buf += decoder.decode(r.value, { stream: true });
          var idx;
          while ((idx = buf.indexOf("\n\n")) >= 0) {
            var block = buf.slice(0, idx);
            buf = buf.slice(idx + 2);
            handleBlock(block);
          }
          return pump();
        });
      }
      return pump();
    });
  }

  function fetchChatOnce(base, body) {
    return fetch(base + "/api/v1/chat", {
      method: "POST",
      mode: "cors",
      credentials: "omit",
      cache: "no-store",
      headers: headersJson(),
      body: JSON.stringify(body),
    }).then(function (res) {
      var sidHeader = res.headers.get("X-Session-Id");
      if (sidHeader) setSession(sidHeader);
      return res.text().then(function (t) {
        if (!res.ok) throw new Error(res.status + " " + t);
        try {
          return JSON.parse(t);
        } catch (e) {
          return { raw: t };
        }
      });
    });
  }

  function extractAssistantFromChatJson(j) {
    if (!j) return "";
    if (typeof j.raw === "string") return j.raw;
    var content =
      j.choices &&
      j.choices[0] &&
      j.choices[0].message &&
      j.choices[0].message.content;
    return content || "";
  }

  function refreshSessions() {
    var base = apiBase();
    if (!base) {
      return Promise.reject(new Error(misconfiguredApiBaseMessage()));
    }
    return fetchJSON(base + "/api/v1/sessions?limit=80", {
      method: "GET",
      headers: headersGet(),
    }).then(function (list) {
      var saved = null;
      try {
        saved = localStorage.getItem(LS_KEY);
      } catch (e) {}
      sel.innerHTML = "";
      var blank = document.createElement("option");
      blank.value = "";
      blank.textContent = "（新規セッション）";
      sel.appendChild(blank);
      if (Array.isArray(list)) {
        for (var i = 0; i < list.length; i++) {
          var s = list[i];
          var opt = document.createElement("option");
          opt.value = s.id || "";
          opt.setAttribute("data-sid", "1");
          var label =
            (s.volumeScope ? s.volumeScope + " · " : "") +
            (s.preview || s.id || "").slice(0, 56);
          if (s.messageCount != null) label += " (" + s.messageCount + ")";
          opt.textContent = label || String(s.id);
          sel.appendChild(opt);
        }
      }
      if (saved && Array.isArray(list) && list.some(function (x) { return String(x.id) === String(saved); })) {
        setSession(saved);
        sel.value = saved;
      } else {
        syncSelect();
      }
    }).catch(function (e) {
      errEl.textContent = apiAuthMessage(e.message || String(e));
      return Promise.reject(e);
    });
  }

  function loadSessionMessages(id) {
    if (!id) return Promise.resolve();
    var base = apiBase();
    if (!base) {
      return Promise.reject(new Error(misconfiguredApiBaseMessage()));
    }
    return fetchJSON(base + "/api/v1/sessions/" + id + "/messages", {
      method: "GET",
      headers: headersGet(),
    }).then(function (rows) {
      if (Array.isArray(rows)) renderHistory(rows);
    });
  }

  fab.addEventListener("click", function () {
    var open = panel.hasAttribute("hidden");
    if (open) {
      panel.removeAttribute("hidden");
      fab.setAttribute("aria-expanded", "true");
      refreshSessions()
        .then(function () {
          var sid = sel.value || sessionId;
          if (sid) loadSessionMessages(sid);
        })
        .catch(function (e) {
          errEl.textContent = apiAuthMessage((e && e.message) || String(e));
        });
      input.focus();
    } else {
      panel.setAttribute("hidden", "");
      fab.setAttribute("aria-expanded", "false");
    }
  });

  closeBtn.addEventListener("click", function () {
    panel.setAttribute("hidden", "");
    fab.setAttribute("aria-expanded", "false");
  });

  newBtn.addEventListener("click", function () {
    setSession(null);
    sel.value = "";
    clearMessages();
    clearErr();
    input.focus();
  });

  sel.addEventListener("change", function () {
    var v = sel.value;
    if (!v) {
      setSession(null);
      clearMessages();
      return;
    }
    setSession(v);
    loadSessionMessages(v).catch(function (e) {
      errEl.textContent = apiAuthMessage(e.message || String(e));
    });
  });

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    clearErr();
    var text = input.value.trim();
    if (!text) return;
    var base = apiBase();
    if (!base) {
      errEl.textContent = misconfiguredApiBaseMessage();
      return;
    }
    sendBtn.disabled = true;
    appendBubble("user", text);
    var assistantBubble = createBubble("assistant", "");
    input.value = "";

    var body = {
      messages: [{ role: "user", content: text }],
    };
    var vs = vol.value.trim();
    if (vs) body.volumeScope = vs;
    if (sessionId) body.sessionId = sessionId;

    streamChat(base, body, assistantBubble.body)
      .catch(function (e) {
        var raw = (e && e.message) || String(e);
        var canFallback =
          raw === "stream_no_delta" ||
          raw.indexOf("stream_failed") >= 0 ||
          raw.indexOf("stream error") >= 0;
        if (!canFallback) throw e;
        return fetchChatOnce(base, body).then(function (j) {
          var content = extractAssistantFromChatJson(j);
          if (content) {
            setAssistantBody(assistantBubble.body, content);
            scrollMessages();
          }
        });
      })
      .then(function () {
        return refreshSessions();
      })
      .then(function () {
        if (sessionId) sel.value = sessionId;
        syncSelect();
      })
      .catch(function (e) {
        if (!assistantBubble.body.textContent && !assistantBubble.body.innerText) {
          setAssistantBody(assistantBubble.body, "（応答を受信できませんでした）");
        }
        var raw = e.message || String(e);
        var hint = raw;
        if (raw === "Failed to fetch" || (e && e.name === "TypeError")) {
          hint =
            raw +
            "（HTTPS では API の URL 未設定・混在コンテンツ・CORS の可能性があります。07-patch-web-api-url.sh と dogen-api の CORS を確認してください。）";
        }
        errEl.textContent = apiAuthMessage(hint);
      })
      .finally(function () {
        sendBtn.disabled = false;
        input.focus();
      });
  });

  try {
    var persisted = localStorage.getItem(LS_KEY);
    if (persisted) sessionId = persisted;
  } catch (e) {}
})();
