---
name: martech-audit
description: "Audit a website's marketing technology stack — GA4, GTM, pixels, data layer, consent, and schema markup — by inspecting live runtime behavior. Use this skill whenever the user wants to check a site's analytics setup, audit tracking pixels, diagnose GTM or GA4 issues, find broken tags, review a prospect's martech stack, do a 'data layer check,' assess tracking health, or run any kind of website analytics/tagging audit. Also trigger when the user mentions 'what pixels are on this site,' 'is their GA4 working,' 'check their tracking,' 'martech health check,' 'tag audit,' or 'pixel audit.' This skill produces a scored, bizdev-ready report that identifies broken tracking, missing events, and optimization opportunities."
---

# Martech Audit

Audit a website's marketing technology stack by inspecting live runtime behavior. Produces a scored report identifying broken tracking, missing events, consent gaps, and optimization opportunities.

## Why This Skill Exists

Most analytics audits look at static HTML or rely on the site owner granting GA4/GTM access. This skill goes further: it loads pages in a real browser, watches what network requests fire, inspects the dataLayer at runtime, and checks for JavaScript errors — catching problems that static analysis misses entirely. The output is a professional report designed to demonstrate expertise and open conversations with prospects.

## Tool Requirements

This skill works best with **chrome-devtools-mcp** (runtime browser inspection). The full audit depends on evaluating JavaScript in a live browser, observing network requests, and inspecting the dataLayer at runtime.

**If chrome-devtools-mcp is not available**, tell the user and offer a static-analysis fallback:
> "chrome-devtools-mcp is not available. I can run a static HTML analysis using curl/tavily_extract, which will catch ~60% of issues (tag presence, schema, OG tags, privacy policy gaps, cross-domain links, UTM redirect survival) but cannot verify: runtime dataLayer events, consent-gated tag loading, actual pixel fire rates, or JavaScript errors. Want me to proceed with static analysis?"

**If chrome-devtools-mcp is available but the site blocks headless browsers** (bot protection redirecting to Google, CAPTCHA walls, or blank pages), this is a different failure mode — the browser works but the site rejects it. Detect this by checking if the loaded page's domain matches the target domain after navigation. If it doesn't:
1. Note the bot protection in the report (this is itself a finding — overly aggressive bot blocking can affect SEO crawlers and analytics debugging tools)
2. Fall back to static HTML analysis via `curl` with a standard browser User-Agent string, or `tavily_extract`
3. Clearly caveat which checks could not be performed in the report header

Static analysis can still catch: GTM/GA4/pixel presence in HTML, schema markup, OG/meta tags, canonical URLs, privacy policy disclosure gaps, cross-domain link issues, form hidden field presence, UTM redirect survival (via HTTP header inspection), and multi-platform architecture fractures. These are often the highest-value bizdev findings anyway.

**Static analysis pixel detection precision warning:** In static mode, detect pixels by their initialization code (`fbq(`, `ttq.load(`, `pintrk(`, `_linkedin_partner_id`, `clarity(`, `hj(`), NOT by brand name mentions. A page mentioning "facebook.com/companyname" in a social link or having `facebook-domain-verification` in a meta tag does NOT mean the Facebook Pixel is present. Similarly, `tiktok.com/@handle` in a footer link is not the TikTok pixel. Many ad pixels are loaded by GTM at runtime and leave zero trace in the static HTML — in that case, report "pixel presence could not be confirmed (GTM-loaded, requires runtime verification)" rather than claiming the pixel is present or absent.

## Audit Workflow

### Phase 1: Scope and Crawl

1. **Get the target URL** from the user
2. **Map the site structure** using `tavily_map` — identify key page types:
   - Homepage
   - Service/product pages
   - Pricing page (if exists)
   - Contact/demo/booking page (the conversion page)
   - Blog (sample 1 post)
   - Privacy policy page (for compliance audit)

   **If `tavily_map` returns empty** (common with Shopify sites, bot-protected sites, or SPAs), fall back to HTML link extraction: fetch the homepage via `tavily_extract` or `curl`, then parse internal links from `<a href="...">` tags. This reliably produces the site structure even when crawlers are blocked.

3. **Select 4-6 pages** covering these types. Always include homepage + the primary conversion page + the privacy policy.

**Enterprise site architecture note:** Large sites often run different applications on different URL paths or subdomains (e.g., marketing site on `/` is AEM/WordPress, shop on `/shop/` is a React SPA, blog on `blog.` subdomain is HubSpot). These often have **completely different tagging stacks** — different GTM containers, different pixels, different analytics. Always include at least one page from each distinct application area to catch cross-architecture gaps. If the homepage has 9 GTM containers but the shop has 1, that's a critical finding about fractured measurement.

**Multi-site audit isolation:** When auditing multiple sites in a single session (e.g., `dell.com` then `apple.com`), use `isolatedContext` on `new_page` for each target to prevent cookie/state contamination between sites. Without isolation, cookies from Site A leak into Site B's browser context — requests from Dell's fraud detection gateway appeared on Apple's page in testing. Use: `new_page → url, isolatedContext: "dell"` for the first site, `new_page → url, isolatedContext: "apple"` for the second.

### Phase 2: Runtime Inspection (per page)

