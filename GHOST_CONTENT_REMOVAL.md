# Dynamic content ownership

Podcast episodes, podcast transcripts and blog posts are not stored or generated in this repository.

- Podcast episode metadata and existence are governed by the production podcast RSS feed.
- Transcript bodies and existence are governed by the `TRANSCRIPTS_BUCKET` R2 binding.
- Blog post bodies, images and the blog manifest are governed by the `BLOG_BUCKET` and `BLOG_IMAGES_BUCKET` R2 bindings.
- Missing R2/RSS content must fail closed. The repository must not recreate, cache or publish a committed fallback copy.
