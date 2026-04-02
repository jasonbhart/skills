#!/usr/bin/env python3
"""
Deterministic SEO audit checker.

Takes the raw JSON output from the browser eval script (one per page)
and produces structured pass/fail findings. Run this AFTER collecting
data from all pages to get consistent, repeatable results.

Usage:
    python check_seo.py page1.json page2.json ...
    python check_seo.py --dir /path/to/eval-outputs/

Input: JSON files, each containing the output of the evaluate_script call
       for one page. Each file should also include a "url" field.

Output: JSON to stdout with findings array + summary scores.
"""

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_homepage(url):
    """Detect homepage URLs including regional patterns like /us-en/home.html."""
    try:
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")
        # Exact root
        if path in ("", "/", "/index.html", "/index.htm"):
            return True
        # Regional homepage: /xx-xx/, /xx-xx/home.html, /xx/, /en/, etc.
        if re.match(r'^/[a-z]{2}(-[a-z]{2})?(/home(\.html?)?)?$', path, re.IGNORECASE):
            return True
        return False
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Per-page checks
# ---------------------------------------------------------------------------

def check_http_status(page, all_pages):
    """Non-200 HTTP status code."""
    findings = []
    status = page.get("httpStatus")
    if status is not None and status != 200:
        findings.append({
            "id": "NON_200_STATUS",
            "severity": "critical",
            "title": f"Page returned HTTP {status}",
            "detail": (
                f"Expected HTTP 200 but received {status}. "
                "This may indicate a soft 404, redirect landing on the wrong page, "
                "or a server error. Search engines may not index this content."
            ),
            "page": page.get("url", "unknown"),
        })
    return findings


def check_title(page, all_pages):
    """Missing, too short, or too long title tag."""
    findings = []
    title = page.get("title")
    length = page.get("titleLength", 0)
    url = page.get("url", "unknown")

    if not title or not title.strip():
        findings.append({
            "id": "MISSING_TITLE",
            "severity": "critical",
            "title": "Page has no title tag",
            "detail": (
                "The <title> element is empty or missing. This is the single most "
                "important on-page SEO element — it appears in search results and "
                "browser tabs. Every indexable page must have a unique, descriptive title."
            ),
            "page": url,
        })
    else:
        if length > 60:
            findings.append({
                "id": "TITLE_TOO_LONG",
                "severity": "moderate",
                "title": f"Title tag is {length} characters (recommended: ≤60)",
                "detail": (
                    f"Title: \"{title[:80]}{'...' if len(title) > 80 else ''}\". "
                    "Google typically displays 50-60 characters in search results. "
                    "Longer titles get truncated, which can cut off important keywords or "
                    "make the listing look incomplete. Note: Google sometimes rewrites "
                    "titles regardless of length."
                ),
                "page": url,
            })
        if length < 30 and length > 0:
            findings.append({
                "id": "TITLE_TOO_SHORT",
                "severity": "moderate",
                "title": f"Title tag is only {length} characters",
                "detail": (
                    f"Title: \"{title}\". Short titles miss the opportunity to include "
                    "descriptive keywords and compelling copy. Aim for 30-60 characters "
                    "that include the primary keyword and a value proposition. "
                    "Note: homepage titles with just a brand name can be acceptable if "
                    "the brand is a household name — most sites should append a "
                    "descriptor (e.g., 'Brand | What You Do')."
                ),
                "page": url,
            })
    return findings


def check_description(page, all_pages):
    """Missing or overly long meta description."""
    findings = []
    desc = page.get("description")
    length = page.get("descriptionLength", 0)
    url = page.get("url", "unknown")

    if not desc or not desc.strip():
        findings.append({
            "id": "MISSING_DESCRIPTION",
            "severity": "moderate",
            "title": "No meta description",
            "detail": (
                "The meta description is missing. While Google may auto-generate a snippet "
                "from page content, a well-crafted meta description improves click-through "
                "rates from search results. Include a compelling summary with the target "
                "keyword in 120-160 characters."
            ),
            "page": url,
        })
    elif length > 160:
        findings.append({
            "id": "DESCRIPTION_TOO_LONG",
            "severity": "info",
            "title": f"Meta description is {length} characters (recommended: ≤160)",
            "detail": (
                f"Description starts with: \"{desc[:100]}...\". "
                "Google typically truncates descriptions over 155-160 characters on desktop "
                "(120 on mobile). The excess text won't be shown but isn't harmful — this is "
                "a minor optimization."
            ),
            "page": url,
        })
    return findings


