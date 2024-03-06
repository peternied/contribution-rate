import argparse
import re
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import requests

import request_cache

# Constants
HEADERS = {"Accept": "application/vnd.github.v3+json"}
OUTPUT_DIR = "./output/"
PAGE_COUNT_LIMIT = 5
ARGS = None
BOTS_TO_IGNORE = ["opensearch-trigger-bot[bot]", "codecov", "dependabot[bot]"]


def github_url():
    return f"https://api.github.com/repos/{ARGS.github_owner}/{ARGS.github_repo}"


def get_pull_requests(since=None, pr_number=None):
    """
    Fetch pull requests from the GitHub API.
    """
    pull_requests = []  # List to store pull requests
    params = {
        "state": "closed",
        "sort": "created",
        "direction": "desc",
        "per_page": 25,
    }

    if since:
        # Ensure 'since' is in ISO 8601 format
        since = datetime.strptime(since, "%Y-%m-%d").isoformat()
        params["since"] = since

    if pr_number:
        # Fetch a specific pull request by number
        response = requests.get(f"{github_url()}/pulls/{pr_number}", headers=HEADERS)
        if response.status_code == 200:
            pull_requests.append(response.json())
        else:
            print(f"Error fetching PR #{pr_number}: {response.status_code}")
        return pull_requests

    # Handle pagination for fetching pull requests

    return fetch_github_data(f"{github_url()}/pulls", params)


def fetch_github_data(url, params=None):
    """
    Fetches data from GitHub API handling pagination automatically.

    Parameters:
    - url: The initial URL to fetch data from.
    - headers: The headers to include in the request, typically including authorization.

    Returns:
    A list of items fetched from GitHub.
    """
    all_data = []
    pages = 1
    while True:
        print(f"Starting GET {url}...")
        response = requests.get(url, headers=HEADERS, params=params)
        if response.status_code != 200:
            print(f"Error fetching data: {response.status_code}")
            break
        page_data = response.json()
        if not page_data:
            break  # Break the loop if no more data are returned
        all_data.extend(page_data)

        # GitHub provides the next page URL in the link header
        if "next" not in response.links:
            break
        url = response.links["next"]["url"]  # Update the URL to fetch the next page
        pages += 1
        if pages == ARGS.page_limit:
            print(f"Leaving early for easy of debugging")
            break

    print(f"Load data from github from URL '{url}' in {pages} pages.")
    return all_data


def fetch_pr_comments(pr_number, last_modified_time):
    url = f"{github_url()}/issues/{pr_number}/comments"
    comments = request_cache.fetch(pr_number, url, last_modified_time, fetch_github_data)
    return comments


def fetch_pr_events(pr_number, last_modified_time):
    url = f"{github_url()}/issues/{pr_number}/events"
    events = request_cache.fetch(pr_number, url, last_modified_time, fetch_github_data)
    return events


def fetch_test_results(base_url, pr_number, last_modified_time):
    url = f"{base_url}/testReport/api/json?tree=suites[cases[status,className,name]]"
    test_results = request_cache.fetch(
        pr_number, url, last_modified_time, fetch_json_data
    )
    return test_results


def fetch_json_data(url):
    print(
        f"Starting GET {url} after delay of {ARGS.non_github_delay_seconds} seconds ..."
    )
    time.sleep(ARGS.non_github_delay_seconds)
    response = requests.get(url, headers=HEADERS, params=None)
    if response.status_code != 200:
        return {}
    try:
        return response.json()
    except:
        return {}


