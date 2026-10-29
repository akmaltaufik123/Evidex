# Illustrated EVIDEX guide assets

Six separate images generated with the built-in image generation tool for the
EVIDEX Next onboarding guide. Images are illustrative schematics, not live
screenshots, official Telegram assets or evidence of a real account. No live
credentials were used. Converted to WebP at original resolution for distribution;
no content, labels or composition were edited after generation.

## Active Paper & Ink series (0.2.1)

The active guide now selects the six `*-paper.webp` files. They show content
objects (envelope, keys, connection, link, lock and archival folder), with no
browser bars, phone frames or invented UI. Their full generation prompts are in
[paper-prompts.json](paper-prompts.json). These were generated as six separate
images with the built-in image tool, then converted to WebP without changing
composition or content. Readable instructions remain in the bilingual catalog.

The original six files and prompt notes below are preserved as archive assets;
they are no longer displayed by the active guide.

## Prompt set and files

All prompts used this shared brief: one landscape 3:2 instructional illustration,
calm navy (#101a2a), teal (#71dbb8) and Telegram blue, approachable editorial tech
style, masked credentials only, generous spacing, no private conversations.

- `01-telegram-portal.webp`: laptop at my.telegram.org; phone number masked;
  Telegram phone beside it with a masked service code. Show portal sign-in as
  a schematic illustration, not a real screenshot.
- `02-api-details.webp`: developer-portal page, highlight API development tools,
  API ID and API hash; mask all credential values. Minimal readable labels.
- `03-connection-test.webp`: EVIDEX NEXT laptop with API ID/API hash fields,
  masked values, Test connection button and connection-check indicator. This
  illustrates transport checking, not account authorization.
- `04-telegram-source.webp`: generic Example channel Telegram profile, highlighted
  t.me/example public link and copy icon, arrow to the local Telegram source
  field. No actual account, private invite or personal data.
- `05-telegram-login.webp`: phone with masked Telegram login code and local EVIDEX
  panel with distinct Login code and Two-factor password fields. No usable codes
  or secrets; the user only completes a login they initiated.
- `06-evidence-results.webp`: EVIDEX NEXT completed job, Open evidence folder
  button and generic photo/video/text/hash-record cards. No private messages or
  claim of legal admissibility, authenticity or official endorsement.

Text instructions, image alternatives and the illustration notice are translated
in `evidex_next_content.json`. The same images are used in both languages; English
labels inside schematic pictures are examples and are not the app's translations.

## Official instruction sources

- https://core.telegram.org/api/obtaining_api_id
- https://my.telegram.org
- https://telegram.org/faq

The site shows source links alongside the relevant guide steps. API portal
verification and EVIDEX account verification are explained as separate requests.
