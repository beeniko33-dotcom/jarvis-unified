// Copy this file to jarvis-config.js in the deployed control-panel root.
// Use the isolated QA project's URL and publishable key only.
// Never place a Supabase secret/service_role key in this browser configuration.
window.JARVIS_CONFIG = Object.freeze({
  supabaseUrl: "https://<qa-project-ref>.supabase.co",
  supabasePublishableKey: "<qa-publishable-key>"
});