def check_canonical(page, all_pages):
    """Missing or mismatched canonical URL.
    Plan deviation: split CANONICAL_MISMATCH into CANONICAL_CROSS_DOMAIN (critical)
    and CANONICAL_MISMATCH (moderate). A same-domain mismatch (trailing slash, param
    normalization) is far less severe than a cross-domain canonical that effectively
    deindexes the page."""
    findings = []
    canonical = page.get("canonical", {})
    url = page.get("url", "unknown")

    if not canonical.get("url"):
        findings.append({
            "id": "MISSING_CANONICAL",
            "severity": "moderate",
            "title": "No canonical URL declared",
            "detail": (
                "The page has no <link rel=\"canonical\"> tag. Canonical tags tell search "
                "engines which version of a page is the primary one, preventing duplicate "
                "content issues from URL parameters, trailing slashes, or protocol "
                "variations (http vs https). Every indexable page should have a self-"
                "referencing canonical."
            ),
            "page": url,
        })
    elif canonical.get("mismatch"):
        # Check if it's a plausible intentional redirect (pagination, etc.)
        canon_url = canonical.get("url", "")
        # Don't flag if canonical points to same domain (likely intentional)
        try:
            canon_host = urlparse(canon_url).hostname or ""
            page_host = urlparse(url).hostname or ""
            # Compare root domains: strip "www." to avoid flagging
            # www.example.com vs example.com as cross-domain (it's routine)
            canon_root = canon_host.removeprefix("www.")
            page_root = page_host.removeprefix("www.")
            if canon_root and page_root and canon_root != page_root:
                findings.append({
                    "id": "CANONICAL_CROSS_DOMAIN",
                    "severity": "critical",
                    "title": "Canonical points to a different domain",
                    "detail": (
                        f"Page URL: {url}\n"
                        f"Canonical: {canon_url}\n"
                        "A cross-domain canonical tells search engines this page is a "
                        "duplicate of content on another domain. If unintentional, this "
                        "effectively deindexes the page."
                    ),
                    "page": url,
                })
            elif canonical.get("mismatch"):
                findings.append({
                    "id": "CANONICAL_MISMATCH",
                    "severity": "moderate",
                    "title": "Canonical URL differs from page URL",
                    "detail": (
                        f"Page URL: {url}\n"
                        f"Canonical: {canon_url}\n"
                        "The canonical tag points to a different URL on the same domain. "
                        "This may be intentional (e.g., consolidating parameter variations) "
                        "or a misconfiguration. Verify this is the desired behavior — an "
                        "incorrect canonical can suppress indexing of this page."
                    ),
                    "page": url,
                })
        except Exception:
            # Malformed canonical URL — report rather than silently skip
            findings.append({
                "id": "CANONICAL_MISMATCH",
                "severity": "moderate",
                "title": "Canonical URL could not be parsed",
                "detail": (
                    f"Canonical URL \"{canonical.get('url', '')}\" could not be parsed. "
                    "This may indicate a malformed canonical tag. Verify the canonical "
                    "URL is a valid, absolute URL."
                ),
                "page": url,
            })
    return findings


def check_h1(page, all_pages):
    """Missing or multiple H1 tags."""
    findings = []
    headings = page.get("headings", {})
    h1_count = headings.get("h1Count", 0)
    url = page.get("url", "unknown")

    if h1_count == 0:
        findings.append({
            "id": "MISSING_H1",
            "severity": "critical",
            "title": "Page has no H1 heading",
            "detail": (
                "No <h1> tag found. The H1 is the primary heading of the page and "
                "signals the main topic to search engines. Every page should have "
                "exactly one H1 that includes or closely relates to the target keyword."
            ),
            "page": url,
        })
    elif h1_count > 1:
        h1_texts = headings.get("h1Texts", [])
        unique_texts = set(t.strip().lower() for t in h1_texts if t.strip())

        # 2 H1s with identical text = responsive duplicate (very common pattern)
        if h1_count == 2 and len(unique_texts) <= 1:
            findings.append({
                "id": "MULTIPLE_H1",
                "severity": "info",
                "title": f"Page has 2 identical H1 tags (likely responsive variant)",
                "detail": (
                    f"H1 text: \"{h1_texts[0][:120] if h1_texts else '(empty)'}\" "
                    "appears twice. This is a common responsive design pattern where "
                    "one H1 is shown on desktop and another on mobile via CSS. Search "
                    "engines typically handle this correctly."
                ),
                "page": url,
            })
        # 5+ H1s = clearly broken template/framework
        elif h1_count >= 5:
            shown = h1_texts[:5]
            omitted = h1_count - len(shown)
            suffix = f" ... and {omitted} more" if omitted > 0 else ""
            findings.append({
                "id": "MULTIPLE_H1",
                "severity": "critical",
                "title": f"Page has {h1_count} H1 tags — heading structure is broken",
                "detail": (
                    f"H1 tags found ({h1_count} total): {shown}{suffix}. "
                    f"Having {h1_count} H1 tags indicates a template or CSS framework "
                    "is misusing H1 for styling rather than semantics. This severely "
                    "dilutes the primary topic signal. The H1 should be reserved for "
                    "the single main heading of the page."
                ),
                "page": url,
            })
        else:
            findings.append({
                "id": "MULTIPLE_H1",
                "severity": "moderate",
                "title": f"Page has {h1_count} H1 tags",
                "detail": (
                    f"H1 tags found: {h1_texts[:5]}. "
                    "While HTML5 technically allows multiple H1s in sectioning elements, "
                    "best practice for SEO is one H1 per page. Multiple H1s dilute the "
                    "primary topic signal. Note: some CSS frameworks use H1 for visual "
                    "sizing — verify these are actual content headings."
                ),
                "page": url,
            })
    return findings


