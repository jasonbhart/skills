#!/usr/bin/env python3
"""
Deterministic martech audit checker.

Takes the raw JSON output from the browser eval script (one per page)
and produces structured pass/fail findings. Run this AFTER collecting
data from all pages to get consistent, repeatable results.

Usage:
    python check_findings.py page1.json page2.json ...
    python check_findings.py --dir /path/to/eval-outputs/

Input: JSON files, each containing the output of the evaluate_script call
       for one page. Each file should also include a "url" field.

Output: JSON to stdout with findings array + summary scores.
"""

import json
import re
import sys
from pathlib import Path


# --- Check definitions ---
# Each check is a function that receives (page_data, all_pages_data)
# and returns a list of Finding dicts.

def check_double_tagging(page, all_pages):
    """Double-tagging: hardcoded gtag.js alongside GTM, or multiple GTM containers.
    Uses first-party classification to avoid false positives from vendor-loaded containers."""
    findings = []
    ti = page.get("tagInstallations", {})

    if ti.get("doubleTagging"):
        findings.append({
            "id": "DOUBLE_TAG_GTAG_GTM",
            "severity": "moderate",
            "title": "Hardcoded gtag.js alongside GTM container — possible double-tagging",
            "detail": (
                f"First-party GA4 IDs: {ti.get('firstPartyGa4Ids', ti.get('ga4Ids', []))}. "
                f"First-party GTM IDs: {ti.get('firstPartyGtmIds', ti.get('gtmIds', []))}. "
                "This is only a problem if BOTH send to the same GA4 property. "
                "Many sites intentionally use hardcoded gtag.js for GA4 and GTM strictly for "
                "marketing pixels/ads — in that case there is no double-counting. "
                "Verify by checking if GTM also has a GA4 Configuration tag sending to the same "
                "measurement ID before concluding events are duplicated."
                + (f" (Also detected {len(ti.get('thirdPartyGtmIds', []))} third-party vendor container(s) "
                   f"loaded by other scripts: {ti.get('thirdPartyGtmIds', [])} — these are excluded from this finding.)"
                   if ti.get("thirdPartyGtmIds") else "")
            ),
            "page": page.get("url", "unknown"),
        })

    if ti.get("multipleGtmContainers"):
        first_party_ids = ti.get("firstPartyGtmIds", ti.get("gtmIds", []))
        findings.append({
            "id": "MULTIPLE_GTM_CONTAINERS",
            "severity": "moderate",
            "title": f"Multiple first-party GTM containers on same page: {first_party_ids}",
            "detail": (
                "Two containers share one dataLayer. Each dataLayer.push is visible to both "
                "containers. If both have GA4/conversion tags for the same property, events "
                "will be duplicated. However, some organizations intentionally partition "
                "containers by responsibility (e.g., analytics vs ads) — verify whether "
                "overlapping tags exist before concluding data is duplicated."
                + (f" (Third-party vendor containers excluded: {ti.get('thirdPartyGtmIds', [])})"
                   if ti.get("thirdPartyGtmIds") else "")
            ),
            "page": page.get("url", "unknown"),
        })

    return findings


def check_pii_in_datalayer(page, all_pages):
    """PII (emails, phone numbers) leaking into the dataLayer."""
    findings = []
    dlq = page.get("dataLayerQuality", {})
    pii = dlq.get("piiDetected") or {}

    issues = []
    if pii.get("hasEmails"):
        issues.append("email addresses")
    if pii.get("hasPhoneNumbers"):
        issues.append("phone numbers")
    if pii.get("suspiciousKeys"):
        issues.append(f"suspicious keys: {pii['suspiciousKeys']}")

    if issues:
        findings.append({
            "id": "PII_IN_DATALAYER",
            "severity": "critical",
            "title": f"PII detected in dataLayer: {', '.join(issues)}",
            "detail": (
                "Personal data in the dataLayer is visible to every tag and pixel. "
                "Violates GA4 TOS (account suspension risk) and GDPR."
            ),
            "page": page.get("url", "unknown"),
        })

    return findings


def check_ecommerce_fields(page, all_pages):
    """Purchase events missing transaction_id, currency, or value."""
    findings = []
    dlq = page.get("dataLayerQuality", {})

    for i, purchase in enumerate(dlq.get("ecommerceIssues", [])):
        issues = []
        if not purchase.get("hasTransactionId"):
            issues.append("transaction_id (no deduplication — page refresh = duplicate revenue)")
        if not purchase.get("hasCurrency"):
            issues.append("currency (GA4 assumes USD for all transactions)")
        if not purchase.get("hasValue"):
            issues.append("value (no revenue data)")
        if not purchase.get("hasItems"):
            issues.append("items array (no product-level data)")

        if issues:
            findings.append({
                "id": "ECOMMERCE_MISSING_FIELDS",
                "severity": "critical",
                "title": f"Purchase event #{i+1} missing: {', '.join(issues)}",
                "detail": "Incomplete purchase data corrupts revenue reports and ROAS calculations.",
                "page": page.get("url", "unknown"),
            })

    return findings


def check_datalayer_quality(page, all_pages):
    """DataLayer health: bloat, only system events."""
    findings = []
    dlq = page.get("dataLayerQuality", {})
    dl = page.get("dataLayer", [])

    # Bloat check
    total = dlq.get("totalPushes", 0)
    if total > 50:
        findings.append({
            "id": "DATALAYER_BLOAT",
            "severity": "moderate",
            "title": f"DataLayer has {total} pushes on single page load",
            "detail": "Excessive pushes from plugins/themes. Slows GTM processing and creates noise.",
            "page": page.get("url", "unknown"),
        })

    # Only system events check
    system_events = {"gtm.js", "gtm.dom", "gtm.load"}
    events = [item.get("event") for item in dl if isinstance(item, dict) and item.get("event")]
    custom_events = [e for e in events if e not in system_events and not e.startswith("gtm.")]
    if events and not custom_events:
        findings.append({
            "id": "DATALAYER_NO_CUSTOM_EVENTS",
            "severity": "moderate",
            "title": "DataLayer contains only system events — no custom dataLayer events",
            "detail": (
                f"Events found: {list(set(events))}. "
                "No custom events in the dataLayer, but this doesn't necessarily mean zero tracking. "
                "GTM can fire tags via click/form/visibility triggers, GA4 Enhanced Measurement, "
                "or server-side tagging — none of which require custom dataLayer pushes. "
                "Check GTM's tag firing (network requests after interactions) before concluding "
                "tracking is absent."
            ),
            "page": page.get("url", "unknown"),
        })

    return findings


def check_consent(page, all_pages):
    """Consent management: no CMP, no Consent Mode, cookies set before consent."""
    findings = []
    consent = page.get("consent", {})
    cookies = page.get("knownCookies", [])

    has_cmp = any([
        consent.get("cookiebot"),
        consent.get("onetrust"),
        consent.get("osano"),
        consent.get("termly"),
        consent.get("trustarc"),
        consent.get("bannerVisible"),
        consent.get("usercentrics"),
        consent.get("didomi"),
        consent.get("ketch"),
        consent.get("iubenda"),
    ])

    # Use consentModeState.hasDefaults as the authoritative signal for whether
    # Consent Mode is actually active (parsed from dataLayer), rather than the
    # string-matching boolean in consent.consentMode which can disagree.
    # Also check consentModeDefaults (fallback format from eval script) — if present,
    # consent mode IS configured even if consent.consentMode missed it.
    cms = page.get("consentModeState", {})
    has_consent_mode = (
        cms.get("hasDefaults", False)
        or consent.get("consentMode", False)
        or bool(page.get("consentModeDefaults"))
    )

    if not has_cmp and cookies:
        findings.append({
            "id": "NO_CONSENT_MANAGEMENT",
            "severity": "critical",
            "title": "No consent management — tracking cookies set without user consent",
            "detail": (
                f"Cookies set on load: {cookies[:5]}{'...' if len(cookies) > 5 else ''}. "
                "Violates GDPR for EU visitors and ePrivacy Directive. "
                "Google may reject conversion data from non-consented sessions."
            ),
            "page": page.get("url", "unknown"),
        })

    if has_cmp and not has_consent_mode:
        findings.append({
            "id": "NO_CONSENT_MODE",
            "severity": "moderate",
            "title": "Cookie banner present but no Google Consent Mode integration",
            "detail": (
                "Tags may fire regardless of consent choice. Google Consent Mode v2 is "
                "required since July 2025 for EU traffic — without it, Google disables "
                "conversion tracking and remarketing."
            ),
            "page": page.get("url", "unknown"),
        })

    return findings


def check_schema_markup(page, all_pages):
    """Missing JSON-LD schema markup."""
    findings = []
    schema = page.get("schema", {})

    # schema can be a list of type strings (from eval) or a dict with a count key
    schema_count = len(schema) if isinstance(schema, list) else schema.get("count", 0)

    if schema_count == 0:
        findings.append({
            "id": "NO_SCHEMA_MARKUP",
            "severity": "moderate",
            "title": "No JSON-LD schema markup found",
            "detail": "Missing structured data reduces rich snippet eligibility in search results.",
            "page": page.get("url", "unknown"),
        })

    return findings


def check_canonical(page, all_pages):
    """Missing canonical URL."""
    findings = []
    # canonical may be at top level (from eval) or nested under meta
    meta = page.get("meta", {})
    canonical = page.get("canonical") or meta.get("canonical")

    if not canonical:
        findings.append({
            "id": "NO_CANONICAL_URL",
            "severity": "moderate",
            "title": "Missing canonical URL",
            "detail": "Risk of duplicate content issues across URL variations (trailing slash, www, etc.).",
            "page": page.get("url", "unknown"),
        })

    return findings


