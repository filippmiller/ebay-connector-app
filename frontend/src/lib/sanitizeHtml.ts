import DOMPurify from 'dompurify';

/**
 * Sanitize HTML coming from external systems (eBay messages, etc.).
 *
 * This helper centralizes our XSS policy so all callers get the same
 * protection and we can tighten it over time if needed.
 */
export function sanitizeHtml(input: string | null | undefined): string {
  if (!input) return '';

  return DOMPurify.sanitize(input, {
    // Start from DOMPurify's built-in safe HTML profile.
    USE_PROFILES: { html: true },
    // Extra hardening: explicitly forbid script-like tags and common vectors.
    FORBID_TAGS: ['script', 'style', 'noscript', 'iframe', 'object', 'embed'],
    FORBID_ATTR: [
      'onerror',
      'onclick',
      'onload',
      'onmouseover',
      'onmouseenter',
      'onmouseleave',
      'onfocus',
      'onfocusin',
      'onfocusout',
    ],
  });
}