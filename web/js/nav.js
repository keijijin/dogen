(function () {
  var btn = document.querySelector(".nav-toggle");
  var nav = document.querySelector(".site-nav");
  if (!btn || !nav) return;
  btn.addEventListener("click", function () {
    nav.classList.toggle("is-open");
    var open = nav.classList.contains("is-open");
    btn.setAttribute("aria-expanded", open ? "true" : "false");
  });
})();

(function loadDogenQuiz() {
  var ref = document.querySelector('script[src*="nav.js"]');
  if (!ref || ref.getAttribute("data-dogen-quiz") === "0") return;
  var q = document.createElement("script");
  q.src = new URL("quiz.js", ref.src).href;
  q.defer = true;
  document.body.appendChild(q);
})();

/**
 * OIDC 有効時は oidc-config → pkce →（ui）を chat-dock より先に読み込む。
 * 並列だと chat-dock が先に走り、localStorage 未設定でも Bearer fake を送って API が 403 になることがある。
 */
(function loadDogenOidcAndChatDock() {
  var ref = document.querySelector('script[src*="nav.js"]');
  if (!ref) return;
  var chatOff = ref.getAttribute("data-dogen-chat") === "0";
  var oidcOff = ref.getAttribute("data-dogen-oidc") === "0";

  function appendOidcUi(then) {
    var u = document.createElement("script");
    u.src = new URL("oidc-ui.js", ref.src).href;
    u.onload = then;
    u.onerror = then;
    document.body.appendChild(u);
  }

  function loadOidcScriptsOnly(then) {
    var cfg = document.createElement("script");
    cfg.src = new URL("oidc-config.js", ref.src).href;
    cfg.onload = function () {
      var p = document.createElement("script");
      p.src = new URL("oidc-pkce.js", ref.src).href;
      p.onload = function () {
        appendOidcUi(then);
      };
      p.onerror = then;
      document.body.appendChild(p);
    };
    cfg.onerror = then;
    document.body.appendChild(cfg);
  }

  function appendDock() {
    var s = document.createElement("script");
    s.src = new URL("chat-dock.js", ref.src).href;
    s.defer = true;
    document.body.appendChild(s);
  }

  function loadRuntimeThenDock() {
    var rc = document.createElement("script");
    rc.src = new URL("runtime-config.js", ref.src).href;
    rc.onload = appendDock;
    rc.onerror = appendDock;
    document.body.appendChild(rc);
  }

  if (!chatOff) {
    var css = document.createElement("link");
    css.rel = "stylesheet";
    css.href = new URL("../css/chat-dock.css", ref.src).href;
    document.head.appendChild(css);
    if (!oidcOff) {
      loadOidcScriptsOnly(loadRuntimeThenDock);
    } else {
      loadRuntimeThenDock();
    }
  } else if (!oidcOff) {
    loadOidcScriptsOnly(function () {});
  }
})();