def check_og_tags(page, all_pages):
    """OG/Twitter Card meta tag validation."""
    findings = []
    og = page.get("ogTags", {})
    url = page.get("url", "unknown")

    # OG image type typo (image/.png instead of image/png)
    img_type = og.get("ogImageType") or page.get("meta", {}).get("ogImageType") or ""
    if re.match(r"image/\.\w+", img_type):
        findings.append({
            "id": "OG_IMAGE_TYPE_TYPO",
            "severity": "moderate",
            "title": f"OG image type has invalid MIME: '{img_type}' (should be 'image/png' or 'image/jpeg')",
            "detail": "Social platforms may fail to parse the image metadata.",
            "page": url,
        })

    # Twitter handle with space
    tw_creator = og.get("twitterCreator") or page.get("meta", {}).get("twitterCreator") or ""
    if tw_creator and " " in tw_creator:
        findings.append({
            "id": "TWITTER_HANDLE_INVALID",
            "severity": "moderate",
            "title": f"Twitter creator handle contains space: '{tw_creator}'",
            "detail": "Twitter/X Cards won't link to the author's profile.",
            "page": url,
        })

    # Blog/article page with og:type = website
    og_type = og.get("ogType") or ""
    # Only flag individual articles, not index/listing pages like /blog or /news
    if re.search(r'/(blog|news|article|insight|resource|post)/[^/?#]+', url.lower()) and og_type == "website":
        findings.append({
            "id": "BLOG_OG_TYPE_WEBSITE",
            "severity": "moderate",
            "title": "Blog/article page uses og:type 'website' instead of 'article'",
            "detail": "Social platforms can't distinguish blog articles from generic pages.",
            "page": url,
        })

    return findings


def check_cross_domain_links(page, all_pages):
    """Cross-domain links missing _gl parameter."""
    findings = []

    # Support both formats:
    # - SKILL.md orchestrator produces "crossDomainLinks" as list of {href, hasGlParam} objects
    # - Standalone eval produces "crossDomain" as {linkerParam: bool, linkerInLinks: int}
    links = page.get("crossDomainLinks", [])
    if links:
        # Filter out links to subdomains of the same root domain — these share
        # cookies automatically and do NOT need _gl linker parameters.
        page_url = page.get("url", "")
        broken = [l for l in links if not l.get("hasGlParam")
                  and not _same_root_domain(page_url, l.get("href", ""))]
        if broken:
            hrefs = [l.get("href", "?")[:80] for l in broken[:3]]
            findings.append({
                "id": "CROSS_DOMAIN_NO_GL",
                "severity": "moderate",
                "title": f"{len(broken)} cross-domain link(s) without _gl parameter in static markup",
                "detail": (
                    f"Links: {hrefs}. "
                    "Note: GA4's linker plugin typically injects _gl on click, not in static HTML. "
                    "Verify cross-domain tracking is configured in GA4 Admin > Data Streams > "
                    "Configure tag settings > Configure your domains. If configured, the _gl parameter "
                    "will be added dynamically at click time and this finding is informational."
                ),
                "page": page.get("url", "unknown"),
            })

    # Inbound _gl check — independent of outbound links (both can be present)
    cd = page.get("crossDomain", {})
    if cd.get("linkerParam"):
        findings.append({
            "id": "CROSS_DOMAIN_ACTIVE",
            "severity": "info",
            "title": "Cross-domain linker parameter (_gl) detected in page URL",
            "detail": (
                "The current page was loaded with a _gl parameter, indicating cross-domain "
                "tracking is configured and active for inbound traffic."
            ),
            "page": page.get("url", "unknown"),
        })

    return findings


def check_form_hidden_fields(page, all_pages):
    """Forms on conversion pages missing hidden fields for gclid/UTM capture."""
    findings = []
    # Use formHiddenFieldValues (attribution-only fields) rather than forms
    # (which includes ALL hidden fields like CSRF tokens). A form with a CSRF
    # token but no tracking fields should still be flagged.
    filtered_forms = page.get("formHiddenFieldValues", [])
    # Fall back to forms if formHiddenFieldValues is missing (old data format)
    if not filtered_forms:
        filtered_forms = page.get("forms", [])
    url = page.get("url", "unknown")

    # Only flag on pages that look like conversion pages
    conversion_keywords = [
        "contact", "demo", "book", "schedule", "signup", "register", "trial",
        "get-started", "request", "quote", "apply", "consultation", "meeting",
        "pricing", "start", "onboard",
    ]
    is_conversion_page = any(kw in url.lower() for kw in conversion_keywords)

    if is_conversion_page and filtered_forms:
        for form in filtered_forms:
            hidden = form.get("hiddenFields", [])
            if not hidden:
                findings.append({
                    "id": "FORM_NO_HIDDEN_TRACKING_FIELDS",
                    "severity": "moderate",
                    "title": f"Form '{form.get('id') or form.get('action') or 'unnamed'}' has no hidden tracking fields",
                    "detail": (
                        "No gclid, utm_source, utm_medium, or utm_campaign capture. "
                        "Offline conversion import will fail and CRM leads have no source attribution."
                    ),
                    "page": url,
                })

    return findings


def check_tag_sprawl(page, all_pages):
    """Too many third-party tracking domains."""
    findings = []
    domains = page.get("thirdPartyTrackingDomains", [])

    # Type guard: if the eval stored a count instead of the array, skip gracefully
    if not isinstance(domains, list):
        return findings

    # Exclude known non-tracking infrastructure domains (CDNs, payment, auth, error tracking)
    non_tracking_patterns = [
        "cdn.jsdelivr.net", "cdnjs.cloudflare.com", "unpkg.com", "ajax.googleapis.com",
        "fonts.googleapis.com", "fonts.gstatic.com", "js.stripe.com", "m.stripe.com",
        "js.braintreegateway.com", "recaptcha.net", "www.gstatic.com",
        "cdn.auth0.com", "sentry.io", "browser.sentry-cdn.com", "cdn.lr-in.com",
        "cdn.polyfill.io", "polyfill.io", "static.cloudflareinsights.com",
        # Consent management SDKs (infrastructure, not marketing tags)
        "cdn.cookielaw.org", "consent.cookiebot.com", "cdn.osano.com",
        "app.termly.io", "consent.trustarc.com",
        # Analytics/tag vendor CDNs (the library itself, not the data collection endpoint)
        "cdn1.adoberesources.net", "cdn.adoberesources.net",
    ]
    tracking_domains = [d for d in domains
                        if not any(p in d for p in non_tracking_patterns)]

    if len(tracking_domains) > 20:
        severity = "critical"
    elif len(tracking_domains) > 15:
        severity = "moderate"
    else:
        return findings

    excluded_count = len(domains) - len(tracking_domains)
    findings.append({
        "id": "TAG_SPRAWL",
        "severity": severity,
        "title": f"{len(tracking_domains)} third-party marketing/tracking domains on single page",
        "detail": (
            f"Domains: {tracking_domains[:10]}{'...' if len(tracking_domains) > 10 else ''}. "
            + (f"({excluded_count} non-tracking infrastructure domains excluded.) " if excluded_count else "")
            + "Each adds network requests and main-thread blocking time. "
            "Check for zombie tags from vendors no longer in use."
        ),
        "page": page.get("url", "unknown"),
    })

    return findings


def check_ghost_preconnects(page, all_pages):
    """Preconnect hints for domains that don't have matching loaded scripts."""
    findings = []
    preconnects = page.get("preconnects", [])
    scripts = page.get("scripts", [])
    pixels = page.get("pixels", {})

    # Known pixel preconnect domains and their corresponding pixel detection keys
    pixel_domains = {
        "connect.facebook.net": "facebook",
        "platform.linkedin.com": "linkedin",
        "platform.twitter.com": "twitter",
        "analytics.tiktok.com": "tiktok",
        "snap.licdn.com": "linkedin",
    }

    ghosts = set()
    for pc in preconnects:
        for domain, pixel_key in pixel_domains.items():
            if domain in pc and not pixels.get(pixel_key):
                # Also check if any script loads from this domain
                script_match = any(domain in s for s in scripts)
                if not script_match:
                    ghosts.add(f"{domain} ({pixel_key} pixel)")
    ghosts = sorted(ghosts)

    if ghosts:
        findings.append({
            "id": "GHOST_PRECONNECTS",
            "severity": "moderate",
            "title": f"Preconnect hints for {len(ghosts)} unimplemented pixel(s)",
            "detail": (
                f"Ghost preconnects: {ghosts}. "
                "DNS lookups wasted on every page. Reveals planned-but-abandoned integrations."
            ),
            "page": page.get("url", "unknown"),
        })

    return findings


