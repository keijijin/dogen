/* 初回デプロイ用スタブ。OIDC 有効化は ./09-configure-oidc.sh がこの ConfigMap を上書きする。
 * 注意: このファイルを 06-dogen-web.yaml に埋め込まないこと（apply のたびに設定が消えるのを防ぐ）。 */
window.DOGEN_OIDC = {
  enabled: false,
  authority: "",
  client_id: "dogen-web",
  redirect_path: "/auth/callback.html",
  post_logout_redirect_path: "/",
  save_return_path: true,
  scope: "openid profile email",
};
