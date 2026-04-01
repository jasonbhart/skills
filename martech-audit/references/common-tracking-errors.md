# Common Tracking Errors

JavaScript errors, logic errors, and misconfigurations that silently break tracking. These are the highest-value findings for bizdev — site owners rarely know about them.

## JavaScript Errors (Console)

### Fatal — Tracking Completely Broken

| Error | Cause | Impact |
|-------|-------|--------|
| `fbq is not defined` | Facebook Pixel script failed to load (ad blocker, network error, or script removed but code still calls fbq()) | All Facebook conversion tracking broken. Ad spend wasted. |
| `gtag is not defined` | gtag.js failed to load but page code tries to call gtag() | GA4 custom events silently fail. Pageviews may still work via GTM. |
| `ga is not defined` | Legacy Universal Analytics code still in templates after migration to GA4 | UA events fail. Common during GA4 migration — old code left behind. |
| `dataLayer is not defined` | GTM container code loads before `window.dataLayer = window.dataLayer || []` initialization | GTM triggers won't fire. All tag-based tracking broken. |
| `analytics is not defined` | Segment snippet failed to load | All downstream tools that depend on Segment get no data. |
| `Uncaught TypeError: Cannot read properties of undefined (reading 'push')` | Code tries `dataLayer.push()` before dataLayer exists | Events silently lost. |
| `hj is not defined` / `clarity is not defined` | Session recording script blocked or failed | No heatmap/recording data. Lower priority but wastes subscription cost. |

### Degraded — Partial Data Loss

| Error | Cause | Impact |
|-------|-------|--------|
| `net::ERR_BLOCKED_BY_CLIENT` on tracking URLs | Ad blocker or browser privacy feature | Expected for ~30% of users. Not actionable unless it's blocking first-party requests. |
| `net::ERR_BLOCKED_BY_ORB` (Opaque Resource Blocking) | Cross-origin resource blocked by browser security | Third-party script can't load. Check if it's a critical tracking script. |
| `Failed to load resource: the server responded with a status of 403` on pixel URL | Pixel ID is wrong, domain not allowlisted, or account suspended | That pixel is collecting zero data. |
| `Failed to load resource: the server responded with a status of 404` on tracking script | Script URL changed, file deleted, or CDN misconfigured | Tracking for that platform is dead. |
| CORS errors on `collect` endpoints | Server-side proxy misconfigured, or wrong domain in CORS headers | GA4 events may fail to send. Check if using server-side tagging. |

## Logic Errors (Not Visible in Console)

These don't throw JavaScript errors but still cause bad data. Detect them by analyzing the dataLayer, network requests, and page behavior.

### DataLayer Issues

| Problem | How to Detect | Impact |
|---------|---------------|--------|
| **DataLayer only has system events** | `dataLayer` contains only `gtm.js`, `gtm.dom`, `gtm.load` — no custom events | GTM is running but doing nothing useful. Most common issue on sites that "set up GTM" but never configured tags. |
| **DataLayer pushes after GTM loads** | Check push timestamps vs GTM load. If critical data pushes happen after `gtm.load`, triggers that depend on page-load data will miss it. | Tags that need data at page load fire with empty variables. |
| **Duplicate dataLayer pushes** | Same event pushed multiple times (e.g., `page_view` fires 2-3 times) | Inflated event counts. Skews all reporting. |
| **Ecommerce object not cleared** | No `dataLayer.push({ ecommerce: null })` before new ecommerce events | Previous product data bleeds into subsequent events. Corrupts purchase/product data. |
| **PII leaking into dataLayer** | `JSON.stringify(dataLayer)` contains email addresses (`@`), phone numbers, or keys like `email`, `phone`, `firstName` | Every tag/pixel can read PII. Violates GA4 TOS (account suspension risk) and GDPR (fines up to 4% global revenue). |
| **DataLayer bloat (>50 pushes per page)** | `dataLayer.length` on a simple page view exceeds 50 | Plugins/themes pushing noise. Slows GTM container processing, masks real interactions, increases TBT. |

### Conversion Tracking Issues