def check_abm_integration(page, all_pages):
    """ABM/intent tools detected but not pushing data to GA4."""
    findings = []
    b2b = page.get("b2bTools", {})
    abm = page.get("abmIntegration", {})
    dims = page.get("customDimensionHints", 0)

    # 6sense detected but no dataLayer event or unidentified match
    if b2b.get("6sense") and not abm.get("6sense_event"):
        findings.append({
            "id": "ABM_6SENSE_NO_DATA",
            "severity": "moderate",
            "title": "6sense script loaded but expected dataLayer event not found",
            "detail": (
                "6sense tag is present but '6si_company_details_loaded' event never fired. "
                "Note: some implementations use custom event names, global object callbacks, or "
                "server-side enrichment instead. Check if 6sense data reaches GA4 via a different path "
                "before concluding the integration is broken."
            ),
            "page": page.get("url", "unknown"),
        })
    elif b2b.get("6sense") and abm.get("6sense_match") == "Unidentified":
        findings.append({
            "id": "ABM_6SENSE_UNIDENTIFIED",
            "severity": "moderate",
            "title": "6sense loaded but returned 'Unidentified' match",
            "detail": (
                "6sense API responded but couldn't identify the visitor's company. "
                "This is normal for some traffic (VPNs, ISPs), but if consistent across "
                "pages it may indicate an API key or configuration issue."
            ),
            "page": page.get("url", "unknown"),
        })

    # Demandbase detected but no dataLayer event
    if b2b.get("demandbase") and not abm.get("demandbase_event"):
        findings.append({
            "id": "ABM_DEMANDBASE_NO_DATA",
            "severity": "moderate",
            "title": "Demandbase tag loaded but no data pushed to dataLayer",
            "detail": (
                "Demandbase tag is present but 'Demandbase_Loaded' event never fired. "
                "Firmographic data is not flowing to GA4. Check if the tag callback is "
                "configured to push to dataLayer."
            ),
            "page": page.get("url", "unknown"),
        })

    # Clearbit detected but no dataLayer event
    if b2b.get("clearbit") and not abm.get("clearbit_event"):
        findings.append({
            "id": "ABM_CLEARBIT_NO_DATA",
            "severity": "moderate",
            "title": "Clearbit Reveal loaded but no data pushed to dataLayer",
            "detail": (
                "Clearbit Reveal script is present but 'Clearbit Loaded' event never fired. "
                "Company identification data is not reaching GA4."
            ),
            "page": page.get("url", "unknown"),
        })

    # Any ABM tool detected + data flowing, but no custom dimensions in GA4
    any_abm_detected = any([
        b2b.get("6sense"), b2b.get("demandbase"), b2b.get("clearbit"),
    ])
    any_abm_event = any([
        abm.get("6sense_event"), abm.get("demandbase_event"), abm.get("clearbit_event"),
    ])
    if any_abm_detected and any_abm_event and dims == 0:
        findings.append({
            "id": "ABM_NO_CUSTOM_DIMENSIONS",
            "severity": "moderate",
            "title": "ABM tool pushing events but no custom dimensions found in dataLayer",
            "detail": (
                "The ABM vendor's event fires but no GA4 custom dimension parameters "
                "(company_name, industry, buying_stage, etc.) appear in the dataLayer. "
                "Data may not be registered as custom dimensions in GA4 Admin, or the "
                "GTM variable mapping is missing."
            ),
            "page": page.get("url", "unknown"),
        })

    return findings


def check_video_embeds(page, all_pages):
    """Video embeds (YouTube/Vimeo) missing tracking API parameters."""
    findings = []
    raw = page.get("videoEmbeds", [])
    # videoEmbeds can be a dict {"youtubeIframes": [...]} or a list of video objects
    if isinstance(raw, dict):
        videos = raw.get("youtubeIframes", []) + raw.get("vimeoIframes", [])
    else:
        videos = raw

    def _has_tracking_api(v):
        """Check if video embed has tracking API enabled. Supports both new format
        (hasTrackingApi field) and old format (only hasNoCookie for YouTube)."""
        if "hasTrackingApi" in v:
            return v["hasTrackingApi"]
        # Old format: hasNoCookie only — no tracking API info available, skip
        return True  # Don't flag old-format data since we can't determine API status

    untracked = [v for v in videos if isinstance(v, dict) and not _has_tracking_api(v)]
    if untracked:
        platforms = [v.get("platform", "youtube" if "youtube" in v.get("src", "") else "vimeo" if "vimeo" in v.get("src", "") else "?") for v in untracked]
        findings.append({
            "id": "VIDEO_EMBED_NO_TRACKING_API",
            "severity": "moderate",
            "title": f"{len(untracked)} video embed(s) missing tracking API ({', '.join(platforms)})",
            "detail": (
                "YouTube needs enablejsapi=1, Vimeo needs api=1 in the iframe src. "
                "Without these, GA4 Enhanced Measurement can't track video_start, "
                "video_progress, or video_complete — zero engagement data on video content."
            ),
            "page": page.get("url", "unknown"),
        })

    return findings


def check_crm_cookies(all_pages):
    """CRM tracking cookies detected — flag for subdomain scope verification (cross-page, runs once)."""
    findings = []

    # Collect CRM cookies across all pages (deduplicate)
    all_found = {}
    for page in all_pages:
        crm = page.get("crmCookieScope", {})
        found = crm.get("found", {})
        all_found.update(found)

    if all_found:
        platforms = list(set(all_found.values()))
        cookie_names = list(all_found.keys())
        findings.append({
            "id": "CRM_COOKIE_SCOPE_CHECK",
            "severity": "moderate",
            "title": f"CRM cookies detected ({', '.join(platforms)}) — verify subdomain scope",
            "detail": (
                f"Cookies found: {cookie_names}. If the site uses subdomains (blog, app, docs, "
                "help), these cookies must be scoped to .domain.com not the hostname. "
                "Host-only scoping means the same buyer appears as separate anonymous "
                "visitors on each subdomain, breaking lead scoring and attribution."
            ),
            "page": "cross-page",
        })

    return findings


def check_chatbot_engagement_inflation(page, all_pages):
    """Chatbot firing interaction events on page load before user action."""
    findings = []
    chat = page.get("chatAutoInteraction", {})
    early_events = chat.get("earlyEventsOnLoad", [])

    # Filter out system-ready events that are status broadcasts, not interactions.
    # Events like drift_ready, intercom_booted, qualified_loaded are initialization
    # signals — they only inflate engagement if someone mapped them to a GA4 event.
    system_events = {"drift_ready", "intercom_booted", "qualified_loaded",
                     "drift_controller_ready", "chat_widget_loaded"}
    interaction_events = [e for e in early_events if e.lower() not in system_events]

    if interaction_events:
        findings.append({
            "id": "CHATBOT_AUTO_INTERACTION",
            "severity": "moderate",
            "title": f"Chat tool fires interaction events on load: {interaction_events[:3]}",
            "detail": (
                "Chat-related dataLayer events fire before any user interaction. "
                "In GA4, custom events alone don't automatically create engaged sessions "
                "(unlike Universal Analytics where any event dropped bounce rate). However, "
                "if these events are marked as conversions in GA4, or if they trigger additional "
                "network requests that extend session duration past 10 seconds, they can still "
                "distort engagement metrics. Verify in GTM whether these events trigger any "
                "GA4 tags — if they don't, they're just dataLayer noise."
            ),
            "page": page.get("url", "unknown"),
        })

    return findings


def check_pixels_no_conversion_events(page, all_pages):
    """Ad pixels detected but only firing base pageview — no conversion events."""
    findings = []
    pixels = page.get("pixels", {})
    dl = page.get("dataLayer", [])
    url = page.get("url", "unknown")

    # Only check on conversion-like pages
    conversion_keywords = [
        "contact", "demo", "book", "schedule", "signup", "register", "trial",
        "get-started", "request", "quote", "apply", "consultation", "meeting",
        "pricing", "start", "thank", "success", "confirm",
    ]
    is_conversion_page = any(kw in url.lower() for kw in conversion_keywords)
    if not is_conversion_page:
        return findings

    # Check if any AD pixel is present but no conversion-specific events exist in dataLayer.
    # Filter to actual ad platforms — exclude UX/analytics tools (hotjar, clarity, heap,
    # fullstory, segment, intercom) which don't have "conversion events."
    ad_pixel_keys = {"facebook", "linkedin", "twitter", "tiktok", "google_ads", "bing", "hubspot", "marketo"}
    active_pixels = [name for name, detected in pixels.items() if detected and name in ad_pixel_keys]
    if not active_pixels:
        return findings

    # Look for conversion-like events in dataLayer
    conversion_events = [
        "generate_lead", "sign_up", "purchase", "form_submit", "form_submitted",
        "book_call", "demo_booked", "lead", "conversion", "submit",
        "CompleteRegistration", "Lead", "Schedule",
    ]
    dl_events = [item.get("event", "") for item in dl if isinstance(item, dict)]
    has_conversion_event = any(
        any(ce.lower() in ev.lower() for ce in conversion_events)
        for ev in dl_events
    )

    if not has_conversion_event:
        findings.append({
            "id": "PIXELS_NO_CONVERSION_EVENT",
            "severity": "moderate",
            "title": f"Conversion page has pixels ({', '.join(active_pixels[:3])}) but no conversion event in dataLayer",
            "detail": (
                "Ad pixels are installed on this conversion page, but no conversion-specific event "
                "(generate_lead, form_submit, etc.) was found in the dataLayer. Note: conversions "
                "may fire via direct pixel calls (fbq('track','Lead'), lintrk()), GTM click/visibility "
                "triggers, iframe postMessage handlers, or server-side APIs — these bypass the dataLayer. "
                "Verify in each ad platform's event manager before concluding conversions are missing."
            ),
            "page": url,
        })

    return findings


def check_linkedin_no_conversions(page, all_pages):
    """LinkedIn Insight Tag installed but no conversion events configured."""
    findings = []
    li = page.get("linkedinInsightTag", {})

    if li.get("hasInsightTag") and not li.get("hasConversionCall"):
        findings.append({
            "id": "LINKEDIN_PAGEVIEW_ONLY",
            "severity": "moderate",
            "title": "LinkedIn Insight Tag installed but no inline conversion events found",
            "detail": (
                "The LinkedIn Insight Tag loads for audience building and pageview tracking, "
                "but no lintrk() conversion calls were found in page source. Note: LinkedIn "
                "also supports URL-based conversions configured in Campaign Manager (no inline "
                "code needed) and GTM-fired conversions on form submit. Check Campaign Manager "
                "before concluding no conversions are configured."
            ),
            "page": page.get("url", "unknown"),
        })

    return findings


def check_pardot_third_party(page, all_pages):
    """Pardot/Account Engagement using third-party tracking domains instead of first-party."""
    findings = []
    pardot = page.get("pardotTracking", {})

    if pardot.get("detected") and pardot.get("usesThirdPartyDomain"):
        findings.append({
            "id": "PARDOT_THIRD_PARTY_DOMAIN",
            "severity": "moderate",
            "title": "Pardot tracking uses third-party domain (pi.pardot.com)",
            "detail": (
                "Pardot/Account Engagement tracking loads from pi.pardot.com or go.pardot.com "
                "instead of a branded first-party domain. Safari ITP and Firefox ETP cap "
                "these cookies, degrading visitor tracking for 30-40% of traffic. Prospect "
                "browsing history becomes fragmented after 7 days."
            ),
            "page": page.get("url", "unknown"),
        })

    return findings


