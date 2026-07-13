# Data Schema

Use one JSON object per ASIN. Keep key names stable so daily snapshots can be compared without custom mapping.

## Record Fields

Identity:
- `asin`: required ASIN.
- `resolved_asin`: final ASIN shown after navigation; normally equal to `asin` and empty when it cannot be verified.
- `redirected_to_asin`: destination ASIN when Amazon redirects the requested ASIN; otherwise empty.
- `scraped_at`: ISO-8601 timestamp for this ASIN.
- `title`: product title.
- `image_url`: main image URL.
- `brand`: brand name.
- `seller_name`: seller or storefront name.

Price:
- `current_price`: numeric current sale price.
- `list_price`: numeric original/list price.
- `discount_percent`: numeric discount percentage.
- `limited_discount_status`: string status such as `none`, `active`, or `unknown`.
- `discount_ends_at`: ISO-8601 timestamp or empty string.

Coupons:
- `has_coupon`: boolean.
- `coupon_value`: amount or percentage as a string because Amazon displays mixed formats.
- `coupon_valid_until`: ISO-8601 date/time or empty string.
- `coupon_minimum`: threshold text or empty string.

Ranking and traffic:
- `small_category_node`: leaf category name.
- `small_bsr_rank`: numeric small-category BSR.
- `main_category_rank`: numeric large-category rank.

Inventory and variants:
- `variant_count`: numeric variant total.
- `is_out_of_stock`: boolean.
- `variant_price_min`: numeric minimum variant price.
- `variant_price_max`: numeric maximum variant price.

Reviews:
- `rating`: numeric average rating.
- `review_count`: numeric total review count.
- `new_negative_review_today`: boolean or numeric count if the extension exposes the count.

Ads and deals:
- `has_sp_ad`: boolean.
- `has_sd_ad`: boolean.
- `has_ld`: boolean.
- `has_7_day_deal`: boolean.

Crawl status:
- `status`: `ok`, `failed`, `unavailable`, or `invalid`.
- `error_type`: machine-readable error category, empty for successful records.
- `error_message`: short human-readable error text.

Use `status=invalid` and `error_type=asin_redirected` when `redirected_to_asin` differs from the requested `asin`. Never store destination-product metrics as if they belonged to the requested ASIN.

## Persistence Rules

Do not store the user's original pasted URL. Store `asin` only; generate direct links as `https://www.amazon.com/dp/{asin}` when building Feishu cards or reports.

Use empty strings for unavailable text fields, `null` for unavailable numeric/date fields, and booleans only where the source data can support a true/false value. If Seller Sprite times out, still emit a failed record with `asin`, `scraped_at`, `status`, `error_type`, and `error_message`.

Successful records must provide `title`, `current_price`, `rating`, `small_bsr_rank`, and `main_category_rank` whenever Seller Sprite exposes them. Snapshot validation checks at least 90% coverage for each of these core fields across successful records.
