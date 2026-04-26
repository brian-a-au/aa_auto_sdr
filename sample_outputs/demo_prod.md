# SDR — Demo Production (demo.prod)

> Captured at 2026-04-26T12:00:00+00:00 · tool version 1.0.0

## Summary

| Field | Value |
| --- | --- |
| RSID | demo.prod |
| Name | Demo Production |
| Timezone | US/Pacific |
| Currency | USD |
| Captured at | 2026-04-26T12:00:00+00:00 |
| Tool version | 1.0.0 |
| Dimensions | 4 |
| Metrics | 3 |
| Segments | 2 |
| Calculated Metrics | 1 |
| Virtual Report Suites | 1 |
| Classifications | 1 |

## Dimensions

| id | name | type | category | parent | pathable | description | tags | extra |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| variables/evar1 | User ID | string | Conversion |  | false | Authenticated user identifier | `[]` | `{}` |
| variables/evar2 | Plan | string | Conversion |  | false |  | `[]` | `{}` |
| variables/events | Custom Events | counter |  |  | false |  | `[]` | `{}` |
| variables/prop1 | Page Type | string | Content |  | true | Section taxonomy | `["taxonomy"]` | `{}` |

## Metrics

| id | name | type | category | precision | segmentable | description | tags | data_group | extra |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| metrics/orders | Orders | int | Commerce | 0 | true | Conversion events | `[]` | Commerce | `{}` |
| metrics/pageviews | Page Views | int | Traffic | 0 | true | Total page views | `[]` |  | `{}` |
| metrics/visits | Visits | int | Traffic | 0 | true |  | `[]` |  | `{}` |

## Segments

| id | name | description | rsid | owner_id | definition | compatibility | tags | created | modified | extra |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| s_111 | Mobile Users | Mobile device traffic | demo.prod | 42 | `{"container": {"context": "hits", "func": "container", "pred": {"func": "eq", "val": "mobile"}}, "version": [1, 0, 0]}` | `{}` | `[]` | 2025-01-01T00:00:00Z | 2025-01-02T00:00:00Z | `{}` |
| s_222 | Returning Visitors |  | demo.prod | 42 | `{"container": {"context": "visits", "func": "container", "pred": {"func": "eq", "val": "returning"}}, "version": [1, 0, 0]}` | `{}` | `[]` |  |  | `{}` |

## Calculated Metrics

| id | name | description | rsid | owner_id | polarity | precision | type | definition | tags | categories | extra |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cm_1 | Conversion Rate | Orders divided by visits | demo.prod | 42 | positive | 4 | decimal | `{"formula": {"args": ["metrics/orders", "metrics/visits"], "func": "divide"}}` | `[]` | `["Conversion"]` | `{}` |

## Virtual Report Suites

| id | name | parent_rsid | timezone | description | segment_list | curated_components | modified | extra |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| vrs_eu | EU Visitors Only | demo.prod | Europe/Berlin | EU-only traffic view | `["s_eu"]` | `[]` | 2025-03-01T00:00:00Z | `{}` |

## Classifications

| id | name | rsid | extra |
| --- | --- | --- | --- |
| ds_5 | Campaign Metadata | demo.prod | `{}` |