def check_enhanced_conversions_missing(page, all_pages):
    """Google Ads present but Enhanced Conversions not configured on conversion pages."""
    findings = []
    gae = page.get("googleAdsEnhanced", {})
    url = page.get("url", "unknown")

    conversion_keywords = [
        "contact", "demo", "book", "schedule", "signup", "register", "trial",
        "get-started", "request", "quote", "apply", "consultation", "meeting",
        "pricing", "start", "thank", "success", "confirm",
    ]
    is_conversion_page = any(kw in url.lower() for kw in conversion_keywords)

    if not is_conversion_page:
        return findings

    if gae.get("hasGoogleAds") and not gae.get("hasEnhancedConfig") and not gae.get("hasUserDataInDL"):
        findings.append({
            "id": "GOOGLE_ADS_NO_ENHANCED_CONVERSIONS",
            "severity": "moderate",
            "title": "Google Ads pixel present but Enhanced Conversions not detected on this page",
            "detail": (
                "Google Ads tag fires on this page but no Enhanced Conversions configuration "
                "(enhanced_conversions, user_data) was found in page source or dataLayer. "
                "Note: Enhanced Conversions may be configured on a different page (e.g., the "
                "thank-you page after form submit), via GTM server-side tagging, or through "
                "the Google Ads API. Check Google Ads diagnostics before concluding it's missing. "
                "If truly absent, 15-25% of conversions go unmatched and Smart Bidding "
                "optimizes with incomplete data."
            ),
            "page": url,
        })

    return findings


def check_thank_you_indexable(page, all_pages):
    """Thank-you/confirmation pages that are publicly indexable."""
    findings = []
    url = page.get("url", "unknown")
    indexability = page.get("pageIndexability", {})

    thank_you_keywords = [
        "thank-you", "thankyou", "thanks", "/success", "/confirm", "/welcome", "/submitted",
    ]
    # Exclude blog/article/resource URLs to avoid false positives on
    # "customer-success-stories" or "how-to-thank-your-sponsors"
    content_paths = ["/blog/", "/news/", "/article/", "/resource/", "/post/", "/insight/"]
    is_content_page = any(p in url.lower() for p in content_paths)
    is_thank_you = not is_content_page and any(kw in url.lower() for kw in thank_you_keywords)

    # Support both enriched format (pageIndexability.hasNoindex) and standalone eval (meta.robots)
    has_noindex = indexability.get("hasNoindex", False)
    if not has_noindex:
        robots = page.get("meta", {}).get("robots") or ""
        has_noindex = "noindex" in robots.lower()

    if is_thank_you and not has_noindex:
        findings.append({
            "id": "THANK_YOU_PAGE_INDEXABLE",
            "severity": "moderate",
            "title": "Thank-you/confirmation page is publicly indexable (no noindex)",
            "detail": (
                "This confirmation page has no noindex meta tag, making it crawlable by "
                "search engines and reachable by direct URL. Bot traffic and accidental "
                "visits inflate conversion counts, pollute remarketing audiences, and may "
                "expose internal workflow details. Add <meta name='robots' content='noindex'>."
            ),
            "page": url,
        })

    return findings


def check_hidden_fields_empty(page, all_pages):
    """Hidden attribution fields exist in forms but have empty values.

    Two-phase check: compares hidden field values WITHOUT UTMs (initial page load)
    vs WITH UTMs (Step 10 re-check). Many forms intentionally populate hidden fields
    only when URL params exist. Only flag as broken if fields are still empty even
    with UTMs present in the URL."""
    findings = []
    form_values = page.get("formHiddenFieldValues", [])
    form_values_with_utms = page.get("formHiddenFieldValuesWithUtms", [])
    url = page.get("url", "unknown")

    conversion_keywords = [
        "contact", "demo", "book", "schedule", "signup", "register", "trial",
        "get-started", "request", "quote", "apply", "consultation", "meeting",
        "pricing", "start", "onboard",
    ]
    is_conversion_page = any(kw in url.lower() for kw in conversion_keywords)

    if not is_conversion_page:
        return findings

    # Build lookup of post-UTM field values by stable identity for comparison.
    # Match forms by (id, action, field_names) fingerprint — NOT by array index,
    # because React hydration, modals, or A/B tests can reorder forms between snapshots.
    def _form_fingerprint(form):
        fid = form.get("id") or ""
        action = form.get("action") or ""
        field_names = sorted(f["name"] for f in form.get("hiddenFields", []))
        return (fid, action, tuple(field_names))

    utm_form_lookup = {}
    for form in form_values_with_utms:
        fp = _form_fingerprint(form)
        populated = {f["name"] for f in form.get("hiddenFields", []) if f.get("value")}
        utm_form_lookup[fp] = populated

    has_utm_data = bool(form_values_with_utms)

    for i, form in enumerate(form_values):
        hidden = form.get("hiddenFields", [])
        if not hidden:
            continue

        empty_fields = [f["name"] for f in hidden if not f.get("value")]
        if not empty_fields:
            continue

        form_key = form.get("id") or form.get("action") or f"form-{i}"

        if not has_utm_data:
            # No UTM re-check data available — fall back with caveat
            findings.append({
                "id": "HIDDEN_FIELDS_EMPTY",
                "severity": "moderate",
                "title": f"Form '{form_key}' has empty attribution fields: {empty_fields}",
                "detail": (
                    f"Hidden fields {empty_fields} are empty on initial page load (no UTMs in URL). "
                    "This may be by design — many forms populate these fields only when URL parameters "
                    "are present. Verify by loading the page with UTM parameters appended."
                ),
                "page": url,
            })
            continue

        fp = _form_fingerprint(form)
        populated_with_utms = utm_form_lookup.get(fp, set())

        # Fields that are empty without UTMs but populated with UTMs = working as designed
        still_empty = [f for f in empty_fields if f not in populated_with_utms]

        if still_empty:
            findings.append({
                "id": "HIDDEN_FIELDS_EMPTY",
                "severity": "critical",
                "title": f"Form '{form_key}' has empty attribution fields even with UTMs: {still_empty}",
                "detail": (
                    f"Hidden fields {still_empty} remain empty even when UTM parameters are present "
                    "in the URL. The JavaScript that should populate them is broken or missing. "
                    "CRM leads will have blank source attribution and offline conversion import "
                    "will silently fail."
                ),
                "page": url,
            })
        # If all empty fields were fixed by UTMs, no finding — working as designed

    return findings


def check_utm_survival(page, all_pages):
    """UTM parameters stripped by redirect chains — inflates Direct traffic in GA4."""
    findings = []
    utm = page.get("utmSurvival")
    if not utm or not utm.get("tested"):
        return findings

    url = page.get("url", "unknown")

    if not utm.get("utmSurvived"):
        stripped_by = utm.get("strippedBy", "unknown redirect")
        redirect_count = utm.get("redirectCount", 0)
        detail_parts = [
            f"UTM parameters were stripped by {stripped_by}",
        ]
        if redirect_count:
            detail_parts.append(f"({redirect_count} redirect hop(s) detected)")
        detail_parts.append(
            "Every UTM-tagged link — email, paid ads, social, partner — "
            "appears as Direct traffic in GA4. Campaign ROI is unmeasurable."
        )
        findings.append({
            "id": "UTM_PARAMS_STRIPPED",
            "severity": "critical",
            "title": f"Redirects strip UTM parameters on {url}",
            "detail": ". ".join(detail_parts),
            "page": url,
        })

    # gclid stripped = Google Ads offline conversion import broken
    if utm.get("utmSurvived") and not utm.get("gclidSurvived"):
        findings.append({
            "id": "GCLID_STRIPPED",
            "severity": "critical",
            "title": f"Redirects strip gclid on {url}",
            "detail": (
                "The gclid click ID is stripped by redirects even though UTM "
                "parameters survive. Google Ads offline conversion import and "
                "Enhanced Conversions cannot match conversions back to clicks. "
                "Smart Bidding optimizes blind."
            ),
            "page": url,
        })

    # UTMs survive in URL but GA4 didn't receive them
    if utm.get("utmSurvived") and utm.get("ga4ReceivedUtms") is False:
        findings.append({
            "id": "GA4_MISSED_UTMS",
            "severity": "critical",
            "title": f"UTMs in URL but GA4 didn't capture them on {url}",
            "detail": (
                "UTM parameters survived the redirect chain and are present "
                "in the final URL, but the GA4 collect request did not contain "
                "them. The analytics tag likely loaded after a client-side "
                "redirect that silently reset the URL. Traffic still appears "
                "as Direct in GA4 reports."
            ),
            "page": url,
        })

    # gclid not persisted to cookies/storage/fields
    if not utm.get("gclidSurvived", True) or utm.get("gclidPersisted") is False:
        # Only fire if gclid made it to the page but wasn't stored
        if utm.get("gclidSurvived") and utm.get("gclidPersisted") is False:
            findings.append({
                "id": "GCLID_NOT_PERSISTED",
                "severity": "moderate",
                "title": f"gclid not persisted to cookies or storage on {url}",
                "detail": (
                    "The gclid parameter survived the redirect chain but was "
                    "not stored in cookies, localStorage, or hidden form fields. "
                    "If the user converts in a later session, Google Ads cannot "
                    "match the conversion to the original click."
                ),
                "page": url,
            })

    return findings


