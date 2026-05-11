/**
 * main.js — frontend logic for the cloud resume site.
 *
 * - Fetches and displays the visitor counter from the API Gateway endpoint.
 * - Fills in the dynamic year in the footer.
 *
 * Set API_ENDPOINT to your deployed HTTP API URL once SAM has finished its
 * first deploy. The SAM stack outputs `VisitorCounterApiUrl` — copy that
 * value here, commit, and push to trigger the frontend pipeline.
 */

// TODO: replace with your deployed API Gateway URL (no trailing slash).
const API_ENDPOINT = "https://ix9pgk095h.execute-api.us-west-2.amazonaws.com/visitors";

/** Update the footer year. */
function setYear() {
  const el = document.getElementById("year");
  if (el) el.textContent = new Date().getFullYear();
}

/** Fetch + render the visitor count. */
async function loadVisitorCount() {
  const el = document.getElementById("visitor-count");
  if (!el) return;

  if (API_ENDPOINT.includes("REPLACE_ME")) {
    el.textContent = "—";
    el.title = "API endpoint not configured yet";
    return;
  }

  try {
    const res = await fetch(API_ENDPOINT, { method: "POST" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    el.textContent = Number(data.count).toLocaleString();
  } catch (err) {
    console.error("Visitor counter failed:", err);
    el.textContent = "—";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  setYear();
  loadVisitorCount();
});
