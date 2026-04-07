# Martech Eval Shopify Detection Fixes

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix pixel detection blind spots exposed by the getpuroair.com audit — GTM-loaded pixels, Shopify web pixel sandboxes, and missing platform signatures.

**Architecture:** Four targeted edits across the martech-audit skill: supplement pixel detection in the eval script using gtmObject keys, add Shopify web pixel awareness to the SKILL.md orchestrator instructions, add missing platforms to pixel-signatures.md, and refine the double-tagging check detail in check_findings.py.

**Tech Stack:** JavaScript (eval script), Python (checker), Markdown (skill docs + references)

---

### Task 1: Add gtmObject-based pixel detection to martech-eval.js

**Files:**
- Modify: `~/.claude/skills/martech-audit/scripts/martech-eval.js:313-340` (pixels object)
- Modify: `~/.claude/skills/martech-audit/scripts/martech-eval.js:1-15` (header comment)

The `pixels` object currently only checks `allScriptText`. GTM-loaded pixels (Google Ads, TikTok via Shopify web pixels) are invisible because they don't appear as `<script>` elements in the parent DOM. However, `gtmObject` (already collected) contains registered tag IDs like `AW-660213988`. We can use this as a supplementary detection signal.

- [ ] **Step 1: Add gtmObject-based supplementary detection to pixels object**

In `scripts/martech-eval.js`, replace the `google_ads` line (line 326) with a version that also checks gtmObject for `AW-` prefixed keys:

```javascript
google_ads: allScriptText.includes('googleads') || allScriptText.includes('gtag_report_conversion') ||
  allScriptText.includes('googleadservices') || r.gtmObject.some(k => /^AW-/.test(k)),
```

This adds two new signals:
- `googleadservices` in allScriptText (catches hardcoded conversion snippets)
- `AW-` prefix in gtmObject keys (catches GTM-managed Google Ads)

- [ ] **Step 2: Add Shopify web pixel iframe detection field**

After the `pixels` object (after line 340), add a new field that detects Shopify web pixel sandboxes by scanning iframes:

```javascript
// Shopify Web Pixel sandbox detection — these iframes load pixels (TikTok,
// Google Ads, Bing, etc.) in isolated contexts invisible to allScriptText.
// The eval script cannot inspect inside them, but knowing they exist helps
// the orchestrator understand why network evidence may show pixels the eval missed.
r.shopifyWebPixels = (() => {
  const wpIframes = Array.from(document.querySelectorAll('iframe')).filter(i =>
    (i.src || '').includes('web-pixels') && (i.src || '').includes('sandbox')
  );
  return {
    detected: wpIframes.length > 0,
    count: wpIframes.length,
    ids: wpIframes.map(i => {
      const m = (i.src || '').match(/web-pixel-(\d+)/);
      return m ? m[1] : null;
    }).filter(Boolean),
  };
})();
```

- [ ] **Step 3: Update the header comment to mention Shopify web pixel blind spot**

In lines 1-15, after the existing note about GTM-loaded pixels (line 14-15), add:

```javascript
//
// Shopify web pixel sandboxes are a similar blind spot — Shopify loads pixels
// (TikTok, Google Ads, Bing, Reddit, etc.) inside isolated <iframe> elements
// that the parent page's JS cannot access. The shopifyWebPixels field flags
// when these sandboxes are present so the orchestrator knows to rely on
// network evidence for pixel detection on Shopify sites.
```

- [ ] **Step 4: Verify the script is still valid JS**

```bash
node -c ~/.claude/skills/martech-audit/scripts/martech-eval.js
```

Expected: no syntax errors.

- [ ] **Step 5: Commit**

```bash
cd ~/.claude/skills/martech-audit
git add scripts/martech-eval.js
git commit -m "fix(martech-eval): add gtmObject-based Google Ads detection and Shopify web pixel awareness

Google Ads loaded via GTM was invisible to allScriptText pixel detection.
Now also checks gtmObject for AW- prefix and allScriptText for googleadservices.
Adds shopifyWebPixels field to flag Shopify web pixel sandbox iframes."
```

---

### Task 2: Add Shopify web pixel guidance to SKILL.md

**Files:**
- Modify: `~/.claude/skills/martech-audit/SKILL.md:155-161` (after Step 2 eval note, before Step 2b)

The SKILL.md instructs the orchestrator on how to interpret eval results. It needs a section explaining that Shopify web pixel sandboxes are a detection blind spot, and that network evidence must be merged with eval results on Shopify sites.