def check_cta_tracking(page, all_pages):
    """CTA buttons with zero tracking attributes."""
    findings = []
    ctas = page.get("ctaTracking", page.get("ctas", []))

    def _has_tracking(c):
        """Check for tracking attributes across both ctaTracking and ctas formats."""
        # ctaTracking format: hasDataAttributes (bool), dataAttributes (list)
        if c.get("hasDataAttributes") or len(c.get("dataAttributes", [])) > 0:
            return True
        # ctas format: hasOnclick (bool), dataAttrs (list)
        if c.get("hasOnclick") or len(c.get("dataAttrs", [])) > 0:
            return True
        return False

    untracked = [c for c in ctas if not _has_tracking(c)]
    if len(untracked) >= 2:
        labels = [c.get("text", "?")[:40] for c in untracked[:3]]
        findings.append({
            "id": "CTA_NO_TRACKING",
            "severity": "moderate",
            "title": f"{len(untracked)} CTA button(s) have zero tracking attributes",
            "detail": (
                f"Buttons: {labels}. "
                "No inline onclick or data-* tracking attributes detected. Note: GTM's built-in "
                "Click trigger and addEventListener-based tracking (standard in React/Next.js apps) "
                "leave zero DOM attributes on buttons — this is normal. Verify in GTM whether a "
                "Click or Link Click trigger covers these elements before concluding they're untracked."
            ),
            "page": page.get("url", "unknown"),
        })

    return findings


# --- Consent Deep Checks ---


def check_consent_mode_defaults(page, all_pages):
    """Consent Mode defaults: granted when should be denied, missing V2 signals, or no defaults."""
    findings = []
    cms = page.get("consentModeState", {})
    consent = page.get("consent", {})
    url = page.get("url", "unknown")

    has_cmp = any([
        consent.get("cookiebot"), consent.get("onetrust"),
        consent.get("osano"), consent.get("termly"), consent.get("trustarc"),
        consent.get("bannerVisible"),
        consent.get("usercentrics"),
        consent.get("didomi"),
        consent.get("ketch"),
        consent.get("iubenda"),
    ])

    defaults = cms.get("defaults", {})

    # Also check top-level consentModeDefaults (from eval script) if consentModeState is empty.
    # This fallback format is a simple {signal: value} dict — it doesn't capture the full
    # defaultCommands array, so we can't see region-scoped defaults. We also check the
    # dataLayer directly for Arguments-style consent pushes with a region parameter.
    _used_fallback = False
    if not defaults and page.get("consentModeDefaults"):
        defaults = page["consentModeDefaults"]
        _used_fallback = True
        # Check dataLayer for region-scoped consent defaults
        has_region = False
        for item in page.get("dataLayer", []):
            if not isinstance(item, dict):
                continue
            # Check for Arguments-style consent pushes stored as {"0": "consent", "1": "default", "2": {...}}
            if item.get("0") == "consent" and item.get("1") == "default":
                payload = item.get("2", {})
                if isinstance(payload, dict) and "region" in payload:
                    has_region = True
                    break
        cms = {
            "hasDefaults": True,
            "defaults": defaults,
            "hasRegionScoping": has_region,
            "hasV2Signals": "ad_user_data" in defaults and "ad_personalization" in defaults,
            "hasPartialV2": ("ad_user_data" in defaults) != ("ad_personalization" in defaults),
        }

    if not has_cmp:
        return findings  # No CMP = already flagged by check_consent

    # CMP present but Consent Mode defaults not set at all.
    # Only emit this if consent mode is partially present (e.g., consentMode flag detected
    # but no defaults). If consent mode is entirely absent, check_consent already emits
    # NO_CONSENT_MODE — don't duplicate.
    has_any_consent_mode_signal = (
        consent.get("consentMode", False)
        or cms.get("hasDefaults", False)
    )
    if has_cmp and not cms.get("hasDefaults"):
        if has_any_consent_mode_signal:
            # Consent Mode was partially detected but defaults are missing
            findings.append({
                "id": "CONSENT_MODE_NO_DEFAULTS",
                "severity": "moderate",
                "title": "CMP present but no Consent Mode default state configured",
                "detail": (
                    "A consent banner exists but Google Consent Mode has no 'default' command in the "
                    "dataLayer. Note: some sites use strict script blocking (GTM doesn't load until "
                    "consent is granted), which is fully GDPR-compliant but means no Consent Mode "
                    "defaults will be present. If GTM is consent-gated, this finding is informational. "
                    "If GTM loads immediately, the absence of defaults means Google tags don't know "
                    "whether to wait for consent or fire."
                ),
                "page": url,
            })
        # Either way, no defaults means nothing more to check
        return findings

    # Check if ad_storage or analytics_storage defaults to "granted" — wrong for EU/EEA
    # But respect region-scoped defaults: a site that pushes 'denied' for EU and 'granted'
    # globally is compliant. The JS eval now tracks hasRegionScoping for this case.
    has_region_scoping = cms.get("hasRegionScoping", False)

    granted_by_default = []
    for key in ["ad_storage", "analytics_storage", "ad_user_data", "ad_personalization"]:
        if defaults.get(key) == "granted":
            granted_by_default.append(key)

    if granted_by_default and not has_region_scoping:
        # If we used the fallback format, we may be seeing the global defaults
        # while missing a region-scoped 'denied' push for EU. Downgrade to moderate.
        severity = "moderate" if _used_fallback else "critical"
        caveat = (
            " Note: this may be the global fallback default — the site could have a separate "
            "region-scoped 'denied' default for EU/EEA that wasn't captured in this data format. "
            "Verify by checking all consent('default', ...) calls in the page source or GTM."
        ) if _used_fallback else ""
        findings.append({
            "id": "CONSENT_MODE_DEFAULTS_GRANTED",
            "severity": severity,
            "title": f"Consent Mode defaults to 'granted' for: {granted_by_default}",
            "detail": (
                f"Consent state: {defaults}. "
                "Defaulting to 'granted' means tracking fires before the user acts on the banner. "
                "This is illegal under GDPR/ePrivacy for EU visitors. Defaults should be 'denied' "
                "with a region parameter restricting to EU/EEA, or 'denied' globally."
                + caveat
            ),
            "page": url,
        })
    elif granted_by_default and has_region_scoping:
        findings.append({
            "id": "CONSENT_MODE_DEFAULTS_GRANTED",
            "severity": "info",
            "title": f"Consent Mode defaults to 'granted' for {granted_by_default} (region-scoped)",
            "detail": (
                f"Consent state: {defaults}. Region-scoped defaults detected — the site likely "
                "pushes 'denied' for EU/EEA and 'granted' as a global fallback. This is a valid "
                "and recommended implementation pattern. Verify that the EU-specific default "
                "correctly denies ad_storage and analytics_storage."
            ),
            "page": url,
        })

    # Check for Consent Mode v2 signals (ad_user_data, ad_personalization)
    # Both are required — having only one is a partial implementation.
    if cms.get("hasDefaults") and not cms.get("hasV2Signals"):
        if cms.get("hasPartialV2"):
            findings.append({
                "id": "CONSENT_MODE_PARTIAL_V2",
                "severity": "moderate",
                "title": "Consent Mode has only one of two required v2 signals",
                "detail": (
                    f"Defaults include: {list(defaults.keys())}. "
                    "Consent Mode v2 requires BOTH 'ad_user_data' AND 'ad_personalization'. "
                    "Only one is present. This partial implementation still breaks EU "
                    "remarketing and conversion measurement for the missing signal."
                ),
                "page": url,
            })
        else:
            findings.append({
                "id": "CONSENT_MODE_V1_ONLY",
                "severity": "moderate",
                "title": "Consent Mode v1 detected — missing v2 required signals",
                "detail": (
                    f"Defaults only include: {list(defaults.keys())}. "
                    "Consent Mode v2 requires 'ad_user_data' and 'ad_personalization' signals. "
                    "Since March 2024, Google requires v2 for EU remarketing and conversion "
                    "measurement. Without these signals, Google Ads conversion data is degraded."
                ),
                "page": url,
            })

    return findings


def check_rogue_scripts_outside_gtm(page, all_pages):
    """Tracking scripts hardcoded outside GTM — bypass Consent Mode entirely."""
    findings = []
    rogue = page.get("scriptsOutsideGTM", {})
    consent = page.get("consent", {})

    has_cmp = any([
        consent.get("cookiebot"), consent.get("onetrust"),
        consent.get("osano"), consent.get("termly"), consent.get("trustarc"),
        consent.get("bannerVisible"),
        consent.get("usercentrics"), consent.get("didomi"),
        consent.get("ketch"), consent.get("iubenda"),
    ])

    scripts = rogue.get("scripts", [])
    if has_cmp and scripts:
        findings.append({
            "id": "ROGUE_SCRIPTS_BYPASS_CONSENT",
            "severity": "moderate",
            "title": f"{len(scripts)} tracking script(s) hardcoded outside GTM — bypass consent",
            "detail": (
                f"Scripts: {scripts[:3]}. "
                "These scripts appear in the HTML outside GTM. However, some CMPs dynamically inject "
                "tracking scripts into the page only AFTER consent is granted (without using "
                "type='text/plain' or data-cookieconsent attributes). If this audit ran post-consent, "
                "these scripts may have been injected by the CMP's callback — not pre-loaded. "
                "Verify by checking pre-consent network requests: if no requests to these domains "
                "fire before the user accepts cookies, the CMP is working correctly. If they do fire "
                "pre-consent, move them into GTM or gate them with the CMP's script blocking."
            ),
            "page": page.get("url", "unknown"),
        })

    return findings


def check_iframe_cookie_leak(page, all_pages):
    """YouTube iframes using youtube.com instead of youtube-nocookie.com."""
    findings = []
    leaky_iframes = page.get("iframeCookieRisk", [])

    if leaky_iframes:
        findings.append({
            "id": "IFRAME_COOKIE_LEAK",
            "severity": "moderate",
            "title": f"{len(leaky_iframes)} YouTube embed(s) using youtube.com instead of youtube-nocookie.com",
            "detail": (
                f"Iframes: {[s[:80] for s in leaky_iframes[:3]]}. "
                "Standard YouTube embeds drop Google tracking cookies (NID, VISITOR_INFO, YSC). "
                "Note: if the CMP blocks the iframe src until consent is granted (replacing it "
                "with a placeholder), this is a false positive — the iframe only exists because "
                "the audit ran post-consent. Verify by checking pre-consent state. If the iframe "
                "is always present regardless of consent, replace with youtube-nocookie.com."
            ),
            "page": page.get("url", "unknown"),
        })

    return findings


