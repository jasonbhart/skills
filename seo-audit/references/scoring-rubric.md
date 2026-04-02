# SEO Scoring Rubric

Each category is scored 1-10. The overall score is the weighted average.

## Crawlability & Indexation — Weight: 20%

| Score | Criteria |
|-------|----------|
| 9-10 | All pages have self-referencing canonicals, robots.txt is clean, sitemap.xml exists and is referenced, no unexpected noindex, hreflang correct (if applicable). |
| 7-8 | Canonicals present on most pages. Sitemap exists. No critical indexation issues. |
| 5-6 | Some pages missing canonicals. Sitemap exists but may be incomplete. Minor robots.txt issues. |
| 3-4 | Missing canonicals on multiple pages. No sitemap, or sitemap has errors. Accidental noindex on content pages. |
| 1-2 | Critical indexation failures: noindex on homepage, robots.txt blocking important paths, canonical loops, or no canonical/sitemap at all. |

## On-Page Optimization — Weight: 25%

| Score | Criteria |
|-------|----------|
| 9-10 | Every page has unique title (30-60 chars) with target keyword, unique meta description (120-160 chars), single H1, clean heading hierarchy, good internal linking. |
| 7-8 | Titles and descriptions present and mostly unique. H1 on all pages. Minor issues (a few long titles, one duplicate description). |
| 5-6 | Titles present but some duplicates or missing descriptions. H1 inconsistent. Some heading hierarchy issues. |
| 3-4 | Multiple pages missing titles or descriptions. No H1 on several pages. Thin content on key pages. |
| 1-2 | Missing titles, missing H1s, no meta descriptions, broken heading structure across the site. |

## Schema & Structured Data — Weight: 15%

| Score | Criteria |
|-------|----------|
| 9-10 | JSON-LD for Organization (homepage), BreadcrumbList (interior pages), and page-specific types (Article, Service, FAQ, Product). All schema validates with required fields. |
| 7-8 | Organization schema present. Some page-specific schema. Minor validation issues. |
| 5-6 | Basic schema present (e.g., WebSite only) but no page-specific types. Or Microdata instead of JSON-LD. |
| 3-4 | Only itemtype on `<html>` tag (minimal Microdata). No JSON-LD. |
| 1-2 | No structured data at all. |

## Core Web Vitals & Performance — Weight: 15%

| Score | Criteria |
|-------|----------|
| 9-10 | All images have dimensions (no CLS risk), responsive images with srcset, lazy loading on below-fold images, few render-blocking resources, LCP element has fetchpriority="high". |
| 7-8 | Most images sized. Some lazy loading. Moderate render-blocking resources. |
| 5-6 | Many images without dimensions. No lazy loading. Several render-blocking scripts. No responsive images. |
| 3-4 | Significant CLS risks. Heavy render-blocking. Large unoptimized images. |
| 1-2 | Extreme performance issues: many render-blocking resources, no image optimization, mixed content warnings. |

## Social & Sharing — Weight: 10%

| Score | Criteria |
|-------|----------|
| 9-10 | Complete OG tags (title, description, image, url, type) on all pages. Unique OG images per page. Twitter Card tags present. |
| 7-8 | OG tags present on all pages. Some use a shared default image. Twitter tags present. |
| 5-6 | OG tags present but same image on 75%+ of pages. Missing Twitter tags. |
| 3-4 | OG tags on some pages but not others. Missing OG image. |
| 1-2 | No OG tags or Twitter Card tags. |

## Technical Foundation — Weight: 15%

| Score | Criteria |
|-------|----------|
| 9-10 | HTTPS everywhere, no mixed content, viewport meta set, html lang attribute, no broken anchor links, proper security headers. |
| 7-8 | HTTPS, viewport set, lang attribute present. Minor issues (a few broken anchors). |
| 5-6 | HTTPS but some mixed content. Missing html lang. Some broken anchors. |
| 3-4 | Missing viewport meta. No html lang. Multiple broken anchors. |
| 1-2 | No HTTPS, or critical mixed content, or missing viewport on multiple pages. |

## Calculating Overall Score

```
overall = (crawlability * 0.20) + (on_page * 0.25) + (schema * 0.15) +
          (cwv_performance * 0.15) + (social * 0.10) + (technical * 0.15)
```

Round to nearest integer for display.
