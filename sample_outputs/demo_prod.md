# SDR — Demo Production (demo.prod)

> Captured at 2026-04-26T12:00:00+00:00 · tool version 1.0.0

## Coverage

| Family | State | Count | Expansion level |
| --- | --- | --- | --- |
| Dimensions | Collected | 4 |  |
| Metrics | Collected | 3 |  |
| Segments | Collected | 2 |  |
| Calculated Metrics | Collected | 1 |  |
| Virtual Report Suites | Collected | 1 |  |
| Classifications | Collected | 1 |  |

## Quality

No quality audit ran.

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

| id | name | description | rsid | owner_id | definition | compatibility | tags | created | modified | extra | definition_summary | metric_references | segment_references |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| s_111 | Mobile Users | Mobile device traffic | demo.prod | 42 | `{"container": {"context": "hits", "func": "container", "pred": {"func": "streq", "str": "mobile", "val": {"func": "attr", "name": "variables/evar2"}}}, "func": "segment", "version": [1, 0, 0]}` | `{}` | `[]` | 2025-01-01T00:00:00Z | 2025-01-02T00:00:00Z | `{}` | `Hit where variables/evar2 = 'mobile'` |  |  |
| s_222 | Returning Visitors |  | demo.prod | 42 | `{"container": {"context": "visits", "func": "container", "pred": {"func": "and", "preds": [{"func": "gt", "num": 1, "val": {"func": "attr", "name": "variables/visitnumber"}}, {"evt": {"func": "event", "name": "metrics/pageviews"}, "func": "event-exists"}]}}, "func": "segment", "version": [1, 0, 0]}` | `{}` | `[]` |  |  | `{}` | `Visit where variables/visitnumber > 1 AND metrics/pageviews exists` | metrics/pageviews |  |

## Calculated Metrics

| id | name | description | rsid | owner_id | polarity | precision | type | definition | tags | categories | extra | formula_summary | metric_references | segment_references |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cm_1 | Conversion Rate | Orders divided by visits | demo.prod | 42 | positive | 4 | decimal | `{"formula": {"col1": {"func": "metric", "name": "metrics/orders"}, "col2": {"func": "segment", "metric": {"func": "metric", "name": "metrics/visits"}, "segment_id": "s_222"}, "func": "divide"}, "func": "calc-metric", "version": [1, 0, 0]}` | `[]` | `["Conversion"]` | `{}` | `metrics/orders / metrics/visits[segment s_222]` | metrics/orders, metrics/visits | s_222 |

## Virtual Report Suites

| id | name | parent_rsid | timezone | description | segment_list | curated_components | modified | extra |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| vrs_eu | EU Visitors Only | demo.prod | Europe/Berlin | EU-only traffic view | `["s_eu"]` | `[]` | 2025-03-01T00:00:00Z | `{}` |

## Classifications

| id | name | rsid | extra |
| --- | --- | --- | --- |
| ds_5 | Campaign Metadata | demo.prod | `{}` |

## References

| Family | ID | Name | Relation | Kind | Target Family | Target ID | Target Name | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Calculated Metrics | cm_1 | Conversion Rate | references | metric | Metrics | metrics/orders | Orders | resolved |
| Calculated Metrics | cm_1 | Conversion Rate | references | metric | Metrics | metrics/visits | Visits | resolved |
| Calculated Metrics | cm_1 | Conversion Rate | references | segment | Segments | s_222 | Returning Visitors | resolved |
| Segments | s_222 | Returning Visitors | references | metric | Metrics | metrics/pageviews | Page Views | resolved |
| Segments | s_222 | Returning Visitors | referenced by |  | Calculated Metrics | cm_1 | Conversion Rate | resolved |
| Virtual Report Suites | vrs_eu | EU Visitors Only | references | segment |  | s_eu |  | unresolved |
