/**
 * タブ用ファビコン（各ページの <head> に明示が無い場合の補完。script は /js/nav.js 基準でサイトルートを解決）
 */
(function installDogenIcons() {
  try {
    var ref = document.querySelector('script[src*="nav.js"]');
    if (!ref || ref.getAttribute("data-dogen-icon") === "0") return;
    var base = new URL("..", ref.src);
    function hasIcon(href) {
      var links = document.head ? document.head.querySelectorAll('link[rel="icon"]') : [];
      for (var i = 0; i < links.length; i++) {
        if (links[i].getAttribute("href") === href) return true;
      }
      return false;
    }
    var png32 = new URL("img/app-icon-dogen-32.png", base).href;
    var ico = new URL("favicon.ico", base).href;
    var apple = new URL("apple-touch-icon.png", base).href;
    if (!hasIcon(png32)) {
      var l1 = document.createElement("link");
      l1.rel = "icon";
      l1.type = "image/png";
      l1.sizes = "32x32";
      l1.href = png32;
      document.head.appendChild(l1);
    }
    if (!hasIcon(ico)) {
      var l2 = document.createElement("link");
      l2.rel = "icon";
      l2.href = ico;
      l2.setAttribute("sizes", "any");
      document.head.appendChild(l2);
    }
    if (!document.querySelector('link[rel="apple-touch-icon"]')) {
      var a = document.createElement("link");
      a.rel = "apple-touch-icon";
      a.href = apple;
      document.head.appendChild(a);
    }
  } catch (e) {}
})();

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