| Problem | How to Detect | Impact |
|---------|---------------|--------|
| **No conversion events on contact/demo page** | Load the conversion page, submit (or inspect) the form — no custom event in dataLayer | Cannot attribute any conversions to traffic sources. The #1 most common gap. |
| **Third-party embed breaks session** | Conversion page uses iframe (Calendly, Google Calendar, HubSpot forms) — GA4 session doesn't carry into iframe | Conversion appears as new session from the embed domain. Attribution completely broken. |
| **Form redirect loses data** | Form submits to external URL (e.g., HubSpot form → hubspot.com → thank-you page) without cross-domain tracking | Session breaks at form submit. Conversion not attributed. |
| **Thank-you page has no event** | Success/confirmation page loads but no conversion event fires | Can't use destination-based goals OR event-based conversions. |
| **Form tracked on page load instead of submit** | `form_submitted` event fires when page loads, not when form is submitted | Every page view counts as a conversion. Massively inflated numbers. |
| **Form conversion fires on failed validation** | Submit empty/invalid form — conversion event fires despite validation errors | 20-30% of reported "conversions" are failed form submissions. Google Ads optimizes toward wrong behavior. |
| **Duplicate conversion events (no transaction_id)** | Refresh thank-you page — purchase/lead event fires again. Check payload for `transaction_id` parameter. | Revenue inflated 20-30%. Page refresh = phantom sale. ROAS calculations wrong. |
| **Cross-domain _gl parameter missing** | Click link to checkout/booking domain — URL has no `_gl=` parameter | New session on every domain hop. Original traffic source replaced by self-referral. |
| **Hidden form fields missing for gclid/UTM** | Inspect form — no hidden inputs capturing `gclid`, `utm_source`, `utm_medium`, `utm_campaign` | Offline conversion import fails. CRM leads have no source attribution. Google Ads can't optimize toward revenue. |
| **Payment gateway self-referral** | Complete purchase flow through Stripe/PayPal — return URL has no `_gl` or referral exclusion | Payment processor steals attribution credit for every sale. Campaign ROAS invisible. |

### Double-Tagging Issues

| Problem | How to Detect | Impact |
|---------|---------------|--------|
| **Hardcoded gtag.js alongside GTM** | Page source contains both `gtag/js?id=G-` script AND `gtm.js` loading same measurement ID | Every event counted twice. Sessions, pageviews, revenue all 2x inflated. Bounce rate artificially low. |
| **Multiple GTM containers** | Page source contains two or more `GTM-XXXXXX` IDs | Shared dataLayer processed by both containers. Duplicate events, conflicting triggers, double conversions. |
| **WordPress plugin re-initializing GA4** | GA4 collect requests go to both sGTM endpoint AND google-analytics.com with same measurement ID | Data split between server and client paths. sGTM enrichment only applies to some events. |
| **Enhanced Measurement + custom GTM tracking overlap** | Scroll/click/download triggers fire duplicate events (two `scroll`, two `click` events in Network tab) | Inflated engagement metrics. Scroll depth, outbound clicks, file downloads all 2x. |

### High-Cardinality & Data Quality Issues

| Problem | How to Detect | Impact |
|---------|---------------|--------|
| **High-cardinality event parameters** | DataLayer events use unique IDs, timestamps, or user-specific values as event parameter values (e.g., `event_label: "user_12345"`, `page_title` with dynamic query strings) | GA4 has a 500 unique values per day limit per custom dimension. Excess values get bucketed into `(other)`, making reports useless. High-cardinality custom dimensions also slow GA4 reporting and can cause data thresholding. |
| **URL-based parameters without normalization** | `page_location` or custom event parameters include query strings, fragment identifiers, or session IDs (e.g., `?sid=abc123`, `?fbclid=...`) | Thousands of unique "pages" for what is really one page. Content performance reports become unusable. Page-level conversion rates are meaningless because traffic is fragmented. |
| **User-level values in event-scoped dimensions** | Event parameters contain user IDs, email hashes, account IDs, or other user-specific values that should be user-scoped custom dimensions | Creates cardinality explosion at event scope (every event × every user = massive unique count). Burns through the 500-value limit instantly. Data gets bucketed into `(other)`. |
| **Dynamically generated event names** | Event names constructed from variables (e.g., `click_cta_${buttonId}`, `view_product_${sku}`) instead of using a standard event name + properties | GA4 has a 500 distinct event name limit per property. Dynamic names exhaust this quickly. Events that exceed the limit are silently dropped — no error, just missing data. |
| **Debug/test mode left on in production** | `debug_mode: true` in gtag config, or GTM preview cookies left behind | Debug events pollute production data. DebugView shows phantom traffic. Can inflate event counts. |

