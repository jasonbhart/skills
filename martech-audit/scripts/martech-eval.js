// Canonical martech eval script — single source of truth.
// SKILL.md references this file; do not duplicate inline.
//
// IMPORTANT LIMITATION: This script runs at page-load time and captures the
// dataLayer snapshot at that moment. Interaction-triggered events (CTA clicks,
// form submissions, scroll depth, booking conversions) will NOT appear in the
// dataLayer at page load — they only fire on user action. A dataLayer showing
// only system events (gtm.js, gtm.dom, gtm.load) does NOT mean the site lacks
// custom event tracking. Check the page source for event listener code
// (addEventListener, dataLayer.push inside click/scroll/message handlers) before
// reporting "no custom events" as a finding.
//
// Similarly, pixels loaded by GTM at runtime (not hardcoded in HTML) will not
// appear in allScriptText. Use network request evidence (list_network_requests)
// to confirm pixel presence for GTM-managed tags.
//
// Shopify web pixel sandboxes are a similar blind spot — Shopify loads pixels
// (TikTok, Google Ads, Bing, Reddit, etc.) inside isolated <iframe> elements
// that the parent page's JS cannot access. The shopifyWebPixels field flags
// when these sandboxes are present so the orchestrator knows to rely on
// network evidence for pixel detection on Shopify sites.
() => {
  const r = {};
  r.url = location.href;

  // Script deferral detection — WP Rocket, Partytown, Flying Scripts, etc.
  // These systems delay ALL JS until user interaction, making runtime globals
  // (gtag, dataLayer, google_tag_manager) appear absent even when tracking is
  // fully configured. Detecting deferral prevents false "no tracking" findings.
  r.scriptDeferral = (() => {
    const allInlineText = Array.from(document.querySelectorAll('script')).map(s => s.innerHTML || '').join(' ');
    const rocketLazy = allInlineText.includes('RocketLazyLoadScripts') ||
      document.querySelectorAll('script[data-rocket-src]').length > 0 ||
      allInlineText.includes('rocketlazyloadscript');
    const partytown = document.querySelectorAll('script[type="text/partytown"]').length > 0 ||
      allInlineText.includes('partytown');
    const flyingScripts = Array.from(document.querySelectorAll('script')).some(s =>
      s.hasAttribute('data-flying-scripts-id') || (s.className || '').includes('fvm-'));
    const perfmatters = document.querySelectorAll('script[data-perfmatters-type]').length > 0;
    const litespeed = allInlineText.includes('litespeed') && allInlineText.includes('delay');
    const detected = rocketLazy || partytown || flyingScripts || perfmatters || litespeed;
    const system = rocketLazy ? 'wp-rocket' : partytown ? 'partytown' : flyingScripts ? 'flying-scripts' :
      perfmatters ? 'perfmatters' : litespeed ? 'litespeed' : null;
    const deferredScriptCount = document.querySelectorAll(
      'script[data-rocket-src]:not([src]), script[type="text/partytown"], script[type="rocketlazyloadscript"], script[data-perfmatters-type]'
    ).length;
    return { detected, system, deferredScriptCount };
  })();

  // GTM and GA4
  r.gtmObject = (() => {
    try {
      return typeof google_tag_manager !== 'undefined' && google_tag_manager &&
        typeof google_tag_manager === 'object' ? Object.keys(google_tag_manager) : [];
    } catch(e) { return []; }
  })();
  r.gtagExists = typeof gtag === 'function';

  const allScriptEls = Array.from(document.querySelectorAll('script'));
  const allScriptText = allScriptEls.map(s => {
    const src = s.src || s.getAttribute('data-rocket-src') || s.getAttribute('data-src') || '';
    // Decode base64 data: URIs from WP Rocket deferred scripts — these contain
    // the actual GTM/GA4/pixel code that won't be in innerHTML or src
    let decodedContent = '';
    if (src.startsWith('data:') && src.includes('base64,')) {
      try { decodedContent = atob(src.split('base64,')[1]); } catch(e) {}
    }
    return src + ' ' + (s.innerHTML || '').substring(0, 2000) + ' ' + decodedContent.substring(0, 2000);
  }).join(' ');
  const gtagInstalls = allScriptText.match(/G-[A-Z0-9]{4,12}/g) || [];
  const gtmInstalls = allScriptText.match(/GTM-[A-Z0-9]{4,12}/g) || [];
  // GT- prefix: newer Google Tag IDs (from Google Site Kit, tag.google.com).
  // These load gtag.js like GA4 IDs but are a different ID format.
  const googleTagInstalls = allScriptText.match(/GT-[A-Z0-9]{4,12}/g) || [];

  // First-party vs third-party container classification
  const noscriptHtml = Array.from(document.querySelectorAll('noscript')).map(ns => ns.innerHTML).join(' ');
  const noscriptGtmIds = [...new Set((noscriptHtml.match(/GTM-[A-Z0-9]{4,12}/g) || []))];
  const topLevelScripts = Array.from(document.querySelectorAll('head > script, body > script'));
  const topLevelText = topLevelScripts.map(s => {
    const src = s.src || s.getAttribute('data-rocket-src') || s.getAttribute('data-src') || '';
    return src + ' ' + s.innerHTML;
  }).join(' ');
  const topLevelGtmIds = [...new Set((topLevelText.match(/GTM-[A-Z0-9]{4,12}/g) || []))];
  const topLevelGa4Ids = [...new Set((topLevelText.match(/G-[A-Z0-9]{4,12}/g) || []))];
  const allGtmIds = [...new Set(gtmInstalls)];
  const runtimeGtmIds = r.gtmObject.filter(k => /^GTM-[A-Z0-9]{4,12}$/.test(k));
  const domDetectedGtmIds = [...new Set([...noscriptGtmIds, ...topLevelGtmIds])];
  const runtimeOnlyIds = runtimeGtmIds.filter(id => !domDetectedGtmIds.includes(id));
  const promotedRuntimeIds = domDetectedGtmIds.length === 0 ? runtimeOnlyIds : [];
  const firstPartyGtmIds = [...new Set([...domDetectedGtmIds, ...promotedRuntimeIds])];
  const thirdPartyGtmIds = allGtmIds.filter(id => !firstPartyGtmIds.includes(id));
  const allGa4Ids = [...new Set(gtagInstalls)];
  const thirdPartyGa4Ids = allGa4Ids.filter(id => !topLevelGa4Ids.includes(id));
  const firstPartyHardcodedGtag = topLevelScripts.some(
    s => s.src && s.src.includes('gtag/js?id=G-') && !s.src.includes('&cx=c')
  );

  // Detect hardcoded gtag.js loading GT- (Google Tag) IDs — these are newer
  // tag IDs from Google Site Kit / tag.google.com and indicate a separate
  // tagging installation that may conflict with GTM-managed GA4.
  const allGoogleTagIds = [...new Set(googleTagInstalls)];
  const firstPartyHardcodedGoogleTag = topLevelScripts.some(
    s => s.src && s.src.includes('gtag/js?id=GT-') && !s.src.includes('&cx=c')
  );

  r.tagInstallations = {
    ga4Ids: allGa4Ids, gtmIds: allGtmIds,
    googleTagIds: allGoogleTagIds,
    firstPartyGtmIds, firstPartyGa4Ids: topLevelGa4Ids,
    thirdPartyGtmIds, thirdPartyGa4Ids,
    hardcodedGtag: firstPartyHardcodedGtag,
    hardcodedGoogleTag: firstPartyHardcodedGoogleTag,
    multipleGtmContainers: firstPartyGtmIds.length > 1,
    // Double-tagging: hardcoded gtag.js (G- or GT-) alongside GTM
    doubleTagging: (firstPartyHardcodedGtag || firstPartyHardcodedGoogleTag) && firstPartyGtmIds.length > 0,
  };

  // Server-side GTM detection — catches Stape, Addingwell, and custom sGTM setups.
  // Key insight: sGTM replaces the GTM snippet's script src domain from
  // www.googletagmanager.com to a first-party domain. Stape also randomizes the
  // script filename (not gtm.js) and base64-encodes the container ID in URL params.
  r.serverSideGtm = (() => {
    // Find the GTM bootstrap script — it pushes gtm.start to dataLayer and creates
    // a script element. Check if its src points to a non-Google domain.
    const gtmBootstrap = topLevelScripts.find(s => {
      const text = s.innerHTML || '';
      return text.includes('gtm.start') && text.includes('gtm.js');
    });
    if (!gtmBootstrap) return { detected: false };

    const text = gtmBootstrap.innerHTML || '';
    // Extract the script src URL from the GTM snippet
    // Standard: j.src='https://www.googletagmanager.com/gtm.js?id='+i
    // Stape: j.src='https://tags.domain.com/xZfzofixhj.js?'+i
    const srcMatch = text.match(/\.src\s*=\s*['"]([^'"]+)['"]/);
    if (!srcMatch) return { detected: false };

    const loaderUrl = srcMatch[1];
    const isFirstParty = !loaderUrl.includes('googletagmanager.com') &&
                         !loaderUrl.includes('google-analytics.com');
    if (!isFirstParty) return { detected: false };

    // Extract the sGTM domain
    let sgtmDomain = null;
    try { sgtmDomain = new URL(loaderUrl.startsWith('//') ? 'https:' + loaderUrl : loaderUrl).hostname; }
    catch(e) { sgtmDomain = loaderUrl.split('/')[2] || null; }

    // Check for base64-encoded container ID (Stape pattern).
    // Stape encodes "id=GTM-XXXX" as base64 in a URL parameter named fX or st.
    // The param may be URL-encoded (%3D for =) and can appear either in the
    // .src URL string or in the IIFE call arguments (5th param).
    let decodedContainerId = null;
    const fxMatch = text.match(/fX=([A-Za-z0-9+/%]+={0,2})/);
    if (fxMatch) {
      try {
        const decoded = decodeURIComponent(fxMatch[1]);
        decodedContainerId = atob(decoded);
      } catch(e) {
        try { decodedContainerId = atob(fxMatch[1]); } catch(e2) {}
      }
    }

    // Check for obfuscated loader filename (not gtm.js)
    const isObfuscated = !loaderUrl.includes('gtm.js');

    return {
      detected: true,
      domain: sgtmDomain,
      loaderUrl: loaderUrl.substring(0, 120),
      obfuscatedLoader: isObfuscated,
      decodedContainerId: decodedContainerId,
      // Stape-specific: randomized filename + base64 params
      isStapePattern: isObfuscated && !!fxMatch,
    };
  })();

  // DataLayer
  r.dataLayer = window.dataLayer ? window.dataLayer.map(item => {
    try { return JSON.parse(JSON.stringify(item)); }
    catch(e) { return { event: item.event || 'unparseable' }; }
  }) : [];

  r.dataLayerQuality = {
    totalPushes: window.dataLayer ? window.dataLayer.length : 0,
    piiDetected: window.dataLayer ? (() => {
      let dl;
      try { dl = JSON.stringify(window.dataLayer); }
      catch(e) { dl = window.dataLayer.map(i => { try { return JSON.stringify(i); } catch(e2) { return ''; } }).join(' '); }
      return {
        hasEmails: /[a-zA-Z0-9._%+-]{3,}@(?!\dx\.)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/.test(dl),
        hasPhoneNumbers: /\b\d{3}[-.]\d{3}[-.]?\d{4}\b/.test(dl),
        suspiciousKeys: window.dataLayer.flatMap(item =>
          Object.keys(item || {}).filter(k =>
            /^(email|e_mail|phone|telephone|first.?name|last.?name|full.?name|address|street|ssn|password|credit.?card)/i.test(k)
          )
        ),
      };
    })() : null,
    ecommerceIssues: window.dataLayer ? window.dataLayer.filter(item =>
      item && item.event === 'purchase'
    ).map(item => ({
      hasTransactionId: !!(item.ecommerce?.transaction_id || item.transaction_id),
      hasCurrency: !!(item.ecommerce?.currency || item.currency),
      hasValue: (item.ecommerce?.value !== undefined && item.ecommerce?.value !== null)
        || (item.value !== undefined && item.value !== null),
      hasItems: Array.isArray(item.ecommerce?.items || item.items),
    })) : [],
    events: window.dataLayer ? [...new Set(window.dataLayer.filter(i => i && i.event).map(i => i.event))] : [],
    // Event naming consistency — detect mixed conventions in custom events.
    // Excludes system events AND known vendor-pushed events (Clearbit, Demandbase,
    // 6sense, Drift, Intercom, etc.) whose naming the site owner can't control.
    eventNamingConsistency: (() => {
      const systemPrefixes = ['gtm.', 'gtm_consent', 'optimize.', 'consent'];
      const vendorPatterns = [
        /^(6si_|_6si)/i, /^demandbase/i, /^clearbit/i, /^drift/i, /^intercom/i,
        /^qualified/i, /^hubspot/i, /^hs_/i, /^hbspt/i, /^klaviyo/i,
        /^hotjar/i, /^hj[._]/, /^fullstory/i, /^fs[._]/, /^heap/i,
        /^segment/i, /^amplitude/i, /^mixpanel/i, /^posthog/i,
        /^chat_widget/, /^message_/, /^Leadfeeder/i, /^rb2b/i, /^warmly/i,
        /^cookie/i, /^OneTrust/i, /^Osano/i, /^Cookiebot/i,
      ];
      const customEvents = (window.dataLayer || [])
        .filter(i => i && i.event
          && !systemPrefixes.some(p => i.event.startsWith(p))
          && !vendorPatterns.some(p => p.test(i.event)))
        .map(i => i.event);
      if (customEvents.length < 2) return { checked: false, reason: 'too_few_events' };
      const unique = [...new Set(customEvents)];
      const hasSnakeCase = unique.some(e => /^[a-z][a-z0-9]*(_[a-z0-9]+)+$/.test(e));
      const hasCamelCase = unique.some(e => /^[a-z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]*$/.test(e));
      const hasSpaces = unique.some(e => /\s/.test(e));
      const hasDashes = unique.some(e => /^[a-z][a-z0-9]*(-[a-z0-9]+)+$/.test(e));
      const formats = [];
      if (hasSnakeCase) formats.push('snake_case');
      if (hasCamelCase) formats.push('camelCase');
      if (hasSpaces) formats.push('spaces');
      if (hasDashes) formats.push('kebab-case');
      const examples = {};
      unique.forEach(e => {
        if (/^[a-z][a-z0-9]*(_[a-z0-9]+)+$/.test(e) && !examples.snake_case) examples.snake_case = e;
        else if (/^[a-z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]*$/.test(e) && !examples.camelCase) examples.camelCase = e;
        else if (/\s/.test(e) && !examples.spaces) examples.spaces = e;
        else if (/^[a-z][a-z0-9]*(-[a-z0-9]+)+$/.test(e) && !examples['kebab-case']) examples['kebab-case'] = e;
      });
      return {
        checked: true,
        mixedFormats: formats.length > 1,
        formats,
        examples,
        totalCustomEvents: unique.length,
      };
    })(),
    // E-commerce funnel completeness — detect which standard GA4 ecommerce events fire
    ecommerceFunnel: (() => {
      const dl = window.dataLayer || [];
      const events = dl.filter(i => i && i.event).map(i => i.event);
      const funnelEvents = {
        view_item: events.includes('view_item'),
        view_item_list: events.includes('view_item_list'),
        add_to_cart: events.includes('add_to_cart'),
        view_cart: events.includes('view_cart'),
        begin_checkout: events.includes('begin_checkout'),
        add_payment_info: events.includes('add_payment_info'),
        purchase: events.includes('purchase'),
      };
      const present = Object.entries(funnelEvents).filter(([,v]) => v).map(([k]) => k);
      const missing = Object.entries(funnelEvents).filter(([,v]) => !v).map(([k]) => k);
      return {
        events: funnelEvents,
        presentCount: present.length,
        missingCount: missing.length,
        present,
        missing,
        hasAnyEcommerce: present.length > 0,
      };
    })(),
  };

  // Cookies
  const allCookies = document.cookie.split(';').map(c => c.trim().split('=')[0]);
  const knownPrefixes = ['_ga', '_gid', '_fbp', '_fbc', '_gcl', 'li_', '_tt_',
    '_ck', '_hjSession', '_hjSessionUser', '_clck', '_clsk', 'hubspotutk', 'FPLC',
    'intercom-', 'mp_', 'ajs_', '_pin_', '_rdt_', 'fs_uid', 'driftt_', 'crisp-'];
  r.knownCookies = allCookies.filter(c =>
    knownPrefixes.some(p => c.startsWith(p)) || c === 'hubspotutk'
  );
  const browserCookies = ['__cf', '__cfduid', 'cf_clearance', '_GRECAPTCHA'];
  r.customCookies = allCookies.filter(c =>
    !knownPrefixes.some(p => c.startsWith(p)) && c !== 'hubspotutk' &&
    !browserCookies.some(p => c.startsWith(p)) && c.length > 1
  );

  // localStorage (reveals additional tools)
  r.localStorage = (() => {
    try {
      return Object.keys(localStorage).filter(k =>
        k.includes('ck') || k.includes('gcl') || k.includes('intercom') ||
        k.includes('hubspot') || k.includes('segment') || k.includes('amplitude') ||
        k.includes('mixpanel') || k.includes('posthog') || k.includes('heap') ||
        k.includes('reb2b') || k.includes('leadfeeder') || k.includes('clearbit') ||
        k.includes('drift') || k.includes('optimizely') || k.includes('vwo') ||
        k.includes('analytics') || k.includes('_fs_') || k.includes('lr-')
      );
    } catch(e) { return []; }
  })();

  // Scripts + third-party domains
  r.scripts = Array.from(document.querySelectorAll('script[src]')).map(s => s.src);
  const thirdPartyDomains = new Set();
  r.scripts.forEach(src => {
    try {
      const host = new URL(src).hostname;
      if (host !== location.hostname) thirdPartyDomains.add(host);
    } catch(e) {}
  });
  r.thirdPartyTrackingDomains = [...thirdPartyDomains].sort();

  // Pixels
  r.pixels = {
    facebook: allScriptText.includes('fbevents') || allScriptText.includes('fbq('),
    linkedin: allScriptText.includes('snap.licdn.com') || allScriptText.includes('_linkedin_partner_id'),
    twitter: allScriptText.includes('platform.twitter.com/oct') || allScriptText.includes('twq(') || allScriptText.includes('ads-twitter.com'),
    tiktok: allScriptText.includes('analytics.tiktok.com') || allScriptText.includes('ttq.load'),
    hotjar: allScriptText.includes('hotjar.com') || allScriptText.includes('hj('),
    hubspot: allScriptText.includes('js.hs-scripts.com') || allScriptText.includes('hs-analytics'),
    clarity: allScriptText.includes('clarity.ms') || allScriptText.includes('clarity('),
    segment: allScriptText.includes('cdn.segment.com') || allScriptText.includes('analytics.identify'),
    heap: allScriptText.includes('heap-') || allScriptText.includes('heap.load'),
    fullstory: allScriptText.includes('fullstory.com') || allScriptText.includes('FS.identify'),
    intercom: allScriptText.includes('widget.intercom.io') || allScriptText.includes('Intercom('),
    google_ads: allScriptText.includes('googleads') || allScriptText.includes('gtag_report_conversion') ||
      allScriptText.includes('googleadservices') || r.gtmObject.some(k => /^AW-/.test(k)),
    bing: allScriptText.includes('bat.bing.com') || allScriptText.includes('UET'),
    marketo: allScriptText.includes('munchkin.marketo.net') || allScriptText.includes('Munchkin.init') || (typeof Munchkin !== 'undefined'),
    pinterest: allScriptText.includes('pinimg.com/ct') || allScriptText.includes('pintrk') || allScriptText.includes('ct.pinterest.com'),
    reddit: allScriptText.includes('redditstatic.com/ads') || allScriptText.includes('rdt('),
    snapchat: allScriptText.includes('sc-static.net') || allScriptText.includes('tr.snapchat.com') || allScriptText.includes('snaptr('),
    taboola: allScriptText.includes('cdn.taboola.com') || allScriptText.includes('tfa.js'),
    thetradedesk: allScriptText.includes('js.adsrvr.org') || allScriptText.includes('insight.adsrvr.org'),
    quantcast: allScriptText.includes('quantserve.com') || allScriptText.includes('quantcount.com'),
    yahoo: allScriptText.includes('s.yimg.com/wi') || allScriptText.includes('dotpixel-a.akamaihd.net'),
    liveramp: allScriptText.includes('rlcdn.com') || allScriptText.includes('liadm.com'),
    tvsquared: allScriptText.includes('tvsquared.com') || allScriptText.includes('tv2track'),
    connexity: allScriptText.includes('cnnx.link') || allScriptText.includes('connexity.net'),
    dnb: allScriptText.includes('d41.co') || allScriptText.includes('dnb_coretag'),
  };

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

  // Alternative TMS
  r.alternativeTMS = {
    tealium_iq: allScriptText.includes('tags.tiqcdn.com') || allScriptText.includes('utag.js'),
    tealium_eventstream: allScriptText.includes('collect.tealiumiq.com') || allScriptText.includes('datacloud.tealiumiq.com'),
    adobe_launch: allScriptText.includes('assets.adobedtm.com') && allScriptText.includes('launch-'),
    adobe_dtm: allScriptText.includes('assets.adobedtm.com') && !allScriptText.includes('launch-'),
    ensighten: allScriptText.includes('nexus.ensighten.com') || allScriptText.includes('ensighten') ||
      allScriptText.includes('Bootstrapper') || (allScriptText.includes('serverComponent.php') && allScriptText.includes('namespace=')),
    signal: allScriptText.includes('s.thebrighttag.com') || allScriptText.includes('thebrighttag'),
    _satellite: typeof _satellite !== 'undefined',
  };
  r.legacyTMS = r.alternativeTMS;

  // Adobe analytics stack — detect standard AND first-party deployments
  r.adobeStack = {
    appMeasurement: allScriptText.includes('AppMeasurement') || allScriptText.includes('s_code') ||
      allScriptText.includes('appmeasurement') || r.scripts.some(s => /\/b\/ss\//.test(s)),
    aepWebSdk: allScriptText.includes('alloy') && (allScriptText.includes('adoberesources.net')
      || allScriptText.includes('edge.adobedc.net') || allScriptText.includes('configure')),
    visitorId: allScriptText.includes('demdex.net') || allScriptText.includes('VisitorAPI') ||
      allScriptText.includes('d_visid_ver') || allScriptText.includes('AMCV_'),
    adobeTarget: allScriptText.includes('mbox') || typeof window.adobe?.target !== 'undefined' ||
      allScriptText.includes('/mbox/json') || allScriptText.includes('securemvt') ||
      allScriptText.includes('/rest/v1/delivery') || document.cookie.includes('mbox'),
    firstPartyCollection: r.scripts.some(s => /smetrics\./i.test(s) || s.includes('omtrdc.net') ||
      s.includes('securemetrics') || /\/b\/ss\//.test(s)),
    orgId: (allScriptText.match(/[A-F0-9]{24}@AdobeOrg/i) || [null])[0] ||
      (document.cookie.match(/AMCV_([A-F0-9]{24}%40AdobeOrg)/i) || [null, null])[1]?.replace('%40', '@') || null,
    adobeCookies: allCookies.filter(c => /^(s_vi|s_fid|s_cc|s_ecid|s_sq|s_ppv|AMCV|AMCVS|mbox|at_check)/.test(c)),
  };

  r.gtmContainerCount = firstPartyGtmIds.length;
  r.thirdPartyGtmContainerCount = thirdPartyGtmIds.length;

  // B2B tools
  r.b2bTools = {
    rb2b: typeof reb2b !== 'undefined' || allScriptText.includes('b2bjsstore') || allScriptText.includes('reb2b'),
    leadfeeder: allScriptText.includes('leadfeeder') || typeof ldfdr !== 'undefined',
    clearbit: allScriptText.includes('clearbit.com') || typeof clearbit !== 'undefined',
    demandbase: allScriptText.includes('demandbase.com') || allScriptText.includes('Demandbase'),
    zoominfo: allScriptText.includes('ws.zoominfo.com'),
    '6sense': allScriptText.includes('6sense.com') || allScriptText.includes('6sc.co') || allScriptText.includes('_6si'),
    bombora: allScriptText.includes('bombora.com'),
    warmly: allScriptText.includes('warmly.ai') || typeof warmly !== 'undefined',
    dealfront: allScriptText.includes('dealfront'),
  };

  // ABM integration health
  r.abmIntegration = {
    '6sense_event': window.dataLayer ? window.dataLayer.some(item => item && item.event === '6si_company_details_loaded') : false,
    '6sense_match': window.dataLayer ? (window.dataLayer.filter(item => item && item['6si_company_match']).map(item => item['6si_company_match'])[0] || null) : null,
    demandbase_event: window.dataLayer ? window.dataLayer.some(item => item && item.event === 'Demandbase_Loaded') : false,
    demandbase_profile: typeof Demandbase !== 'undefined' ? (Demandbase?.IpApi?.CompanyProfile?.company_name || null) : null,
    clearbit_event: window.dataLayer ? window.dataLayer.some(item => item && item.event === 'Clearbit Loaded') : false,
    clearbit_company: typeof reveal !== 'undefined' ? (reveal?.company?.name || null) : null,
  };

  // Custom dimension hints
  const abmKeyPattern = /^(6si_|demandbase_|company_name|industry|employee_range|revenue_range|buying_stage)/;
  r.customDimensionHints = window.dataLayer ? window.dataLayer.filter(item => {
    if (!item || typeof item !== 'object') return false;
    if (Object.keys(item).some(k => abmKeyPattern.test(k))) return true;
    if (item.length !== undefined && typeof item[0] === 'string' && item[2] && typeof item[2] === 'object') {
      return Object.keys(item[2]).some(k => abmKeyPattern.test(k));
    }
    return false;
  }).length : 0;

  // Consent — all major CMPs
  r.consent = {
    cookiebot: allScriptText.includes('cookiebot.com'),
    onetrust: allScriptText.includes('onetrust.com') || allScriptText.includes('optanon') || allScriptText.includes('cookielaw.org'),
    osano: allScriptText.includes('osano.com'),
    termly: allScriptText.includes('termly.io'),
    trustarc: allScriptText.includes('trustarc.com') || allScriptText.includes('teconsent'),
    usercentrics: allScriptText.includes('usercentrics.eu') || allScriptText.includes('usercentrics.com'),
    didomi: allScriptText.includes('didomi.io') || allScriptText.includes('Didomi'),
    ketch: allScriptText.includes('ketch.com') || allScriptText.includes('semaphore.ketch'),
    iubenda: allScriptText.includes('iubenda.com'),
    // Check both single and double quotes — Hugo and other minifiers convert quote styles
    consentMode: allScriptText.includes("gtag('consent'") || allScriptText.includes('gtag("consent"') ||
      allScriptText.includes('consent_mode') ||
      (window.dataLayer || []).some(item => item && (
        item.event === 'gtm_consent_default' || item.event === 'gtm_consent_update' ||
        (item.value && (item.value.event === 'gtm_consent_default' || item.value.event === 'gtm_consent_update')) ||
        (typeof item === 'object' && (item[0] === 'consent' || item[1] === 'consent'))
      )),
    bannerVisible: (() => {
      const candidates = document.querySelectorAll(
        '[class*="cookie"], [id*="cookie"], [class*="consent"], [id*="consent"], [class*="gdpr"], ' +
        '#onetrust-banner-sdk, .cookiebot-banner, #teconsent, #truste-consent-track, ' +
        '#usercentrics-root, #didomi-host, [id*="iubenda"]'
      );
      return Array.from(candidates).some(el => {
        try {
          const rect = el.getBoundingClientRect();
          const style = window.getComputedStyle(el);
          return rect.height > 40 && style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
        } catch(e) { return false; }
      });
    })(),
  };

  // Consent Mode state — full analysis with region scoping
  r.consentModeState = (() => {
    const consentKeys = ['ad_storage', 'analytics_storage', 'ad_user_data', 'ad_personalization',
      'functionality_storage', 'personalization_storage', 'security_storage'];
    const defaultCommands = [];
    const defaults = {};
    const updates = {};
    (window.dataLayer || []).forEach(item => {
      if (!item || typeof item !== 'object') return;
      // Detect consent commands in three formats:
      // 1. Real array: ["consent", "default", {...}]
      // 2. Arguments object (no .length): {"0":"consent","1":"default","2":{...}}
      // 3. Nested value wrapper: {value: {event:"gtm_consent_default", ad_storage:"granted",...}}
      const isConsentCmd = (Array.isArray(item) || (item.length !== undefined && typeof item[0] === 'string') ||
        (!Array.isArray(item) && item[0] === 'consent')) && item[0] === 'consent';
      if (isConsentCmd) {
        const params = item[2] || {};
        if (item[1] === 'default') {
          defaultCommands.push({...params});
          if (!params.region || defaultCommands.length === 1) Object.assign(defaults, params);
        }
        if (item[1] === 'update') Object.assign(updates, params);
      }
      // Check both direct event and nested value wrapper
      const consentEvent = item.event || (item.value && item.value.event) || null;
      const consentSource = (consentEvent === item.event) ? item : (item.value || {});
      if (consentEvent === 'gtm_consent_default' || consentEvent === 'gtm_consent_update') {
        const target = consentEvent.includes('default') ? defaults : updates;
        const cmd = {};
        for (const [k, v] of Object.entries(consentSource)) {
          if (consentKeys.includes(k)) { target[k] = v; cmd[k] = v; }
        }
        if (consentEvent === 'gtm_consent_default' && Object.keys(cmd).length > 0) {
          if (consentSource.region) cmd.region = consentSource.region;
          defaultCommands.push(cmd);
        }
      }
    });
    return {
      defaults, updates, defaultCommands,
      hasDefaults: Object.keys(defaults).length > 0,
      hasV2Signals: 'ad_user_data' in defaults && 'ad_personalization' in defaults,
      hasPartialV2: ('ad_user_data' in defaults) !== ('ad_personalization' in defaults),
      hasRegionScoping: defaultCommands.some(c => c.region),
    };
  })();

  // OG and Twitter Card meta tags
  r.ogTags = {
    ogTitle: document.querySelector('meta[property="og:title"]')?.content || null,
    ogDescription: document.querySelector('meta[property="og:description"]')?.content || null,
    ogType: document.querySelector('meta[property="og:type"]')?.content || null,
    ogImage: document.querySelector('meta[property="og:image"]')?.content || null,
    ogImageType: document.querySelector('meta[property="og:image:type"]')?.content || null,
    twitterCard: document.querySelector('meta[name="twitter:card"]')?.content || null,
    twitterCreator: document.querySelector('meta[name="twitter:creator"]')?.content || null,
    twitterSite: document.querySelector('meta[name="twitter:site"]')?.content || null,
  };

  // Schema markup (JSON-LD)
  r.schema = Array.from(document.querySelectorAll('script[type="application/ld+json"]')).map(s => {
    try { const d = JSON.parse(s.textContent); return d['@type'] || 'unknown'; }
    catch(e) { return 'parse_error'; }
  });

  // Meta tags
  r.meta = {
    title: document.title || null,
    description: document.querySelector('meta[name="description"]')?.content || null,
    canonical: document.querySelector('link[rel="canonical"]')?.href || null,
    robots: document.querySelector('meta[name="robots"]')?.content || null,
    ogImage: document.querySelector('meta[property="og:image"]')?.content || null,
  };
  // Backward compat alias
  r.canonical = r.meta.canonical;

  // Preconnects + dns-prefetch
  r.preconnects = Array.from(document.querySelectorAll('link[rel="preconnect"], link[rel="dns-prefetch"]')).map(l => l.href);

  // Preconnect hints that corroborate deferred-but-present tracking
  r.preconnectTrackingHints = r.preconnects.filter(href =>
    /googletagmanager\.com|google-analytics\.com|clarity\.ms|stape|facebook\.net|snap\.licdn\.com|bat\.bing\.com|analytics\.tiktok\.com|hotjar\.com|doubleclick\.net/.test(href)
  );

  // Cross-domain links (conversion-related external links)
  r.crossDomainLinks = Array.from(document.querySelectorAll('a[href]')).filter(a => {
    try {
      const linkHost = new URL(a.href).hostname;
      return linkHost !== location.hostname && (
        a.href.includes('checkout') || a.href.includes('pay') || a.href.includes('book') ||
        a.href.includes('schedule') || a.href.includes('calendly') || a.href.includes('stripe') ||
        a.href.includes('hubspot') || a.href.includes('typeform')
      );
    } catch(e) { return false; }
  }).slice(0, 10).map(a => ({
    text: a.textContent.trim().substring(0, 60),
    href: a.href.substring(0, 200),
    hasGlParam: a.href.includes('_gl='),
  }));
  // Lightweight cross-domain summary (for standalone --dir mode)
  r.crossDomain = {
    linkerParam: location.search.includes('_gl='),
    linkerInLinks: Array.from(document.querySelectorAll('a[href]')).filter(a => a.href.includes('_gl=')).length,
  };

  // Forms — hidden fields with names AND values
  r.forms = Array.from(document.querySelectorAll('form')).map(f => ({
    id: f.id || null, action: f.action || null,
    hasSubmitHandler: !!f.onsubmit,
    hiddenFields: Array.from(f.querySelectorAll('input[type="hidden"]')).map(i => ({
      name: i.name, value: i.value || '',
    })),
  }));
  // Filtered view: only tracking-param hidden fields with values (for attribution check)
  r.formHiddenFieldValues = r.forms.map(f => ({
    id: f.id, action: f.action,
    hiddenFields: f.hiddenFields.filter(i => /gclid|utm_|fbclid|li_fat|msclk|_gl|source|medium|campaign/i.test(i.name)),
  }));

  // Video embeds
  r.videoEmbeds = Array.from(document.querySelectorAll('iframe')).filter(i =>
    i.src && (i.src.includes('youtube.com') || i.src.includes('vimeo.com') || i.src.includes('wistia.com'))
  ).map(i => ({
    src: i.src.substring(0, 200),
    platform: i.src.includes('youtube') ? 'youtube' : i.src.includes('vimeo') ? 'vimeo' : 'wistia',
    hasNoCookie: i.src.includes('youtube-nocookie.com'),
    hasTrackingApi: i.src.includes('youtube') ? i.src.includes('enablejsapi=1') :
                    i.src.includes('vimeo') ? i.src.includes('api=1') : true,
  }));

  // Iframes + postMessage listener detection
  r.iframes = Array.from(document.querySelectorAll('iframe')).map(i => (i.src || '').substring(0, 150));
  r.hasPostMessageListener = allScriptText.includes("addEventListener('message'") ||
    allScriptText.includes('addEventListener("message"') ||
    allScriptText.includes("addEventListener( 'message'") ||
    allScriptText.includes('addEventListener( "message"');

  // Chatbots
  r.chatbots = {
    drift: allScriptText.includes('drift.com') || typeof drift !== 'undefined',
    intercom: allScriptText.includes('intercom.io') || typeof Intercom !== 'undefined',
    hubspotChat: allScriptText.includes('js.usemessages.com'),
    qualified: allScriptText.includes('qualified.com'),
    liveChat: allScriptText.includes('livechat') || allScriptText.includes('livechatinc'),
  };

  // CTA buttons
  r.ctaTracking = Array.from(document.querySelectorAll('a[href], button')).filter(el => {
    const text = (el.textContent || '').trim().toLowerCase();
    return ['buy', 'add to cart', 'shop now', 'customize', 'get started', 'sign up',
      'contact', 'demo', 'free trial', 'get quote', 'request', 'schedule'].some(kw => text.includes(kw));
  }).slice(0, 10).map(el => ({
    tag: el.tagName, text: (el.textContent || '').trim().substring(0, 50),
    hasDataAttributes: Object.keys(el.dataset).length > 0,
    dataAttributes: Object.keys(el.dataset),
  }));
  // Backward compat alias for SKILL.md orchestrator format
  r.ctas = Array.from(document.querySelectorAll('a[href*="contact"], a[href*="schedule"], a[href*="book"], a[href*="demo"], a[href*="signup"], a[href*="trial"], button[type="submit"]')).slice(0, 10).map(el => ({
    text: el.textContent.trim().substring(0, 60),
    href: el.href || null,
    hasOnclick: !!el.onclick,
    dataAttrs: Array.from(el.attributes).filter(a => a.name.startsWith('data-')).map(a => a.name),
  }));

  // --- Enrichment fields (previously SKILL.md-only, now canonical) ---

  // DataLayer sequencing — race condition detection
  r.dataLayerSequencing = (() => {
    const dl = window.dataLayer || [];
    const gtmJsIndex = dl.findIndex(item => item && item.event === 'gtm.js');
    const gtmDomIndex = dl.findIndex(item => item && item.event === 'gtm.dom');
    const gtmLoadIndex = dl.findIndex(item => item && item.event === 'gtm.load');
    const customDataPushes = dl.map((item, i) => {
      if (!item || typeof item !== 'object') return null;
      if (item.event && (item.event.startsWith('gtm.') || item.event.includes('consent'))) return null;
      const keys = Object.keys(item);
      const businessKeys = keys.filter(k =>
        /^(user_?id|user_?type|company_?name|company_?id|industry|plan_?type|tier|segment_?id|revenue|lead_?score|account_?id|buying_?stage)/i.test(k)
      );
      if (businessKeys.length > 0) return { index: i, keys: businessKeys, event: item.event || null };
      return null;
    }).filter(Boolean);
    const latePushes = customDataPushes.filter(p => gtmJsIndex >= 0 && p.index > gtmJsIndex);
    return { gtmJsIndex, gtmDomIndex, gtmLoadIndex, customDataPushes, latePushes, hasRaceCondition: latePushes.length > 0 };
  })();

  // Tracking scripts outside GTM (bypass Consent Mode)
  r.scriptsOutsideGTM = (() => {
    const trackingDomains = [
      'facebook.net', 'fbevents', 'snap.licdn.com', 'platform.twitter.com',
      'analytics.tiktok.com', 'bat.bing.com', 'hotjar.com', 'clarity.ms',
      'fullstory.com', 'heapanalytics.com', 'cdn.amplitude.com', 'cdn.segment.com',
      'js.hs-scripts.com', 'hs-analytics',
    ];
    const rogueTracking = Array.from(document.querySelectorAll('head > script[src], body > script[src]')).filter(s => {
      if (s.hasAttribute('data-gtmsrc') || s.hasAttribute('data-gtmscriptid') ||
          s.className.includes('gtm') || s.id.includes('gtm')) return false;
      const scriptType = (s.type || '').toLowerCase();
      if (scriptType && scriptType !== 'text/javascript' && scriptType !== 'module') return false;
      if (s.hasAttribute('data-cookieconsent') || s.hasAttribute('data-categories') ||
          s.className.includes('optanon') || s.hasAttribute('data-consent')) return false;
      return trackingDomains.some(d => s.src.includes(d));
    }).map(s => s.src.substring(0, 150));
    return { scripts: rogueTracking, count: rogueTracking.length };
  })();

  // YouTube iframes using youtube.com instead of youtube-nocookie.com
  r.iframeCookieRisk = Array.from(document.querySelectorAll('iframe')).filter(i =>
    i.src && i.src.includes('youtube.com/embed') && !i.src.includes('youtube-nocookie.com')
  ).map(i => i.src.substring(0, 200));

  // CRM cookie subdomain scoping
  r.crmCookieScope = (() => {
    const crmCookies = { hubspotutk: 'HubSpot', _mkto_trk: 'Marketo', messagesUtk: 'HubSpot Chat' };
    const found = {};
    for (const [name, platform] of Object.entries(crmCookies)) {
      if (document.cookie.includes(name)) found[name] = platform;
    }
    return { hostname: location.hostname, found };
  })();

  // Chatbot auto-interaction events
  r.chatAutoInteraction = (() => {
    const earlyEvents = (window.dataLayer || []).filter(item =>
      item && item.event && (item.event.includes('drift') || item.event.includes('intercom') ||
        item.event.includes('qualified') || item.event.includes('hubspot_chat') ||
        item.event.includes('chat_') || item.event.includes('message_'))
    ).map(item => item.event);
    return { earlyEventsOnLoad: earlyEvents };
  })();

  // LinkedIn Insight Tag details
  r.linkedinInsightTag = (() => {
    const hasInsightTag = allScriptText.includes('snap.licdn.com') || allScriptText.includes('_linkedin_partner_id') || allScriptText.includes('insight.min.js');
    const hasLintrkFunction = typeof window.lintrk === 'function';
    const hasConversionCall = allScriptText.includes('lintrk(') && allScriptText.includes('conversion_id');
    return { hasInsightTag, hasLintrkFunction, hasConversionCall };
  })();

  // Pardot tracking domain check
  r.pardotTracking = (() => {
    const thirdPartyPardot = r.scripts.some(s => s.includes('pi.pardot.com') || s.includes('go.pardot.com') || s.includes('cdn.pardot.com'));
    const hasPardot = thirdPartyPardot || allScriptText.includes('piAId') || allScriptText.includes('pardot');
    return { detected: hasPardot, usesThirdPartyDomain: thirdPartyPardot };
  })();

  // Google Ads Enhanced Conversions — check allScriptText AND dataLayer (Arguments-object format)
  r.googleAdsEnhanced = (() => {
    const hasGoogleAds = r.pixels.google_ads;
    const hasEnhancedConfig = allScriptText.includes('enhanced_conversions') || allScriptText.includes('user_data') || allScriptText.includes('enhanced_conversion_data') ||
      (window.dataLayer || []).some(item => {
        if (!item || typeof item !== 'object') return false;
        // Check direct config: {allow_enhanced_conversions: true}
        if (item.allow_enhanced_conversions) return true;
        // Check Arguments-object format: {"0":"config","1":"AW-xxx","2":{allow_enhanced_conversions:true}}
        if (item[0] === 'config' && item[2] && item[2].allow_enhanced_conversions) return true;
        return false;
      });
    const hasUserDataInDL = (window.dataLayer || []).some(item => {
      if (!item || typeof item !== 'object') return false;
      // Direct property format
      if (item.enhanced_conversion_data || item.user_data) return true;
      if (item.eventModel && item.eventModel.enhanced_conversion_data) return true;
      // Arguments-object format: {"0":"set","1":"user_data","2":{...}}
      if (item[0] === 'set' && item[1] === 'user_data' && item[2]) return true;
      return false;
    });
    return { hasGoogleAds, hasEnhancedConfig, hasUserDataInDL };
  })();

  // Page indexability (for thank-you page check)
  r.pageIndexability = {
    robotsMeta: document.querySelector('meta[name="robots"]')?.content || null,
    hasNoindex: (document.querySelector('meta[name="robots"]')?.content || '').includes('noindex'),
    url: location.href,
  };

  // HubSpot form embed type
  r.hubspotForms = {
    iframeEmbeds: Array.from(document.querySelectorAll('iframe[src*="share.hsforms.com"], iframe[src*="hsforms.com"]')).length,
    jsEmbeds: Array.from(document.querySelectorAll('.hbspt-form, [id*="hbspt-form"]')).length,
    hasHbsptObject: typeof hbspt !== 'undefined',
  };

  // Cloudflare Zaraz
  r.cloudflareZaraz = {
    detected: r.scripts.some(s => s.includes('/cdn-cgi/zaraz/')) || allScriptText.includes('zaraz'),
    scriptSrc: r.scripts.find(s => s.includes('/cdn-cgi/zaraz/')) || null,
  };

  // SPA framework detection
  r.spaFramework = {
    nextjs: !!document.querySelector('#__next') || typeof __NEXT_DATA__ !== 'undefined',
    nuxt: !!document.querySelector('#__nuxt') || typeof __NUXT__ !== 'undefined',
    react: !!document.querySelector('[data-reactroot], #root[data-react-helmet]'),
    angular: !!document.querySelector('[ng-app], [ng-version]'),
  };

  return r;
}
