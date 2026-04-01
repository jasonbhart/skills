# Scoring Rubric

Each category is scored 1-10. The overall score is the weighted average.

## Tag Presence (GTM/GA4) — Weight: 15%

| Score | Criteria |
|-------|----------|
| 9-10 | GTM + GA4 both present and loading on all pages. Server-side tagging configured. No failed requests. |
| 7-8 | GTM + GA4 present on all pages. Client-side only. No errors. |
| 5-6 | GA4 present (gtag.js direct, no GTM) on all pages. Or GTM present but GA4 misconfigured. |
| 3-4 | Tracking present on some pages but missing on others. Or only a non-Google analytics tool. |
| 1-2 | No analytics tracking detected, or tracking scripts failing to load. |

## Event Tracking Maturity — Weight: 15%

| Score | Criteria |
|-------|----------|
| 9-10 | Custom events beyond pageviews: CTA clicks, scroll depth, video engagement, file downloads. Events follow naming conventions (object_action format). |
| 7-8 | Some custom events beyond enhanced measurement defaults. Reasonable naming. |
| 5-6 | Enhanced measurement events only (automatic scroll, outbound clicks). No custom events. |
| 3-4 | Only pageview events. DataLayer contains only GTM system events (gtm.js, gtm.dom, gtm.load). |
| 1-2 | No events firing at all, or events firing with errors. |

## Conversion Tracking — Weight: 20%

| Score | Criteria |
|-------|----------|
| 9-10 | Key conversions tracked (form submit, demo booked, signup). Conversion values assigned. Events marked as conversions in GA4. Cross-domain tracking on embedded forms. |
| 7-8 | Primary conversion tracked. Basic form submission event. |
| 5-6 | Form tracking exists but incomplete (e.g., tracks form start but not submit, or misses embedded forms). |
| 3-4 | Contact/conversion page exists but no conversion events fire. |
| 1-2 | No conversion tracking at all. Cannot attribute any outcomes to traffic sources. |

## Data Layer Quality — Weight: 10%

| Score | Criteria |
|-------|----------|
| 9-10 | Rich dataLayer with page type, content group, user state, product/service data. Custom variables populated before GTM loads. |
| 7-8 | DataLayer includes some custom data beyond defaults (page type or user info). |
| 5-6 | DataLayer exists but only contains GTM system events. |
| 3-4 | DataLayer initialized but essentially empty. |
| 1-2 | No dataLayer, or dataLayer has errors/malformed pushes. |

## Privacy & Consent — Weight: 10%

| Score | Criteria |
|-------|----------|
| 9-10 | Consent Management Platform present. Google Consent Mode v2 implemented (default deny, update on consent). Tags respect consent state. |
| 7-8 | CMP present and functional. Basic consent mode. |
| 5-6 | Cookie banner present but no Consent Mode integration. Tags fire regardless of consent. |
| 3-4 | No cookie banner but tracking cookies are being set. Compliance risk. |
| 1-2 | Third-party cookies set with no consent mechanism. Active compliance violation for EU/UK/CA visitors. |

## SEO & Schema Markup — Weight: 10%

| Score | Criteria |
|-------|----------|
| 9-10 | JSON-LD schema for Organization, WebSite, and page-specific types (Article, Service, FAQ). Canonical URLs on all pages. Complete OG tags. |
| 7-8 | Some schema markup present. Canonical URLs set. Good meta tags. |
| 5-6 | Meta title + description present. OG tags present. No schema markup. |
| 3-4 | Meta tags present but incomplete (missing descriptions or OG tags on some pages). No canonical. |
| 1-2 | Missing or broken meta tags. No schema. No OG tags. |

## Pixel Coverage — Weight: 10%

| Score | Criteria |
|-------|----------|
| 9-10 | GA4 + 2 or more advertising/remarketing pixels active and verified. Appropriate for business type (B2B = LinkedIn, B2C = Meta, etc.). |
| 7-8 | GA4 + 1 additional pixel active and working. |
| 5-6 | GA4 only, but functioning correctly. |
| 3-4 | GA4 only with issues, or preconnect hints for pixels that aren't actually implemented. |
| 1-2 | No working pixels, or all pixels have errors. |

**Non-Google stacks:** Sites that deliberately avoid Google analytics and ad pixels (e.g., Apple using only Adobe via first-party domains) should be scored per the rubric as-is (zero pixels = 1-2/10), but add a context note in the report explaining the deliberate architectural choice. Do not inflate the score — the rubric measures what's present, not intent. The context note lets readers understand the tradeoff.

## Tag Performance Impact — Weight: 10%

| Score | Criteria |
|-------|----------|
| 9-10 | Lighthouse Performance 90+. All tracking scripts loaded async. TBT from third-party code under 200ms. No tag-caused CLS. Tags fire at appropriate timing (non-essential deferred to Window Loaded or later). Server-side tagging offloads client processing. |
| 7-8 | Lighthouse Performance 70-89. Most scripts async. Third-party TBT under 500ms. Minor CLS from consent banner or chat widget. |
| 5-6 | Lighthouse Performance 50-69. Some render-blocking tracking scripts. Third-party TBT 500ms-1s. Noticeable CLS from tag injections. Non-essential tags firing on Page View. |
| 3-4 | Lighthouse Performance 30-49. Multiple render-blocking scripts. Third-party TBT 1-2s. Significant CLS from consent banner + chat + A/B testing. Zombie tags loading scripts for unused vendors. |
| 1-2 | Lighthouse Performance under 30. Tracking scripts dominate page load. Third-party TBT over 2s. Tag waterfall chains (A loads B loads C). GTM container over 200KB. 15+ third-party domains on a single page. |

## Calculating Overall Score

```
overall = (tag_presence * 0.15) + (event_tracking * 0.15) + (conversion_tracking * 0.20) +
          (data_layer * 0.10) + (privacy * 0.10) + (seo_schema * 0.10) + (pixel_coverage * 0.10) +
          (tag_performance * 0.10)
```

Round to nearest integer for display.
