# Contribution rate

Small python executable to measure details impacting contribution rate for OpenSearch 

## Reports
<!-- REPORTS_START -->
_Updated on May 02, 2024_
- [Latest business_days_to_merge_by_week Report](/reports/20240502/business_days_to_merge_by_week.csv)
- [Latest pull_request_metrics_by_contributor_metrics Report](/reports/20240502/pull_request_metrics_by_contributor_metrics.csv)
- [Latest pull_requests_metrics_by_type_of_contribution Report](/reports/20240502/pull_requests_metrics_by_type_of_contribution.csv)
- [Latest top_test_failures Report](/reports/20240502/top_test_failures.csv)
<!-- REPORTS_END -->

## Usage

```
usage: github_pr_analyzer.py [-h] --token TOKEN [--since SINCE] [--pr PR] [--page-limit PAGE_LIMIT] [--non-github-delay-seconds NON_GITHUB_DELAY_SECONDS] [--github-owner GITHUB_OWNER] [--github-repo GITHUB_REPO]

Analyze GitHub Pull Requests.

options:
  -h, --help            show this help message and exit
  --token TOKEN         GitHub API token
  --since SINCE         Collect PRs updated after this date (YYYY-MM-DD).
  --pr PR               Collect data for a specific PR number.
  --page-limit PAGE_LIMIT
                        Limit how much data is pulled from GitHub by page count
  --non-github-delay-seconds NON_GITHUB_DELAY_SECONDS
                        Delay between requests for non-github sources
  --github-owner GITHUB_OWNER
                        GitHub owner of the repository
  --github-repo GITHUB_REPO
                        GitHub repository
```

### Example output
```
Arguments: Namespace(token='<HIDDEN>', since='2022-01-01', pr=None, page_limit=5)
Starting GET https://api.github.com/repos/opensearch-project/opensearch/pulls...
Starting GET https://api.github.com/repositories/334274271/pulls?state=closed&sort=created&direction=desc&per_page=100&since=2022-01-01T00%3A00%3A00&page=2...
...
Loading data from cache for PR #11541 and URL 'https://api.github.com/repos/opensearch-project/opensearch/issues/11541/comments' with timestamp 2023-12-08T20:28:59Z.
Writing weekly_metrics metrics to ./output/weekly_metrics.csv
                           number  business_days_to_merge  number_of_commenters
created_at                                                                     
2023-12-10 00:00:00+00:00       5                0.000000              2.400000
2023-12-17 00:00:00+00:00      49                3.408333              3.081633
2023-12-24 00:00:00+00:00      24                2.125000              2.500000
2023-12-31 00:00:00+00:00      10               15.750000              3.500000
2024-01-07 00:00:00+00:00      50                3.406915              2.480000
2024-01-14 00:00:00+00:00      50                2.202128              3.000000
2024-01-21 00:00:00+00:00      41                5.572368              2.975610
2024-01-28 00:00:00+00:00      56                2.175926              2.839286
2024-02-04 00:00:00+00:00      62                2.474057              2.677419
2024-02-11 00:00:00+00:00      65                0.788793              2.646154
2024-02-18 00:00:00+00:00      33                1.287500              2.818182
2024-02-25 00:00:00+00:00      41                0.783784              2.731707
2024-03-03 00:00:00+00:00      14                0.329545              2.642857
   number_of_commenters  number  business_days_to_merge  number_of_comments
0                     1      37                0.525000            2.027027
1                     2     215                0.896446            3.786047
2                     3     138                2.842000            6.543478
3                     4      61                4.202830           10.672131
4                     5      31                7.926724           12.806452
5                     6      14                8.375000           21.928571
6                     7       3               13.333333           32.000000
7                     8       1                6.000000           45.000000
```
