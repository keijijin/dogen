/**
 * 任意のデプロイ用設定（例: OpenShift では ConfigMap で上書き）。
 * window.DOGEN_CHAT_API_BASE = "https://dogen-api-....apps....";
 */
if (typeof window.DOGEN_CHAT_API_BASE === "undefined") {
  window.DOGEN_CHAT_API_BASE = "";
}
