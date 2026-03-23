/**
 * dojo/static/dojo/js/csrf.js
 *
 * Django requires a CSRF token on all POST requests.
 * This helper reads the cookie Django sets and attaches it
 * automatically to every fetch() call made by our SPA JS.
 *
 * Include this script BEFORE any app JS in the templates.
 * Usage in templates:  <script src="{% static 'dojo/js/csrf.js' %}"></script>
 */

(function () {
    'use strict';

    // Read the csrftoken cookie Django sets on page load
    function getCookie(name) {
        const cookies = document.cookie.split(';');
        for (const cookie of cookies) {
            const [k, v] = cookie.trim().split('=');
            if (k === name) return decodeURIComponent(v);
        }
        return null;
    }

    // Patch the global fetch() to always include the CSRF header on same-origin POSTs
    const _originalFetch = window.fetch;
    window.fetch = function (url, options = {}) {
        const method = (options.method || 'GET').toUpperCase();
        const isSafeMethod = ['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method);
        const isSameOrigin = !url.startsWith('http') || url.startsWith(window.location.origin);

        if (!isSafeMethod && isSameOrigin) {
            options.headers = options.headers || {};
            // If headers is a plain object (which our app always uses), add the token
            if (typeof options.headers === 'object' && !(options.headers instanceof Headers)) {
                options.headers['X-CSRFToken'] = getCookie('csrftoken');
            }
        }

        // Always send cookies (Django session)
        options.credentials = options.credentials || 'same-origin';

        return _originalFetch(url, options);
    };
})();
