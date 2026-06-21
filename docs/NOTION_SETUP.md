# Notion Setup Guide

This guide walks you through setting up the Notion integration for `aa_auto_sdr` from scratch. By the end you will be able to run `aa_auto_sdr <RSID> --format notion` and see a Notion page appear under a parent page you control.

For the full command reference, see [CLI_REFERENCE.md](CLI_REFERENCE.md#notion-integration). For environment variable details, see [CONFIGURATION.md](CONFIGURATION.md#notion-integration-optional).

## What you need

Before you start, confirm that you have the following:

- A Notion workspace where you have permission to create pages and integrations.
- A parent page in that workspace where the SDR pages will be created. You can use an existing page or create a new one.
- Optionally, a Notion database to use as the SDR Registry. The registry is a queryable index of every report suite you have published. It is not required for the basic `--format notion` flow.

## 1. Install the notion extra

The Notion integration is an optional extra. Install it before running any Notion commands:

```bash
uv pip install 'aa-auto-sdr[notion]'
```

If you run `aa_auto_sdr <RSID> --format notion` without installing the extra, the tool prints this message to stderr and exits:

```
Error: Notion output requires the notion extra.
Install it with: uv pip install 'aa-auto-sdr[notion]'
```

## 2. Create a Notion internal integration

1. Go to [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations) (or open Notion, go to **Settings and members**, and click **Integrations**).
2. Click **New integration**.
3. Give it a name (for example, "aa_auto_sdr") and select your workspace.
4. Click **Submit**. Notion shows you the integration's **Internal Integration Token**.
5. Copy the token. It starts with `secret_`.
6. Set it as an environment variable:

```bash
export NOTION_TOKEN=secret_...
```

Keep this token private. It has access to every page and database that the integration is invited to.

## 3. Share a parent page with the integration

SDR pages are created as children of a parent page. The integration must be explicitly invited to that page or it will receive a 401 or 403 response. This is the step most people miss.

1. Create a new page in Notion (or pick an existing one) to serve as the parent.
2. Open the page. Click **Share** in the top-right corner.
3. In the **Connections** section (or **Add connection** depending on your Notion version), search for the integration name you created in step 2 and select it.
4. Confirm the connection.

The page is now shared with the integration.

### Get the parent page ID

The page ID is the 32-character hexadecimal string at the end of the page URL. For example:

```
https://www.notion.so/My-Parent-Page-abc123def456abc123def456abc123de
                                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
```

The ID is `abc123def456abc123def456abc123de`. Copy it and set it:

```bash
export NOTION_PARENT_PAGE_ID=abc123def456abc123def456abc123de
```

## 4. Optional: set up the SDR Registry database

The SDR Registry is a Notion database that holds one row per report suite you have published. It gives you a queryable overview of every RSID, its component counts, the last time it was updated, and a direct link to its detail page. If you do not need this, skip to step 5.

### Create the database

1. In Notion, create a new full-page database (not an inline one). Give it a name like "AA SDR Registry".
2. Keep it as a standard single-data-source database.
3. Share it with your integration the same way you shared the parent page: **Share**, then **Add connection**, then pick your integration.

### Add the required properties

Run the following command to see the exact property names and types that the tool expects:

```bash
aa_auto_sdr --notion-print-database-schema
```

The output lists required properties and optional properties. Create each required property in your database using the exact name and type shown. For example, `RSID` must be a **Text** (rich_text) property and `Last Updated` must be a **Date** property.

The tool can also add missing properties for you. After creating the database with at least the `Name` (title) property, run:

```bash
aa_auto_sdr --notion-repair-database --yes
```

This compares the live database against the canonical schema and adds any missing properties. It never changes existing property types or removes properties you have added.

### Get the database ID

The database ID is the 32-character string in the database URL, in the same position as the page ID:

```
https://www.notion.so/abc123def456abc123def456abc123de?v=...
                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
```

Set it:

```bash
export NOTION_REGISTRY_DATABASE_ID=abc123def456abc123def456abc123de
```

### Multi-organization registry

If you manage multiple Adobe Analytics organizations and want to track them all in one database, use `--notion-company` (or `NOTION_REGISTRY_COMPANY`) to tag each row with an organization name. When set, the registry row key becomes `(Company, RSID)` instead of RSID alone, which prevents collisions when two organizations share an RSID name.

For the full meaning of each Notion environment variable, see [CONFIGURATION.md](CONFIGURATION.md#notion-integration-optional).

## 5. First run

With `NOTION_TOKEN` and `NOTION_PARENT_PAGE_ID` set, run:

```bash
aa_auto_sdr <RSID> --format notion
```

What happens:

- The tool fetches the report suite from the Adobe Analytics 2.0 API.
- It creates a Notion page under your parent page, titled with the report suite name and RSID.
- It writes the page ID to `.notion_pages.json` in the current directory (or `--output-dir` if specified).

On success, open Notion and check your parent page. A new child page should be there.

Re-running the same command updates the existing page in place. The tool reads the page ID from `.notion_pages.json` and sends an update request rather than creating a duplicate.

If you also have `NOTION_REGISTRY_DATABASE_ID` set, the run adds or updates one row in the registry database after writing the detail page.

## 6. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `Error: Notion output requires the notion extra.` | `notion-client` not installed | Run `uv pip install 'aa-auto-sdr[notion]'` |
| `Error: NOTION_TOKEN is not set.` | Env var missing or not exported | `export NOTION_TOKEN=secret_...` |
| `Error: NOTION_PARENT_PAGE_ID is not set.` | Env var missing or not exported | `export NOTION_PARENT_PAGE_ID=<page-id>` |
| 401 or 403 when writing the detail page | Integration not invited to the parent page | Open the parent page in Notion, Share, Add connection, pick the integration |
| 401 or 403 for the registry database | Integration not invited to the database | Open the database, Share, Add connection, pick the integration |
| Cannot find the page or database ID | Unsure where to look | Copy the URL from Notion. The 32-character hex string at the end of the path (before any `?v=` query string) is the ID |

## Next steps

- [CLI_REFERENCE.md — Notion Integration](CLI_REFERENCE.md#notion-integration): all commands, registry flags, maintenance modes (`--notion-prune-orphans`, `--notion-repair-database`), watch mode, and batch publishing.
- [CONFIGURATION.md — Notion Integration](CONFIGURATION.md#notion-integration-optional): the full environment variable table and credential resolution order.
