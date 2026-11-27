/**
 * LinkedIn Job Capture Bookmarklet for Mansi Job Hunt Engine
 *
 * Usage:
 * 1. Create a new Chrome bookmark named "Capture LinkedIn Job".
 * 2. Paste the minified `javascript:(function(){...})();` snippet below as the bookmark URL.
 * 3. While browsing a LinkedIn job posting in your logged-in Chrome tab, click the bookmark.
 * 4. It downloads a JSON file (e.g. `linkedin_job_4406539395.json`) ready for:
 *      python3 scripts/linkedin_ingest.py --from-json ~/Downloads/linkedin_job_4406539395.json
 */

javascript:(function(){
  try {
    var url = window.location.href;
    var idMatch = url.match(/currentJobId=(\d+)/) || url.match(/\/jobs\/view\/(?:[^/?#]*-)?(\d{6,})/);
    var jobId = idMatch ? idMatch[1] : "";
    var pick = function(selectors) {
      for (var i = 0; i < selectors.length; i++) {
        var el = document.querySelector(selectors[i]);
        if (el && el.innerText && el.innerText.trim()) return el.innerText.trim();
      }
      return "";
    };
    var title = pick([
      ".job-details-jobs-unified-top-card__job-title h1",
      ".job-details-jobs-unified-top-card__job-title",
      ".jobs-unified-top-card__job-title",
      "h1.t-24",
      "h1"
    ]);
    var company = pick([
      ".job-details-jobs-unified-top-card__company-name a",
      ".job-details-jobs-unified-top-card__company-name",
      ".jobs-unified-top-card__company-name a",
      ".jobs-unified-top-card__company-name"
    ]);
    var location = pick([
      ".job-details-jobs-unified-top-card__primary-description-container .tvm__text",
      ".jobs-unified-top-card__bullet",
      ".job-details-jobs-unified-top-card__tertiary-description-container"
    ]) || "Bengaluru";
    var description = pick([
      "#job-details",
      ".jobs-description-content__text",
      ".jobs-description__content"
    ]);
    var payload = {
      title: title,
      company: company,
      location: location,
      url: jobId ? ("https://www.linkedin.com/jobs/view/" + jobId + "/") : url,
      job_id: jobId,
      description: description,
      captured_at: new Date().toISOString()
    };
    var blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "linkedin_job_" + (jobId || Date.now()) + ".json";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  } catch (err) {
    alert("LinkedIn Job Capture failed: " + err.message);
  }
})();