## Tag Performance Issues

Problems where tag configurations directly hurt page load speed, Core Web Vitals, and search rankings.

| Problem | How to Detect | Impact |
|---------|---------------|--------|
| **Render-blocking tracking scripts** | Page source: `<script src="...gtag/js">` in `<head>` without `async` or `defer` attribute | Blocks HTML parsing. Every ms the script takes to download = every ms the page is blank. GTM snippet should always be async. |
| **Non-essential tags firing on Page View** | In Lighthouse "Reduce third-party code" audit, see which tracking domains have high main-thread blocking time. Cross-reference with tag firing triggers. | Heatmaps, session recording, chat widgets, remarketing pixels firing on Page View compete with the critical rendering path. Should fire on Window Loaded or later. |
| **Tag waterfall chains** | Network tab waterfall: Tag A (GTM) loads Tag B (pixel SDK) which loads Tag C (data partner). Count the dependency chain depth. | Each hop adds network latency (DNS + connect + download + parse). A 3-hop chain can add 1-2 seconds. Flatten by loading independent scripts in parallel. |
| **GTM container bloat** | Check GTM container JS file size in Network tab. Containers over 100KB compressed (visible in Transfer Size) indicate excessive tags/triggers/variables. | Large containers take longer to download, parse, and evaluate. Every tag adds evaluation time even if its trigger doesn't match. |
| **Consent banner CLS** | Lighthouse CLS audit shows layout shift caused by cookie banner injection. Consent banner element has no reserved space in initial layout. | Banner pushes content down after initial paint. Directly impacts CLS Core Web Vital. Can be fixed with `min-height` placeholder or fixed positioning. |
| **Chat widget CLS/LCP impact** | Lighthouse identifies chat widget (Intercom, Drift, Crisp) as contributing to LCP delay or CLS. Widget loads large JS bundles and injects DOM elements. | Chat widgets average 200-500KB of JavaScript. Loading on Page View can delay LCP by 500ms+. Should load on Window Loaded or after user interaction. |
| **A/B testing FOOC (Flash of Original Content)** | Optimizely/VWO/Google Optimize script loads, applies visual changes after paint — user sees original content briefly, then it shifts | CLS spike + poor user experience. Anti-flicker snippets help but add their own blocking time. Test tool should load very early or use server-side rendering. |
| **Zombie tags (scripts for unused vendors)** | Network tab shows requests to domains for tools the company no longer uses (check for defunct analytics, old ad platforms, expired A/B tests). Cross-reference with `thirdPartyTrackingDomains`. | Each zombie tag adds download + parse + execution time for zero business value. Common after agency transitions or tool trials that were never cleaned up. |
| **Double-loaded scripts (same vendor loaded twice)** | Network tab shows two requests to the same vendor SDK (e.g., `fbevents.js` loaded twice, or same `analytics.js` loaded via GTM and hardcoded). | Double the download, double the execution, double the events. Often the root cause of double-counting AND performance degradation simultaneously. |
| **No preconnect hints for critical tracking domains** | Missing `<link rel="preconnect">` for domains that will be requested early (e.g., sGTM domain, GA4 collect endpoint) | Without preconnect, each first-party tracking request pays DNS + TCP + TLS penalty (~100-300ms). Preconnect eliminates this for known endpoints. |

### CTA/Click Tracking Issues

| Problem | How to Detect | Impact |
|---------|---------------|--------|
| **CTAs are plain links with no tracking** | Inspect CTA buttons — no `onclick`, no `data-*` attributes, no GTM click trigger | Can't tell which CTAs drive engagement. Can't A/B test button text/position. |
| **Click trigger too broad** | GTM has "All Elements" click trigger with no filters | Every click on the page fires the tag. Massive event volume, noisy data. |
| **Click trigger too narrow** | GTM click trigger targets specific element ID/class, but site redesign changed it | Tag stops firing silently after CSS update. No error, just missing data. |

### Pixel Issues