def check_heading_hierarchy(page, all_pages):
    """Broken heading hierarchy (e.g., H1 -> H3 skipping H2)."""
    findings = []
    headings = page.get("headings", {})
    url = page.get("url", "unknown")

    if not headings.get("headingHierarchyValid", True) and headings.get("totalHeadings", 0) > 2:
        outline = headings.get("outline", [])
        # Find the first skip
        skip_desc = ""
        prev_level = 0
        for h in outline:
            level = h.get("level", 0)
            if prev_level > 0 and level > prev_level + 1:
                skip_desc = f"H{prev_level} → H{level} (skipped H{prev_level + 1})"
                break
            prev_level = level

        findings.append({
            "id": "HEADING_HIERARCHY_BROKEN",
            "severity": "moderate",
            "title": f"Heading hierarchy skips a level{': ' + skip_desc if skip_desc else ''}",
            "detail": (
                "The heading structure jumps from one level to a non-sequential level "
                f"(e.g., {skip_desc or 'H2 → H4'}). A proper heading hierarchy (H1 → H2 → H3) "
                "helps search engines understand the content structure and improves "
                "accessibility for screen readers."
            ),
            "page": url,
        })
    return findings


def check_images_alt(page, all_pages):
    """Images missing alt text."""
    findings = []
    images = page.get("images", {})
    without_alt = images.get("imagesWithoutAlt", 0)
    total = images.get("totalImages", 0)
    url = page.get("url", "unknown")

    if without_alt > 0 and total > 0:
        pct = round(without_alt / total * 100)
        findings.append({
            "id": "IMAGES_MISSING_ALT",
            "severity": "moderate",
            "title": f"{without_alt} of {total} images missing alt text ({pct}%)",
            "detail": (
                "Images without alt attributes are invisible to search engines and "
                "screen readers. Alt text should describe the image content — not be "
                "keyword-stuffed. Decorative images should use alt=\"\" (empty alt), "
                "not omit the attribute entirely."
            ),
            "page": url,
        })
    return findings


def check_images_responsive(page, all_pages):
    """Large images without srcset / responsive handling."""
    findings = []
    images = page.get("images", {})
    large = images.get("largeImages", [])
    url = page.get("url", "unknown")

    if len(large) > 0:
        examples = [f"{img.get('src', '?')}" for img in large[:3]]
        findings.append({
            "id": "IMAGES_NO_RESPONSIVE",
            "severity": "moderate",
            "title": f"{len(large)} large image(s) without responsive srcset",
            "detail": (
                f"Large images detected without srcset or <picture> element: "
                f"{', '.join(examples)}. "
                "Without responsive images, mobile users download unnecessarily large "
                "files, hurting Core Web Vitals (LCP) and page speed scores."
            ),
            "page": url,
        })
    return findings


def check_images_dimensions(page, all_pages):
    """Images without explicit width/height (CLS risk)."""
    findings = []
    images = page.get("images", {})
    # Use the images section or cwvIndicators
    no_dims = images.get("imagesWithoutDimensions", 0)
    total = images.get("totalImages", 0)
    url = page.get("url", "unknown")

    # Threshold >2: a couple of unsized icons/decorative images are common;
    # flag when 3+ images lack dimensions (meaningful CLS risk).
    if no_dims > 2 and total > 0:
        pct = round(no_dims / total * 100)
        findings.append({
            "id": "CLS_RISK_IMAGES",
            "severity": "moderate",
            "title": f"{no_dims} images missing width/height attributes (CLS risk)",
            "detail": (
                f"{no_dims} of {total} images ({pct}%) lack explicit width and height "
                "attributes. When images load without reserved space, the page layout "
                "shifts — this is the #1 cause of Cumulative Layout Shift (CLS), a "
                "Core Web Vital that affects search rankings. Add width and height "
                "attributes to <img> tags, or use CSS aspect-ratio."
            ),
            "page": url,
        })
    return findings


def check_lazy_loading(page, all_pages):
    """No lazy loading on image-heavy pages."""
    findings = []
    images = page.get("images", {})
    lazy_count = images.get("lazyLoadedCount", 0)
    total = images.get("totalImages", 0)
    url = page.get("url", "unknown")

    if total > 5 and lazy_count == 0:
        findings.append({
            "id": "NO_LAZY_LOADING",
            "severity": "info",
            "title": f"Page has {total} images but none use lazy loading",
            "detail": (
                "No images have loading=\"lazy\" or equivalent lazy-loading attributes. "
                "Lazy loading defers off-screen images until the user scrolls near them, "
                "reducing initial page weight and improving LCP. Note: above-the-fold "
                "images should NOT be lazy-loaded — only below-the-fold content benefits."
            ),
            "page": url,
        })
    return findings


