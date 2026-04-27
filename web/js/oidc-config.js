/**
 * OIDC（公開クライアント + PKCE）用の設定。
 * 有効にする場合は enabled を true にし、authority / client_id を埋めてください。
 *
 * authority … Issuer の URL（末尾スラッシュ不要）。Quarkus の OIDC_AUTH_SERVER_URL と同一にする。
 *   Keycloak: https://<ホスト>/realms/<レルム名>
 *   他 IdP: 発行者 URL（多くの場合、.well-known/openid-configuration がこの下に付く）
 *
 * IdP 側で「公開クライアント（SPA）」を作成し、リダイレクト URI に
 *   <このサイトの origin>/auth/callback.html
 * を登録してください。トークンエンドポイントへのブラウザからの POST が CORS 許可されている必要があります。
 */
window.DOGEN_OIDC = {
  enabled: false,
  // 有効化する場合（例: Compose の Keycloak）: authority を Issuer URL に。OpenShift は ConfigMap で上書き。
  authority: "http://127.0.0.1:8180/realms/dogen",
  // Keycloak の realm import（deploy/local/keycloak/realm-dogen.json）に含まれる SPA クライアント
  client_id: "dogen-web",
  /** 例: "/auth/callback.html"（origin は自動付与） */
  redirect_path: "/auth/callback.html",
  /** ログアウト後に戻るパス（origin は自動付与） */
  post_logout_redirect_path: "/",
  /** ログイン開始前のパスを覚えておき、成功後に戻す（省略可） */
  save_return_path: true,
  // offline_access はレルム／クライアントでオフライン許可が無いと Keycloak が拒否するため含めない
  scope: "openid profile email",
};