| Problem | How to Detect | Impact |
|---------|---------------|--------|
| **Preconnect hints for unimplemented pixels** | `<link rel="preconnect" href="connect.facebook.net">` exists but no fbq() call | Wasted DNS lookups. Reveals pixel was planned but never finished. |
| **Multiple GTM containers** | Two different GTM container IDs loading on same page | Duplicate events, conflicting triggers, unexpected tag behavior. |
| **Pixel ID mismatch** | Pixel loads but with wrong account ID (common after agency handoff) | Data goes to wrong account. Site owner sees zero data. |
| **Test/debug mode left on** | `debug_mode: true` in gtag config, or GTM in preview mode cookie left behind | Debug events pollute production data. DebugView shows phantom traffic. |

### Server-Side Tagging Issues

| Problem | How to Detect | Impact |
|---------|---------------|--------|
| **Server container down** | Requests to custom domain return 5xx errors | All server-side tags fail. May fall back to client-side (if configured) or lose data entirely. |
| **Mixed client/server without fallback** | Some requests go to custom domain, some to google-analytics.com | Inconsistent. If server container fails, unclear what happens. |
| **Stale server container** | Server container version is months behind client container | New tags/triggers added in client container aren't reflected server-side. |
| **Transport URL not configured (sGTM bypassed)** | sGTM subdomain exists (in DNS/page source) but GA4 collect requests go directly to `google-analytics.com` instead | Entire sGTM investment wasted. No ad-blocker bypass, no first-party cookies, no server-side enrichment. Paying for hosting with zero benefit. |
| **Consent not forwarded to server container** | `gcs` parameter in sGTM-bound requests doesn't change between consent-granted and consent-denied states | Server fires all tags regardless of consent choice. Direct GDPR violation — users who said "no" are still being tracked server-side. |
| **Cookie domain mismatch (Safari ITP cap)** | sGTM subdomain resolves to different IP range than main domain (CNAME to Stape/Addingwell instead of A record) | Safari ITP caps cookies to 7 days instead of 2 years. 30-40% of traffic (Safari users) treated as new visitors weekly. Defeats the purpose of sGTM cookies. |
| **"No Client claimed the request" (silent drop)** | Events reach sGTM endpoint but responses are empty/unexpected, no set-cookie headers when expected | Events silently dropped. No server-side tags fire. Downstream integrations (Meta CAPI, GA4 server tags, data warehouse) receive nothing. |

### Consent Issues

| Problem | How to Detect | Impact |
|---------|---------------|--------|
| **Tags fire before consent** | Tracking requests appear in network tab immediately on page load, before any consent interaction | Violates GDPR/ePrivacy. Google may reject conversion data. |
| **Consent Mode not configured** | No `gtag('consent', 'default', ...)` call anywhere | Google Ads can't model conversions for unconsented users. |
| **Banner present but no Consent Mode integration** | Cookie banner shows but tags fire regardless of choice | Cosmetic compliance only. Still technically non-compliant. |
| **Consent defaults to 'granted'** | `gtag('consent', 'default', { analytics_storage: 'granted' })` | Defeats the purpose. Should default to 'denied' and update on user action. |

## Ad Platform & Attribution Issues

Problems where ad conversion tracking, attribution fields, or platform integration is broken or incomplete.