def check_datalayer_race_condition(page, all_pages):
    """Business data pushed to dataLayer after GTM tags already fired."""
    findings = []
    seq = page.get("dataLayerSequencing", {})

    late_pushes = seq.get("latePushes", [])
    if late_pushes:
        late_keys = []
        for push in late_pushes:
            late_keys.extend(push.get("keys", []))
        late_keys = list(set(late_keys))

        findings.append({
            "id": "DATALAYER_RACE_CONDITION",
            "severity": "moderate",
            "title": f"DataLayer sequencing: {len(late_pushes)} business data push(es) arrived after gtm.js",
            "detail": (
                f"Late keys: {late_keys}. "
                f"gtm.js fired at dataLayer index {seq.get('gtmJsIndex', '?')}, but business data "
                f"({late_keys}) was pushed at later indices. This is only a problem if tags fire on "
                "Page View — if tags use DOM Ready, Window Loaded, or custom event triggers, the data "
                "arrives in time. Verify trigger timing in GTM before treating this as broken."
            ),
            "page": page.get("url", "unknown"),
        })

    return findings


def check_booking_iframe_tracking(page, all_pages):
    """Scheduling/booking iframe on conversion page with no event listener."""
    findings = []
    url = page.get("url", "")

    # Only check pages that look like conversion pages
    conversion_paths = ["contact", "book", "schedule", "demo", "meeting", "call"]
    if not any(p in url.lower() for p in conversion_paths):
        return findings

    iframes = page.get("iframes", [])
    if not iframes:
        return findings

    scheduling_domains = [
        "calendar.google.com", "calendly.com", "hubspot.com/meetings",
        "acuityscheduling.com", "chilipiper.com", "savvycal.com",
        "tidycal.com", "cal.com",
    ]

    scheduling_iframes = [
        src for src in iframes
        if any(d in src for d in scheduling_domains)
    ]

    if not scheduling_iframes:
        return findings

    has_listener = page.get("hasPostMessageListener", False)

    if not has_listener:
        domain = "unknown"
        for src in scheduling_iframes:
            for d in scheduling_domains:
                if d in src:
                    domain = d
                    break
            break

        findings.append({
            "id": "BOOKING_IFRAME_NO_TRACKING",
            "severity": "moderate",
            "title": f"Booking iframe ({domain}) on conversion page — no visible event listener",
            "detail": (
                f"The conversion page embeds a scheduling tool via iframe ({domain}) "
                f"but no postMessage listener was found in inline script text. "
                f"Note: this check can only inspect inline scripts and script URLs — if the "
                f"site uses compiled/bundled JavaScript (React, Next.js, Webpack, etc.), the "
                f"listener may exist inside a bundle file and not be visible to this scan. "
                f"Verify in the browser console: run `getEventListeners(window)` and look for "
                f"'message' listeners. If none exist, booking completions are invisible to analytics."
            ),
            "page": url,
        })

    return findings


def check_no_cmp_with_tracking(all_pages):
    """No consent management despite active tracking (cross-page, fires once)."""
    findings = []

    # Check if ANY page has a CMP
    any_cmp = any(
        any([
            page.get("consent", {}).get("cookiebot"),
            page.get("consent", {}).get("onetrust"),
            page.get("consent", {}).get("osano"),
            page.get("consent", {}).get("termly"),
            page.get("consent", {}).get("trustarc"),
            page.get("consent", {}).get("bannerVisible"),
            page.get("consent", {}).get("usercentrics"),
            page.get("consent", {}).get("didomi"),
            page.get("consent", {}).get("ketch"),
            page.get("consent", {}).get("iubenda"),
        ])
        for page in all_pages
    )

    if any_cmp:
        return findings

    # Check if the site has active tracking on any page
    any_tracking = any(
        page.get("gtmContainerCount", 0) > 0
        or page.get("networkEvidence", {}).get("serverSideTagging", False)
        or any(page.get("pixels", {}).get(k) for k in page.get("pixels", {}))
        or any((page.get("alternativeTMS") or page.get("legacyTMS") or {}).get(k)
               for k in (page.get("alternativeTMS") or page.get("legacyTMS") or {}))
        for page in all_pages
    )

    if not any_tracking:
        return findings

    # If cookies are present, check_consent already handles no-CMP-with-cookies
    any_cookies = any(page.get("knownCookies", []) for page in all_pages)
    if any_cookies:
        return findings

    findings.append({
        "id": "NO_CMP_WITH_TRACKING",
        "severity": "info",
        "title": "No consent management platform despite active tracking",
        "detail": (
            "Tracking is active (GTM or other TMS detected) but no consent banner or CMP was found. "
            "If the site serves EU visitors, a CMP with Google Consent Mode v2 is recommended. "
            "Server-side tagging can set cookies that bypass client-side detection — verify whether "
            "analytics cookies are being set."
        ),
        "page": "cross-page",
    })

    return findings


def check_adobe_stack(page, all_pages):
    """Adobe analytics stack — detect dual analytics, deprecated DTM, etc."""
    findings = []
    url = page.get("url", "unknown")
    adobe = page.get("adobeStack", {})
    tms = (page.get("alternativeTMS") or page.get("legacyTMS") or {})

    if not adobe and not tms:
        return findings

    # Dual Adobe analytics: legacy AppMeasurement alongside AEP Web SDK
    if adobe.get("appMeasurement") and adobe.get("aepWebSdk"):
        findings.append({
            "id": "DUAL_ADOBE_ANALYTICS",
            "severity": "moderate",
            "title": "Dual Adobe analytics: legacy AppMeasurement + AEP Web SDK",
            "detail": (
                "Both the legacy AppMeasurement library and the modern Adobe AEP Web SDK "
                "(Alloy) are loaded. This is common during migrations but means duplicate "
                "data collection, increased page weight, and potential data discrepancies. "
                "Complete the migration to AEP and remove AppMeasurement."
            ),
            "page": url,
        })

    # Deprecated Adobe DTM (end-of-life)
    if tms.get("adobe_dtm"):
        findings.append({
            "id": "ADOBE_DTM_DEPRECATED",
            "severity": "moderate",
            "title": "Adobe DTM detected — end-of-life tag manager",
            "detail": (
                "Adobe Dynamic Tag Management (DTM) reached end-of-life. "
                "It should be migrated to Adobe Launch (now Adobe Experience Platform Tags). "
                "DTM no longer receives updates or security patches."
            ),
            "page": url,
        })

    # Dual TMS: GTM + Tealium or GTM + Adobe Launch
    gtm_present = page.get("gtmContainerCount", 0) > 0
    alt_tms_names = []
    if tms.get("tealium_iq"):
        alt_tms_names.append("Tealium iQ")
    if tms.get("adobe_launch"):
        alt_tms_names.append("Adobe Launch")
    if tms.get("adobe_dtm"):
        alt_tms_names.append("Adobe DTM")
    if tms.get("ensighten"):
        alt_tms_names.append("Ensighten")

    if gtm_present and alt_tms_names:
        findings.append({
            "id": "DUAL_TMS",
            "severity": "moderate",
            "title": f"Dual tag management: GTM + {', '.join(alt_tms_names)}",
            "detail": (
                f"Both Google Tag Manager and {', '.join(alt_tms_names)} are loaded on the same page. "
                f"Events are processed by multiple TMS systems, risking duplicate pixel fires, "
                f"conflicting consent handling, and doubled maintenance burden. "
                f"Consolidate to a single TMS."
            ),
            "page": url,
        })

    return findings


# --- Cross-page checks (run once across all pages) ---

