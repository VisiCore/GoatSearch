# GoatSearch

![Ian the Goat](https://static.visicoretech.com/img/goatsearch.png)

Modern, distributed observability and security architectures require modern solutions. Welcome to GoatSearch!

## About GoatSearch

GoatSearch allows you to render [Cribl](https://cribl.io) Search results through a [Splunk](https://splunk.com/) search or dashboard! Simply configure your tenant and use the GoatSearch Explorer to craft your first query. Once the results are generated, use them as you would any other data in Splunk.  Don't just think inside the search bar! GoatSearch can do all kinda cool things - like Instant Replays.  Suggestions? Enhancements? Bugs? Cool use cases? [Open an Issue](https://github.com/VisiCore/GoatSearch/issues) or [Submit a Pull Request](https://github.com/VisiCore/GoatSearch/pulls)!

[GoatSearch Overview](https://www.youtube.com/watch?v=j-7lvHqZvhI)

## Get GoatSearch:
- [Download GoatSearch](https://raw.githubusercontent.com/VisiCore/GoatSearch/refs/heads/main/release/dist/GoatSearch-latest.tgz)
- [Older Versions](https://github.com/VisiCore/GoatSearch/tree/main/release/dist)

## GoatSearch Details:

Welcome to GoatSearch! The `goatsearch` command allows you to run Cribl KQL searches through a Splunk search bar to  view search results, add to dashboards, and use in alerts!

Unsure how to use GoatSearch? Hey, we gotchu! We've built the GoatSearch Explorer dashboard to guide crafting a `goatsearch`. Simply configure your tenant, select your dataset, and let Explorer guide your syntax!

Need help configuring your Cribl tenant? Check out our [GoatSearch Credentials](https://youtu.be/kmNcNLcbFWo) tutorial! The tutorial is also linked from the setup page.

Want to see the new features in 1.1.0? Check our [GoatSearch 1.1.0 Release Notes](https://www.youtube.com/watch?v=olBvx2z-IHg)

Here is a list of the `goatsearch` options available as of version 1.1.0:

- `query`: This string contains the KQL query to execute. If `query` and `sid` are missing, `goatsearch` returns a list of available datasets.
- `sid`: Instead of running a new search, `sid` allows you to pass a Cribl Search ID to retrieve results from an existing search. `sid` will take priority over `query` if both are passed.
- `tenant`: Specifies the tenant to query. Tenants must be configured on the Setup page, and omitting `tenant` will use the default - if configured.
- `workspace`: Specifies the workspace to query. If omitted, `workspace` defaults to `main`.
- `earliest`: Specifies the relative time modifier or absolute epoch time of the earliest event to retrieve. If omitted, defaults to the time range picker. Must be Cribl KQL format - not SPL.
- `latest`: Specifies the relative time modifier or absolute epoch time of the latest event to retrieve. If omitted, defaults to the time range picker. Must be Cribl KQL format - not SPL.
- `sample`: Specifies the sample ratio. For a 1:100 sample ratio, use `100`. Defaults to `1`.
- `page`: Specifies the page size for API calls. Only tune this if you are on a high-latency network.
- `retry`: Specifies the number of search retries before giving up if execution or queuing fails. Retries are separated by a hard-limit of 5 seconds. Defaults to `10`.
- `debug`: Boolean - see how the sausage is made. Maybe wish you hadn't. Debug messages are assigned sourcetype `goatsearch:json`

The GoatSearch package also has a `goatpass` command. It handles passwords (client secrets) and that's all we're gonna tell you. If you want to figure it out be our guest - however long that takes will be infinitely longer than just letting it do its thing.

## Version History
### 1.1.0 (July 17, 2025)
[Release notes video walkthrough](https://www.youtube.com/watch?v=olBvx2z-IHg)

#### Enhancements:
- Applies Cribl parser/field extractions to search results
- Allows searching by SID
- `goatsearch` command now respects earliest and latest parameters
- Better processing of KQL transforming commands (`summarize`, `project`, `top-talkers`)
- Dataset previews on GoatSearch Explorer
- Roles/Capabilities to use GoatSearch and configure tenants (`goatsearch_user`, `goatsearch_admin`)
- `goatsearch` command now respects retry keyword to buffer multiple concurrent searches

#### Bug Fixes
- Corrects an issue where certain expected metadata fields were not present in the Cribl Search results
- Corrects an issue where searches fail inexplicably due to Cribl Search limits
- Corrects an issue where multiple Cribl Searches are instantiated but only one actioned

### 1.0.11 (July 17, 2025)
1.1.0 RC 2

### 1.0.10 (July 17, 2025)
1.1.0 RC 1

### 1.0.1 (July 10, 2025)
#### Bug Fixes
- Corrects an issue where datasets will not populate on non-default workspaces
- Corrects an issue in retrieving results where _raw is not a JSON object.

### 1.0.0 (July 4, 2025)
The official 1.0.0 release of GoatSearch is here bringing you:

#### Features:
- Configured datasets now appear on GoatSearch Explorer
- Default settings for tenant and workspace
- Events on the Splunk search timeline 
- Dropdowns for sample ratio and API page size

#### Bug Fixes:
- Search icon from settings now properly links to and populates GoatSearch Explorer
- Cancel button in settings now works 😅
- Chased off a little debug token from the Explorer
- At times, buttons would not reset on settings when a no-refresh-needed setting changed
- passwords.conf is now pruned when deleting a GoatSearch tenant.

### 0.10.3 (July 1, 2025)
#### Features:
- Adds GoatSearch Explorer

#### Bug Fixes:
- Corrects an issue with sample ratio/API expected format

### 0.10.2 (July 1, 2025)
Initial Release

## Notes for Developers
If you want to contribute to GoatSearch, please consider the following:
1. All pull requests must be validated against the original Cribl search. Event counts and fields must match over any time period.
2. Existing functionality must not break.
3. Make sure that you ignore the `$APP_HOME/release` directory from both builds and AppInspect packages. You can use the Duck Off! feature in [Duck Yeah!](https://splunkbase.splunk.com/app/7015). We recommend Duck Yeah! to validate your builds.
4. Do not remove contributor information from the headers.