| Problem | How to Detect | Impact |
|---------|---------------|--------|
| **Google Ads Enhanced Conversions missing** | Submit test lead on conversion page, inspect `googleadservices` payload for `em` (hashed email) parameter. If absent, enhanced conversions aren't configured. | 15-25% of conversions go unmatched in post-cookie world. Smart Bidding optimizes with incomplete data, inflating CPA. |
| **LinkedIn Insight Tag pageview-only** | Check for `insight.min.js` or `snap.licdn.com` loading. Test key actions (form submit, CTA click) — if no additional `lintrk()` calls with `conversion_id` fire, only base pageviews are tracked. | LinkedIn can build audiences but can't optimize toward actual conversions. Expensive LinkedIn ad spend bids toward pageviews instead of pipeline. |
| **UTM parameters stripped by redirects** | Append `?utm_source=test` to URL and navigate. If server redirect (trailing slash, HTTP→HTTPS, www normalization) drops the query string before analytics loads, UTMs are lost. | Massive inflation of "Direct" traffic. Every UTM-tagged campaign — email, social, partner — appears to drive zero results. |
| **Ad click IDs stripped during conversion path** | Load landing page with `?gclid=test&fbclid=test&li_fat_id=test`. Follow the conversion path through SPA navigation, scheduler handoff (Calendly/Chili Piper), or form redirect. Check if IDs survive in final URL, cookies, localStorage, or hidden fields. | Paid traffic converts but offline attribution and ad platform matching break. Google Ads can't close the loop on revenue. |
| **Hidden attribution fields never populate** | Inspect form DOM before submit — look for hidden inputs named `gclid`, `utm_source`, etc. Check if their `value` attributes are empty despite UTM parameters being in the URL. | CRM looks attribution-ready but every lead record has blank source data. Offline conversion import silently fails. |
| **Thank-you pages publicly indexable** | Navigate directly to `/thank-you`, `/confirmation`, `/success` pages. Check for `<meta name="robots" content="noindex">` or `X-Robots-Tag` header. If absent, page is crawlable. | Bot traffic and direct URL hits inflate conversion counts, pollute remarketing audiences, and may expose workflow details. |
| **Pardot third-party tracking domains** | Inspect script sources and network requests for `pi.pardot.com` or `go.pardot.com` instead of a branded first-party domain. | Safari ITP and Firefox ETP cap third-party cookies, degrading visitor tracking for 30-40% of traffic. Prospect browsing history fragments after 7 days. |
| **Conversion tags fire on failed form submissions** | Submit an empty/invalid form (trigger client-side validation). Watch network tab — if Google Ads, LinkedIn, or Meta conversion tags fire despite validation errors, conversions are inflated. | 20-30% of reported "conversions" are failed form submissions. Ad platforms optimize toward the wrong behavior. |

## Underused GA4/GTM Features (Optimization Opportunities)

Features that are available but rarely configured — each one is a value-add suggestion for a prospect call. These aren't "errors" but their absence is a missed opportunity that demonstrates the auditor's depth of knowledge.

### GA4 Features Not Enabled by Default

| Feature | How to Detect It's Missing | Business Value | Sales Hook |
|---------|--------------------------|----------------|------------|
| **Enhanced Measurement events** | DataLayer has zero `scroll`, `click`, `file_download`, `video_start` events. No Enhanced Measurement events visible in collect requests. | Free engagement data with zero code: scroll depth, outbound clicks, file downloads, video engagement, site search. Toggle in GA4 admin. | "You're getting pageview data but nothing about what people actually do on the page. One toggle gives you scroll depth, link clicks, and downloads — no code needed." |
| **Google Signals** | Cannot detect externally, but can be inferred — if remarketing audiences are small or cross-device reports are empty despite traffic volume | Enables cross-device tracking, demographics, and interest reports. Required for audience building in Google Ads. | "Cross-device reporting and demographics are likely disabled. Turning on Google Signals lets you see the same user across their phone and laptop." |
| **User-ID tracking** | Check dataLayer for `user_id` parameter in `config` or `set` calls. If absent on authenticated pages (post-login, account pages), it's not implemented. | Stitches sessions across devices for logged-in users. Without it, the same person on Chrome and Safari looks like two users. | "Your logged-in users are counted as separate people on each device. User-ID tracking fixes that and gives you accurate user counts." |
| **Custom dimensions / metrics** | GA4 collect requests only contain standard parameters (no `ep.` prefixed custom event parameters beyond basic ones) | Custom dimensions let you slice data by business-specific attributes (plan type, user role, industry, feature flags). Without them, all users look the same. | "Your analytics can't distinguish between free and paid users, or between trial and enterprise accounts. Custom dimensions unlock that segmentation." |
| **Conversion marking** | No events marked as conversions (only default `first_visit` and `purchase` if ecommerce). Check if key events like `generate_lead`, `sign_up`, `form_submit` are configured as conversions. | Conversions are what GA4 optimizes toward and what Google Ads bids on. If key events aren't marked as conversions, Smart Bidding has no signal. | "Your form submissions aren't marked as conversions in GA4. Google Ads literally doesn't know what a successful outcome looks like for your campaigns." |
| **Audience triggers** | No audiences configured (requires admin access to verify, but can be inferred from no remarketing lists in Google Ads) | Audiences enable remarketing, lookalike targeting, and triggered actions. Most GA4 properties have zero custom audiences. | "You could be building audiences of people who read 3+ blog posts, visited pricing, or downloaded a resource — then retarget them on Google Ads and LinkedIn." |
| **Data retention set to 14 months** | Cannot detect externally, but default is 2 months. If prospect mentions losing historical data, this is likely the cause. | Default 2-month retention means Explorations and funnel reports can only look back 2 months. Setting to 14 months preserves user-level data for year-over-year analysis. | "By default GA4 only keeps detailed data for 2 months. Changing one setting to 14 months gives you a full year of explorations and funnel data." |
| **Internal traffic filter activated** | Cannot detect externally, but if direct traffic % is unusually high for a small team, internal visits may be polluting data | Filters out employee traffic from analytics. For small companies, internal traffic can be 10-20% of total. | "Your team's own browsing is mixed into your analytics. Internal traffic filters keep your data clean and your conversion rates accurate." |
| **Referral exclusion list** | Self-referrals from own domains or payment processors appearing as traffic sources (infer from checkout flow architecture) | Prevents session breaks when users cross to payment processors (Stripe, PayPal) or subdomains. | "Every time someone pays through Stripe, GA4 credits Stripe as the traffic source instead of the ad that drove the sale." |
| **Enhanced Conversions** | Check conversion request payloads for `em` (hashed email) parameter. If absent on thank-you/purchase pages, enhanced conversions aren't configured. | Improves Google Ads conversion matching from ~50% to 60-80%+. Critical as third-party cookies disappear. | "You're leaving 15-25% of conversion data on the table. Enhanced conversions send hashed user data to improve match rates — especially important as cookies go away." |