def check_schema_markup(page, all_pages):
    """No structured data (JSON-LD or Microdata)."""
    findings = []
    schema = page.get("schema", {})
    url = page.get("url", "unknown")

    json_ld_types = schema.get("jsonLdTypes", [])
    microdata_types = schema.get("microdataTypes", [])

    # Filter out boilerplate Microdata (WebPage/WebSite on <html> tag) that
    # Hugo themes add by default — these don't represent real schema implementation
    meaningful_microdata = [t for t in microdata_types if t not in ("WebPage", "WebSite")]

    if not json_ld_types and not meaningful_microdata:
        findings.append({
            "id": "NO_SCHEMA_MARKUP",
            "severity": "moderate",
            "title": "No structured data (JSON-LD or Microdata) found",
            "detail": (
                "The page has no JSON-LD schema markup or Microdata. Structured data "
                "helps search engines understand the page content and can enable rich "
                "results (star ratings, FAQ dropdowns, breadcrumbs, etc.). "
                "At minimum, add Organization schema on the homepage and BreadcrumbList "
                "on interior pages. Note: some CMS plugins inject JSON-LD via JavaScript "
                "at runtime — if a CMS is in use, verify with Google's Rich Results Test."
            ),
            "page": url,
        })
    return findings


def check_org_schema(page, all_pages):
    """Homepage missing Organization schema."""
    findings = []
    schema = page.get("schema", {})
    url = page.get("url", "unknown")

    is_homepage = _is_homepage(url)

    # Only flag if the site already has some JSON-LD (suggesting partial schema
    # implementation). If no JSON-LD exists at all, NO_SCHEMA_MARKUP covers it.
    # This matches the gating pattern in check_breadcrumb_schema.
    has_any_json_ld = bool(schema.get("jsonLdTypes"))
    if is_homepage and not schema.get("hasOrganization") and has_any_json_ld:
        findings.append({
            "id": "NO_ORG_SCHEMA",
            "severity": "moderate",
            "title": "Homepage missing Organization schema",
            "detail": (
                "The homepage has JSON-LD schema but no Organization (or LocalBusiness) "
                "type. Adding Organization JSON-LD with name, url, logo, and contactPoint "
                "helps Google build a Knowledge Panel and correctly attribute the site "
                "to the business entity."
            ),
            "page": url,
        })
    return findings


def check_breadcrumb_schema(page, all_pages):
    """Non-homepage pages missing BreadcrumbList schema."""
    findings = []
    schema = page.get("schema", {})
    url = page.get("url", "unknown")

    is_homepage = _is_homepage(url)

    # Only flag if the page has real JSON-LD schema (not just minimal Microdata
    # like itemtype="WebPage" on the html tag, which Hugo themes add by default
    # and doesn't represent actionable schema implementation)
    has_json_ld = bool(schema.get("jsonLdTypes"))

    if not is_homepage and not schema.get("hasBreadcrumb") and has_json_ld:
        findings.append({
            "id": "NO_BREADCRUMB_SCHEMA",
            "severity": "info",
            "title": "Page has schema markup but no BreadcrumbList",
            "detail": (
                "This page has structured data but no BreadcrumbList schema. Breadcrumb "
                "schema enables breadcrumb-style navigation in search results, improving "
                "CTR and helping users understand the site hierarchy."
            ),
            "page": url,
        })
    return findings


def check_schema_validation(page, all_pages):
    """JSON-LD schema with missing required fields."""
    findings = []
    validation = page.get("schemaValidation", {})
    issues = validation.get("issues", [])
    url = page.get("url", "unknown")

    if issues:
        issue_strs = [f"  - {i['type']}: {i['message']}" for i in issues[:5]]
        findings.append({
            "id": "SCHEMA_VALIDATION_ERRORS",
            "severity": "moderate",
            "title": f"Structured data has {len(issues)} validation issue(s)",
            "detail": (
                "JSON-LD schema markup is present but has missing or incomplete fields:\n"
                + "\n".join(issue_strs)
                + "\n\nIncomplete schema may not trigger rich results. Use Google's "
                "Rich Results Test to verify which fields are required vs recommended."
            ),
            "page": url,
        })
    return findings


def check_og_tags(page, all_pages):
    """Missing Open Graph tags."""
    findings = []
    og = page.get("og", {})
    url = page.get("url", "unknown")

    if not og.get("title") and not og.get("image"):
        # Check if any OG tags exist at all
        has_any_og = any(og.get(k) for k in ["description", "url", "type", "siteName"])
        tag_label = "Missing critical OG tags" if has_any_og else "No Open Graph tags found"
        findings.append({
            "id": "MISSING_OG_TAGS",
            "severity": "moderate",
            "title": tag_label,
            "detail": (
                "The page is missing og:title and og:image — the two most important "
                "Open Graph tags. Without them, social media previews (Facebook, "
                "LinkedIn, Slack, Discord) are auto-generated and often unattractive."
                + (f" Note: other OG tags are present (og:description, og:url, etc.) "
                   "but without og:title and og:image, the preview will still be poor."
                   if has_any_og else "")
            ),
            "page": url,
        })
    elif not og.get("image"):
        findings.append({
            "id": "MISSING_OG_IMAGE",
            "severity": "moderate",
            "title": "Open Graph image (og:image) missing",
            "detail": (
                "The page has og:title but no og:image. Social shares without an "
                "image get dramatically less engagement. Add a relevant, high-quality "
                "image (1200x630px recommended for most platforms)."
            ),
            "page": url,
        })
    elif not og.get("title"):
        findings.append({
            "id": "MISSING_OG_TITLE",
            "severity": "moderate",
            "title": "Open Graph title (og:title) missing",
            "detail": (
                "The page has og:image but no og:title. Without a title, social "
                "previews may show the raw URL or auto-generate a poor title from "
                "page content. Add og:title matching or closely related to the "
                "page's <title> tag."
            ),
            "page": url,
        })
    return findings


