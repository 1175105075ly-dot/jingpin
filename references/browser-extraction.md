# Browser Extraction

Use an automation browser profile with Seller Sprite installed and authenticated. Prefer Chrome when extension state, cookies, or login are needed.

## Page Wait Strategy

For each canonical ASIN URL:

1. Navigate to `https://www.amazon.com/dp/{asin}`.
2. Wait for a base Amazon product DOM signal, such as `#dp`, `#productTitle`, `#detailBullets_feature_div`, or `#centerCol`.
3. Start a 30-second Seller Sprite wait loop.
4. Poll every 500-1000 ms for an extension-rendered module or text marker that is stable in the user's environment.
5. Once detected, wait 3 additional seconds before extracting.
6. If Seller Sprite is not detected within 30 seconds, record `status=failed`, `error_type=seller_sprite_timeout`, and continue with the next ASIN.

## Extraction Guidance

Prefer structured DOM text and extension table/module fields over screenshots. Normalize currency and ranking values before writing records. If a field cannot be read reliably, set it to `null` or empty string and record a short note in the temporary crawl log; do not invent data.

Detect Amazon page failures separately from extension failures:
- 404 or unavailable page: `status=unavailable`, `error_type=amazon_unavailable`.
- CAPTCHA or blocked page: `status=failed`, `error_type=amazon_blocked`.
- Seller Sprite missing after DOM success: `status=failed`, `error_type=seller_sprite_timeout`.
- Parse failure after module appears: `status=failed`, `error_type=parse_error`.

## Temporary Files

Keep browser traces, screenshots, raw HTML snippets, and task lists under the run's `tmp/` folder. Delete them during final cleanup unless the user explicitly asks to preserve debugging evidence.