**CRITICAL: Do NOT dispatch parallel sub-agents for browser inspection.** All chrome-devtools-mcp tool calls share a single Chrome browser instance. Parallel agents cause tab selection confusion (agent A evaluates agent B's tab), navigation timeouts, stuck performance traces, and false findings. Inspect pages **sequentially** — one page at a time, in this session. Non-browser work (tavily_extract for privacy policy, curl for redirect checks) can be parallelized safely.

For each selected page, open it in chrome-devtools-mcp and run these checks. The order matters — some checks depend on the page being fully loaded.

#### Step 1: Load the page and verify it loaded correctly

```
new_page → url
```

**Bot-blocking detection (critical — do this FIRST before any other checks):**

After the page loads, immediately verify the loaded domain matches the target:
```javascript
evaluate_script: () => ({ loadedUrl: document.location.href, loadedHost: document.location.hostname })
```

If the hostname does NOT match the target domain (e.g., you navigated to `joinweightcare.com` but `document.location.hostname` is `www.google.com`), the site has **bot protection that redirects headless browsers**. Common culprits: Shopify's Blockify app, DataDome, PerimeterX, Cloudflare Bot Management, AWS WAF. Do NOT proceed with the JS eval — you'd be inspecting the wrong site.

Instead: fall back to static HTML analysis (see Tool Requirements above). Note the bot protection as a finding in the report — overly aggressive bot blocking can affect Googlebot rendering, SEO crawler tools, accessibility testing, and analytics debugging.

**If the domain matches**, continue with network request collection:
```
list_network_requests → resourceTypes: ["script", "ping", "xhr", "fetch"]
```

From the network requests, identify:
- **GTM containers** — requests to `googletagmanager.com/gtm.js` (extract container ID: `GTM-XXXXXXX`)
- **GA4 collection** — requests to `google-analytics.com/g/collect` or custom domains proxying to it
- **Server-side tagging** — if GA4/GTM requests go through a **first-party domain** (e.g., `tags.example.com` instead of `www.googletagmanager.com`), this indicates server-side tagging via Stape, Tealium, or similar. This is a significant positive finding worth calling out.
- **Third-party pixels** — see `references/pixel-signatures.md` for URL patterns
- **Failed requests** — any `net::ERR_*` status codes, 4xx, or 5xx responses on tracking scripts
- **Blocked requests** — `ERR_BLOCKED_BY_ORB`, `ERR_BLOCKED_BY_CLIENT` (ad blockers or CORS issues)

#### Step 1b: Wait for consent-gated tags to load

**Critical timing issue:** Many enterprise sites gate GTM containers and pixels behind consent callbacks (OneTrust, CookieLaw, Cookiebot). Tags only load AFTER the consent banner auto-resolves or the user accepts. If you run the JS eval immediately after page load, you'll see an empty tracking stack and produce a false "no analytics" finding.

Before running the Step 2 eval, **wait for consent resolution**:

1. Wait 5-8 seconds after initial page load for the consent banner to auto-resolve (many CMPs auto-grant for returning visitors or specific regions)
2. If the consent banner is still visible and blocking, use `click` to accept it (look for "Accept All" or "Allow All" buttons)
3. After accepting, wait another 3-5 seconds for the consent-gated tags to load
4. Verify by checking `list_network_requests` — you should see new requests to `googletagmanager.com/gtm.js`, pixel domains, etc. If the network request count hasn't grown significantly since Step 1, the page likely doesn't gate tags on consent (or consent was already resolved).

**How to detect consent-gated loading:** Look in the initial network requests for a consent SDK (e.g., `cdn.cookielaw.org`, `consent.cookiebot.com`) AND check if GTM/pixel requests are absent. If consent SDK is present but tracking scripts are missing, consent gating is almost certainly the cause — wait and retry.

#### Step 1c: Check for script deferral systems (WP Rocket, Partytown, etc.)

**Critical: false finding prevention.** Performance optimization plugins like WP Rocket, Partytown, Flying Scripts, and Perfmatters delay ALL JavaScript execution until the user interacts with the page (mouse move, click, scroll, keypress). If you run the JS eval on a page with script deferral active, every tracking check will return false/empty and you will produce a catastrophically wrong "no tracking" finding.

**How to detect:** The eval script now includes a `scriptDeferral` field. If `scriptDeferral.detected` is true but runtime globals (`gtmObject`, `gtagExists`) are empty, tracking is present but dormant. Additionally, look for these signals:
- Very few network requests for tracking scripts (only 1-2 instead of the expected dozens)
- Preconnect hints for `googletagmanager.com`, `clarity.ms`, etc. but no corresponding script loads
- `<noscript>` tags containing GTM iframe snippets but no corresponding `<script>` loads
- Inline scripts containing GTM/GA4/Consent Mode code stored as base64 `data:` URIs

**How to resolve:** Simulate user interaction before running the eval:
```
evaluate_script: () => {
  document.dispatchEvent(new MouseEvent('mousemove', {bubbles: true}));
  window.dispatchEvent(new MouseEvent('mousemove'));
  return 'interaction simulated';
}
```
Wait 5-8 seconds for deferred scripts to execute, then verify with `list_network_requests` that tracking scripts have loaded. Only then run the full eval.

**Report the deferral as a finding:** Script deferral is a performance optimization, not necessarily a problem. But note that users who view the page without interacting (reading on mobile, using keyboard navigation) are invisible until they interact. The initial page_view is delayed. Recommend excluding GTM, consent defaults, and critical analytics from the deferral.

#### Step 2: Inspect the JavaScript environment

Run `evaluate_script` with the canonical eval script from `scripts/martech-eval.js`. Read the file and pass its contents to `evaluate_script`. **Do not inline a copy of this script — always read from the file to avoid drift.**

```
evaluate_script: <contents of scripts/martech-eval.js>
```

The script collects: GTM/GA4 containers (first-party vs third-party classification), dataLayer contents and quality, cookies, all major pixels (25 vendors), alternative TMS (Tealium, Adobe Launch/DTM), Adobe analytics stack, B2B tools (6sense, Demandbase, Clearbit, etc.), ABM integration health, consent state (9 CMPs + Consent Mode v2 with region scoping), OG/Twitter Card tags, schema markup, cross-domain links, forms with hidden field values, video embeds with tracking API detection, iframe inventory, postMessage listeners, CTA tracking attributes, chatbot auto-interaction events, LinkedIn Insight Tag conversions, Pardot domain check, Google Ads Enhanced Conversions, page indexability, HubSpot form embed type, Cloudflare Zaraz, SPA framework detection, CRM cookie scoping, rogue scripts outside GTM, dataLayer sequencing/race conditions, YouTube iframe cookie risk, and Shopify Web Pixel sandbox detection.

<details><summary>Key fields produced (click to expand)</summary>

| Field | Description |
|-------|-------------|
| `tagInstallations` | GTM/GA4 IDs with first-party vs third-party classification |
| `dataLayer`, `dataLayerQuality` | Full dataLayer contents, PII scan, ecommerce validation |
| `dataLayerSequencing` | Race condition detection (business data arriving after gtm.js) |
| `pixels` | 25 pixel vendors detected (FB, LinkedIn, Twitter, TikTok, Hotjar, HubSpot, Clarity, Segment, Heap, FullStory, Intercom, Google Ads, Bing, Marketo, Pinterest, Reddit, Snapchat, Taboola, The Trade Desk, Quantcast, Yahoo, LiveRamp, TVSquared, Connexity, D&B) |
| `consent`, `consentModeState` | 9 CMPs + Consent Mode v2 defaults/updates with region scoping |
| `ogTags`, `meta` | OG/Twitter Card validation, canonical, robots, description |
| `crossDomainLinks`, `crossDomain` | Conversion-related external links + _gl parameter check |
| `forms`, `formHiddenFieldValues` | Hidden tracking fields with names AND values |
| `videoEmbeds` | YouTube/Vimeo/Wistia with enablejsapi/api tracking API check |
| `iframes`, `hasPostMessageListener` | All iframes + postMessage listener detection |
| `scriptsOutsideGTM` | Tracking scripts bypassing Consent Mode |
| `shopifyWebPixels` | Shopify Web Pixel sandbox detection (count, IDs) — flags when pixels load in isolated iframes invisible to allScriptText |
| `linkedinInsightTag` | Base tag vs conversion event detection |
| `pardotTracking` | Third-party vs first-party domain check |
| `googleAdsEnhanced` | Enhanced Conversions config and user data in dataLayer |
| `pageIndexability` | Robots meta / noindex for thank-you page check |
| `cloudflareZaraz` | Edge-side tag management detection |
| `spaFramework` | Next.js, Nuxt, React, Angular detection |
| `hubspotForms` | Iframe vs JS embed type (iframe loses attribution) |

</details>

Previously this script was inlined here. It now lives at `scripts/martech-eval.js` as the single source of truth — both this skill and the `check_findings.py` CLI consume the same field contract.

**IMPORTANT:** After the eval completes, the result is a JSON object. Do NOT modify the script — if you need additional data, collect it in a separate `evaluate_script` call.

<!-- Old inline eval removed — canonical source is now scripts/martech-eval.js -->

#### Step 2a: Shopify Web Pixel sandbox reconciliation

**Shopify sites only.** Shopify's Web Pixels system loads advertising and analytics pixels (TikTok, Google Ads, Bing, Reddit, Snapchat, etc.) inside sandboxed `<iframe>` elements. These iframes run in isolated JavaScript contexts — the eval script **cannot detect pixels loaded this way**. The `shopifyWebPixels` field in the eval output flags when these sandboxes are present.

If `shopifyWebPixels.detected` is true:

1. **Do not trust `pixels.*: false` at face value** — a pixel showing `false` in the eval may still be active via a Shopify web pixel. Always cross-reference with `list_network_requests` before reporting a pixel as absent.
2. **Expect triple-tagging, not just double** — Shopify's web pixel system fires its own `page_view` and conversion events independently of both hardcoded gtag.js and GTM. If the eval shows `doubleTagging: true` on a Shopify site, the actual situation is likely triple-counting (hardcoded + GTM + Shopify web pixel).
3. **SecurityError console spam is expected** — Shopify web pixel sandboxes generate `SecurityError: Failed to read 'matchMedia' from Window` errors. These are platform noise, not site bugs. Note them as informational, not as a finding.
4. **Reconcile pixel detection with network evidence** — For each pixel domain found in `list_network_requests` but not in the eval's `pixels` object, add it to the detected tools list in the report. Common Shopify web pixel-loaded platforms: TikTok, Google Ads (via Shopify's own conversion pixel), Bing, Reddit, Snapchat.
5. **Check for additional Shopify ecosystem tools in network requests** — SafeOpt (`manage.safeopt.com`), Mountain.com (`px.mountain.com`, `dx.mountain.com`), and Shopify's own attribution (`trekkie.storefront`) are common on Shopify sites and won't appear in the eval.