def check_consistency(all_pages):
    """GTM/GA4 consistency across pages."""
    findings = []

    all_gtm_ids = set()
    all_ga4_ids = set()
    pages_without_gtm = []
    pages_without_ga4 = []

    for page in all_pages:
        ti = page.get("tagInstallations", {})
        net = page.get("networkEvidence", {})

        # Use first-party IDs when available; fall back to all IDs for backward compat
        gtm = set(ti.get("firstPartyGtmIds", ti.get("gtmIds", [])))
        ga4 = set(ti.get("firstPartyGa4Ids", ti.get("ga4Ids", [])))

        # Network evidence supplements DOM scanning — catches SPA-injected and
        # consent-gated containers invisible to top-level script selectors
        raw_net_gtm = net.get("gtmJsRequests", [])
        net_gtm = set(raw_net_gtm) if isinstance(raw_net_gtm, list) else set()
        gtm = gtm | net_gtm

        # Also merge GA4 property IDs from network evidence (catches GTM-managed GA4)
        raw_net_ga4 = net.get("ga4PropertyIds", [])
        net_ga4 = set(raw_net_ga4) if isinstance(raw_net_ga4, list) else set()
        ga4 = ga4 | net_ga4

        # Runtime detection: google_tag_manager object contains GTM and GA4 IDs
        # that aren't visible in page source (e.g., sGTM rewrites script URLs).
        # This catches GTM-managed GA4 without needing networkEvidence.
        gtm_obj = page.get("gtmObject", [])
        if isinstance(gtm_obj, list):
            for key in gtm_obj:
                if isinstance(key, str):
                    if re.match(r'^GTM-[A-Z0-9]{4,12}$', key):
                        gtm.add(key)
                    elif re.match(r'^G-[A-Z0-9]{4,12}$', key):
                        ga4.add(key)

        # Cookie evidence: _ga_XXXXXXX cookies prove GA4 is collecting data,
        # even when the measurement ID isn't in page source (sGTM, GTM-managed).
        for cookie in page.get("knownCookies", []):
            if isinstance(cookie, str) and cookie.startswith("_ga_"):
                # _ga_XXXXXXX → G-XXXXXXX (GA4 stream cookie suffix = measurement ID suffix)
                suffix = cookie[4:]
                if suffix and re.match(r'^[A-Z0-9]{4,12}$', suffix):
                    ga4.add(f"G-{suffix}")

        all_gtm_ids.update(gtm)
        all_ga4_ids.update(ga4)

        if not gtm:
            pages_without_gtm.append(page.get("url", "?"))
        if not ga4:
            pages_without_ga4.append(page.get("url", "?"))

    if pages_without_gtm:
        if len(pages_without_gtm) == len(all_pages):
            findings.append({
                "id": "NO_GTM",
                "severity": "moderate",
                "title": "No Google Tag Manager found on any page",
                "detail": (
                    "GTM is not installed. The site may use an alternative TMS "
                    "(Segment, Tealium, Adobe Launch) or manage tags via hardcoded scripts. "
                    "Check legacyTMS detection and network requests for alternative tag managers."
                ),
                "page": "cross-page",
            })
        else:
            findings.append({
                "id": "INCONSISTENT_GTM",
                "severity": "critical",
                "title": f"GTM missing on {len(pages_without_gtm)} of {len(all_pages)} pages",
                "detail": f"Pages without GTM: {pages_without_gtm}",
                "page": "cross-page",
            })

    # Network evidence: GA4 collect requests prove GA4 is working even if no G-XXXXXXX
    # appears in page source (common with GTM-managed GA4).
    any_ga4_collect = any(
        page.get("networkEvidence", {}).get("ga4CollectSeen", False)
        for page in all_pages
    )

    # Server-side tagging: sGTM loads GA4 entirely server-side — no G-XXXXXXX in page
    # source, no analytics script domains to match. If sGTM is detected, the site almost
    # certainly has analytics running (nobody deploys sGTM without GA4).
    any_sgtm = any(
        page.get("networkEvidence", {}).get("serverSideTagging", False)
        for page in all_pages
    )

    # Check if the site uses any alternative analytics platform (Adobe, Amplitude, etc.)
    # so we don't flag NO_GA4 as critical when they have a deliberate non-Google stack.
    has_alternative_analytics = any(
        any([
            page.get("pixels", {}).get("segment"),
            page.get("pixels", {}).get("heap"),
            # Amplitude (check scripts — no dedicated pixel key in eval)
            any("amplitude.com" in s or "cdn.amplitude.com" in s for s in page.get("scripts", [])),
            # Adobe stack (structured detection from eval script)
            page.get("adobeStack", {}).get("appMeasurement"),
            page.get("adobeStack", {}).get("aepWebSdk"),
            page.get("adobeStack", {}).get("firstPartyCollection"),
            # Adobe AEP / Analytics (fallback: check scripts for common Adobe domains)
            any("adoberesources.net" in s or "demdex.net" in s or "adobedtm.com" in s
                or "omtrdc.net" in s or "smetrics." in s
                for s in page.get("scripts", [])),
            # Tealium (often implies Tealium-managed analytics)
            (page.get("alternativeTMS") or page.get("legacyTMS") or {}).get("tealium_iq", False),
            # Matomo / Piwik
            any("matomo" in s or "piwik" in s for s in page.get("scripts", [])),
            # PostHog
            any("posthog" in s for s in page.get("scripts", [])),
            # Mixpanel
            any("mixpanel.com" in s for s in page.get("scripts", [])),
            # HubSpot (full analytics platform, not just a pixel)
            page.get("pixels", {}).get("hubspot"),
            # Marketo Munchkin
            page.get("pixels", {}).get("marketo"),
            # Cloudflare Zaraz (edge-side tag management)
            page.get("cloudflareZaraz", {}).get("detected"),
        ])
        for page in all_pages
    )

    if pages_without_ga4:
        if len(pages_without_ga4) == len(all_pages) and not any_ga4_collect:
            if has_alternative_analytics:
                findings.append({
                    "id": "NO_GA4",
                    "severity": "info",
                    "title": "No GA4 — site uses alternative analytics platform",
                    "detail": (
                        "Google Analytics 4 is not installed, but an alternative analytics platform "
                        "(Adobe, Amplitude, Segment, etc.) was detected. This is a valid choice. "
                        "Note: if the site runs Google Ads, GA4 provides direct signal to Smart Bidding "
                        "that alternative platforms cannot — consider GA4 as a supplementary install."
                    ),
                    "page": "cross-page",
                })
            elif any_sgtm:
                # sGTM detected — GA4 is almost certainly running server-side.
                # Don't emit NO_ANALYTICS; downgrade to info.
                sgtm_domains = [
                    page.get("networkEvidence", {}).get("sgtmDomain", "unknown")
                    for page in all_pages
                    if page.get("networkEvidence", {}).get("serverSideTagging")
                ]
                findings.append({
                    "id": "GA4_VIA_SGTM",
                    "severity": "info",
                    "title": "GA4 likely running via server-side GTM",
                    "detail": (
                        f"No GA4 measurement ID visible in page source, but server-side tagging "
                        f"detected via {list(set(sgtm_domains))}. GA4 is almost certainly "
                        f"managed within the sGTM container. Cannot confirm from static analysis — "
                        f"runtime browser inspection needed to verify GA4 collect requests."
                    ),
                    "page": "cross-page",
                })
            else:
                findings.append({
                    "id": "NO_ANALYTICS",
                    "severity": "critical",
                    "title": "No analytics platform detected on any page",
                    "detail": (
                        "Neither GA4 nor any alternative analytics platform (Adobe, Amplitude, "
                        "Segment, Mixpanel, PostHog, Matomo) was detected. The site has no "
                        "web analytics — visitor behavior is completely unmeasured."
                    ),
                    "page": "cross-page",
                })
        elif len(pages_without_ga4) == len(all_pages) and any_ga4_collect:
            # GA4 IDs not in page source but collect requests prove it's working (GTM-managed)
            findings.append({
                "id": "GA4_VIA_GTM_ONLY",
                "severity": "info",
                "title": "GA4 is deployed via GTM (no hardcoded G- ID in page source)",
                "detail": (
                    "GA4 collect requests were observed in network traffic, but no G-XXXXXXX ID "
                    "appears in top-level page scripts. GA4 is managed entirely through GTM. "
                    "This is a valid and common deployment pattern."
                ),
                "page": "cross-page",
            })
        else:
            # Some pages missing — check if network evidence covers them
            pages_truly_without_ga4 = [
                page.get("url", "?") for page in all_pages
                if page.get("url", "?") in pages_without_ga4
                and not page.get("networkEvidence", {}).get("ga4CollectSeen", False)
            ]
            if pages_truly_without_ga4:
                findings.append({
                    "id": "INCONSISTENT_GA4",
                    "severity": "critical",
                    "title": f"GA4 missing on {len(pages_truly_without_ga4)} of {len(all_pages)} pages",
                    "detail": f"Pages without GA4 (confirmed by both source scan and network): {pages_truly_without_ga4}",
                    "page": "cross-page",
                })

    # Check if different pages have different GTM container IDs (first-party only).
    # Only flag if pages actually DIFFER — a site that consistently uses 2 GTM
    # containers on every page is intentional partitioning, not inconsistency.
    if len(all_gtm_ids) > 1:
        per_page = {}
        for page in all_pages:
            ti = page.get("tagInstallations", {})
            net = page.get("networkEvidence", {})
            gtm = set(ti.get("firstPartyGtmIds", ti.get("gtmIds", [])))
            raw_net = net.get("gtmJsRequests", [])
            gtm |= set(raw_net) if isinstance(raw_net, list) else set()
            per_page[page.get("url", "?")] = sorted(gtm)
        unique_sets = set(frozenset(ids) for ids in per_page.values())
        if len(unique_sets) > 1:
            findings.append({
                "id": "INCONSISTENT_GTM_IDS",
                "severity": "moderate",
                "title": f"Different GTM container IDs across pages: {sorted(all_gtm_ids)}",
                "detail": f"Per-page breakdown: {per_page}",
                "page": "cross-page",
            })

    # Check if different pages use different GA4 property IDs — fractured measurement.
    # Only flag if pages actually DIFFER (same logic as GTM above).
    if len(all_ga4_ids) > 1:
        per_page_ga4 = {}
        for page in all_pages:
            ti = page.get("tagInstallations", {})
            net = page.get("networkEvidence", {})
            ids = set(ti.get("firstPartyGa4Ids", ti.get("ga4Ids", [])))
            raw_net = net.get("ga4PropertyIds", [])
            ids |= set(raw_net) if isinstance(raw_net, list) else set()
            per_page_ga4[page.get("url", "?")] = sorted(ids)
        unique_ga4_sets = set(frozenset(ids) for ids in per_page_ga4.values())
        if len(unique_ga4_sets) > 1:
            findings.append({
                "id": "INCONSISTENT_GA4_IDS",
                "severity": "critical",
                "title": f"Different GA4 property IDs across pages: {sorted(all_ga4_ids)}",
                "detail": (
                    f"Per-page breakdown: {per_page_ga4}. "
                    "Different GA4 properties mean user journeys that cross page boundaries create "
                    "separate sessions in separate properties. Attribution breaks at the handoff."
                ),
                "page": "cross-page",
            })

    return findings