def check_twitter_card(page, all_pages):
    """Missing Twitter Card tags."""
    findings = []
    twitter = page.get("twitter", {})
    url = page.get("url", "unknown")

    if not twitter.get("card"):
        findings.append({
            "id": "MISSING_TWITTER_CARD",
            "severity": "info",
            "title": "No Twitter Card meta tags",
            "detail": (
                "The page has no twitter:card meta tag. Twitter/X will fall back to "
                "Open Graph tags if available, so this is low priority if OG tags are "
                "set. Add twitter:card=\"summary_large_image\" for optimal display."
            ),
            "page": url,
        })
    return findings


def check_noindex(page, all_pages):
    """Unexpected noindex on important pages."""
    findings = []
    robots = page.get("robots", {})
    url = page.get("url", "unknown")

    if robots.get("hasNoindex"):
        # Check if this is a page that SHOULD be noindexed
        url_lower = url.lower()
        expected_noindex = any(kw in url_lower for kw in [
            "thank-you", "thankyou", "confirmation", "success",
            "staging", "preview", "draft", "admin", "login",
            "/search", "tag/", "tags/",
            "/author/", "/authors/", "/feed", "/rss",
            "/cart", "/checkout", "/account", "/unsubscribe",
        ])
        if not expected_noindex:
            findings.append({
                "id": "UNEXPECTED_NOINDEX",
                "severity": "critical",
                "title": "Page has noindex directive",
                "detail": (
                    f"The robots meta tag contains 'noindex': \"{robots.get('meta', '')}\". "
                    "This prevents search engines from indexing this page. If this is "
                    "intentional (staging, private content), this finding can be ignored. "
                    "If not, this is a critical issue — the page will not appear in "
                    "search results."
                ),
                "page": url,
            })
    return findings


def check_viewport(page, all_pages):
    """Missing or misconfigured viewport meta tag."""
    findings = []
    cwv = page.get("cwvIndicators", {})
    url = page.get("url", "unknown")

    if not cwv.get("viewportMeta"):
        findings.append({
            "id": "MISSING_VIEWPORT",
            "severity": "critical",
            "title": "No viewport meta tag",
            "detail": (
                "The page is missing <meta name=\"viewport\" content=\"width=device-width, "
                "initial-scale=1\">. Without this, mobile browsers render the page at "
                "desktop width and scale down, making it unusable on mobile. Google uses "
                "mobile-first indexing — a missing viewport is a critical mobile usability "
                "failure."
            ),
            "page": url,
        })
    elif not cwv.get("hasViewportWidth"):
        findings.append({
            "id": "VIEWPORT_NO_WIDTH",
            "severity": "moderate",
            "title": "Viewport meta tag missing width=device-width",
            "detail": (
                f"Viewport content: \"{cwv.get('viewportMeta', '')}\". "
                "The viewport meta tag exists but does not include width=device-width. "
                "Without this directive, mobile browsers may not scale the page correctly. "
                "Use: <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">."
            ),
            "page": url,
        })
    return findings


def check_mixed_content(page, all_pages):
    """HTTPS page loading HTTP resources."""
    findings = []
    security = page.get("security", {})
    url = page.get("url", "unknown")

    if security.get("hasMixedContent"):
        count = security.get("mixedContentCount", 0)
        findings.append({
            "id": "MIXED_CONTENT",
            "severity": "critical",
            "title": f"Mixed content: {count} HTTP resource(s) on HTTPS page",
            "detail": (
                "This HTTPS page loads resources over plain HTTP. Browsers may block "
                "these resources (showing broken images or scripts) and display security "
                "warnings. Google considers HTTPS a ranking signal — mixed content "
                "undermines this. Update all resource URLs to use HTTPS."
            ),
            "page": url,
        })
    return findings


def check_thin_content(page, all_pages):
    """Pages with very little text content."""
    findings = []
    content = page.get("content", {})
    word_count = content.get("wordCount", 0)
    url = page.get("url", "unknown")

    # Don't flag homepages or obvious landing/listing pages
    url_lower = url.lower()
    is_landing = any(kw in url_lower for kw in [
        "/contact", "/pricing", "/demo", "/signup", "/login",
        "/thank-you", "/404", "/search", "/about",
        "/services/", "/service/", "/solutions/", "/solution/",
        "/features/", "/feature/", "/capabilities",
        "/get-started", "/partners", "/integrations",
        "/case-studies", "/case-study/", "/portfolio",
        "/product/", "/products/", "/careers", "/jobs",
        "/events", "/webinar",
        # Ecommerce category/listing pages — intentionally product-focused
        "/shop/", "/shop", "/store/", "/store",
        "/cat/", "/category/", "/categories/",
        "/collection/", "/collections/",
        "/catalog/", "/browse/",
    ])
    is_homepage = _is_homepage(url)

    if word_count < 300 and not is_homepage and not is_landing:
        findings.append({
            "id": "THIN_CONTENT",
            "severity": "moderate",
            "title": f"Thin content: only {word_count} words",
            "detail": (
                f"The page has approximately {word_count} words of visible text. "
                "While there's no magic word count, pages with very little content "
                "struggle to rank for competitive queries. If this is a content page "
                "(blog, service, product), consider expanding it with more substantive "
                "information. Note: some page types (landing pages, tool pages, "
                "galleries) are intentionally thin — this may not apply."
            ),
            "page": url,
        })
    return findings