#### Step 2b: Consent Deep Checks (run on homepage, separate browser context)

These checks require observing the page in **pre-consent** and **post-consent** states. Because Step 1b already accepted consent (so tags would load for the main eval), this step uses a **fresh browser page** to get a clean slate.

**Setup — open a fresh page and clear consent state:**
```
new_page → homepage URL
```
**Critical: clear consent cookies before checking.** A new tab shares cookies with the main audit page (where Step 1b already accepted consent). Before checking pre-consent state, run:
```javascript
evaluate_script: () => {
  // Delete known CMP cookies to simulate a first-time visitor.
  // CMPs scope cookies to the root domain (.example.com), not the hostname
  // (www.example.com). Try all possible domain levels to handle both simple
  // domains (www.example.com) and ccTLDs (www.company.co.uk, shop.brand.com.au).
  const parts = location.hostname.split('.');
  // Build list of candidate domains: hostname itself + all parent domains
  // e.g., for "www.company.co.uk" → [".www.company.co.uk", ".company.co.uk", ".co.uk"]
  const domainCandidates = [];
  for (let i = 0; i < parts.length - 1; i++) {
    domainCandidates.push('.' + parts.slice(i).join('.'));
  }
  const cmpCookies = ['OptanonConsent', 'OptanonAlertBoxClosed', 'CookieConsent',
    'CookieConsentPolicy', 'osano_consentmanager', 'osano_consentmanager_uuid',
    'cookielawinfo-checkbox-', 'termly_gtm_template_default_consents',
    'euconsent-v2', '__cmpcc', 'notice_preferences', 'notice_gdpr_prefs'];
  document.cookie.split(';').forEach(c => {
    const name = c.trim().split('=')[0];
    if (cmpCookies.some(p => name.startsWith(p))) {
      // Try host-only (no domain) plus every parent domain level
      // This handles .example.com, .co.uk, .com.au, etc.
      document.cookie = name + '=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/';
      domainCandidates.forEach(d => {
        document.cookie = name + '=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/;domain=' + d;
      });
    }
  });
  // Also clear localStorage consent keys (some CMPs store state there too)
  try {
    Object.keys(localStorage).filter(k =>
      /optanon|cookieconsent|osano|termly|euconsent|cmp/i.test(k)
    ).forEach(k => localStorage.removeItem(k));
  } catch(e) {}
  return 'consent cookies cleared';
}
```
Then **reload the page** (`navigate_page` → same URL) so the CMP re-initializes without its cookie. Now the page is in true pre-consent state.

If `new_page` fails (e.g., browser context limit), skip Step 2b consent deep checks entirely and note "Consent deep checks skipped — could not open a fresh browser context" in the report.

**State 1 — Pre-consent (fresh page, no interaction):**
Before clicking anything on the consent banner in this new page:

1. Check `list_network_requests` for tracking domains (google-analytics.com, facebook.net, snap.licdn.com, bat.bing.com, analytics.tiktok.com, hotjar.com, clarity.ms, etc.). If tracking requests fired before the user interacted with the banner, flag as **decorative banner** — the consent banner is cosmetic.
2. Check cookies via `evaluate_script`: `() => document.cookie` — if `_ga`, `_fbp`, `_gcl_au`, `li_fat_id`, `_hjSession` or similar tracking cookies exist before consent, those scripts dropped cookies pre-consent.
3. Run a quick consent state eval: `evaluate_script` to read `consentModeState.defaults`. If `ad_storage` or `analytics_storage` defaults to `"granted"`, this is a misconfiguration for EU traffic — consent should start as `"denied"`.

**State 2 — Post-consent (accept all):**
After recording pre-consent state, click "Accept All" (or equivalent) on the consent banner in the same fresh page, wait 3-5 seconds, then:

1. Re-run `list_network_requests`. Compare to pre-consent. New tracking requests should appear (GA4, pixels, etc.). If the request count barely changed, tags may be **over-blocked** — consent was granted but tags never actually started firing.
2. Check if a `consent` `update` event appeared in the dataLayer with states changed to `"granted"`. If no update event fired, the CMP isn't communicating with GTM.
3. Navigate to a second page within this fresh context. Check if the consent banner re-appears. If it does, the CMP cookie didn't persist — **consent amnesia**. Check for the CMP cookie: `OptanonConsent` (OneTrust), `CookieConsent` (Cookiebot), `osano_consentmanager` (Osano).

**Consent Mode Basic vs Advanced:**
After declining consent (on a separate test, or if observable from pre-consent state):
- If GA4 collect requests still fire but with `gcs=G100` or similar denied-state parameters and no cookies — this is **Advanced mode** (cookieless pings, good for modeling). This is the correct implementation.
- If zero GA4 requests fire when consent is denied — this is **Basic mode**. The site loses all behavioral modeling and conversion modeling for non-consenting users. This is unnecessary data loss.

**sGTM consent forwarding** (if server-side tagging detected):
Inspect GA4 collect requests going to the first-party sGTM endpoint. Look for `gcs` (Google Consent State) and `gcd` (Google Consent Default) parameters in the URL. If these parameters are missing, the server container has no way to respect consent — it forwards data to downstream platforms regardless of the user's choice.

**Cleanup:**
```
close_page → the fresh consent-check page
```
Return to the main audit page (use `select_page` if needed) and continue with Step 3.

Record all consent deep-check findings in your notes for the report. The deterministic checker (Phase 3.5) will flag the programmatic consent issues; this step catches the behavioral ones that require multi-state observation.

#### Network Evidence Fields

Before saving each page's JSON for the deterministic checker, add these fields derived from `list_network_requests` (Step 1). The JS eval can't see network requests, so these bridge the gap:

```json
{
  "networkEvidence": {
    "ga4CollectSeen": true,
    "ga4PropertyIds": ["G-XXXXXXX"],
    "gtmJsRequests": ["GTM-XXXXX"],
    "serverSideTagging": false,
    "sgtmDomain": null
  }
}
```

