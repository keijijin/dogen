(function () {
  var LS_KEY = "dogen_chat_session_id";
  var TOKEN_KEY = "dogen_bearer_token";
  var API_BASE = window.DOGEN_CHAT_API_BASE || "http://127.0.0.1:8081";

  function bearer() {
    var t = null;
    try {
      t = localStorage.getItem(TOKEN_KEY);
    } catch (e) {}
    return t && t.trim() ? "Bearer " + t.trim() : "Bearer fake";
  }

  function headersJson() {
    return {
      Accept: "application/json",
      "Content-Type": "application/json",
      Authorization: bearer(),
    };
  }

  function headersGet() {
    return { Accept: "application/json", Authorization: bearer() };
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

  function appendBubble(role, text) {
    var div = document.createElement("div");
    div.className = "dogen-msg dogen-msg--" + (role === "user" ? "user" : "assistant");
    var span = document.createElement("span");
    span.className = "dogen-msg__meta";
    span.textContent = role === "user" ? "あなた" : "応答";
    div.appendChild(span);
    var body = document.createElement("div");
    body.textContent = text;
    div.appendChild(body);
    messagesEl.appendChild(div);
    scrollMessages();
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
    return fetch(url, options).then(function (res) {
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

  function refreshSessions() {
    return fetchJSON(API_BASE + "/api/v1/sessions?limit=80", {
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
    });
  }

  function loadSessionMessages(id) {
    if (!id) return Promise.resolve();
    return fetchJSON(API_BASE + "/api/v1/sessions/" + id + "/messages", {
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
      refreshSessions().then(function () {
        var sid = sel.value || sessionId;
        if (sid) loadSessionMessages(sid);
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
      errEl.textContent = e.message || String(e);
    });
  });

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    clearErr();
    var text = input.value.trim();
    if (!text) return;
    sendBtn.disabled = true;
    appendBubble("user", text);
    input.value = "";

    var body = {
      messages: [{ role: "user", content: text }],
    };
    var vs = vol.value.trim();
    if (vs) body.volumeScope = vs;
    if (sessionId) body.sessionId = sessionId;

    fetch(API_BASE + "/api/v1/chat", {
      method: "POST",
      headers: headersJson(),
      body: JSON.stringify(body),
    })
      .then(function (res) {
        var sidHeader = res.headers.get("X-Session-Id");
        if (sidHeader) setSession(sidHeader);
        return res.text().then(function (t) {
          if (!res.ok) throw new Error(res.status + " " + t);
          return t;
        });
      })
      .then(function (t) {
        var j = JSON.parse(t);
        var content =
          j.choices &&
          j.choices[0] &&
          j.choices[0].message &&
          j.choices[0].message.content;
        if (content) appendBubble("assistant", content);
        else appendBubble("assistant", JSON.stringify(j, null, 2));
        return refreshSessions();
      })
      .then(function () {
        if (sessionId) sel.value = sessionId;
        syncSelect();
      })
      .catch(function (e) {
        errEl.textContent = e.message || "送信に失敗しました";
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