def check_html_lang(page, all_pages):
    """Missing lang attribute on <html>."""
    findings = []
    a11y = page.get("accessibility", {})
    url = page.get("url", "unknown")

    if not a11y.get("htmlLang"):
        findings.append({
            "id": "MISSING_HTML_LANG",
            "severity": "moderate",
            "title": "No lang attribute on <html> element",
            "detail": (
                "The <html> tag has no lang attribute (e.g., <html lang=\"en\">). "
                "This attribute helps search engines understand the page language for "
                "serving the right audience, and is required for accessibility (screen "
                "readers use it to select the correct pronunciation)."
            ),
            "page": url,
        })
    return findings


def check_render_blocking(page, all_pages):
    """Excessive render-blocking resources."""
    findings = []
    resources = page.get("resources", {})
    blocking_count = resources.get("renderBlockingScriptCount", 0)
    blocking_css = resources.get("blockingCSSCount", 0)
    url = page.get("url", "unknown")

    # Only count render-blocking SCRIPTS (not stylesheets).
    # All normal stylesheets are technically render-blocking unless they have a
    # specific media query — flagging them would fire on every site and isn't
    # actionable without critical-CSS extraction (an advanced optimization).
    if blocking_count > 3:
        scripts = resources.get("renderBlockingScripts", [])
        findings.append({
            "id": "RENDER_BLOCKING",
            "severity": "moderate",
            "title": f"{blocking_count} render-blocking scripts in <head>",
            "detail": (
                "Scripts in <head> without async or defer block rendering, delaying "
                "First Contentful Paint (FCP) and Largest Contentful Paint (LCP). "
                + (f"Scripts: {scripts[:3]}. " if scripts else "")
                + "Add async or defer attributes to non-critical scripts, or move them "
                "to the end of <body>."
            ),
            "page": url,
        })
    return findings


def check_broken_anchors(page, all_pages):
    """Links with href='#' or empty href."""
    findings = []
    links = page.get("links", {})
    broken = links.get("brokenAnchors", [])
    url = page.get("url", "unknown")

    # Threshold >3: mobile nav toggles, accordions, and tab UIs commonly use
    # href="#" for toggle triggers. 1-3 is likely UI scaffolding. Flag at 4+.
    if len(broken) > 3:
        examples = [f"\"{b.get('text', '?')}\" (href={b.get('href', '?')})" for b in broken[:5]]
        findings.append({
            "id": "BROKEN_ANCHOR_LINKS",
            "severity": "moderate",
            "title": f"{len(broken)} links with empty or placeholder hrefs",
            "detail": (
                f"Found {len(broken)} links with href=\"#\", empty href, or "
                "javascript:void(0). These are not crawlable by search engines and "
                "provide no SEO value. Examples: " + "; ".join(examples) + ". "
                "Replace with real URLs or use <button> elements for interactive "
                "elements that don't navigate."
            ),
            "page": url,
        })
    return findings


# ---------------------------------------------------------------------------
# Cross-page checks
# ---------------------------------------------------------------------------

def check_duplicate_titles(all_pages):
    """Multiple pages sharing the exact same title."""
    findings = []
    title_map = {}
    for page in all_pages:
        title = (page.get("title") or "").strip()
        if title:
            title_map.setdefault(title, []).append(page.get("url", "unknown"))

    for title, urls in title_map.items():
        if len(urls) > 1:
            findings.append({
                "id": "DUPLICATE_TITLES",
                "severity": "critical",
                "title": f"Duplicate title across {len(urls)} pages",
                "detail": (
                    f"Title: \"{title[:80]}{'...' if len(title) > 80 else ''}\"\n"
                    f"Pages: {', '.join(urls[:5])}\n"
                    "Duplicate titles make it hard for search engines to determine which "
                    "page should rank for a given query. Each page should have a unique "
                    "title reflecting its specific content."
                ),
                "page": "cross-page",
            })
    return findings


def check_duplicate_descriptions(all_pages):
    """Multiple pages sharing the exact same meta description."""
    findings = []
    desc_map = {}
    for page in all_pages:
        desc = (page.get("description") or "").strip()
        if desc:
            desc_map.setdefault(desc, []).append(page.get("url", "unknown"))

    for desc, urls in desc_map.items():
        if len(urls) > 1:
            findings.append({
                "id": "DUPLICATE_DESCRIPTIONS",
                "severity": "moderate",
                "title": f"Duplicate meta description across {len(urls)} pages",
                "detail": (
                    f"Description: \"{desc[:100]}{'...' if len(desc) > 100 else ''}\"\n"
                    f"Pages: {', '.join(urls[:5])}\n"
                    "Each page should have a unique meta description tailored to its "
                    "content. Duplicate descriptions are a missed CTR opportunity."
                ),
                "page": "cross-page",
            })
    return findings


