IMPLEMENTATION INSTRUCTIONS

1. Copy the /components folder into your website root.
2. Copy the /assets/js/include.js file into your assets/js directory.

3. In every page (home, ebooks, blog, etc):

Replace the header with:
<div data-include="/components/header.html"></div>

Replace the footer with:
<div data-include="/components/footer.html"></div>

Add before </body>:
<script src="/assets/js/include.js"></script>

Benefits:
- One shared header/footer across all pages
- Faster site maintenance
- Works with Cloudflare Pages static hosting
