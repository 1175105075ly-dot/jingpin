# Browser Extraction

Use the user's Chrome profile with Seller Sprite installed and authenticated. The primary data source is the Amazon collection/search page enhanced by the Seller Sprite extension; do not switch to SellerSprite product-store pages unless the user explicitly asks for a fallback.

## Page Wait Strategy

For each `crawl_pages[]` collection/search page URL:

1. Navigate to the temporary collection URL from `crawl_pages[].url`.
2. Wait for a base Amazon search/list DOM signal, such as `#search`, `[data-component-type="s-search-result"]`, or `div.s-main-slot`.
3. Start a 30-second Seller Sprite wait loop.
4. Poll every 500-1000 ms for an extension-rendered module or text marker that is stable in the user's environment. Good markers include visible Seller Sprite labels, extension-added tables, extension-added sales/BSR fields, or DOM nodes whose class/text clearly belongs to Seller Sprite.
5. Once detected, wait 3 additional seconds before extracting.
6. If Seller Sprite is not detected within 30 seconds, emit failed records for the ASINs expected on that collection page with `status=failed`, `error_type=seller_sprite_timeout`, and continue with the next page.

## Extraction Guidance

Prefer structured DOM text and extension table/module fields over screenshots. Match each scraped product card or Seller Sprite row back to an expected ASIN from `crawl_pages[].expected_asins`. Normalize currency and ranking values before writing records. If a field cannot be read reliably, set it to `null` or empty string and record a short note in the temporary crawl log; do not invent data.

For the first pass, extract Amazon-native fields even if some Seller Sprite fields are absent: ASIN, title, image URL, current price, rating, review count, coupon/deal text when visible, and crawl status. Fill Seller Sprite-only metrics such as BSR, estimated review risk, ads, variants, or deal flags only when the extension exposes them clearly.

If an expected ASIN is not present in the loaded collection page, mark it as `status=failed`, `error_type=asin_missing_from_collection`, unless the user explicitly asks to open detail pages as a fallback.

Detect Amazon page failures separately from extension failures:
- 404 or unavailable page: `status=unavailable`, `error_type=amazon_unavailable`.
- CAPTCHA or blocked page: `status=failed`, `error_type=amazon_blocked`.
- Seller Sprite missing after DOM success: `status=failed`, `error_type=seller_sprite_timeout`.
- Parse failure after module appears: `status=failed`, `error_type=parse_error`.

## Temporary Files

Keep the collection URL, browser traces, screenshots, raw HTML snippets, and task lists under the run's `tmp/` folder only. Do not copy temporary collection URLs into snapshots or reports. Delete temporary files during final cleanup unless the user explicitly asks to preserve debugging evidence.
