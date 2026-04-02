// Canonical SEO eval script — single source of truth.
// SKILL.md references this file; do not duplicate inline.
() => {
  const r = {};
  r.url = location.href;

  // HTTP status from Navigation Timing API
  try {
    const nav = performance.getEntriesByType('navigation')[0];
    r.httpStatus = nav ? nav.responseStatus || null : null;
  } catch (e) { r.httpStatus = null; }

  // --- Title ---
  r.title = document.title || null;
  r.titleLength = r.title ? r.title.length : 0;
  r.titleTruncated = r.titleLength > 60;

  // --- Meta Description ---
  r.description = (() => {
    const el = document.querySelector('meta[name="description"]');
    return el ? el.content : null;
  })();
  r.descriptionLength = r.description ? r.description.length : 0;
  r.descriptionTruncated = r.descriptionLength > 160;

  // --- Canonical ---
  r.canonical = (() => {
    const el = document.querySelector('link[rel="canonical"]');
    if (!el) return { url: null, isSelfReferencing: false, mismatch: false };
    const href = el.href;
    // Normalize: strip trailing slash and fragment for comparison
    const normalize = u => {
      try {
        const p = new URL(u);
        // Strip common tracking params before comparing — canonicals
        // correctly omit UTM/tracking params from the URL
        const params = new URLSearchParams(p.search);
        ['utm_source','utm_medium','utm_campaign','utm_term','utm_content',
         'fbclid','gclid','msclkid','ref','source'].forEach(k => params.delete(k));
        const cleanSearch = params.toString() ? '?' + params.toString() : '';
        return p.origin + p.pathname.replace(/\/$/, '') + cleanSearch;
      } catch (e) { return u; }
    };
    const normCanonical = normalize(href);
    const normCurrent = normalize(location.href);
    // If canonical has no query params but page URL does, the canonical is
    // intentionally stripping tracking params — compare paths only
    const canonHasParams = new URL(href).search.length > 1;
    const currentHasParams = new URL(location.href).search.length > 1;
    const pathOnly = u => { try { const p = new URL(u); return p.origin + p.pathname.replace(/\/$/, ''); } catch(e) { return u; } };
    const isSelf = normCanonical === normCurrent ||
      (!canonHasParams && currentHasParams && pathOnly(href) === pathOnly(location.href));
    return {
      url: href,
      isSelfReferencing: isSelf,
      mismatch: !isSelf,
    };
  })();

  // --- Robots Meta ---
  r.robots = (() => {
    const el = document.querySelector('meta[name="robots"]');
    const content = el ? el.content : null;
    return {
      meta: content,
      hasNoindex: content ? content.toLowerCase().includes('noindex') : false,
      hasNofollow: content ? content.toLowerCase().includes('nofollow') : false,
    };
  })();

  // --- Headings ---
  r.headings = (() => {
    const all = Array.from(document.querySelectorAll('h1, h2, h3, h4, h5, h6'));
    const h1s = all.filter(h => h.tagName === 'H1');
    const h2s = all.filter(h => h.tagName === 'H2');
    const h3s = all.filter(h => h.tagName === 'H3');

    // Check heading hierarchy: levels should not skip (e.g., H1 -> H3 with no H2)
    let hierarchyValid = true;
    let prevLevel = 0;
    for (const h of all) {
      const level = parseInt(h.tagName[1], 10);
      if (prevLevel > 0 && level > prevLevel + 1) {
        hierarchyValid = false;
        break;
      }
      prevLevel = level;
    }

    return {
      h1Count: h1s.length,
      h1Texts: h1s.map(h => h.textContent.trim().substring(0, 200)),
      h2Count: h2s.length,
      h2Texts: h2s.map(h => h.textContent.trim().substring(0, 200)),
      h3Count: h3s.length,
      totalHeadings: all.length,
      headingHierarchyValid: hierarchyValid,
      outline: all.slice(0, 30).map(h => ({
        level: parseInt(h.tagName[1], 10),
        text: h.textContent.trim().substring(0, 120),
      })),
    };
  })();

  // --- Images ---
  r.images = (() => {
    const imgs = Array.from(document.querySelectorAll('img'));
    const withoutAlt = imgs.filter(i => !i.hasAttribute('alt'));
    const emptyAlt = imgs.filter(i => i.hasAttribute('alt') && i.alt.trim() === '');
    const lazyLoaded = imgs.filter(i =>
      i.loading === 'lazy' ||
      i.hasAttribute('data-src') ||
      i.hasAttribute('data-lazy-src') ||
      i.classList.contains('lazyload')
    );
    const withSrcset = imgs.filter(i => i.hasAttribute('srcset') || i.closest('picture'));
    // Exclude SVGs — they are vector, don't cause CLS, and don't need srcset
    // Parse pathname to handle query strings (e.g., logo.svg?v=123)
    const isSvg = i => {
      try {
        const src = i.src || i.currentSrc || '';
        if (!src) return false;
        if (src.startsWith('data:image/svg')) return true;
        return new URL(src, location.href).pathname.toLowerCase().endsWith('.svg');
      } catch (e) { return false; }
    };

    const withoutDimensions = imgs.filter(i =>
      !isSvg(i) &&
      !i.hasAttribute('width') && !i.hasAttribute('height') &&
      !i.style.width && !i.style.height &&
      // Exclude tiny icons (< 50px) — they don't cause meaningful CLS
      (i.naturalWidth > 50 || !i.complete)
    );

    // Large raster images without srcset (potential responsive issue)
    // SVGs excluded: they are resolution-independent and scale natively
    const largeImages = imgs.filter(i => {
      if (isSvg(i)) return false;
      // Skip images with no src (lazy-loaded placeholders not yet populated)
      if (!i.src && !i.currentSrc) return false;
      const w = i.naturalWidth || i.width || 0;
      const h = i.naturalHeight || i.height || 0;
      return w * h > 90000 && !i.hasAttribute('srcset') && !i.closest('picture');
    }).map(i => ({
      src: (i.src || i.currentSrc || '').substring(0, 200),
      width: i.naturalWidth || i.width,
      height: i.naturalHeight || i.height,
    }));

    return {
      totalImages: imgs.length,
      imagesWithoutAlt: withoutAlt.length,
      imagesWithEmptyAlt: emptyAlt.length,
      lazyLoadedCount: lazyLoaded.length,
      hasResponsiveImages: withSrcset.length > 0,
      responsiveImageCount: withSrcset.length,
      imagesWithoutDimensions: withoutDimensions.length,
      largeImages: largeImages.slice(0, 10),
    };
  })();

  // --- Links ---
  r.links = (() => {
    const anchors = Array.from(document.querySelectorAll('a[href]'));
    const currentHost = location.hostname;
    const internal = [];
    const external = [];
    const broken = [];
    const nofollow = [];
    const externalDomains = new Set();

    for (const a of anchors) {
      const href = a.href;
      const rel = (a.getAttribute('rel') || '').toLowerCase();

      // Broken anchors: href="#" or empty effective href
      const rawHref = a.getAttribute('href') || '';
      const trimmedHref = rawHref.trim().toLowerCase();
      if (rawHref === '#' || rawHref === '' || trimmedHref.startsWith('javascript:')) {
        broken.push({ href: rawHref, text: a.textContent.trim().substring(0, 80) });
        continue;
      }

      try {
        const u = new URL(href);
        // Skip non-http schemes (mailto:, tel:, ftp:, etc.)
        if (u.protocol !== 'http:' && u.protocol !== 'https:') continue;
        if (u.hostname === currentHost || u.hostname.endsWith('.' + currentHost)) {
          internal.push(href);
        } else {
          external.push(href);
          externalDomains.add(u.hostname);
        }
      } catch (e) {
        // Relative URL or malformed — treat as internal
        internal.push(href);
      }

      if (rel.includes('nofollow')) {
        nofollow.push({ href: href.substring(0, 200), text: a.textContent.trim().substring(0, 80) });
      }
    }

    return {
      totalLinks: anchors.length,
      internalLinkCount: internal.length,
      externalLinkCount: external.length,
      brokenAnchors: broken.slice(0, 20),
      nofollowLinks: nofollow.slice(0, 20),
      externalDomains: Array.from(externalDomains).sort(),
    };
  })();

  // --- Schema / JSON-LD ---
  r.schema = (() => {
    const scripts = Array.from(document.querySelectorAll('script[type="application/ld+json"]'));
    const jsonLdRaw = [];
    const jsonLdTypes = [];

    for (const s of scripts) {
      try {
        const parsed = JSON.parse(s.textContent);
        jsonLdRaw.push(parsed);
        // Handle @graph arrays and top-level arrays (both valid JSON-LD)
        const items = Array.isArray(parsed) ? parsed
          : parsed['@graph'] ? parsed['@graph'] : [parsed];
        for (const item of items) {
          if (item['@type']) {
            const types = Array.isArray(item['@type']) ? item['@type'] : [item['@type']];
            jsonLdTypes.push(...types);
          }
        }
      } catch (e) {
        jsonLdRaw.push({ _parseError: true, raw: s.textContent.substring(0, 500) });
      }
    }

    // Microdata
    const microdataEls = Array.from(document.querySelectorAll('[itemtype]'));
    const microdataTypes = microdataEls.map(el => {
      const t = el.getAttribute('itemtype');
      return t ? t.replace('http://schema.org/', '').replace('https://schema.org/', '') : null;
    }).filter(Boolean);

    // Normalize URL-form @type values (e.g., "https://schema.org/Organization" -> "organization")
    const normalizeType = t => t.replace(/^https?:\/\/schema\.org\//i, '').toLowerCase();
    const typeSet = new Set(jsonLdTypes.map(normalizeType));

    return {
      jsonLdCount: scripts.length,
      jsonLdTypes: jsonLdTypes,
      jsonLdRaw: jsonLdRaw,
      microdataTypes: [...new Set(microdataTypes)],
      hasOrganization: typeSet.has('organization') || typeSet.has('localbusiness'),
      hasWebSite: typeSet.has('website'),
      hasBreadcrumb: typeSet.has('breadcrumblist'),
      hasArticle: typeSet.has('article') || typeSet.has('blogposting') || typeSet.has('newsarticle'),
      hasFaqPage: typeSet.has('faqpage'),
      hasProduct: typeSet.has('product'),
      hasService: typeSet.has('service'),
    };
  })();

  // --- Open Graph Tags ---
  r.og = (() => {
    const get = prop => {
      const el = document.querySelector(`meta[property="${prop}"]`);
      return el ? el.content : null;
    };
    return {
      title: get('og:title'),
      description: get('og:description'),
      image: get('og:image'),
      url: get('og:url'),
      type: get('og:type'),
      siteName: get('og:site_name'),
      imageWidth: get('og:image:width'),
      imageHeight: get('og:image:height'),
      imageType: get('og:image:type'),
    };
  })();

  // --- Twitter Cards ---
  r.twitter = (() => {
    const get = name => {
      const el = document.querySelector(`meta[name="${name}"]`);
      return el ? el.content : null;
    };
    return {
      card: get('twitter:card'),
      title: get('twitter:title'),
      description: get('twitter:description'),
      image: get('twitter:image'),
      site: get('twitter:site'),
      creator: get('twitter:creator'),
    };
  })();

  // --- Hreflang ---
  r.hreflang = (() => {
    const links = Array.from(document.querySelectorAll('link[rel="alternate"][hreflang]'));
    const tags = links.map(l => ({
      lang: l.hreflang,
      href: l.href,
    }));
    // Check if current page has a self-referencing hreflang
    // Normalize by stripping query params — hreflang hrefs should be canonical-clean
    const normHreflang = u => {
      try { const p = new URL(u); return (p.origin + p.pathname).replace(/\/$/, ''); }
      catch (e) { return u.replace(/\/$/, ''); }
    };
    const currentNorm = normHreflang(location.href);
    const hasSelf = tags.some(t => normHreflang(t.href) === currentNorm);
    return {
      tags: tags,
      count: tags.length,
      hasSelfHreflang: hasSelf,
    };
  })();

  // --- Resource Hints ---
  r.resourceHints = (() => {
    const collect = rel => Array.from(document.querySelectorAll(`link[rel="${rel}"]`))
      .map(l => l.href).filter(Boolean);
    return {
      preconnects: collect('preconnect'),
      prefetches: collect('prefetch'),
      preloads: collect('preload'),
      dnsPrefetch: collect('dns-prefetch'),
    };
  })();

  // --- Core Web Vitals Indicators ---
  r.cwvIndicators = (() => {
    // Images without explicit dimensions (CLS risk)
    // Exclude SVGs — they are vector and don't cause layout shift
    const imgs = Array.from(document.querySelectorAll('img'));
    const isSvg = i => {
      try {
        const src = i.src || i.currentSrc || '';
        if (!src) return false;
        if (src.startsWith('data:image/svg')) return true;
        return new URL(src, location.href).pathname.toLowerCase().endsWith('.svg');
      } catch (e) { return false; }
    };
    const noDimensions = imgs.filter(i =>
      !isSvg(i) &&
      !i.hasAttribute('width') && !i.hasAttribute('height') &&
      !i.style.width && !i.style.height &&
      // Exclude tiny/icon images
      (i.naturalWidth > 50 || !i.complete)
    ).length;

    // LCP candidate heuristic — find largest visible element
    let lcpCandidate = null;
    try {
      // Check for hero images or large above-fold elements
      const heroImg = document.querySelector('img[fetchpriority="high"]') ||
        document.querySelector('[class*="hero"] img') ||
        document.querySelector('main img:first-of-type');
      if (heroImg) {
        lcpCandidate = {
          tag: 'img',
          src: (heroImg.src || heroImg.currentSrc || '').substring(0, 200),
          width: heroImg.naturalWidth || heroImg.width,
          height: heroImg.naturalHeight || heroImg.height,
          hasFetchPriority: heroImg.fetchPriority === 'high',
        };
      }
    } catch (e) { /* best effort */ }

    // Viewport meta
    const vpEl = document.querySelector('meta[name="viewport"]');
    const vpContent = vpEl ? vpEl.content : null;

    return {
      imagesWithoutDimensions: noDimensions,
      lcpCandidate: lcpCandidate,
      viewportMeta: vpContent,
      hasViewportWidth: vpContent ? vpContent.includes('width=') : false,
    };
  })();

  // --- Page Weight / Resources ---
  r.resources = (() => {
    const scripts = Array.from(document.querySelectorAll('script'));
    const stylesheets = Array.from(document.querySelectorAll('link[rel="stylesheet"]'));
    const inlineStyles = Array.from(document.querySelectorAll('style'));

    // Render-blocking: scripts in <head> without async/defer
    // Exclude type="module" — ES modules are deferred by spec
    const renderBlocking = scripts.filter(s =>
      s.parentElement && s.parentElement.tagName === 'HEAD' &&
      s.src &&
      !s.async && !s.defer &&
      s.type !== 'application/ld+json' &&
      s.type !== 'application/json' &&
      s.type !== 'module'
    ).map(s => s.src.substring(0, 200));

    // Render-blocking stylesheets (no media query or media="all")
    const blockingCSS = stylesheets.filter(l => {
      const media = l.media;
      return !media || media === 'all' || media === '';
    }).length;

    return {
      totalScripts: scripts.filter(s => s.src || s.textContent.trim().length > 10).length,
      externalScripts: scripts.filter(s => s.src).length,
      inlineScriptCount: scripts.filter(s => !s.src && s.textContent.trim().length > 10).length,
      totalStylesheets: stylesheets.length,
      inlineStyleCount: inlineStyles.length,
      renderBlockingScripts: renderBlocking.slice(0, 10),
      renderBlockingScriptCount: renderBlocking.length,
      blockingCSSCount: blockingCSS,
    };
  })();

  // --- Accessibility Basics ---
  r.accessibility = (() => {
    const htmlLang = document.documentElement.lang || null;

    // Skip link
    const skipLink = document.querySelector(
      'a[href="#content"], a[href="#main"], a[href="#main-content"], a.skip-link, a.skip-to-content'
    );

    // Forms without proper labels
    const forms = Array.from(document.querySelectorAll('form'));
    const inputsWithoutLabels = Array.from(document.querySelectorAll(
      'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="reset"]), textarea, select'
    )).filter(input => {
      // Check for associated label
      if (input.id && document.querySelector(`label[for="${input.id}"]`)) return false;
      if (input.closest('label')) return false;
      if (input.getAttribute('aria-label') || input.getAttribute('aria-labelledby')) return false;
      if (input.placeholder) return false; // Not ideal but not "unlabeled"
      return true;
    }).length;

    return {
      htmlLang: htmlLang,
      hasSkipLink: !!skipLink,
      formCount: forms.length,
      inputsWithoutLabels: inputsWithoutLabels,
    };
  })();

  // --- Security ---
  r.security = (() => {
    const isHttps = location.protocol === 'https:';

    // Check for mixed content: http:// resources on an https page
    let mixedContentCount = 0;
    if (isHttps) {
      // Only check actually-fetched resources — exclude canonical, preconnect,
      // dns-prefetch, alternate, etc. which are not loaded as page resources
      // Extract individual URLs from srcset attributes (e.g., "http://img.jpg 1x, http://img2.jpg 2x")
      const srcsetUrls = Array.from(document.querySelectorAll('img[srcset], source[srcset]'))
        .flatMap(e => (e.srcset || '').split(',').map(s => s.trim().split(/\s+/)[0]).filter(Boolean));
      const resourceEls = [
        ...Array.from(document.querySelectorAll('script[src]')).map(e => e.src),
        ...Array.from(document.querySelectorAll('link[rel="stylesheet"][href]')).map(e => e.href),
        ...Array.from(document.querySelectorAll('img[src]')).map(e => e.src),
        ...Array.from(document.querySelectorAll('iframe[src]')).map(e => e.src),
        ...Array.from(document.querySelectorAll('video[src], audio[src], source[src]')).map(e => e.src),
        ...srcsetUrls,
      ];
      mixedContentCount = resourceEls.filter(src =>
        src && src.startsWith('http://') && !src.startsWith('http://localhost')
      ).length;
    }

    return {
      isHttps: isHttps,
      hasMixedContent: mixedContentCount > 0,
      mixedContentCount: mixedContentCount,
    };
  })();

  // --- Content Metrics ---
  r.content = (() => {
    // Word count from main content area (excludes nav/footer/sidebar)
    const mainEl = document.querySelector('main, [role="main"], article') || document.body;
    const bodyText = mainEl ? mainEl.innerText : '';
    const words = bodyText.split(/\s+/).filter(w => w.length > 0);

    // Check for pagination rel links
    const hasNext = !!document.querySelector('link[rel="next"]');
    const hasPrev = !!document.querySelector('link[rel="prev"]');

    return {
      wordCount: words.length,
      hasPaginationRel: hasNext || hasPrev,
      paginationNext: hasNext ? document.querySelector('link[rel="next"]').href : null,
      paginationPrev: hasPrev ? document.querySelector('link[rel="prev"]').href : null,
    };
  })();

  // --- Structured Data Validation (basic field checks) ---
  r.schemaValidation = (() => {
    const issues = [];
    try {
      const scripts = Array.from(document.querySelectorAll('script[type="application/ld+json"]'));
      for (const s of scripts) {
        try {
          const data = JSON.parse(s.textContent);
          // Handle @graph arrays and top-level arrays (both valid JSON-LD)
          const items = Array.isArray(data) ? data
            : data['@graph'] ? data['@graph'] : [data];
          for (const item of items) {
            const rawType = item['@type'];
            if (!rawType) continue;
            // Normalize @type to array to handle {"@type":["Article","NewsArticle"]}
            const types = Array.isArray(rawType) ? rawType : [rawType];
            // Normalize URL-form @type (e.g., "https://schema.org/Organization" -> "Organization")
            const normType = v => v.replace(/^https?:\/\/schema\.org\//i, '');
            const hasType = t => types.some(raw => normType(raw) === t);
            const typeLabel = types.join(', ');

            // Check @context — JSON-LD without it is invalid
            const context = item['@context'] || data['@context'];
            if (!context || (typeof context === 'string' &&
                !context.includes('schema.org'))) {
              issues.push({ type: typeLabel, field: '@context', message: `${typeLabel} missing or invalid @context (must be schema.org)` });
            }

            // Organization: should have name and url
            if (hasType('Organization') || hasType('LocalBusiness')) {
              if (!item.name) issues.push({ type: typeLabel, field: 'name', message: 'Organization missing name' });
              if (!item.url) issues.push({ type: typeLabel, field: 'url', message: 'Organization missing url' });
            }

            // Article: should have headline, author, datePublished
            if (hasType('Article') || hasType('BlogPosting') || hasType('NewsArticle')) {
              if (!item.headline) issues.push({ type: typeLabel, field: 'headline', message: 'Article missing headline' });
              if (!item.author) issues.push({ type: typeLabel, field: 'author', message: 'Article missing author' });
              if (!item.datePublished) issues.push({ type: typeLabel, field: 'datePublished', message: 'Article missing datePublished' });
              if (!item.image) issues.push({ type: typeLabel, field: 'image', message: 'Article missing image' });
            }

            // FAQPage: should have mainEntity
            if (hasType('FAQPage')) {
              if (!item.mainEntity || (Array.isArray(item.mainEntity) && item.mainEntity.length === 0)) {
                issues.push({ type: typeLabel, field: 'mainEntity', message: 'FAQPage missing questions' });
              }
            }

            // Product: should have name and offers
            if (hasType('Product')) {
              if (!item.name) issues.push({ type: typeLabel, field: 'name', message: 'Product missing name' });
              if (!item.offers) issues.push({ type: typeLabel, field: 'offers', message: 'Product missing offers/pricing' });
            }

            // BreadcrumbList: should have itemListElement
            if (hasType('BreadcrumbList')) {
              if (!item.itemListElement || (Array.isArray(item.itemListElement) && item.itemListElement.length === 0)) {
                issues.push({ type: typeLabel, field: 'itemListElement', message: 'BreadcrumbList has no items' });
              }
            }
          }
        } catch (e) {
          issues.push({ type: 'unknown', field: '_parse', message: 'Invalid JSON-LD: ' + e.message });
        }
      }
    } catch (e) { /* best effort */ }
    return { issues: issues };
  })();

  // --- Meta Tags (additional) ---
  r.meta = (() => {
    const charset = document.characterSet || document.charset || null;
    const author = document.querySelector('meta[name="author"]')?.content || null;
    const generator = document.querySelector('meta[name="generator"]')?.content || null;
    const themeColor = document.querySelector('meta[name="theme-color"]')?.content || null;

    // Check for Google site verification
    const googleVerification = document.querySelector('meta[name="google-site-verification"]')?.content || null;
    const bingVerification = document.querySelector('meta[name="msvalidate.01"]')?.content || null;

    return {
      charset: charset,
      author: author,
      generator: generator,
      themeColor: themeColor,
      googleVerification: googleVerification,
      bingVerification: bingVerification,
    };
  })();

  // --- SPA Framework Detection ---
  r.spaFramework = (() => {
    try {
      return {
        nextjs: !!document.querySelector('#__next') || typeof __NEXT_DATA__ !== 'undefined',
        nuxt: !!document.querySelector('#__nuxt') || typeof __NUXT__ !== 'undefined',
        react: !!document.querySelector('[data-reactroot], #root[data-react-helmet]'),
        angular: !!document.querySelector('[ng-app], [ng-version]'),
        gatsby: !!document.querySelector('#___gatsby'),
        hugo: !!(document.querySelector('meta[name="generator"]')?.content || '').toLowerCase().includes('hugo'),
        wordpress: !!(document.querySelector('meta[name="generator"]')?.content || '').toLowerCase().includes('wordpress'),
      };
    } catch (e) { return {}; }
  })();

  return r;
}
