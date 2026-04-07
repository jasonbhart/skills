# SEO Audit: Schema Validation Depth + LCP Performance Checks

**Date:** 2026-04-07
**Skill:** seo-audit
**Scope:** Extend seo-eval.js, check_seo.py, scoring-rubric.md, and SKILL.md

## Summary

Add two capabilities to the seo-audit skill:

1. **Deeper schema markup validation** against Google rich result eligibility requirements, covering more schema types and distinguishing required vs recommended properties.
2. **LCP performance analysis** with a full Performance trace on the homepage and lightweight eval-based checks on all pages.

Both integrate into the existing audit workflow — no new skills, no new dependencies.

---

## 1. Schema Validation Enhancements

### 1a. seo-eval.js Changes

Currently the eval script extracts `@type` and raw JSON-LD objects. Extend it to:

- For each JSON-LD block, extract **all top-level properties** (not just `@type`)
- For `@graph` arrays, extract each item's type and properties separately
- Detect these additional types (currently not validated): HowTo, Event, SoftwareApplication, LocalBusiness, NewsArticle, BlogPosting

**New field in eval output:**

```json
{
  "schemaDetails": [
    {
      "types": ["Product"],
      "properties": ["name", "image", "offers", "sku", "brand"],
      "offersProperties": ["price", "availability", "priceCurrency"],
      "source": "@graph[2]",
      "context": "https://schema.org"
    }
  ]
}
```

The `schemaDetails` array provides the checker with enough data to validate required/recommended properties without re-parsing JSON-LD.

Nested validation scope is limited to one level deep for known important sub-objects:
- `Product.offers` -> extract `price`, `availability`, `priceCurrency`
- `Event.location` -> extract `@type` (Place vs VirtualLocation), `name`, `address`
- `Event.offers` -> extract `price`, `availability`, `url`
- `HowTo.step` -> extract count and whether each has `name` + `text` or `itemListElement`

### 1b. check_seo.py Changes

Add a `check_schema_eligibility` function that runs per-page. For each detected schema type, validate against Google's rich result requirements.

**Existing types — add recommended property checks:**

| Type | Currently Checked (required) | Add (recommended) |
|------|------------------------------|-------------------|
| Organization | name, url | logo, sameAs, contactPoint |
| Article | headline, author, datePublished, image | dateModified, publisher, description |
| FAQPage | mainEntity | (validate Q items have acceptedAnswer) |
| Product | name, offers | offers.price + offers.availability + offers.priceCurrency, sku, brand, aggregateRating |
| BreadcrumbList | itemListElement | position + name + item on each element |

**New types — full required + recommended checks:**

| Type | Required | Recommended |
|------|----------|-------------|
| HowTo | name, step (with name+text per step) | image, totalTime |
| Event | name, startDate, location | endDate, image, description, offers |
| SoftwareApplication | name, offers | applicationCategory, operatingSystem, aggregateRating |
| LocalBusiness | name, address | telephone, openingHours, geo |
| NewsArticle | headline, author, datePublished, image | dateModified, publisher, description |
| BlogPosting | headline, author, datePublished, image | dateModified, publisher, description |

