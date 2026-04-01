# Pixel Signatures

URL patterns, cookie names, and JavaScript globals for detecting martech platforms at runtime.

## Analytics

| Platform | Script URL Pattern | Cookies | JS Global | Network Collect URL |
|---|---|---|---|---|
| GA4 (client) | `gtag/js?id=G-` | `_ga`, `_ga_XXXXXX`, `_gid` | `gtag`, `google_tag_manager` | `google-analytics.com/g/collect` |
| GA4 (server-side) | `custom-domain/gtag/js?id=G-` | `_ga`, `_ga_XXXXXX` | `gtag`, `google_tag_manager` | `custom-domain/g/collect` (look for `sst.` params) |
| GTM (client) | `googletagmanager.com/gtm.js?id=GTM-` | — | `google_tag_manager['GTM-XXXXX']` | — |
| GTM (server-side) | `custom-domain/gtm.js?id=GTM-` | — | `google_tag_manager['GTM-XXXXX']` | — |
| Universal Analytics (legacy) | `google-analytics.com/analytics.js` | `_ga`, `_gid`, `_gat` | `ga` | `google-analytics.com/collect` |
| Mixpanel | `cdn.mxpnl.com` | `mp_` | `mixpanel` | `api.mixpanel.com` |
| Amplitude | `cdn.amplitude.com` | — | `amplitude` | `api.amplitude.com` |
| Heap | `cdn.heapanalytics.com` | — | `heap` | `heapanalytics.com` |
| PostHog | `app.posthog.com/static/array.js` | `ph_` | `posthog` | `app.posthog.com` |
| Plausible | `plausible.io/js/script.js` | — | `plausible` | `plausible.io/api/event` |
| Segment | `cdn.segment.com/analytics.js` | `ajs_` | `analytics` | `api.segment.io` |

## Advertising & Remarketing

| Platform | Script URL Pattern | Cookies | JS Global | Network Collect URL |
|---|---|---|---|---|
| Google Ads | `googleadservices.com/pagead` | `_gcl_au`, `_gcl_aw` | `gtag_report_conversion` | `googleadservices.com/pagead/conversion` |
| Meta (Facebook) Pixel | `connect.facebook.net/en_US/fbevents.js` | `_fbp`, `_fbc` | `fbq` | `facebook.com/tr` |
| LinkedIn Insight | `snap.licdn.com/li.lms-analytics` | `li_fat_id`, `li_sugr` | `_linkedin_partner_id` | `px.ads.linkedin.com` |
| Twitter/X Pixel | `platform.twitter.com/oct.js` | `_twclid` | `twq` | `t.co/i/adsct` |
| TikTok Pixel | `analytics.tiktok.com/i18n/pixel/events.js` | `_ttp`, `_tt_enable_cookie` | `ttq` | `analytics.tiktok.com` |
| Bing/Microsoft Ads | `bat.bing.com/bat.js` | `_uetmsclkid` | `UET` | `bat.bing.com` |
| Pinterest | `assets.pinterest.com/js/pinit.js` | `_pin_unauth`, `_pinterest_ct_ua` | `pintrk` | `ct.pinterest.com` |
| Reddit Pixel | `alb.reddit.com/snoo.js` | `_rdt_uuid` | `rdt` | `alb.reddit.com` |

## Session Recording & Heatmaps

| Platform | Script URL Pattern | Cookies | JS Global |
|---|---|---|---|
| Hotjar | `static.hotjar.com/c/hotjar-` | `_hjSession`, `_hjSessionUser` | `hj` |
| Microsoft Clarity | `clarity.ms/tag/` | `_clck`, `_clsk` | `clarity` |
| FullStory | `fullstory.com/s/fs.js` | `fs_uid` | `FS` |
| Lucky Orange | `d10lpsik1i8c69.cloudfront.net` | — | `__lo_cs_added` |
| Mouseflow | `cdn.mouseflow.com` | `mf_` | `mouseflow` |

## Customer Messaging & Support

| Platform | Script URL Pattern | Cookies | JS Global |
|---|---|---|---|
| Intercom | `widget.intercom.io` | `intercom-id-*` | `Intercom` |
| Drift | `js.driftt.com` | `driftt_aid` | `drift` |
| HubSpot | `js.hs-scripts.com`, `js.hs-analytics.net` | `hubspotutk`, `__hstc`, `__hssc` | `_hsq` |
| Zendesk | `static.zdassets.com` | — | `zE` |
| Crisp | `client.crisp.chat` | `crisp-client` | `$crisp` |
| LiveChat | `cdn.livechatinc.com` | — | `LiveChatWidget` |

