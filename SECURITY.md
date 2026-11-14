# Security Policy

## Supported versions

Security fixes are applied to the latest released version of `aa-auto-sdr`.
Upgrade to the newest release before reporting an issue that may already have
been fixed.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting for this repository:

<https://github.com/brian-a-au/aa_auto_sdr/security/advisories/new>

Private reporting is turned on, so you can open a report without access to
the repository.

Do not open a public issue for a suspected vulnerability. Include the affected
version, impact, reproduction steps or a proof of concept, and any suggested
mitigation. Please remove Adobe credentials, access tokens, organization IDs,
Notion tokens, report suite data, and other sensitive information from the
report.

You should receive an acknowledgement through the private advisory within
seven days. Confirmed issues will be coordinated there until a fix and
disclosure are ready.

## Threat model notes

These notes describe what the tool protects and where its limits are.

- **Read only access to Adobe Analytics.** The tool calls only read methods of
  the Adobe Analytics 2.0 API. It never changes data in an Adobe org. A meta
  test fails the build if code under `src/aa_auto_sdr/api/` calls a write
  method. A way to make the tool change data in Adobe is in scope for this
  policy.
- **Credentials.** The tool supports OAuth Server-to-Server only. It reads
  credentials from a profile under `~/.aa/orgs/`, from environment variables,
  from `config.json`, or from a `.env` file. The repository ignores
  `config.json` and `.env` files in git. Profiles and `config.json` are plain
  JSON files. Protect them with file permissions on your own machine.
- **Logs and error messages.** The tool removes bearer tokens, the
  `Authorization` header, `client_secret`, and `access_token` values from log
  output and from exception text. `--show-config` masks sensitive fields. A
  case where a secret still reaches a log file, the console, or an error
  envelope is in scope.
- **Generated output.** SDR files, snapshots, and diffs contain the names and
  descriptions of components from the report suite. Treat them as customer
  data. The HTML writer escapes all text that comes from Adobe. A way to run
  script in a browser through a generated HTML report is in scope.
- **Outbound connections.** The tool connects to Adobe APIs. It connects to
  the Notion API only when you turn on Notion publishing. It pushes to a git
  remote only when you pass `--git-push`, and it uses the remote you set up in
  your snapshot repository.