def check_og_image_sameness(all_pages):
    """Same OG image used across most or all pages."""
    findings = []
    images = {}
    for page in all_pages:
        img = page.get("ogTags", {}).get("ogImage") or page.get("meta", {}).get("ogImage")
        if img:
            images[page.get("url", "?")] = img

    if len(images) < 3:
        return findings

    unique_images = set(images.values())
    if len(unique_images) == 1:
        findings.append({
            "id": "SAME_OG_IMAGE_ALL_PAGES",
            "severity": "moderate",
            "title": f"Same OG image used across all {len(images)} pages",
            "detail": "Multiple shared links will show identical previews, reducing click-through.",
            "page": "cross-page",
        })
    else:
        # Check if a single default image dominates (>= 75% of pages)
        from collections import Counter
        counts = Counter(images.values())
        most_common_img, most_common_count = counts.most_common(1)[0]
        ratio = most_common_count / len(images)
        if ratio >= 0.75 and most_common_count >= 3:
            findings.append({
                "id": "SAME_OG_IMAGE_MOST_PAGES",
                "severity": "moderate",
                "title": f"Same default OG image on {most_common_count} of {len(images)} pages",
                "detail": (
                    f"Image: {most_common_img[:100]}. "
                    f"Most pages share the same generic social preview image. "
                    f"Page-specific images improve click-through on social shares."
                ),
                "page": "cross-page",
            })

    return findings


# --- Helpers ---

def _get_root_domain(hostname):
    """Extract registrable domain from hostname. Handles common ccTLDs."""
    parts = hostname.split('.')
    if len(parts) <= 2:
        return hostname
    if len(parts[-2]) <= 3 and parts[-2] in ('co', 'com', 'org', 'net', 'ac', 'gov'):
        return '.'.join(parts[-3:])
    return '.'.join(parts[-2:])


def _same_root_domain(url1, url2):
    """Check if two URLs share the same registrable domain."""
    try:
        from urllib.parse import urlparse
        h1 = urlparse(url1).hostname or ""
        h2 = urlparse(url2).hostname or ""
        return _get_root_domain(h1) == _get_root_domain(h2)
    except Exception:
        return False


# --- Script deferral detection ---

def check_deferred_scripts(page, all_pages):
    """Detect script deferral systems (WP Rocket, Partytown, etc.) that may hide tracking."""
    findings = []
    deferral = page.get("scriptDeferral", {})

    if not deferral.get("detected"):
        return findings

    system = deferral.get("system", "unknown")
    deferred_count = deferral.get("deferredScriptCount", 0)

    # Check if tracking globals are absent despite tracking IDs found in HTML
    gtm_obj = page.get("gtmObject", [])
    gtag_exists = page.get("gtagExists", False)
    ti = page.get("tagInstallations", {})
    has_runtime_tracking = bool(gtm_obj) or gtag_exists
    has_html_tracking = bool(ti.get("gtmIds")) or bool(ti.get("ga4Ids"))

    # Also check preconnect hints as corroborating evidence
    preconnect_hints = page.get("preconnectTrackingHints", [])

    if not has_runtime_tracking and (has_html_tracking or preconnect_hints):
        findings.append({
            "id": "DEFERRED_SCRIPTS_HIDING_TRACKING",
            "severity": "critical",
            "title": f"Script deferral ({system}) hiding tracking from runtime checks",
            "detail": (
                f"Detected {system} with {deferred_count} deferred scripts. "
                f"Tracking IDs found in HTML (GTM: {ti.get('gtmIds', [])}, GA4: {ti.get('ga4Ids', [])})"
                + (f", preconnect hints for: {preconnect_hints[:3]}" if preconnect_hints else "")
                + ", but runtime globals (google_tag_manager, gtag) are absent. "
                "Scripts are deferred until user interaction (mousemove, click, scroll). "
                "IMPORTANT: Simulate interaction before concluding tracking is missing: "
                "document.dispatchEvent(new MouseEvent('mousemove', {bubbles: true})), "
                "then wait 5 seconds and re-run the eval."
            ),
            "page": page.get("url", "unknown"),
        })
    elif deferred_count > 0:
        findings.append({
            "id": "SCRIPT_DEFERRAL_DETECTED",
            "severity": "info",
            "title": f"Script deferral system detected: {system} ({deferred_count} deferred scripts)",
            "detail": (
                f"{system} delays JavaScript execution until user interaction. "
                "Tracking globals loaded successfully (audit ran post-interaction). "
                "Note: users who view the page without interacting (reading on mobile, "
                "keyboard navigation) are invisible until they move the mouse or scroll. "
                "Consider excluding GTM and consent scripts from deferral."
            ),
            "page": page.get("url", "unknown"),
        })

    return findings


# --- Cross-domain same-root detection ---

def check_cross_domain_same_root(page, all_pages):
    """Cross-domain links to subdomains of the same root domain share cookies automatically."""
    findings = []
    links = page.get("crossDomainLinks", [])
    if not links:
        return findings

    page_url = page.get("url", "")
    try:
        from urllib.parse import urlparse
        page_host = urlparse(page_url).hostname or ""
    except Exception:
        return findings

    page_root = _get_root_domain(page_host)

    same_root_links = []
    for link in links:
        try:
            from urllib.parse import urlparse
            link_host = urlparse(link.get("href", "")).hostname or ""
            if _get_root_domain(link_host) == page_root and link_host != page_host:
                same_root_links.append(link)
        except Exception:
            continue

    if same_root_links:
        link_hrefs = [l.get("href", "?")[:80] for l in same_root_links[:3]]
        findings.append({
            "id": "CROSS_DOMAIN_SAME_ROOT",
            "severity": "info",
            "title": f"Cross-domain links to same root domain (.{page_root}) — cookies shared automatically",
            "detail": (
                f"Links to: {link_hrefs}. "
                f"These subdomains share the .{page_root} cookie domain, so GA4 cookies "
                "(_ga, _ga_XXXXXXX) are accessible on both sides without _gl linker parameters. "
                "Cross-domain tracking configuration is NOT needed. "
                "Verify by checking that the GA4 Client ID matches on both domains."
            ),
            "page": page.get("url", "unknown"),
        })

    return findings


# --- Registry of all checks ---

PER_PAGE_CHECKS = [
    check_deferred_scripts,
    check_double_tagging,
    check_pii_in_datalayer,
    check_ecommerce_fields,
    check_datalayer_quality,
    check_consent,
    check_schema_markup,
    check_canonical,
    check_og_tags,
    check_cross_domain_links,
    check_cross_domain_same_root,
    check_form_hidden_fields,
    check_tag_sprawl,
    check_ghost_preconnects,
    check_abm_integration,
    check_video_embeds,
    check_chatbot_engagement_inflation,
    check_pixels_no_conversion_events,
    check_linkedin_no_conversions,
    check_pardot_third_party,
    check_enhanced_conversions_missing,
    check_thank_you_indexable,
    check_hidden_fields_empty,
    check_utm_survival,
    check_cta_tracking,
    check_consent_mode_defaults,
    check_rogue_scripts_outside_gtm,
    check_iframe_cookie_leak,
    check_datalayer_race_condition,
    check_booking_iframe_tracking,
    check_adobe_stack,
]

CROSS_PAGE_CHECKS = [
    check_consistency,
    check_og_image_sameness,
    check_crm_cookies,
    check_no_cmp_with_tracking,
]


def run_checks(pages_data):
    """Run all checks and return structured findings."""
    all_findings = []

    # Per-page checks
    for page in pages_data:
        for check_fn in PER_PAGE_CHECKS:
            try:
                results = check_fn(page, pages_data)
                all_findings.extend(results)
            except Exception as e:
                all_findings.append({
                    "id": "CHECK_ERROR",
                    "severity": "info",
                    "title": f"Check '{check_fn.__name__}' failed: {e}",
                    "detail": str(e),
                    "page": page.get("url", "unknown"),
                })

    # Cross-page checks
    for check_fn in CROSS_PAGE_CHECKS:
        try:
            results = check_fn(pages_data)
            all_findings.extend(results)
        except Exception as e:
            all_findings.append({
                "id": "CHECK_ERROR",
                "severity": "info",
                "title": f"Cross-page check '{check_fn.__name__}' failed: {e}",
                "detail": str(e),
                "page": "cross-page",
            })

    # Deduplicate findings with same id + page
    seen = set()
    deduped = []
    for f in all_findings:
        key = (f["id"], f["page"])
        if key not in seen:
            seen.add(key)
            deduped.append(f)

    # Summary
    critical = [f for f in deduped if f["severity"] == "critical"]
    moderate = [f for f in deduped if f["severity"] == "moderate"]
    info = [f for f in deduped if f["severity"] == "info"]

    return {
        "findings": deduped,
        "summary": {
            "total_findings": len(deduped),
            "critical": len(critical),
            "moderate": len(moderate),
            "info": len(info),
            "pages_checked": len(pages_data),
            "checks_run": len(PER_PAGE_CHECKS) + len(CROSS_PAGE_CHECKS),
        },
    }


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Deterministic martech audit checker")
    parser.add_argument("files", nargs="*", help="JSON files with page eval data")
    parser.add_argument("--dir", help="Directory containing JSON eval files")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print output")
    args = parser.parse_args()

    # Collect input files
    json_files = []
    if args.dir:
        json_files.extend(sorted(Path(args.dir).glob("*.json")))
    if args.files:
        json_files.extend(Path(f) for f in args.files)

    if not json_files:
        print("Error: No input files. Provide JSON files or --dir.", file=sys.stderr)
        sys.exit(1)

    # Load page data
    pages = []
    for f in json_files:
        try:
            data = json.loads(f.read_text())
            if not isinstance(data, dict):
                print(f"Warning: {f} is not a JSON object, skipping.", file=sys.stderr)
                continue
            if "url" not in data:
                data["url"] = f.stem  # Use filename as fallback
            pages.append(data)
        except Exception as e:
            print(f"Warning: Could not load {f}: {e}", file=sys.stderr)

    if not pages:
        print("Error: No valid page data loaded.", file=sys.stderr)
        sys.exit(1)

    # Run checks
    results = run_checks(pages)

    # Output
    indent = 2 if args.pretty else None
    print(json.dumps(results, indent=indent))


if __name__ == "__main__":
    main()
