# Common SEO Errors

Reference guide of known SEO issues, organized by impact level.

## Fatal Errors (page effectively deindexed or invisible)

- **noindex on homepage or key pages** — entire page removed from search index
- **Canonical pointing to wrong page** — search engines consolidate signals to the wrong URL
- **Canonical loop** — Page A canonicals to B, B canonicals to A (both may be dropped)
- **robots.txt blocking important paths** — Googlebot can't crawl the content
- **Missing sitemap.xml** — large sites may have orphaned pages never discovered
- **HTTP site without HTTPS redirect** — Google strongly prefers HTTPS; HTTP sites rank lower
- **Cross-domain canonical (unintentional)** — tells Google this page is a copy of another domain
- **Soft 404s** — page returns 200 but shows error/empty content; wastes crawl budget

## Degraded Errors (page ranks but underperforms)

- **Duplicate titles across pages** — search engines can't differentiate pages, may pick the wrong one
- **Missing meta description** — Google auto-generates snippet, often poorly
- **Title too long (>60 chars)** — truncated in SERPs, key info may be cut off
- **Multiple H1 tags** — dilutes primary topic signal
- **No H1 tag** — search engines lose the strongest on-page heading signal
- **Heading hierarchy broken** (H1 → H3, skipping H2) — weakens content structure signal
- **Thin content (<300 words)** — insufficient depth to rank for competitive queries
- **No structured data** — misses rich result opportunities (stars, FAQ, breadcrumbs)
- **Incomplete schema** — JSON-LD present but missing required fields (no rich results triggered)
- **Images without alt text** — invisible to image search and screen readers
- **Duplicate meta descriptions** — missed opportunity for unique CTR optimization
- **Mixed www/non-www canonicals** — splits link equity between two domain variants
- **Missing html lang attribute** — search engines may serve page to wrong language audience

## Silent Errors (not immediately visible but compound over time)

- **Same OG image on 75%+ of pages** — social shares all look identical, reducing engagement
- **No Twitter Card tags** — falls back to OG (minor), but looks suboptimal on Twitter/X
- **No Organization schema on homepage** — no Knowledge Panel, weaker brand SERP presence
- **No BreadcrumbList schema** — no breadcrumb navigation in search results
- **Images without width/height** — causes CLS (Cumulative Layout Shift), a Core Web Vital
- **No lazy loading on image-heavy pages** — slow LCP, wasted bandwidth on mobile
- **Missing hreflang reciprocal** — international targeting signal ignored by search engines
- **Broken anchor links (href="#")** — not crawlable, no SEO value passed
- **Low internal link count** — orphan-like pages get less crawl priority

## Performance Errors (affects Core Web Vitals ranking factor)

- **Render-blocking scripts in head** — delays First Contentful Paint and LCP
- **Render-blocking CSS without media queries** — all CSS blocks rendering even if unused
- **Large images without srcset** — mobile users download desktop-sized images
- **No image compression or modern formats** — WebP/AVIF saves 25-50% over JPEG/PNG
- **No fetchpriority="high" on LCP element** — browser doesn't prioritize the hero image
- **Third-party scripts without async/defer** — blocking the main thread
- **Font loading flash** — FOIT/FOUT from web fonts without display swap
- **Excessive DOM size** — >1500 elements slows rendering and increases memory usage

## CMS-Specific Gotchas

- **WordPress plugin SEO conflicts** — multiple SEO plugins (Yoast + AIOSEO) outputting duplicate meta tags
- **Hugo/static sites missing canonical** — must be explicitly configured in templates
- **SPA content not in initial HTML** — search engines may not execute JavaScript; critical content must be in the initial response or use SSR
- **CMS-generated duplicate pages** — tag/category/author archives creating thin duplicates
- **Pagination without rel=next/prev** — search engines may not connect paginated series (note: Google deprecated rel=next/prev but Bing still uses it)