**Severity mapping:**
- Missing required property -> severity: `critical` (won't qualify for rich results)
- Missing recommended property -> severity: `moderate` (reduces rich result quality)
- Missing schema type entirely on a page that should have one -> out of scope (would require content heuristics)

**Check naming convention** (follows existing pattern in check_seo.py):
- `schema_{type}_missing_required_{prop}` — e.g., `schema_product_missing_required_offers_price`
- `schema_{type}_missing_recommended_{prop}` — e.g., `schema_article_missing_recommended_dateModified`

### 1c. Scoring Rubric Update

The existing "Schema & Structured Data" category in `references/scoring-rubric.md` currently scores on presence. Update to weight eligibility:

- 8-10: Schema present with all required + most recommended properties
- 5-7: Schema present with all required properties, some recommended missing
- 3-4: Schema present but missing required properties (won't get rich results)
- 1-2: No schema or only generic/invalid schema

---

## 2. LCP Performance Enhancements

### 2a. Homepage: Full Trace Analysis (new SKILL.md phase)

Add a new step to Phase 2, run **only on the homepage**, after the existing eval:

1. Run `performance_start_trace` with `reload: true` and `autoStop: true`
2. Analyze insights: LCPBreakdown, DocumentLatency, RenderBlocking, LCPDiscovery via `performance_analyze_insight`
3. Extract the four LCP subparts with timing:
   - TTFB (target: ~40% of LCP)
   - Resource load delay (target: <10%)
   - Resource load duration (target: ~40%)
   - Element render delay (target: <10%)
4. Identify which subpart exceeds its target percentage (the bottleneck)

**Save structured results in page JSON:**

```json
{
  "lcpTrace": {
    "totalLcp": 2.8,
    "ttfb": 0.9,
    "resourceLoadDelay": 0.6,
    "resourceLoadDuration": 1.0,
    "elementRenderDelay": 0.3,
    "bottleneck": "resourceLoadDelay",
    "lcpElement": "img.hero-banner",
    "lcpResourceUrl": "/images/hero.webp",
    "rating": "needs-improvement"
  }
}
```

`rating` values: `good` (<=2.5s), `needs-improvement` (2.5-4.0s), `poor` (>4.0s).

**If the trace times out or fails** (common on heavy pages), skip and note "LCP trace unavailable" in the report. The lightweight checks (2b) still run.

### 2b. All Pages: Lightweight LCP Checks (seo-eval.js extension)

Extend the existing eval script to identify the LCP candidate and check common problems. This uses the PerformanceObserver API, not the trace.

**Updated fields in eval output:**

The `lcpCandidate` object inside the existing `cwvIndicators` section is upgraded with new fields:

```json
{
  "cwvIndicators": {
    "lcpCandidate": {
      "element": "img",
      "selector": "img.hero-banner",
      "url": "/images/hero.webp",
      "isLazy": true,
      "hasFetchpriority": false,
      "hasPreload": false,
      "isText": false,
      "renderTime": 2.8
    }
  }
}
```

The `resources` section gains a combined `renderBlockingResources` array:

```json
{
  "resources": {
    "renderBlockingResources": [
      { "tag": "script", "src": "/js/vendor.js", "hasAsync": false, "hasDefer": false },
      { "tag": "link", "href": "/css/main.css", "media": "all" }
    ]
  }
}
```

**LCP candidate detection approach:**
- Use `new PerformanceObserver` with `type: 'largest-contentful-paint'` if available
- Fall back to heuristic: largest `<img>` visible in the initial viewport (by rendered area, using the browser's actual viewport dimensions — typically 1280x720 in chrome-devtools-mcp) or largest text block
- The eval script registers the observer early and reads the last entry after page load settles

**Render-blocking detection:**
- `<script>` tags in `<head>` without `async` or `defer` attributes (and not `type="module"`)
- `<link rel="stylesheet">` in `<head>` without a `media` attribute that limits scope (e.g., `media="print"` is fine, `media="all"` or no media is blocking)

### 2c. check_seo.py Changes

Add these deterministic checks:

| Check | Severity | Condition |
|-------|----------|-----------|
| `lcp_lazy_loaded` | critical | LCP candidate has `loading="lazy"` |
| `lcp_no_fetchpriority` | moderate | LCP candidate is an image without `fetchpriority="high"` |
| `lcp_no_preload` | moderate | LCP resource URL has no matching `<link rel="preload">` |
| `render_blocking_count` | moderate | More than 3 render-blocking resources in `<head>` |
| `lcp_trace` | critical/moderate | Homepage only: `poor` (>4.0s) = critical, `needs-improvement` (2.5-4.0s) = moderate. Includes bottleneck subpart in finding detail. |

### 2d. SKILL.md Changes

Add a new step to Phase 2 (after existing step 4, before cross-page analysis):

**Step 5: LCP Performance Analysis (homepage only)**
- Instructions for running the performance trace
- How to handle trace failures (skip gracefully)
- How to interpret and save the subpart data

Update the report template to include an LCP section:

```markdown
## LCP Performance (Homepage)
| Subpart | Time | % of LCP | Target | Status |
|---------|------|----------|--------|--------|
| TTFB | X.Xs | XX% | ~40% | OK/High |
| Resource Load Delay | X.Xs | XX% | <10% | OK/High |
| Resource Load Duration | X.Xs | XX% | ~40% | OK/High |
| Element Render Delay | X.Xs | XX% | <10% | OK/High |
| **Total LCP** | **X.Xs** | | <=2.5s | Good/Needs Work/Poor |

**LCP Element:** `<img class="hero-banner" src="...">`
**Bottleneck:** [subpart] — [one-sentence explanation of what to fix]
```

### 2e. Scoring Rubric Update

Update the "Core Web Vitals" or "Performance" category:

- 9-10: LCP good (<=2.5s), no lazy LCP, fetchpriority set, no render-blocking issues
- 7-8: LCP good but minor issues (missing fetchpriority, 1-2 render-blocking resources)
- 5-6: LCP needs improvement (2.5-4.0s) or lazy-loaded LCP
- 3-4: LCP poor (>4.0s) or multiple critical issues
- 1-2: LCP poor with lazy LCP, no fetchpriority, many render-blocking resources

---

## Files Modified

| File | Change |
|------|--------|
| `seo-audit/scripts/seo-eval.js` | Add `schemaDetails`, `lcpCandidate`, `renderBlockingResources` fields |
| `seo-audit/scripts/check_seo.py` | Add `check_schema_eligibility`, `check_lcp_lazy`, `check_lcp_fetchpriority`, `check_lcp_preload`, `check_render_blocking_count`, `check_lcp_trace` functions |
| `seo-audit/references/scoring-rubric.md` | Update Schema and Performance scoring criteria |
| `seo-audit/SKILL.md` | Add LCP trace step to Phase 2, update report template |

## Files NOT Modified

| File | Reason |
|------|--------|
| `martech-audit/*` | Out of scope — martech-audit already has its own performance section via Lighthouse |
| `seo-audit/evals/*` | Eval definitions update separately after implementation |

## Dependencies

- `performance_start_trace` and `performance_analyze_insight` from chrome-devtools-mcp (already a prerequisite)
- `PerformanceObserver` API for LCP candidate detection (available in all modern browsers)
- No new MCP servers, no new Python dependencies