- [ ] **Step 1: Add Shopify web pixel awareness section after Step 2**

Insert the following after line 160 (`<!-- Old inline eval removed -->`) and before line 162 (`#### Step 2b:`):

```markdown
#### Step 2a: Shopify Web Pixel sandbox reconciliation

**Shopify sites only.** Shopify's Web Pixels system loads advertising and analytics pixels (TikTok, Google Ads, Bing, Reddit, Snapchat, etc.) inside sandboxed `<iframe>` elements. These iframes run in isolated JavaScript contexts — the eval script **cannot detect pixels loaded this way**. The `shopifyWebPixels` field in the eval output flags when these sandboxes are present.

If `shopifyWebPixels.detected` is true:

1. **Do not trust `pixels.*: false` at face value** — a pixel showing `false` in the eval may still be active via a Shopify web pixel. Always cross-reference with `list_network_requests` before reporting a pixel as absent.
2. **Expect triple-tagging, not just double** — Shopify's web pixel system fires its own `page_view` and conversion events independently of both hardcoded gtag.js and GTM. If the eval shows `doubleTagging: true` on a Shopify site, the actual situation is likely triple-counting (hardcoded + GTM + Shopify web pixel).
3. **SecurityError console spam is expected** — Shopify web pixel sandboxes generate `SecurityError: Failed to read 'matchMedia' from Window` errors. These are platform noise, not site bugs. Note them as informational, not as a finding.
4. **Reconcile pixel detection with network evidence** — For each pixel domain found in `list_network_requests` but not in the eval's `pixels` object, add it to the detected tools list in the report. Common Shopify web pixel-loaded platforms: TikTok, Google Ads (via Shopify's own conversion pixel), Bing, Reddit, Snapchat.
5. **Check for additional Shopify ecosystem tools in network requests** — SafeOpt (`manage.safeopt.com`), Mountain.com (`px.mountain.com`, `dx.mountain.com`), and Shopify's own attribution (`trekkie.storefront`) are common on Shopify sites and won't appear in the eval.
```

- [ ] **Step 2: Commit**

```bash
cd ~/.claude/skills/martech-audit
git add SKILL.md
git commit -m "docs(martech-audit): add Shopify web pixel sandbox guidance to SKILL.md

Shopify sites load pixels in isolated iframes invisible to the eval script.
New Step 2a instructs the orchestrator to reconcile eval results with network
evidence, expect triple-tagging, and ignore SecurityError console spam."
```

---

### Task 3: Add missing platforms to pixel-signatures.md

**Files:**
- Modify: `~/.claude/skills/martech-audit/references/pixel-signatures.md`

Add platforms discovered during the getpuroair.com audit that are missing from the reference.

- [ ] **Step 1: Add Front to existing Customer Messaging & Support table**

In `references/pixel-signatures.md`, in the "## Customer Messaging & Support" table (after the LiveChat row, line 53), add:

```markdown
| Front | `chat-assets.frontapp.com` | — | `FrontChat` |
```

- [ ] **Step 2: Add Shopify Ecosystem section**

After the "## Server-Side Tagging Indicators" section (after line 115), append a new section:

```markdown
## Shopify Ecosystem

Shopify sites have a distinctive tracking architecture. In addition to standard GTM/pixel setups, Shopify loads its own analytics infrastructure and app-installed pixels via sandboxed Web Pixel iframes.

| Platform | Script URL Pattern | Cookies | JS Global | Notes |
|---|---|---|---|---|
| Shopify Web Pixels | `web-pixels@*/sandbox/modern/` (iframe src) | — | — | Sandboxed iframes that load app-installed pixels (TikTok, Google Ads, Bing, etc.) in isolated contexts. Invisible to eval script. Count iframes to estimate pixel load. |
| Shopify Trekkie | `trekkie.storefront.*.min.js` | `_shopify_s`, `_shopify_y` | — | Shopify's first-party analytics. Always present on Shopify stores. |
| Mountain.com | `px.mountain.com/st`, `dx.mountain.com/spx` | — | — | Shopify attribution/analytics platform. Sends GA4 client ID and page metadata to Mountain's servers. |
| SafeOpt | `manage.safeopt.com` | — | — | Email remarketing and identity resolution. Often installed via Shopify app. Makes HEAD requests to `/consent` endpoint. Should be disclosed in privacy policy. |
| Postscript | `sdk.postscript.io` | — | — | SMS marketing platform for Shopify. Loads SDK script loader and form handler. |
| SMSBump (Yotpo SMS) | `forms-akamai.smsbump.com`, `d18eg7dreypte5.cloudfront.net` | — | — | SMS marketing. Now part of Yotpo. Loads subscription scripts and browse-abandonment timers. |
| Recharge | `static.rechargecdn.com` | — | — | Subscription management for Shopify. Loads widget scripts for subscription product options. |

## Attribution & Multi-Touch

| Platform | Script URL Pattern | Cookies | JS Global | Notes |
|---|---|---|---|---|
| Northbeam | `j.northbeam.io` | — | — | Multi-touch attribution platform. Loads vendor script and account-specific config (`ota-sp/*.js`). |
| StackAdapt | `tags.srv.stackadapt.com/events.js` | — | — | Programmatic DSP. Fires event tracking for campaign attribution. |

## Reviews & UGC

| Platform | Script URL Pattern | Notes |
|---|---|---|
| Okendo | `cdn-static.okendo.io/reviews-widget-plus/js/okendo-reviews.js`, `d3hw6dc1ow8pp2.cloudfront.net` | Product reviews platform. Loads multiple JS modules (core, styles, translation, widget-init, star-rating, carousel, badge). |
| Videowise | `assets.videowise.com/client.js.gz`, `assets.videowise.com/vendors.js.gz` | Video commerce platform. Enables shoppable video on Shopify stores. |
```

- [ ] **Step 3: Commit**

```bash
cd ~/.claude/skills/martech-audit
git add references/pixel-signatures.md
git commit -m "docs(pixel-signatures): add Front, Shopify ecosystem, attribution, and review platforms

Adds Front chat, SafeOpt, Mountain.com, Postscript, SMSBump, Recharge,
Northbeam, StackAdapt, Okendo, Videowise, and Shopify Web Pixels/Trekkie
signatures. All discovered during getpuroair.com audit."
```

---

### Task 4: Refine double-tagging check in check_findings.py

**Files:**
- Modify: `~/.claude/skills/martech-audit/scripts/check_findings.py:34-53` (DOUBLE_TAG_GTAG_GTM finding)

The check correctly identifies double-tagging but the detail text should mention Shopify web pixels as an additional source of duplication when present.

- [ ] **Step 1: Add Shopify web pixel note to double-tagging detail**

In `check_findings.py`, update the `DOUBLE_TAG_GTAG_GTM` finding (lines 36-52). After the existing detail text (before the thirdPartyGtmIds conditional), add a conditional for Shopify web pixels:

Replace lines 34-52 with:

```python
    if ti.get("doubleTagging"):
        shopify_wp = page.get("shopifyWebPixels", {})
        shopify_note = ""
        if shopify_wp.get("detected"):
            shopify_note = (
                f" Additionally, {shopify_wp.get('count', 0)} Shopify Web Pixel sandbox(es) detected — "
                "Shopify fires its own page_view and conversion events independently of both "
                "hardcoded gtag.js and GTM, likely resulting in TRIPLE-counting, not just double."
            )
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
                + shopify_note
                + (f" (Also detected {len(ti.get('thirdPartyGtmIds', []))} third-party vendor container(s) "
                   f"loaded by other scripts: {ti.get('thirdPartyGtmIds', [])} — these are excluded from this finding.)"
                   if ti.get("thirdPartyGtmIds") else "")
            ),
            "page": page.get("url", "unknown"),
        })
```

- [ ] **Step 2: Run the checker against existing test data to verify no regressions**

```bash
cd ~/.claude/skills/martech-audit
python3 scripts/check_findings.py --dir /tmp/martech-audit/getpuroair.com/ --pretty 2>&1 | head -30
```

Expected: `DOUBLE_TAG_GTAG_GTM` finding still appears. It won't have the Shopify note yet because the homepage.json doesn't include `shopifyWebPixels` (the eval hasn't been re-run). But it shouldn't error.

- [ ] **Step 3: Commit**

```bash
cd ~/.claude/skills/martech-audit
git add scripts/check_findings.py
git commit -m "fix(check_findings): add Shopify web pixel triple-tagging note to double-tag check

When shopifyWebPixels.detected is true, the detail text now warns about
triple-counting from hardcoded gtag + GTM + Shopify Web Pixel sandboxes."
```
