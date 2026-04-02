---
name: seo-audit
description: "Audit a website's technical SEO health — meta tags, headings, schema markup, canonicals, Core Web Vitals indicators, and social sharing tags — by inspecting live runtime behavior. Use this skill whenever the user wants to check a site's SEO health, audit on-page SEO, diagnose ranking issues, review meta tags, or run any kind of technical SEO audit. Also trigger when the user mentions 'SEO audit,' 'technical SEO,' 'why am I not ranking,' 'SEO issues,' 'on-page SEO,' 'meta tags review,' 'SEO health check,' 'my traffic dropped,' 'lost rankings,' 'not showing up in Google,' 'page speed issues,' 'core web vitals,' 'schema markup audit,' or vague requests like 'check my SEO.' This skill produces a scored, actionable report identifying missing tags, broken structure, and optimization opportunities."
---

# SEO Audit

Audit a website's technical and on-page SEO by inspecting live pages in a real browser. Produces a scored report identifying structural issues, missing tags, schema gaps, and performance indicators.

## Why This Skill Exists

Most SEO audits rely on crawl tools or static HTML analysis. This skill goes further: it loads pages in a real browser, inspects the DOM after JavaScript execution, validates JSON-LD schema at runtime, and checks for CLS-causing elements — catching problems that static analysis misses entirely. The output is a professional, scored report.

## Tool Requirements

This skill works best with **chrome-devtools-mcp** (runtime browser inspection). The full audit depends on evaluating JavaScript in a live browser to detect runtime-injected schema, SPA content, and actual DOM state.

**If chrome-devtools-mcp is not available**, tell the user and offer a static-analysis fallback:
> "chrome-devtools-mcp is not available. I can run a static HTML analysis using tavily_extract or web_fetch, which will catch ~70% of issues (meta tags, headings, links, canonical, robots, OG tags) but cannot verify: runtime-injected JSON-LD, SPA content, Core Web Vitals indicators, or post-render DOM state. Want me to proceed with static analysis?"

**If chrome-devtools-mcp is available but the site blocks headless browsers** (bot protection redirecting, CAPTCHA walls, or blank pages), detect this by checking if the loaded page's domain matches the target domain after navigation. If it doesn't:
1. Note the bot protection in the report (this is itself a finding)
2. Fall back to static HTML analysis via `tavily_extract` or `web_fetch`
3. Clearly caveat which checks could not be performed

## Audit Workflow

### Phase 1: Scope and Crawl

1. **Get the target URL** from the user
2. **Map the site structure** using `tavily_map` — identify key page types:
   - Homepage
   - Service/product pages
   - Blog post (sample 1)
   - About/team page
   - Contact/conversion page
   - Category or archive pages (if applicable)

   **If `tavily_map` returns empty**, fall back to HTML link extraction: fetch the homepage via `tavily_extract` or `web_fetch`, then parse internal links from `<a href="...">` tags.

3. **Select 4-6 pages** covering these types. Always include homepage + a content page + at least one interior page.

4. **Detect site type** (SaaS, ecommerce, blog, local business, portfolio) — this influences which findings are most relevant and how the report frames recommendations.

### Phase 2: Runtime Inspection (per page)

For each selected page, open it in chrome-devtools-mcp and run these checks. The order matters.

#### Step 1: Load the page and verify it loaded correctly

```
new_page → url
```

**Bot-blocking detection (do this FIRST):**

After the page loads, immediately verify the loaded domain matches the target:
```javascript
evaluate_script: () => ({ loadedUrl: document.location.href, loadedHost: document.location.hostname })
```

If the hostname does NOT match the target domain, the site has bot protection. Fall back to static analysis. Note the bot protection as a finding.

**If the domain matches**, wait for the page to fully render:
- Standard sites: 2-3 seconds is sufficient
- SPAs (React, Next.js, Angular): wait 5-8 seconds for client-side rendering
- Detect SPA frameworks from the eval script's `spaFramework` field on the first page, then adjust wait times for subsequent pages

#### Step 2: Run the SEO eval script

Read the full contents of `scripts/seo-eval.js` and pass it to `evaluate_script`. Do NOT inline the script or modify it.

```
evaluate_script → expression: <contents of scripts/seo-eval.js>
```

The script returns a JSON object with these top-level keys:

| Key | Contents |
|-----|----------|
| `url` | Current page URL |
| `httpStatus` | HTTP status code from Navigation API |
| `title`, `titleLength`, `titleTruncated` | Page title and length metrics |
| `description`, `descriptionLength`, `descriptionTruncated` | Meta description and length |
| `canonical` | Canonical URL, self-referencing check, mismatch flag |
| `robots` | Robots meta content, noindex/nofollow flags |
| `headings` | H1/H2/H3 counts, texts, hierarchy validity, outline |
| `images` | Alt text coverage, lazy loading, responsive images, dimensions |
| `links` | Internal/external counts, broken anchors, nofollow links, external domains |
| `schema` | JSON-LD types, raw objects, microdata, boolean flags for Organization/WebSite/Breadcrumb/Article/FAQ |
| `schemaValidation` | Missing required fields in detected schema |
| `og` | Open Graph tags (title, description, image, url, type) |
| `twitter` | Twitter Card tags |
| `hreflang` | Hreflang tags and self-referencing check |
| `resourceHints` | Preconnect, prefetch, preload, dns-prefetch links |
| `cwvIndicators` | Images without dimensions (CLS risk), LCP candidate, viewport meta |
| `resources` | Script/stylesheet counts, render-blocking resources |
| `accessibility` | HTML lang, skip link, form label coverage |
| `security` | HTTPS status, mixed content detection |
| `content` | Word count, pagination rel links |
| `meta` | Charset, author, generator, site verification codes |
| `spaFramework` | Detected frameworks (Next.js, Nuxt, React, Angular, Hugo, WordPress) |