## Email & Marketing Automation

| Platform | Script URL Pattern | Cookies | JS Global |
|---|---|---|---|
| ConvertKit | `f.convertkit.com/ckjs` | `_ck_visitor`, `_ck_subscriber` | — |
| Mailchimp | `chimpstatic.com` | `mailchimp_` | `mc_` |
| ActiveCampaign | `trackcmp.net` | — | `vgo` |
| Klaviyo | `static.klaviyo.com` | — | `_learnq` |
| Customer.io | `assets.customer.io` | — | `_cio` |

## Consent Management Platforms

| Platform | Script URL Pattern | Cookies | JS Global |
|---|---|---|---|
| Cookiebot | `consent.cookiebot.com` | `CookieConsent` | `Cookiebot` |
| OneTrust | `cdn.cookielaw.org` | `OptanonConsent` | `OneTrust` |
| Osano | `cmp.osano.com` | `osano_consentmanager` | `Osano` |
| Termly | `app.termly.io` | — | `Termly` |
| TrustArc | `consent.trustarc.com` | — | `truste` |

## B2B Visitor Identification

| Platform | Script URL Pattern | JS Global | Cookies/Storage | Notes |
|---|---|---|---|---|
| RB2B | `b2bjsstore` S3 bucket, `reb2b.js` | `reb2b` (check `reb2b.invoked`) | — | De-anonymizes website visitors. Often blocked by ORB due to S3 CORS issues. |
| Leadfeeder (Dealfront) | `leadfeeder.com`, `lftracker.js` | `ldfdr` | `_lfa` | Identifies companies visiting the site. |
| Clearbit Reveal | `clearbit.com/v2/reveal` | `clearbit` | — | Company-level identification from IP. Now part of HubSpot Breeze. |
| Demandbase | `tag.demandbase.com` | `Demandbase` | — | Account-based marketing, company identification. |
| ZoomInfo WebSights | `ws.zoominfo.com` | — | — | Company and contact identification. |
| 6sense | `6sense.com`, `6sc.co` | `_6si` | `_6sas`, `_6suuid` | Intent data and company identification. |
| Bombora | `bombora.com` | — | — | B2B intent data. |
| Warmly | `warmly.ai` | `warmly` | — | Real-time visitor identification + chat. |

These tools perform visitor de-anonymization and should be disclosed in privacy policies. They are frequently broken (blocked by browser security) or misconfigured. Always check both if the script loads AND if the JS global exists (the global may be set by inline code even if the main script fails).

## Enterprise Tag Management Systems (Legacy)

Enterprise sites often run a legacy TMS alongside GTM. Detecting these is a high-value finding because dual TMS = duplicate processing, tag conflicts, and governance headaches.

| Platform | Script URL Pattern | JS Global | Notes |
|---|---|---|---|
| Ensighten | `nexus.ensighten.com` | `Bootstrapper` | Enterprise TMS. Often runs alongside GTM on large sites after a migration that was never fully completed. |
| Tealium iQ | `tags.tiqcdn.com` | `utag` | Enterprise CDP + TMS. Look for `utag.js` and `utag.sync.js`. |
| Signal (BrightTag) | `s.thebrighttag.com` | — | Legacy TMS, now part of TransUnion. |
| Adobe Launch (Tags) | `assets.adobedtm.com` | `_satellite` | Part of Adobe Experience Platform. Look for `launch-` in script URLs. |

## Server-Side Tagging Indicators

| Signal | What It Means |
|--------|---------------|
| GTM/GA4 loaded from first-party domain (not googletagmanager.com) | Server-side GTM container deployed |
| `sst.tft` parameter in GA4 collect URL | Server-side tag firing timestamp |
| `sst.lpc` parameter in GA4 collect URL | Server-side last page change |
| `sst.navt` parameter in GA4 collect URL | Server-side navigation type |
| `sst.ude` parameter in GA4 collect URL | Server-side user data enrichment |
| `sst.sw_exp` parameter in GA4 collect URL | Server-side service worker experiment |
| Stape.io patterns in URL paths | Stape-hosted server container |
| `gtm_health` or `gtg_health` query param | GTM server container health check |
