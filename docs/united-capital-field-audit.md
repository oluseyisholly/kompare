# United Capital source-to-output audit

Verified on 2026-10-23 against the downloaded public price HTML, rendered browser tables, and official product pages. Latest table date: 2026-10-07. Values below are observations, not scraper constants. Validation used an in-memory database only.

| Fund | Bid | Offer | YTD return | Effective Yield Day on Day Return |
| --- | ---: | ---: | ---: | ---: |
| Equity Fund | 2.4801 | 2.5057 | 46.29% | Not published |
| Balanced Fund | 2.9545 | 2.9754 | 44.57% | Not published |
| Wealth for Women Fund | 2.2779 | 2.2937 | 42.88% | Not published |
| Sukuk Fund | 1.192 | 1.192 | 10.68% | 11.55% |
| Fixed Income Fund | 1.9227 | 1.9227 | 8.43% | 8.48% |
| Eurobond Fund | 122.8484 | 122.8484 | 6.16% | 5.89% |
| Global Fixed Income Fund | 1.2339 | 1.2339 | 8.22% | 4.39% |
| Money Market Fund | 1.00 | 1.00 | Not published | 15.38% |
| Stable Income Fund | 132.6749 | 132.6749 | 15.96% | 16.01% |
| Children Investment Fund | 1.528 | 1.528 | 40.08% | Not published |

The last column is exposed with its original label under `latest_snapshot.published_metrics`. Its interpretation remains unresolved; no annual yield is inferred. All four financial cells are exposed, including explicit missing-cell status.

| Fund | Currency | Initial cash minimum | Subsequent cash multiple/minimum | Holding days | Published risk | Distribution | Structure |
| --- | --- | ---: | ---: | ---: | --- | --- | --- |
| Balanced Fund | NGN | 10000.00000000 | Not published | 90 | Not published | Not published | open_ended |
| Children Investment Fund | NGN | 5000000.00000000 | 10000.00000000 | 365 | Moderate | annually | open_ended |
| Equity Fund | NGN | 10000.00000000 | Not published | 90 | Not published | Not published | open_ended |
| Fixed Income Fund | NGN | 10000.00000000 | Not published | 90 | Moderate | Not published | open_ended |
| Global Fixed Income Fund | USD | 50000.00000000 | 500.00000000 | Not published | Not published | Not published | open_ended |
| Money Market Fund | NGN | 10000.00000000 | 5000.00000000 | 14 | Low | quarterly | open_ended |
| Nigerian Eurobond Fund | USD | 100.00000000 | 500.00000000 | 90 | Not published | Not published | open_ended |
| Stable Income Fund | NGN | 50000000.00000000 | 10000000.00000000 | 30 | Low | annually | open_ended |
| Sukuk Fund | NGN | 10000.00000000 | 5000.00000000 | 90 | Low | annually | Not published |
| Wealth for Women Fund | NGN | 10000.00000000 | 5000.00000000 | 90 | Not published | Not published | Not published |

Each product field retains its URL, raw-record reference, observation timestamp and exact supporting statement in `details_metadata`. Unit subscriptions and cash minimums remain distinct. No fees or KYC were collected.

Source URLs: https://unitedcapitalplcgroup.com/fund-prices/ and the product links documented in [the ingestion guide](united-capital-ingestion.md).