Save this output for each page — it will be passed to the rules engine in Phase 3.

#### Step 3: Collect supplementary data

After the eval script runs:

1. **Network requests** (for HTTP header data):
   ```
   list_network_requests → resourceTypes: ["document"]
   ```
   Check for X-Robots-Tag in response headers (some sites use HTTP headers instead of meta tags for noindex).

2. **Performance trace** (optional, for CWV data):
   ```
   performance_start_trace
   ```
   Navigate to the page again, then:
   ```
   performance_stop_trace
   performance_analyze_insight
   ```
   This provides real LCP, CLS, and FCP data. Include in the report if available.

#### Step 4: robots.txt and sitemap.xml (once per domain, not per page)

Fetch these resources using `navigate_page` in a separate tab, `tavily_extract`, or `web_fetch`:

1. **robots.txt** — Check:
   - Does it exist?
   - Does it block any important paths?
   - Does it reference a sitemap?

2. **sitemap.xml** — Check:
   - Does it exist and parse correctly?
   - Are the audited pages listed in it?
   - Is the lastmod date recent?

Add these as additional context for the report — they're not part of the per-page eval but inform the crawlability score.

### Phase 3: Analysis

1. **Write eval outputs to temp files** — one JSON file per page:
   ```
   /tmp/seo-audit/<domain>/<page-slug>.json
   ```

2. **Run the deterministic checker**:
   ```bash
   python3 ~/.claude/skills/seo-audit/scripts/check_seo.py --dir /tmp/seo-audit/<domain>/ --pretty
   ```

3. **Read the findings JSON** — it contains:
   - `findings[]` — array of `{id, severity, title, detail, page}` objects
   - `summary` — counts of critical/moderate/info findings, pages checked, checks run

### Phase 4: Report

Generate a professional SEO audit report with these sections:

#### Executive Summary
- Overall health score (1-10, using `references/scoring-rubric.md`)
- Top 3-5 priority findings
- Site type and scope (pages audited)

#### Scoring Breakdown
Score each category per the rubric:
- Crawlability & Indexation (20%)
- On-Page Optimization (25%)
- Schema & Structured Data (15%)
- Core Web Vitals & Performance (15%)
- Social & Sharing (10%)
- Technical Foundation (15%)

Present as a table with per-category scores and the weighted overall.

#### Critical Findings
List all critical-severity findings with:
- What's wrong
- Why it matters (business impact)
- How to fix it
- Which pages are affected

#### Moderate Findings
Same format as critical, grouped by category.

#### Informational Findings
Brief list — these are positive signals or minor optimizations.

#### Prioritized Action Plan
1. **Immediate fixes** (critical findings — broken indexation, missing titles)
2. **Quick wins** (easy fixes with high impact — add canonical tags, fill alt text)
3. **Medium-term improvements** (schema markup, image optimization)
4. **Long-term recommendations** (content depth, internal linking strategy)

### Report Style

- **Bizdev-ready**: The report should demonstrate expertise without being overly technical. Explain why each finding matters in business terms.
- **Caveated findings**: Every finding should note when it might not apply. E.g., "Multiple H1 tags — Note: some CSS frameworks use H1 for visual sizing."
- **No false positives**: If the data is ambiguous, note the uncertainty rather than asserting a problem. Reference `references/common-seo-errors.md` for known edge cases.
- **Score defensibly**: Use the rubric. If you deviate from it, explain why.

## Static Analysis Fallback

When chrome-devtools-mcp is unavailable, use `tavily_extract` or `web_fetch` to get page HTML. Parse it to construct a partial eval-compatible JSON object:

**Available in static mode** (~70% of checks):
- Title, meta description, canonical, robots meta
- H1/H2/H3 from HTML
- OG tags, Twitter Card tags
- JSON-LD schema (if in static HTML — not runtime-injected)
- Links (internal/external count, broken anchors)
- Image alt text (from `<img>` tags in HTML)
- HTML lang attribute
- HTTPS (from URL)

**NOT available in static mode** (caveat in report):
- Runtime-injected JSON-LD (CMS plugins like Yoast inject via JS)
- SPA content (React/Next.js pages may have empty initial HTML)
- Core Web Vitals performance data
- Images without dimensions check (requires rendered DOM)
- Mixed content detection (requires resource loading)
- HTTP response headers (X-Robots-Tag)

Clearly caveat the static analysis limitation in the report header.

## Scope Boundaries

**This skill covers:** Technical SEO and on-page optimization that can be measured from the rendered page.

**This skill does NOT cover** (defer to other skills):
- Content strategy and keyword research → `content-strategy` skill
- Backlink analysis and off-page SEO → requires Ahrefs/Semrush API access
- AI search optimization → `ai-seo` skill
- Schema markup implementation → `schema-markup` skill (for fixing, not just auditing)
- Site architecture planning → `site-architecture` skill
- Analytics/tracking setup → `martech-audit` skill