- **`ga4CollectSeen`**: `true` if ANY request to `google-analytics.com/g/collect` or a first-party `*/g/collect` endpoint was observed. This is the authoritative signal for GA4 presence — it catches GTM-managed GA4 that has no `G-XXXXXXX` in page source.
- **`ga4PropertyIds`**: List of GA4 measurement IDs extracted from collect request URLs (the `tid` parameter, e.g., `G-XXXXXXX`). Captures property IDs even when GTM-managed, enabling cross-page fractured measurement detection.
- **`gtmJsRequests`**: List of GTM container IDs extracted from `googletagmanager.com/gtm.js?id=GTM-XXX` network requests. Catches dynamically loaded containers invisible to DOM scanning (SPAs, consent-gated injection).
- **`serverSideTagging`**: `true` if GA4/GTM requests route through a first-party domain instead of Google's.
- **`sgtmDomain`**: The first-party domain if server-side tagging detected (e.g., `tags.example.com`), null otherwise.

#### Step 3: Check for JavaScript errors

```
list_console_messages → types: ["error", "warn"]
```

Look specifically for:
- **Tracking-related errors**: `fbq is not defined`, `gtag is not defined`, `dataLayer is not defined`, `ga is not defined`, `analytics is not defined`, `Uncaught TypeError` on tracking functions
- **Network/CORS errors**: blocked requests to tracking endpoints
- **Consent errors**: CMP initialization failures
- **GTM errors**: "Tag failed to fire", custom template errors
- **CSP blocking martech tools**: Look for `Refused to load the script` errors — these mean the site's Content Security Policy is preventing a legitimate marketing tool from loading. The company is paying for software that literally cannot execute. Extract the blocked domain from the error message to identify which tool is affected.

These are the **highest-value findings for bizdev** — a JavaScript error silently breaking tracking is exactly the kind of thing a site owner doesn't know about but cares deeply about once told.

#### Step 4: Detect server-side vs client-side tagging

Check **both** the JS eval output (`serverSideGtm` field) AND network request URLs:

**From the JS eval (`serverSideGtm` field):**
The eval script detects sGTM by checking if the GTM bootstrap snippet's `src` points to a non-Google domain. This catches **Stape's obfuscated loader pattern** — where the GTM script loads from a first-party domain (e.g., `tags.example.com/xZfzofixhj.js`) with a randomized filename and base64-encoded container ID instead of the standard `www.googletagmanager.com/gtm.js?id=GTM-XXXXX`. If `serverSideGtm.detected` is true, report the domain and whether the loader is obfuscated.

**From network requests (runtime only):**

| Pattern | Interpretation |
|---------|---------------|
| Requests to `www.googletagmanager.com/gtm.js` | Client-side GTM (standard) |
| Requests to `custom-domain.com/gtm.js` or randomized filename | Server-side GTM via custom domain |
| GA4 collect requests to `google-analytics.com/g/collect` | Client-side GA4 collection |
| GA4 collect requests to `custom-domain.com/g/collect` or proxied paths | Server-side GA4 collection |
| Both custom-domain AND google-analytics.com requests | Hybrid (server-side + client fallback) |
| `sst.` parameters in GA4 collect URLs (e.g., `sst.tft=`, `sst.lpc=`) | Confirms server-side tagging is active |

**Static analysis note:** sGTM can be partially detected from HTML alone — the GTM snippet's `src` URL reveals the domain. But verifying that GA4 collect requests actually route through the sGTM endpoint requires runtime network inspection. If the eval script reports `serverSideGtm.detected: true` but you can't verify collect routing, note "sGTM loader detected (first-party domain: X), collect routing not verified."

Server-side tagging is a **significant positive** — it improves data quality, bypasses ad blockers, and enables better consent handling. Call it out prominently when found.

#### Step 5: Audit the privacy policy page

Navigate to the privacy policy page (usually `/privacy`, `/privacy-policy`, or linked in the footer). This is a compliance audit, not a legal review — check for:

1. **Disclosed third-party tools** — Does the policy mention GA4, GTM, any pixels found, B2B reveal tools, email marketing platforms, and session recording tools? Each tool that collects user data should be disclosed.
2. **Undisclosed tools** — Compare the tools you detected in Phase 2 against what the privacy policy mentions. Any gap is a finding. B2B reveal tools (RB2B, Leadfeeder, etc.) that de-anonymize visitors are particularly important to disclose and are frequently missing.

   **Critical: search the policy PROSE, not the page HTML.** Privacy policy pages contain the site's own tracking scripts (GTM snippet, pixel code, Shopify app blocks) alongside the policy text. If you search the full page HTML for "klaviyo," you'll find it in a `<script>` tag and falsely conclude it's disclosed — when it's actually just the Klaviyo JS loading on the page. Extract the policy body text first (the content inside the main article/policy div, stripped of `<script>` and `<style>` tags), then search that text for tool mentions. Also exclude navigation menus and footers, which often contain social media links that match brand names (e.g., "facebook.com/company" in a footer link is not a disclosure of the Facebook Pixel).
3. **Cookie disclosure** — Does the policy list specific cookie names and purposes? Are the cookies you found in the audit accounted for?
4. **Data processor disclosure** — Are server-side tagging providers (Stape.io, etc.) disclosed as data processors?

**Important:** Many sites have a privacy "hub" or "central" page that links to sub-policies (e.g., `/privacy/privacy-central.html` → links to cookie policy, data processing, etc.). If the first privacy page you find is a landing page without specific tool disclosures, follow links to the actual detailed privacy statement or cookie policy. The tool disclosure check should be done against the most detailed policy document, not the hub page.

This step is a high-value bizdev finding because privacy policy gaps are concrete, actionable, and carry legal risk the site owner will want to fix.

#### Step 6: Validate OG/Twitter Card meta tags

On each page, check the `ogTags` data from Step 2 for common bugs:
- `og:image:type` should be `image/png` or `image/jpeg` (not `image/.png` — a common typo)
- `twitter:creator` should be a valid handle with no spaces (e.g., `@CompanyName`)
- Blog posts should use `og:type = "article"`, not `"website"`
- Check that `og:description` is unique per page (not the same sitewide default)

#### Step 7: Server-side tagging deep checks (if sGTM detected)

When server-side tagging is detected in Step 4, run these additional checks:

1. **Transport URL verification** — Are GA4 collect requests actually going through the first-party domain, or bypassing it to `google-analytics.com` directly? If both paths exist, a plugin or hardcoded snippet may be undermining the sGTM setup.
2. **Consent forwarding** — Check the `gcs` (Google Consent State) parameter in collect requests to the sGTM endpoint. If the value doesn't change between consent-granted and consent-denied states, consent is not being forwarded to the server container — meaning the server fires tags regardless of user choice. This is a compliance exposure.
3. **Cookie domain alignment** — Note the sGTM subdomain (e.g., `tags.example.com`). If it resolves to a different IP range than the main domain, Safari ITP will cap cookies to 7 days instead of the intended 2 years, undermining the entire purpose of server-side cookie setting. Flag this as a finding when the sGTM subdomain appears to use a CNAME to a third-party (Stape, Addingwell) rather than an A record pointing to the same infrastructure.

#### Step 8: Conversion page deep checks

On the primary conversion page (contact/demo/booking), run these additional checks:

1. **Form validation vs conversion firing** — If there's a form, try to identify whether conversion events fire on button click (wrong — counts failed validations) or on successful submission. Check if the form has client-side validation and whether a dataLayer event or network request fires when validation fails.
2. **Cross-domain link tracking** — Check `crossDomainLinks` from the JS eval. Any link to a booking tool (Calendly, HubSpot meetings), payment processor (Stripe checkout), or app domain should include the `_gl` linker parameter for GA4 session continuity. Missing `_gl` = broken attribution on every conversion. **Same root domain exception:** If the conversion page is on a subdomain of the main site (e.g., `try.example.com` vs `www.example.com`), GA4 cookies (scoped to `.example.com` by default) are shared automatically between all subdomains. No `_gl` linker parameter is needed. Verify by checking that the `_ga` cookie value (Client ID) matches on both domains. Do NOT flag missing `_gl` parameters as broken cross-domain tracking when both domains share the same registrable domain — this is NOT the same as two entirely separate domains (e.g., `example.com` -> `calendly.com`).
3. **Hidden field capture** — Check `forms.hiddenFields`. Well-instrumented forms capture `gclid`, `utm_source`, `utm_medium`, `utm_campaign` in hidden fields for CRM pass-through. Missing hidden fields = offline conversion import will fail, Google Ads can't optimize toward revenue.
4. **Iframe event listeners** — If the conversion page embeds a third-party iframe (Calendly, Google Calendar, HubSpot), check page source for `addEventListener('message', ...)` handlers that listen for booking/submission events and push to dataLayer. Without this, the iframe is a black box. **Google Calendar Appointments** is a particularly common pattern — it loads the full Google Calendar scheduling widget inside an iframe (`calendar.google.com/calendar/appointments/...`), which pulls in 15+ JavaScript chunks from `gstatic.com` plus reCAPTCHA. The booking action happens entirely inside Google's domain, so there is no URL-based conversion detection possible. The only way to capture the booking event is via `postMessage` from the iframe — verify both that a listener exists AND that it actually pushes a conversion event to the dataLayer.

#### Step 9: Tag performance audit (run once on homepage)

Tags are a leading cause of page speed degradation, and site owners rarely connect "we added a pixel" to "our Core Web Vitals tanked." Run this on the homepage (highest traffic page):