### GTM Features Commonly Underused

| Feature | How to Detect It's Missing | Business Value | Sales Hook |
|---------|--------------------------|----------------|------------|
| **Data Layer variable templates** | Custom HTML tags reading `dataLayer` directly via `window.dataLayer` instead of using built-in Data Layer Variable type | Built-in variables are faster, cacheable, and maintainable. Custom HTML reading the dataLayer manually is fragile and a security risk. | "Your GTM container has custom scripts manually reading the dataLayer. GTM has built-in variable templates that are faster and safer." |
| **Trigger groups** | Complex trigger configurations with multiple exceptions instead of using Trigger Groups for sequential tracking (e.g., "track button click only after user saw section X") | Trigger groups let you fire tags only when multiple conditions are met sequentially. Essential for funnel step tracking. | "You could track when someone scrolls past a section AND then clicks the CTA — giving you engagement quality data, not just click counts." |
| **Custom event triggers for SPA** | SPA site using only Page View triggers (which don't fire on virtual navigation). History Change trigger not configured. | History Change triggers detect SPA URL changes without page reloads. Without them, only the landing page gets tracked. | "Your React/Next.js site only tracks the first page load. History Change triggers capture every navigation." |
| **Consent Mode v2 integration** | No `gtag('consent', 'default', ...)` call before GTM. `gcs` parameter missing from collect requests. | Required since July 2025 for EU traffic. Without it, Google disables conversion tracking and remarketing for non-consented sessions. Enables behavioral modeling to recover ~65% of lost conversions. | "Google is already blocking your conversion data from EU users. Consent Mode v2 is required — and the advanced mode recovers 65% of otherwise-lost signals." |
| **Server-side tagging** | All GTM/GA4 requests go directly to Google domains (no first-party proxy) | Bypasses ad blockers (recovers 15-30% of lost data), extends cookie lifetimes, enables server-side enrichment, and improves page load performance by moving tag execution off the client. | "Ad blockers are eating 15-30% of your analytics data. Server-side tagging routes everything through your own domain — invisible to blockers." |
| **GTM Environments** | Only one publish target (Live). No staging/dev environments configured. | Environments let you test tag changes on staging before pushing to production. Without them, every GTM publish is a production deploy with no safety net. | "Your GTM publishes go straight to production with no staging step. Environments let you test changes safely before they affect real visitors." |
| **Built-in tag templates vs Custom HTML** | Custom HTML tags for vendors that have official GTM templates (Meta, LinkedIn, TikTok, etc.) | Templates are sandboxed, auditable, and often more performant. Custom HTML runs arbitrary JavaScript. | "8 of your tags are Custom HTML doing things GTM has built-in templates for. Templates are safer, faster, and easier to maintain." |
