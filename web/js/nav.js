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

(function loadDogenChatDock() {
  var ref = document.querySelector('script[src*="nav.js"]');
  if (!ref || ref.getAttribute("data-dogen-chat") === "0") return;
  var css = document.createElement("link");
  css.rel = "stylesheet";
  css.href = new URL("../css/chat-dock.css", ref.src).href;
  document.head.appendChild(css);
  var s = document.createElement("script");
  s.src = new URL("chat-dock.js", ref.src).href;
  s.defer = true;
  document.body.appendChild(s);
})();

(function loadDogenQuiz() {
  var ref = document.querySelector('script[src*="nav.js"]');
  if (!ref || ref.getAttribute("data-dogen-quiz") === "0") return;
  var q = document.createElement("script");
  q.src = new URL("quiz.js", ref.src).href;
  q.defer = true;
  document.body.appendChild(q);
})();

(function loadDogenOidc() {
  var ref = document.querySelector('script[src*="nav.js"]');
  if (!ref || ref.getAttribute("data-dogen-oidc") === "0") return;
  var cfg = document.createElement("script");
  cfg.src = new URL("oidc-config.js", ref.src).href;
  cfg.onload = function () {
    var p = document.createElement("script");
    p.src = new URL("oidc-pkce.js", ref.src).href;
    p.onload = function () {
      var u = document.createElement("script");
      u.src = new URL("oidc-ui.js", ref.src).href;
      document.body.appendChild(u);
    };
    document.body.appendChild(p);
  };
  document.body.appendChild(cfg);
})();
