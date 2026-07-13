# Browser Extraction

Use the user's Chrome profile with Seller Sprite installed and authenticated. The primary data source is the Amazon collection/search page enhanced by the Seller Sprite extension; do not switch to SellerSprite product-store pages unless the user explicitly asks for a fallback.

## Page Wait Strategy

For each generated `crawl_pages[]` collection/search page URL (maximum eight expected ASINs):

1. Navigate to the temporary collection URL from `crawl_pages[].url`.
2. Wait for a base Amazon search/list DOM signal, such as `#search`, `[data-component-type="s-search-result"]`, or `div.s-main-slot`.
3. Start a 30-second Seller Sprite wait loop.
4. Poll every 500-1000 ms for an extension-rendered module or text marker that is stable in the user's environment. Good markers include visible Seller Sprite labels, extension-added tables, extension-added sales/BSR fields, or DOM nodes whose class/text clearly belongs to Seller Sprite.
5. Once detected, wait 3 additional seconds before extracting.
6. If Amazon or Seller Sprite is incomplete, reload once and repeat the wait sequence.
7. If Seller Sprite is still not detected, continue to canonical detail-page fallback for each expected ASIN instead of failing the whole batch.

## Extraction Guidance

Prefer structured DOM text and extension table/module fields over screenshots. Match each scraped product card or Seller Sprite row back to an expected ASIN from `crawl_pages[].expected_asins`. Normalize currency and ranking values before writing records. If a field cannot be read reliably, set it to `null` or empty string and record a short note in the temporary crawl log; do not invent data.

For the first pass, extract Amazon-native fields even if some Seller Sprite fields are absent: ASIN, title, image URL, current price, rating, review count, coupon/deal text when visible, and crawl status. Fill Seller Sprite-only metrics such as BSR, estimated review risk, ads, variants, or deal flags only when the extension exposes them clearly.

If an expected ASIN is absent or incomplete on the collection page, automatically open `https://www.amazon.com/dp/{asin}` and repeat the extraction. Detail-page fallback is part of the default workflow and does not require another user confirmation.

After detail-page navigation, verify the final page ASIN using the canonical link, page metadata, or visible ASIN fields. If Amazon redirects to a different product, keep the requested ASIN as `asin`, set `status=invalid`, `error_type=asin_redirected`, and record the destination in both `resolved_asin` and `redirected_to_asin`. Do not silently copy the destination product's metrics onto the requested ASIN.

Detect Amazon page failures separately from extension failures:
- 404 or unavailable page: `status=unavailable`, `error_type=amazon_unavailable`.
- CAPTCHA or blocked page: `status=failed`, `error_type=amazon_blocked`.
- Seller Sprite missing after DOM success: `status=failed`, `error_type=seller_sprite_timeout`.
- Parse failure after module appears: `status=failed`, `error_type=parse_error`.
- Detail page redirects to another ASIN: `status=invalid`, `error_type=asin_redirected`.

## Resume Checkpoint

After each collection batch or detail fallback, merge records into `tmp/records.json` by requested ASIN and write the file immediately. On resume, load that file and skip complete `status=ok` records; retry failed, unavailable, invalid, or incomplete records unless the user asks for a clean rerun.

## Temporary Files

Keep the collection URL, browser traces, screenshots, raw HTML snippets, and task lists under the run's `tmp/` folder only. Do not copy temporary collection URLs into snapshots or reports. Delete temporary files during final cleanup unless the user explicitly asks to preserve debugging evidence.