def check_og_image_sameness(all_pages):
    """75%+ of pages using the exact same OG image."""
    findings = []
    if len(all_pages) < 3:
        return findings

    og_images = {}
    for page in all_pages:
        og = page.get("og", {})
        img = og.get("image")
        if img:
            og_images.setdefault(img, []).append(page.get("url", "unknown"))

    for img, urls in og_images.items():
        if len(urls) >= len(all_pages) * 0.75:
            # Downgrade to info on small sites (< 6 pages) — sharing a default
            # OG image across a brochure site is common and low-impact
            severity = "info" if len(all_pages) < 6 else "moderate"
            findings.append({
                "id": "OG_IMAGE_SAMENESS",
                "severity": severity,
                "title": f"{len(urls)} of {len(all_pages)} pages share the same OG image",
                "detail": (
                    f"Image: {img}\n"
                    "When most pages share a generic OG image, social shares all look "
                    "identical — reducing engagement and making it harder for users to "
                    "distinguish between shared links. Create unique OG images for key "
                    "pages (service pages, blog posts) with the page title or topic."
                ),
                "page": "cross-page",
            })
    return findings


def check_canonical_consistency(all_pages):
    """Canonicals mixing www/non-www or http/https."""
    findings = []
    domains = set()
    schemes = set()

    for page in all_pages:
        canonical = page.get("canonical", {})
        canon_url = canonical.get("url")
        if canon_url:
            try:
                parsed = urlparse(canon_url)
                if parsed.hostname:
                    domains.add(parsed.hostname)
                if parsed.scheme:
                    schemes.add(parsed.scheme)
            except Exception:
                pass

    # Check for www/non-www inconsistency
    www_domains = [d for d in domains if d.startswith("www.")]
    non_www_domains = [d for d in domains if not d.startswith("www.")]
    root_domains = set()
    for d in www_domains:
        root_domains.add(d[4:])  # Strip www.

    if root_domains & set(non_www_domains):
        findings.append({
            "id": "INCONSISTENT_CANONICAL_DOMAIN",
            "severity": "critical",
            "title": "Canonical URLs mix www and non-www domains",
            "detail": (
                f"Canonical domains found: {sorted(domains)}\n"
                "Mixing www and non-www in canonical tags creates a split signal — "
                "search engines may treat them as separate sites, splitting link equity "
                "and causing indexing confusion. Pick one and be consistent."
            ),
            "page": "cross-page",
        })

    if "http" in schemes and "https" in schemes:
        findings.append({
            "id": "INCONSISTENT_CANONICAL_SCHEME",
            "severity": "critical",
            "title": "Canonical URLs mix HTTP and HTTPS",
            "detail": (
                "Some canonical tags use http:// and others use https://. All canonical "
                "URLs should use HTTPS. HTTP canonicals signal to search engines that "
                "the insecure version is preferred."
            ),
            "page": "cross-page",
        })
    return findings


def check_hreflang_reciprocal(all_pages):
    """Hreflang tags without reciprocal links."""
    findings = []
    # Collect all hreflang declarations across pages
    page_hreflangs = {}
    for page in all_pages:
        url = page.get("url", "unknown")
        hreflang = page.get("hreflang", {})
        tags = hreflang.get("tags", [])
        if tags:
            page_hreflangs[url] = {t["href"]: t["lang"] for t in tags}

    # Check reciprocals (only among audited pages)
    audited_urls = {p.get("url", "") for p in all_pages}
    checked_any = False
    for url, langs in page_hreflangs.items():
        for target_href, lang in langs.items():
            target_norm = target_href.rstrip("/")
            # Check if the target is one of our audited pages
            for audited_url in audited_urls:
                if audited_url.rstrip("/") == target_norm:
                    checked_any = True
                    # Target page should point back
                    target_hreflangs = page_hreflangs.get(audited_url, {})
                    url_norm = url.rstrip("/")
                    has_reciprocal = any(
                        h.rstrip("/") == url_norm
                        for h in target_hreflangs.keys()
                    )
                    if not has_reciprocal:
                        findings.append({
                            "id": "HREFLANG_NO_RECIPROCAL",
                            "severity": "moderate",
                            "title": f"Hreflang tag missing reciprocal link",
                            "detail": (
                                f"Page {url} declares hreflang={lang} pointing to "
                                f"{target_href}, but that page does not point back. "
                                "Hreflang requires bidirectional links — without reciprocal "
                                "tags, search engines may ignore the signal entirely."
                            ),
                            "page": "cross-page",
                        })

    # If hreflang tags exist but none of the targets were audited,
    # note the limitation so the report doesn't give false assurance
    if page_hreflangs and not checked_any:
        total_targets = sum(len(langs) for langs in page_hreflangs.values())
        findings.append({
            "id": "HREFLANG_NOT_VERIFIED",
            "severity": "info",
            "title": f"Hreflang reciprocals could not be verified ({total_targets} alternate URLs not audited)",
            "detail": (
                "Hreflang tags were found but none of the alternate language URLs "
                "were included in this audit. Reciprocal validation requires auditing "
                "the target pages. Consider adding alternate language pages to the "
                "audit scope to verify bidirectional hreflang links."
            ),
            "page": "cross-page",
        })
    return findings