def calculate_metrics(pull_requests):
    """
    Calculate metrics for each pull request and aggregate them by week.
    """
    # Create a DataFrame from the pull request data
    df = pd.DataFrame(pull_requests)

    # print(f'Pull request data source columns: {df.columns}')

    # Ensure 'created_at' and 'merged_at' are datetime objects
    df["created_at"] = pd.to_datetime(df["created_at"])
    df["merged_at"] = pd.to_datetime(df["merged_at"])

    def categorize_contribution(row):
        if row["user"]["login"] in BOTS_TO_IGNORE:
            return "AUTOMATION"
        if row["author_association"] == "FIRST_TIME_CONTRIBUTOR":
            return "CONTRIBUTOR"
        return row["author_association"]

    df["type_of_contribution"] = df.apply(categorize_contribution, axis=1)

    # Calculate business hours from open to merged
    df["business_days_to_merge"] = df.apply(
        lambda row: (
            simplified_business_days(row["created_at"], row["merged_at"])
            if pd.notnull(row["created_at"]) and pd.notnull(row["merged_at"])
            else np.nan
        ),
        axis=1,
    )

    df["number_of_commenters"] = df.apply(
        lambda row: (
            len(
                set(
                    comment["user"]["login"]
                    for comment in fetch_pr_comments(row["number"], row["updated_at"])
                    if comment["user"]["login"] not in BOTS_TO_IGNORE
                )
            )
            if pd.notnull(row["updated_at"])
            else np.nan
        ),
        axis=1,
    )

    df["number_of_comments"] = df.apply(
        lambda row: (
            len(
                list(
                    comment
                    for comment in fetch_pr_comments(row["number"], row["updated_at"])
                    if comment["user"]["login"] not in BOTS_TO_IGNORE
                )
            )
            if pd.notnull(row["updated_at"])
            else np.nan
        ),
        axis=1,
    )

    def get_number_of_pushes(row):
        if pd.isnull(row["updated_at"]):
            return np.nan

        return len(
            list(
                event
                for event in fetch_pr_events(row["number"], row["updated_at"])
                if event["event"] in ["committed", "head_ref_force_pushed"]
            )
        )

    df["number_of_pushes"] = df.apply(get_number_of_pushes, axis=1)

    def get_number_of_gradle_check_failures(row):
        if pd.isnull(row["updated_at"]):
            return np.nan

        return len(
            list(
                comment
                for comment in fetch_pr_comments(row["number"], row["updated_at"])
                if comment["user"]["login"] in ["github-actions[bot]"]
                and ":x: Gradle check result" in comment["body"]
            )
        )

    df["gradle_check_failures"] = df.apply(get_number_of_gradle_check_failures, axis=1)

    def filter_to_test_failures(test_results):
        if not (isinstance(test_results, dict)) or len(test_results) != 2:
            return []

        all_cases = [
            case for suite in test_results["suites"] for case in suite["cases"]
        ]
        failed_cases = [
            f"{case['className']}.{case['name']}"
            for case in all_cases
            if case["status"] in ["FAILED", "REGRESSION"]
        ]
        return failed_cases

    def get_failing_tests(row):
        if pd.isnull(row["updated_at"]):
            return np.nan

        failing_check_urls = list(
            extract_url(comment["body"])
            for comment in fetch_pr_comments(row["number"], row["updated_at"])
            if comment["user"]["login"] in ["github-actions[bot]"]
            and ":x: Gradle check result" in comment["body"]
        )
        list_of_failing_tests = [
            failure
            for failing_check_url in failing_check_urls
            for failure in filter_to_test_failures(
                fetch_test_results(failing_check_url, row["number"], row["updated_at"])
            )
        ]
        return list_of_failing_tests

    df["failing_tests"] = df.apply(get_failing_tests, axis=1)

    df["user_login"] = df["user"].apply(lambda x: x["login"])

    # Group by week and calculate aggregate metrics
    df.set_index("created_at", inplace=True)

    return df


def extract_url(comment_string):
    pattern = r"\[.*?\]\((https?://[^\s]+)\)"
    match = re.search(pattern, comment_string)

    if match:
        return match.group(
            1
        )  # group(1) refers to the matched URL inside the parentheses
    else:
        return None