1. **Run a performance trace** via `performance_start_trace` (with `reload: true`, `autoStop: true`) on the homepage. This captures real LCP, CLS, and TTFB from the trace. After the trace completes, use `performance_analyze_insight` with the `ThirdParties` insight to get per-domain transfer sizes and main-thread blocking time, and `RenderBlocking` to identify render-blocking requests.

   **Why not `lighthouse_audit`?** The `lighthouse_audit` tool has a known CDP session conflict (ChromeDevTools/chrome-devtools-mcp#1797) that causes `Network.emulateNetworkConditions timed out` errors. This is not a timeout duration issue — it's a bug where the MCP server's existing CDP session holds the Network domain, preventing Lighthouse's internal session from using it. The performance trace approach is more reliable and provides real (not simulated) metrics. If you need a full Lighthouse report, run it via CLI: `npx lighthouse <url> --output=json --chrome-flags="--headless"`.

2. **Analyze network request timing** — from `list_network_requests`, look for:
   - **Render-blocking scripts** — any tracking script loaded synchronously in `<head>` without `async` or `defer`. GTM should always be loaded async. If gtag.js or any pixel script lacks `async`, it blocks rendering.
   - **Script load waterfall** — Tag A loads Tag B which loads Tag C (common when GTM loads a pixel, which loads its own SDK, which loads a data partner). Each hop adds latency. Count the chain depth.
   - **Large script payloads** — GTM containers over 100KB (compressed) suggest bloat. Individual pixel scripts over 50KB are worth flagging.
   - **Slow third-party responses** — any tracking endpoint with TTFB > 500ms or total load time > 1s.

3. **Check for CLS-causing injections** — dynamically injected elements from tags are a top cause of Cumulative Layout Shift:
   - Consent banners that push page content down on load
   - Chat widgets (Intercom, Drift, Crisp) that inject floating elements
   - A/B testing tools (Optimizely, VWO) that cause a "flash of original content" (FOOC) before applying variants
   - Remarketing iframes injected below the fold

4. **Evaluate tag firing timing** — from the dataLayer and network requests, assess when tags fire:

   | Trigger Timing | Performance Impact | When to Use |
   |---------------|-------------------|-------------|
   | Page View (immediate) | Highest — blocks during page parse | Only for critical analytics (GA4 pageview) |
   | DOM Ready | Medium — fires after HTML parsed but before images/fonts | Okay for non-critical tracking |
   | Window Loaded | Low — fires after everything loaded | Best for pixels, remarketing, session recording |
   | Custom Event | Minimal — fires only when needed | Best for conversion tags, click tracking |

   If non-essential tags (heatmaps, session recording, remarketing pixels, chat widgets) fire on "Page View" instead of "Window Loaded" or later, flag this — they're competing with the page render for no reason.

5. **Summarize the performance impact** — produce a mini-table:

   | Metric | Value | Impact from Tags |
   |--------|-------|-----------------|
   | LCP | X.Xs | [Any tag-caused delay? Check LCP breakdown render delay] |
   | TTFB | Xms | [Server response time] |
   | CLS | X.XX | [Any tag-injected layout shifts?] |
   | Third-party transfer | X kB | [From ThirdParties insight — total transfer size] |
   | Third-party main thread | Xms | [From ThirdParties insight — total blocking time] |
   | Third-party domains | X | [From thirdPartyTrackingDomains] |
   | Render-blocking scripts | X | [From RenderBlocking insight] |

#### Step 10: UTM parameter survival check

This is one of the most impactful checks in the entire audit. Redirect chains that strip UTM parameters silently inflate "Direct" traffic in GA4 — every email click, paid ad, social post, and partner link appears to drive zero results. The site owner has no idea because GA4 only shows the *absence* of attribution, not the cause. Most B2B SaaS sites have 2-4 redirect hops on their primary landing pages (HTTP→HTTPS, www normalization, trailing slash), and any hop can strip the query string.

Run this on the **homepage** and the **primary conversion page** (contact/demo/pricing):

**Step 10a: Navigate with test parameters**

Append test parameters to the page URL and navigate:
```
navigate_page → url: "https://example.com/?utm_source=audit_test&utm_medium=test&utm_campaign=martech_audit&gclid=test_click_id"
```

Wait for the page to fully load (3-5 seconds), then run:
```javascript
() => ({
  finalUrl: document.location.href,
  finalSearch: document.location.search,
  // Did UTMs survive?
  utmSurvived: document.location.search.includes('utm_source=audit_test'),
  gclidSurvived: document.location.search.includes('gclid=test_click_id'),
  // How many redirects happened? (Performance API tracks redirect count)
  redirectCount: performance.getEntriesByType('navigation')[0]?.redirectCount || 0,
})
```

**Step 10b: Diagnose the redirect chain**

If UTMs were stripped (`utmSurvived: false`), identify *which* redirect hop caused it. Check the network requests for the page navigation — look for 301/302 status codes. Common culprits in order of frequency:

| Redirect Type | Pattern | Example |
|--------------|---------|---------|
| Trailing slash | `/page?utm=x` → `/page/?utm=x` | Often strips query string |
| www normalization | `www.` ↔ non-`www.` | Server rewrite drops params |
| HTTP→HTTPS | `http://` → `https://` | Misconfigured rewrite rule |
| Marketing platform | `/go/campaign` → `/landing-page` | Short URL / redirect service |
| SPA client-side | React Router / Next.js | `window.location` replaces URL without preserving `search` |

If the page uses client-side routing (React, Next.js, Vue), the redirect won't appear in network requests — the URL change happens in JavaScript. Compare the navigated URL to `document.location.href` to detect this.

**Step 10c: Check GA4 received the parameters**

After the page loads with UTMs, check `list_network_requests` for GA4 collect requests (`google-analytics.com/g/collect` or the sGTM first-party endpoint). Look for `utm_source`, `utm_medium`, `utm_campaign` in the request URL or payload. If UTMs are in `document.location.search` but missing from the GA4 collect request, the analytics tag loaded *after* a client-side redirect stripped the params.

**Step 10d: Check gclid persistence**

Run `evaluate_script` to check if the `gclid` value was captured:
```javascript
() => {
  const gclid = 'test_click_id';
  const cookies = document.cookie;
  const gclidInCookie = cookies.includes(gclid) || cookies.includes('_gcl_aw');
  let gclidInStorage = false;
  try { gclidInStorage = Object.values(localStorage).some(v => v.includes(gclid)); } catch(e) {}
  const gclidInHiddenFields = Array.from(document.querySelectorAll('input[type=hidden]'))
    .some(f => f.value === gclid || (f.name.toLowerCase().includes('gclid') && f.value));
  return { gclidInCookie, gclidInStorage, gclidInHiddenFields };
}
```

If none of these are true, offline conversion import and Google Ads Enhanced Conversions will fail — Ads can't match conversions back to the click that drove them.

**Step 10e: Re-check hidden form fields with UTMs present**

If the page has forms with hidden attribution fields (gclid, utm_source, etc.), re-run the `formHiddenFieldValues` portion of the eval now that UTM params are in the URL. Save the result as `formHiddenFieldValuesWithUtms` in the page JSON. This two-phase check prevents false positives: many forms intentionally populate hidden fields only when URL params exist or on submit. If fields are empty *without* UTMs but populated *with* UTMs, that's working-as-designed. Only flag as broken if fields remain empty even with UTMs in the URL.

**Step 10f: Record structured results**

Save these fields in the page JSON for the deterministic checker and report:
```json
{
  "utmSurvival": {
    "tested": true,
    "utmSurvived": true/false,
    "gclidSurvived": true/false,
    "redirectCount": 0-N,
    "finalUrl": "...",
    "strippedBy": "trailing-slash|www-normalization|https-upgrade|spa-routing|unknown|null",
    "ga4ReceivedUtms": true/false,
    "gclidPersisted": true/false
  }
}
```

### Phase 3: Cross-Page Analysis

After inspecting all pages, look for:

1. **Consistency** — Does GTM/GA4 load on every page? Same container IDs?
2. **Double-tagging** — Check `tagInstallations` across pages. Use `firstPartyGtmIds` and `firstPartyGa4Ids` (not the `gtmIds`/`ga4Ids` totals) to avoid false positives from vendor-loaded containers. Third-party scripts (HubSpot, Drift, ad pixels, etc.) sometimes load their own GTM containers — these show up in `thirdPartyGtmIds` and are informational, not a site-owner issue. If `doubleTagging` is true (first-party hardcoded gtag.js alongside first-party GTM), every event is counted twice. If `multipleGtmContainers` is true, two first-party containers share one dataLayer — duplicate event processing and conflicting triggers. These are among the highest-impact findings because they silently inflate every metric.
3. **DataLayer gaps** — Is the dataLayer only firing system events (`gtm.js`, `gtm.dom`, `gtm.load`) with no custom events? This is the most common problem.
4. **DataLayer quality** — Check `dataLayerQuality`: Is there PII in the dataLayer (email addresses, phone numbers)? This violates GA4 TOS and GDPR. Are purchase events missing `transaction_id` (enables duplicate revenue on page refresh)? Is `currency` present and a valid ISO code?
5. **Ghost preconnects** — DNS-prefetch/preconnect hints for pixel domains that aren't actually loading (e.g., preconnect to `connect.facebook.net` but no Facebook pixel found). These reveal planned-but-unimplemented integrations.
6. **Conversion page gaps** — Does the contact/demo/booking page have form submission tracking? If it uses a third-party embed (Calendly, Google Calendar, HubSpot), is cross-domain tracking configured? Are hidden form fields capturing tracking params for CRM pass-through?
7. **CTA tracking** — Are call-to-action buttons firing events, or are they plain links with no tracking?
8. **Custom/attribution cookies** — Did you find non-standard cookies (in `customCookies`) that suggest custom attribution tracking, A/B testing, or other systems? Report what they appear to do.
9. **B2B tool status** — If a B2B reveal tool was detected, is it actually working (loaded successfully) or broken (blocked by ORB/CORS)? Identify the specific vendor and account ID when possible.
10. **Privacy policy gaps** — Cross-reference all detected tools against what the privacy policy discloses. List any undisclosed tools as a compliance finding.
11. **Tag sprawl** — Check `thirdPartyTrackingDomains` count. More than 15 unique third-party domains on a single page is a performance red flag. Identify any domains for tools/vendors the company likely no longer uses (zombie tags).
12. **sGTM effectiveness** — If server-side tagging was detected, did the deep checks (Step 7) reveal any issues with transport routing, consent forwarding, or cookie domain alignment?
13. **Video embeds missing tracking APIs** — Check `videoEmbeds` for YouTube/Vimeo iframes without `enablejsapi=1` or `api=1`. Without the API, GA4 Enhanced Measurement can't track video engagement — no `video_start`, `video_progress`, or `video_complete` events.
14. **CRM cookie subdomain scoping** — Check `crmCookieScope.found` for HubSpot/Marketo/Pardot cookies. If the site uses subdomains (blog, app, docs), flag that these cookies should be scoped to `.domain.com` not the host. Host-only scoping means the same buyer looks like separate anonymous visitors on each subdomain.
15. **Chatbot inflating engagement metrics** — Check `chatAutoInteraction.earlyEventsOnLoad` for chat-related events that fire before any user interaction. If Drift/Intercom/Qualified push interaction events on page load, GA4 engagement rate goes to ~100% and bounce rate drops to ~0%, hiding underperforming pages.
16. **ABM/intent tool integration** — If B2B tools (6sense, Demandbase, Clearbit, Bombora) are detected, check `abmIntegration`: Did the vendor's dataLayer event fire? Is the match/profile populated or null/unidentified? Are custom dimensions being pushed (`customDimensionHints > 0`)? A tool that loads but doesn't push data to GA4 means the $30-100K/year investment is invisible to analytics — the company can't segment GA4 reports by account, intent, or buying stage.
17. **LinkedIn Insight Tag pageview-only** — Check `linkedinInsightTag`. If `hasInsightTag` is true but `hasConversionCall` is false, the site installed LinkedIn's tag for audience building but never set up event-specific conversions. LinkedIn can see who visited but can't optimize toward demo requests or signups — making expensive LinkedIn ad spend optimize toward pageviews instead of pipeline.
18. **Pardot third-party tracking domains** — Check `pardotTracking`. If `usesThirdPartyDomain` is true, the site loads Pardot tracking via `pi.pardot.com` or `go.pardot.com` instead of a branded first-party domain. Safari ITP and Firefox ETP cap these cookies, degrading visitor tracking for 30-40% of traffic. Prospects don't realize their Pardot data quality degrades every time Apple ships a browser update.
19. **Google Ads Enhanced Conversions missing** — Check `googleAdsEnhanced` on conversion pages. If `hasGoogleAds` is true but `hasEnhancedConfig` and `hasUserDataInDL` are both false, the site isn't sending hashed user data with conversion events. In a post-cookie world, this means 15-25% of conversions go unmatched, Smart Bidding optimizes poorly, and CPA inflates.
20. **Thank-you pages indexable** — Check `pageIndexability` on thank-you/confirmation pages. If `hasNoindex` is false, the page is crawlable by search engines and reachable by direct URL. Bot traffic and accidental visits inflate conversion counts, pollute remarketing audiences, and may expose workflow details.
21. **Hidden attribution fields empty** — Check `formHiddenFieldValues` on conversion pages. If hidden fields exist (names like gclid, utm_source, etc.) but their values are empty strings, the JavaScript that should populate them is broken or missing. The CRM looks attribution-ready but every lead record has blank source data. Offline conversion import silently fails.
22. **UTM parameter stripping** — Check `utmSurvival` from Step 10. If `utmSurvived` is false, flag this as critical. Include `strippedBy` (the redirect type that caused it) and `redirectCount` in the finding. If `gclidSurvived` is false, add that Google Ads offline conversion import is also broken. If `ga4ReceivedUtms` is false even when `utmSurvived` is true, the analytics tag loaded after a client-side redirect stripped the params. This is one of the highest-impact findings because it silently inflates "Direct" traffic — every email click, paid ad, social post, and partner link appears to drive zero results. For B2B SaaS, this means the entire marketing funnel looks broken in GA4 while the real problem is a misconfigured redirect rule.
23. **Decorative consent banner** — From Step 2b pre-consent check: if tracking requests fired before the user interacted with the banner, the consent implementation is theater. The banner exists for optics but provides zero legal protection. This is the #1 most embarrassing GDPR finding.
24. **Over-blocking after consent** — From Step 2b post-consent check: if accepting cookies didn't cause new tracking requests to appear, tags are permanently blocked even for consenting users. The site is unnecessarily blind to legitimate, consented traffic.
25. **Consent Mode defaults to "granted"** — From `consentModeState.defaults`: if `ad_storage` or `analytics_storage` defaults to `"granted"`, the site assumes consent before the user acts. Illegal under GDPR for EU visitors. Easy to detect, hard to defend.
26. **Rogue scripts bypassing consent** — From `scriptsOutsideGTM`: tracking scripts hardcoded in the HTML (outside GTM) that fire regardless of consent state. Even if GTM respects consent, these scripts don't — one rogue pixel undermines the entire compliance effort. **Non-GTM sites:** If the site doesn't use GTM (e.g., Ensighten, Tealium, or direct gtag.js), `scriptsOutsideGTM` is meaningless — all scripts are "outside GTM." In this case, skip this check and instead assess whether the site's TMS (or direct implementation) properly gates tracking scripts behind consent.
27. **YouTube iframe cookie leak** — From `iframeCookieRisk`: YouTube embeds using `youtube.com/embed` instead of `youtube-nocookie.com` drop Google tracking cookies regardless of the parent page's consent state. The iframe bypasses the CMP entirely.
28. **DataLayer race condition** — From `dataLayerSequencing`: business data (user info, firmographics, plan tier) pushed to the dataLayer AFTER `gtm.js` fired. Tags read the dataLayer before the data exists — custom dimensions and segments are silently blank.
29. **Consent state not persisting** — From Step 2b navigation check: if the consent banner re-appears on page 2 after the user already accepted, the CMP cookie didn't persist. Every page load resets consent, fragmenting the session and annoying users.
30. **Consent Mode Basic instead of Advanced** — From Step 2b: if zero GA4 requests fire when consent is denied (no cookieless pings), the site uses Basic mode and loses all behavioral/conversion modeling for non-consenting users. Advanced mode preserves anonymized pings legally.
31. **sGTM not forwarding consent state** — From Step 2b sGTM check: if GA4 collect requests to the first-party endpoint lack `gcs`/`gcd` parameters, the server container can't respect consent and forwards data regardless. Compliance illusion — client looks clean, server doesn't care.
32. **Mixed event naming conventions** — Check `dataLayerQuality.eventNamingConsistency`. If `mixedFormats` is true, the dataLayer has custom events using different naming conventions (e.g., `addToCart` alongside `form_submitted` alongside `Button Click`). GA4 treats these as separate events — the same action tracked under two names fragments reports, breaks audience definitions, and causes conversion undercounting. Google recommends snake_case for all custom events. This is an easy-to-demonstrate data quality finding: "your dataLayer is using 3 different naming conventions — here are the examples."
33. **E-commerce funnel gaps** — Check `dataLayerQuality.ecommerceFunnel`. If `hasAnyEcommerce` is true but critical events are missing (view_item, add_to_cart, or purchase), the GA4 Monetization reports show partial data. Funnel exploration reports have gaps, and remarketing audiences based on funnel stage (e.g., "added to cart but didn't purchase") can't be built. **Important caveat:** ecommerce events are page-specific — `view_item` fires on product pages, `purchase` fires on thank-you pages. Check cross-page before reporting this as an issue; a single page missing `purchase` is expected if it's not the checkout confirmation page.

### Phase 3.5: Run Deterministic Checks

After collecting eval data from all pages, save each page's JS eval result as a JSON file (include a `"url"` field). **Clean the output directory first** (`rm -rf /path/to/page-evals/`) before writing new files — stale JSON from a prior audit run will contaminate the checker since it processes every `.json` file in the directory.

Run the automated checker:

```bash
python scripts/check_findings.py --dir /path/to/page-evals/ --pretty
```

This script runs 37 deterministic checks across all pages and produces structured findings with severity levels. It catches:
- Double-tagging (hardcoded gtag + GTM, multiple containers, duplicate GA4 IDs)
- PII in dataLayer (email/phone regex, suspicious keys)
- Ecommerce field validation (transaction_id, currency, value, items)
- DataLayer quality (bloat >50 pushes, only system events)
- Consent gaps (no CMP with cookies set, CMP without Consent Mode)
- Schema/canonical/OG tag issues (missing markup, MIME typos, invalid handles)
- Cross-domain link gaps (missing _gl parameter)
- Form hidden field gaps (no gclid/UTM capture on conversion pages)
- Tag sprawl (>15 third-party domains)
- Ghost preconnects (preconnect hints for unloaded pixels)
- CTA tracking gaps (buttons with no tracking attributes)
- ABM/intent tool integration (6sense, Demandbase, Clearbit detected but not pushing to GA4)
- Video embeds missing tracking APIs (YouTube without enablejsapi=1, Vimeo without api=1)
- CRM cookie subdomain scoping (HubSpot/Marketo cookies that may be host-only)
- Chatbot engagement inflation (chat events firing on page load before user interaction)
- Pixels on conversion pages with no conversion event in dataLayer (base tag only)
- LinkedIn Insight Tag pageview-only (tag installed but no conversion events configured)
- Pardot third-party tracking domains (pi.pardot.com instead of first-party — ITP cookie capping)
- Google Ads Enhanced Conversions missing (no hashed user data on conversion pages)
- Thank-you pages indexable (no noindex on confirmation/success pages — bot traffic inflates conversions)
- Hidden attribution fields empty (UTM/gclid fields exist but values are blank)
- Consent Mode defaults misconfigured (defaulting to "granted", missing v2 signals, no defaults at all)
- Rogue tracking scripts outside GTM (hardcoded pixels that bypass Consent Mode)
- YouTube iframe cookie leaks (youtube.com instead of youtube-nocookie.com)
- DataLayer race conditions (business data pushed after gtm.js — custom dimensions silently blank)
- Event naming consistency (mixed snake_case/camelCase/spaces in custom dataLayer events)
- E-commerce funnel completeness (some GA4 ecommerce events present but critical steps missing)
- Cross-page consistency (GTM/GA4 missing on some pages, different container IDs)
- OG image sameness (same image across all pages)

Use the script's output as the foundation for the Issues Found section. The script ensures these checks are consistent across every audit — no findings get accidentally skipped. Then layer on your subjective analysis (sGTM deep checks, performance interpretation, privacy policy review, optimization opportunities) on top.

### Phase 4: Score and Report

Use the scoring rubric in `references/scoring-rubric.md` to produce category scores.

## Report Structure

Always use this exact structure:

```markdown
# Martech Audit: [domain]
**Date:** [date]
**Pages inspected:** [list of URLs]
**Method:** [Runtime browser inspection / Static HTML analysis (limited)]

## Executive Summary
[2-3 sentences: overall health, biggest issue, biggest strength]

## Tagging Architecture
[Client-side only / Server-side / Hybrid — explain what was found]

## What's Working
| Area | Finding | Status |
|------|---------|--------|
[Table of positive findings]

## Issues Found

### Critical
| # | Issue | Impact | Remediation |
|---|-------|--------|-------------|
[Issues that are actively breaking tracking or losing data]

### Moderate
| # | Issue | Impact | Remediation |
|---|-------|--------|-------------|
[Issues that reduce data quality or miss opportunities]

### JavaScript & Logic Errors
| # | Error | Page | Impact |
|---|-------|------|--------|
[Console errors, failed network requests, broken scripts — these are the highest-value bizdev findings]

## Privacy & Compliance
[Privacy policy gaps, undisclosed tools, consent issues, B2B reveal tool implications]

## Tag Performance Impact
| Metric | Value | Tag-Related Impact |
|--------|-------|-------------------|
| LCP | X.Xs | [Any tag-caused delay? Check LCP breakdown render delay] |
| TTFB | Xms | [Server response time] |
| CLS | X.XX | [Tag-injected layout shifts] |
| Third-party transfer | X kB | [From ThirdParties insight] |
| Third-party main thread | Xms | [From ThirdParties insight — blocking time] |
| Third-party domains | X | [From thirdPartyTrackingDomains] |
| Render-blocking scripts | X | [From RenderBlocking insight] |

[Key findings: render-blocking scripts, tag firing timing issues, zombie tags, CLS-causing injections, recommendations to reduce impact]

## Optimization Opportunities
| # | Opportunity | Business Value |
|---|-------------|----------------|
[Things that aren't broken but could be better]

## Scoring
| Category | Score | Notes |
|----------|-------|-------|
| Tag presence (GTM/GA4) | X/10 | |
| Event tracking maturity | X/10 | |
| Conversion tracking | X/10 | |
| Data layer quality | X/10 | |
| Privacy & consent | X/10 | |
| SEO & schema markup | X/10 | |
| Pixel coverage | X/10 | |
| Tag performance impact | X/10 | |
| **Overall** | **X/10** | |

## Recommended Next Steps
[3-5 prioritized actions, ordered by impact. Frame as "quick wins" vs "strategic improvements"]
```

## Bizdev Framing

The report should be professional and factual — not salesy. The value proposition is implicit: "we found things you didn't know were broken." The most compelling findings for opening a conversation are, roughly ordered by impact:

1. **Double-tagging (gtag.js + GTM, or multiple GTM containers)** — every metric is inflated 2x. CPA looks half what it actually is. This is extremely common and site owners almost never know.
2. **JavaScript errors silently breaking tracking** — the site owner has no idea data is being lost
3. **Conversion tag firing on page load instead of form submit** — counting visitors as conversions. Google Ads optimizes toward page views.
4. **Zero conversion tracking on the booking/demo page** — they're flying blind on what drives revenue
5. **Broken cross-domain tracking (missing _gl parameter)** — every checkout/booking creates a new session. Attribution dies at the most critical funnel step.
6. **sGTM deployed but bypassed** — paying for server-side infrastructure that collects zero data (transport URL not configured)
7. **PII leaking into dataLayer** — email addresses visible to every tag and pixel. GDPR liability.
8. **Missing consent management / Consent Mode v2** — Google has disabled conversion tracking and remarketing for non-compliant EU traffic since July 2025
9. **Duplicate conversion events (no transaction_id)** — revenue inflated 20-30%. Page refresh = another "sale."
10. **Configured-but-not-implemented pixels** — they paid for tools they're not using
11. **Broken B2B reveal tools** — they're paying for visitor identification that's collecting zero data
12. **Privacy policy gaps** — undisclosed data processors (especially B2B reveal tools that de-anonymize visitors) are a concrete compliance liability
13. **Form missing hidden fields for gclid/UTM capture** — offline conversion import will fail. Google Ads can't optimize toward revenue.
14. **Tag sprawl / zombie tags** — dozens of third-party scripts for vendors no longer in use, adding seconds to page load
15. **Custom attribution cookies without documentation** — they have systems no one understands anymore
16. **UTM parameters stripped by redirects** — every campaign looks like it drives zero results. "Direct" traffic is massively inflated.
17. **Google Ads Enhanced Conversions missing** — 15-25% of conversions unmatched. Smart Bidding optimizes poorly. CPA inflated.
18. **LinkedIn Insight Tag pageview-only** — expensive LinkedIn ads optimizing toward pageviews, not pipeline. No conversion data.
19. **Thank-you pages publicly indexable** — bot traffic and direct URL hits inflate conversion counts and pollute remarketing audiences.
20. **Hidden attribution fields always empty** — CRM looks attribution-ready but every lead record has blank source data. Offline conversion import silently fails.
21. **Pardot using third-party tracking domains** — Safari/Firefox degrading tracking for 30-40% of visitors. Prospect history quality eroding with each browser update.
22. **Decorative consent banner** — tracking fires before the user clicks anything. The banner is legal theater. This is the single most embarrassing finding because it's provable by anyone with DevTools.
23. **Rogue scripts bypassing consent** — GTM respects consent but a hardcoded pixel doesn't. One rogue script undermines the entire compliance effort.
24. **DataLayer race condition** — business data arrives after tags already fired. Custom dimensions and segments are silently blank in GA4 even though the developer wrote the code to push the data.
25. **YouTube iframe cookie leak** — embedded videos dropping Google cookies despite declined consent. The iframe bypasses the CMP entirely.
26. **Consent Mode Basic instead of Advanced** — blocking all Google signals when consent denied, losing behavioral and conversion modeling. Legal anonymized data thrown away.
27. **Consent defaults to "granted"** — consent state assumes permission before the user acts. Provably illegal for EU traffic.
28. **Over-blocking after consent** — tags never actually start firing even when the user grants consent. Compliance achieved, visibility lost.
29. **Mixed event naming conventions** — dataLayer uses 3 different formats (snake_case, camelCase, spaces). GA4 treats `addToCart` and `add_to_cart` as separate events. Reports fragment, audiences miss events, conversion counts underreport.
30. **Incomplete e-commerce funnel** — some GA4 ecommerce events fire (view_item) but critical steps are missing (add_to_cart, purchase). Monetization reports show partial data. Can't build funnel-stage remarketing audiences.

End the report with "Recommended Next Steps" that are specific enough to demonstrate expertise but high-level enough that they'd want help implementing.

## Reference Files

- `references/scoring-rubric.md` — Detailed scoring criteria for each category (read when producing scores)
- `references/pixel-signatures.md` — URL patterns and cookie names for detecting 50+ martech platforms (read when identifying pixels)
- `references/common-tracking-errors.md` — Known JavaScript errors, logic errors, and misconfigurations to watch for (read when analyzing console output and network requests)