def check_schema_coverage(all_pages):
    """Some page types have schema, others don't."""
    findings = []
    if len(all_pages) < 2:
        return findings

    with_schema = []
    without_schema = []
    for page in all_pages:
        schema = page.get("schema", {})
        # Only count JSON-LD as "real" schema — minimal Microdata like
        # itemtype="WebPage" on <html> (added by Hugo/Hugoplate themes)
        # doesn't represent actionable schema implementation
        has = bool(schema.get("jsonLdTypes"))
        if has:
            with_schema.append(page.get("url", "unknown"))
        else:
            without_schema.append(page.get("url", "unknown"))

    if with_schema and without_schema and len(without_schema) < len(all_pages):
        findings.append({
            "id": "SCHEMA_COVERAGE_GAP",
            "severity": "moderate",
            "title": f"Schema markup on {len(with_schema)} pages but missing on {len(without_schema)}",
            "detail": (
                f"Pages with schema: {', '.join(with_schema[:3])}\n"
                f"Pages without: {', '.join(without_schema[:3])}\n"
                "Inconsistent schema coverage suggests the implementation is partial. "
                "Extend structured data to all content pages for consistent rich results."
            ),
            "page": "cross-page",
        })
    return findings


def check_internal_link_distribution(all_pages):
    """Pages with very few internal links (potential orphans)."""
    findings = []
    if len(all_pages) < 3:
        return findings

    # Count how many times each audited page is linked from other audited pages
    audited_urls = {p.get("url", ""): p for p in all_pages}

    for page in all_pages:
        links = page.get("links", {})
        internal_count = links.get("internalLinkCount", 0)
        url = page.get("url", "unknown")

        # Don't flag homepage (it naturally receives links from nav)
        is_homepage = _is_homepage(url)

        # Exclude focused pages that legitimately have few outgoing links
        url_lower = url.lower()
        is_focused = any(kw in url_lower for kw in [
            "/contact", "/pricing", "/demo", "/signup", "/login",
            "/thank-you", "/services/", "/service/", "/get-started",
        ])

        if internal_count < 3 and not is_homepage and not is_focused:
            findings.append({
                "id": "LOW_INTERNAL_LINKS",
                "severity": "moderate",
                "title": f"Page has only {internal_count} internal links",
                "detail": (
                    f"Page {url} contains very few internal links. Internal links help "
                    "search engines discover and understand the relationship between pages. "
                    "Pages with few internal links may be treated as low-priority by crawlers. "
                    "Note: this counts links ON this page, not links TO this page."
                ),
                "page": url,
            })
    return findings


def check_h1_consistency(all_pages):
    """Some pages have proper H1, others don't."""
    findings = []
    if len(all_pages) < 2:
        return findings

    with_h1 = []
    without_h1 = []
    for page in all_pages:
        headings = page.get("headings", {})
        if headings.get("h1Count", 0) >= 1:
            with_h1.append(page.get("url", "unknown"))
        else:
            without_h1.append(page.get("url", "unknown"))

    if with_h1 and without_h1 and len(without_h1) < len(all_pages):
        findings.append({
            "id": "INCONSISTENT_H1_PATTERN",
            "severity": "info",
            "title": f"H1 present on {len(with_h1)} pages but missing on {len(without_h1)}",
            "detail": (
                f"Pages without H1: {', '.join(without_h1[:3])}\n"
                "Inconsistent H1 usage suggests some templates or page types are "
                "missing their primary heading. Review the templates for pages "
                "without H1 tags."
            ),
            "page": "cross-page",
        })
    return findings


# ---------------------------------------------------------------------------
# Check registries
# ---------------------------------------------------------------------------

PER_PAGE_CHECKS = [
    check_http_status,
    check_title,
    check_description,
    check_canonical,
    check_h1,
    check_heading_hierarchy,
    check_images_alt,
    check_images_responsive,
    check_images_dimensions,
    check_lazy_loading,
    check_schema_markup,
    check_org_schema,
    check_breadcrumb_schema,
    check_schema_validation,
    check_og_tags,
    check_twitter_card,
    check_noindex,
    check_viewport,
    check_mixed_content,
    check_thin_content,
    check_html_lang,
    check_render_blocking,
    check_broken_anchors,
]

CROSS_PAGE_CHECKS = [
    check_duplicate_titles,
    check_duplicate_descriptions,
    check_og_image_sameness,
    check_canonical_consistency,
    check_hreflang_reciprocal,
    check_schema_coverage,
    check_internal_link_distribution,
    check_h1_consistency,
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

    # Deduplicate findings with same id + page + title.
    # Title is included because cross-page checks (page="cross-page") can
    # produce multiple distinct findings with the same check ID (e.g.,
    # two separate DUPLICATE_TITLES clusters).
    seen = set()
    deduped = []
    for f in all_findings:
        key = (f["id"], f["page"], f.get("title", ""))
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
            "per_page_checks": len(PER_PAGE_CHECKS),
            "cross_page_checks": len(CROSS_PAGE_CHECKS),
        },
    }


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Deterministic SEO audit checker")
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