def print_metrics(raw_metrics):
    pd.set_option("display.float_format", "{:,.1f}".format)

    weekly_metrics = (
        raw_metrics.groupby("type_of_contribution")
        .resample("W")
        .agg(
            {
                "number": "size",  # Number of PRs
                "business_days_to_merge": "sum",
                "number_of_commenters": "sum",
                "gradle_check_failures": "sum",
            }
        )
    )
    weekly_metrics = weekly_metrics.reset_index()
    weekly_metrics["created_at"] = weekly_metrics["created_at"].dt.strftime("%Y-%m-%d")

    weekly_metrics_csv = OUTPUT_DIR + "business_days_to_merge_by_week.csv"
    print(f"Writing weekly_metrics metrics to {weekly_metrics_csv}")
    weekly_metrics.to_csv(weekly_metrics_csv, index=False)
    print(weekly_metrics)

    prs_by_type_of_contribution_metrics = (
        raw_metrics.groupby("type_of_contribution")
        .agg(
            {
                "number": "size",
                "business_days_to_merge": "count",
                "business_days_to_merge": "mean",
                "number_of_commenters": "mean",
                "number_of_comments": "mean",
            }
        )
        .reset_index()
    )
    print(prs_by_type_of_contribution_metrics)
    prs_by_type_of_contribution_metrics_csv = OUTPUT_DIR + "pull_requests_metrics_by_type_of_contribution.csv"
    prs_by_type_of_contribution_metrics.to_csv(prs_by_type_of_contribution_metrics_csv, index=False)

    contributor_metrics = (
        raw_metrics.groupby(["type_of_contribution", "user_login"])
        .agg(
            {
                "number": "size",
                "business_days_to_merge": "count",
                "business_days_to_merge": "mean",
                "number_of_commenters": "mean",
                "number_of_comments": "mean",
                "number_of_pushes": "mean",
                "number_of_pushes": "mean",
                "gradle_check_failures": "mean",
            }
        )
        .sort_values(by="number", ascending=False)
        .reset_index()
    )
    with pd.option_context("display.max_rows", 10):
        print(contributor_metrics)
    contributor_metrics_csv = OUTPUT_DIR + "pull_request_metrics_by_contributor_metrics.csv"
    contributor_metrics.to_csv(contributor_metrics_csv, index=False)

    # Capture test failures within the past 30 days
    one_month_ago = datetime.now() - timedelta(days=30)
    failing_test_exploded = raw_metrics.explode("failing_tests").reset_index()
    failing_test_exploded["created_at_date"] = pd.to_datetime(
        failing_test_exploded["created_at"]
    ).dt.tz_localize(None)
    failing_test_exploded = failing_test_exploded[
        failing_test_exploded["created_at_date"] >= one_month_ago
    ]

    failures_by_prs = (
        failing_test_exploded.groupby("failing_tests")["number"]
        .apply(list)
        .reset_index(name="pr_numbers")
    )
    failures_by_prs["unique_pr_count"] = failures_by_prs["pr_numbers"].apply(
        lambda x: len(set(x))
    )
    failures_by_prs["pr_numbers"] = failures_by_prs["pr_numbers"].apply(
        lambda pr_list: ["#" + str(pr) for pr in pr_list]
    )
    top_test_impacting_prs = failures_by_prs[
        failures_by_prs["unique_pr_count"] >= 2
    ].nlargest(20, "unique_pr_count")

    # Make sure the pr_numbers column is last since it takes up so much space
    columns_order = [col for col in top_test_impacting_prs.columns if col != 'pr_numbers'] + ['pr_numbers']
    top_test_impacting_prs = top_test_impacting_prs[columns_order]

    top_test_impacting_prs_csv = OUTPUT_DIR + "top_test_failures.csv"
    print(f"Writing top test impacting metrics to {top_test_impacting_prs_csv}")
    top_test_impacting_prs.to_csv(top_test_impacting_prs_csv, index=False)
    print(top_test_impacting_prs)


def simplified_business_hours(start, end):
    """
    Calculate business hours assuming 8 business hours per weekday between start and end datetime objects.
    """
    # Count each day from start to end
    current_day = start.date()
    end_day = end.date()

    total_business_hours = 0

    while current_day <= end_day:
        if start.weekday() < 5:  # Monday to Friday are considered weekdays
            # For the first day, add hours based on the time of day, assuming 8 hours per day
            if current_day == start.date():
                # If it starts on a weekday, assume it's a full business day
                total_business_hours += 8
            # For the last day, only add the remaining hours if it's the same day
            elif current_day == end.date():
                # Subtract the start day hours if end is on the same day
                if start.date() == end.date():
                    total_business_hours -= 8  # Remove the full day added initially
                    # Add the actual hours from start to end on the same day
                    hours = (end - start).seconds // 3600
                    total_business_hours += hours
            else:
                # Any full day in between is considered a full business day
                total_business_hours += 8
        current_day += timedelta(days=1)  # Move to the next day

    # Adjust for the start and end being on the same day but outside business hours
    if start.date() == end.date() and start.weekday() < 5:
        # If both start and end are on the same day, calculate the difference
        hours = (end - start).seconds // 3600
        total_business_hours = min(hours, 8)  # Ensure it doesn't exceed a business day

    return total_business_hours


def simplified_business_days(start, end):
    return simplified_business_hours(start, end) / 8


def main():
    parser = argparse.ArgumentParser(description="Analyze GitHub Pull Requests.")
    parser.add_argument("--token", type=str, required=True, help="GitHub API token")
    parser.add_argument(
        "--since", help="Collect PRs updated after this date (YYYY-MM-DD)."
    )
    parser.add_argument("--pr", help="Collect data for a specific PR number.", type=int)
    parser.add_argument(
        "--page-limit",
        help="Limit how much data is pulled from GitHub by page count",
        type=int,
        default=PAGE_COUNT_LIMIT,
    )
    parser.add_argument(
        "--non-github-delay-seconds",
        help="Delay between requests for non-github sources",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--github-owner",
        help="GitHub owner of the repository",
        default="opensearch-project",
    )
    parser.add_argument("--github-repo", help="GitHub repository", default="opensearch")

    global ARGS
    ARGS = parser.parse_args()

    HEADERS["Authorization"] = f"Bearer {ARGS.token}"

    ARGS.token = "<HIDDEN>"
    print(f"Arguments: {ARGS}")

    pull_requests = get_pull_requests(ARGS.since, ARGS.pr)
    pr_metrics = calculate_metrics(pull_requests)
    print_metrics(pr_metrics)


if __name__ == "__main__":
    main()
