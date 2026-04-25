/**
 * ヘッダー内のログイン / ログアウト（.site-nav の末尾に追加）
 */
(function () {
  function labelFromPayload(p) {
    if (!p) return "ログイン済み";
    return p.name || p.preferred_username || p.email || p.sub || "ログイン済み";
  }

  function authFlowHref() {
    var path = window.location.pathname || "/";
    var parts = path.split("/").filter(Boolean);
    if (parts.length <= 1) return "auth/index.html";
    return "../".repeat(parts.length - 1) + "auth/index.html";
  }

  function render() {
    if (!window.DogenOidc || !window.DogenOidc.isEnabled()) return;
    var nav = document.querySelector(".site-nav");
    if (!nav || document.getElementById("dogen-oidc-slot")) return;

    var wrap = document.createElement("span");
    wrap.id = "dogen-oidc-slot";
    wrap.className = "oidc-auth";

    var loginBtn = document.createElement("button");
    loginBtn.type = "button";
    loginBtn.className = "oidc-auth__btn";
    loginBtn.textContent = "ログイン";
    loginBtn.addEventListener("click", function () {
      window.DogenOidc.startLogin().catch(function (e) {
        alert(e.message || String(e));
      });
    });

    var outSpan = document.createElement("span");
    outSpan.className = "oidc-auth__user";

    var logoutBtn = document.createElement("button");
    logoutBtn.type = "button";
    logoutBtn.className = "oidc-auth__btn oidc-auth__btn--ghost";
    logoutBtn.textContent = "ログアウト";
    logoutBtn.addEventListener("click", function () {
      window.DogenOidc.logout();
    });

    var help = document.createElement("a");
    help.className = "oidc-auth__help";
    help.textContent = "認証の流れ";
    help.href = authFlowHref();

    wrap.appendChild(loginBtn);
    wrap.appendChild(outSpan);
    wrap.appendChild(logoutBtn);
    wrap.appendChild(help);
    nav.appendChild(wrap);

    function sync() {
      var tok = window.DogenOidc.getAccessToken();
      if (tok) {
        loginBtn.style.display = "none";
        outSpan.style.display = "";
        logoutBtn.style.display = "";
        outSpan.textContent = labelFromPayload(window.DogenOidc.parseIdPayload());
      } else {
        loginBtn.style.display = "";
        outSpan.style.display = "none";
        logoutBtn.style.display = "none";
      }
    }

    sync();
    window.addEventListener("storage", function (ev) {
      if (ev.key === "dogen_bearer_token") sync();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", render);
  } else {
    render();
  }
})();
