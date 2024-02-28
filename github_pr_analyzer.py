import argparse
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import requests

import request_data

# Constants
GITHUB_API_BASE_URL = "https://api.github.com/repos/opensearch-project/opensearch"
GITHUB_PULLS_URL = GITHUB_API_BASE_URL + "/pulls"
HEADERS = {"Accept": "application/vnd.github.v3+json"}
OUTPUT_DIR = "./output/"
PAGE_COUNT_LIMIT=5
ARGS = None
BOTS_TO_IGNORE = ['opensearch-trigger-bot[bot]', 'codecov', 'dependabot[bot]']


def get_pull_requests(since=None, pr_number=None):
    """
    Fetch pull requests from the GitHub API.
    """
    pull_requests = []  # List to store pull requests
    params = {
        "state": "closed",
        "sort": "created",
        "direction": "desc",
        "per_page": 100,
    }

    if since:
        # Ensure 'since' is in ISO 8601 format
        since = datetime.strptime(since, "%Y-%m-%d").isoformat()
        params["since"] = since

    if pr_number:
        # Fetch a specific pull request by number
        response = requests.get(f"{GITHUB_PULLS_URL}/{pr_number}", headers=HEADERS)
        if response.status_code == 200:
            pull_requests.append(response.json())
        else:
            print(f"Error fetching PR #{pr_number}: {response.status_code}")
        return pull_requests

    # Handle pagination for fetching pull requests

    return fetch_github_data(GITHUB_PULLS_URL, params)


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
    url = f"{GITHUB_API_BASE_URL}/issues/{pr_number}/comments"
    comments = request_data.fetch(
        pr_number, url, last_modified_time, fetch_github_data
    )
    return comments

def fetch_pr_events(pr_number, last_modified_time):
    url = f"{GITHUB_API_BASE_URL}/issues/{pr_number}/events"
    events = request_data.fetch(
        pr_number, url, last_modified_time, fetch_github_data
    )
    return events


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
        if row['user']['login'] in BOTS_TO_IGNORE:
            return 'AUTOMATION'
        if row['author_association'] == 'FIRST_TIME_CONTRIBUTOR':
            return 'CONTRIBUTOR'
        return row['author_association']

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
                if event['event'] in ['committed', 'head_ref_force_pushed']
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
                if comment["user"]["login"] in ['github-actions[bot]'] and ':x: Gradle check result' in comment['body']
            )
        )
    df["number_of_gradle_check_failures"] = df.apply(get_number_of_gradle_check_failures, axis=1)
    
    df['user_login'] = df['user'].apply(lambda x: x['login'])

    # Group by week and calculate aggregate metrics
    df.set_index("created_at", inplace=True)

    return df


def print_metrics(raw_metrics):
    pd.set_option('display.float_format', '{:,.1f}'.format)

    weekly_metrics = raw_metrics.resample("W").agg(
        {
            "number": "size",  # Number of PRs
            "business_days_to_merge": "mean",
            "number_of_commenters": "mean",
            "number_of_gradle_check_failures": "mean",
        }
    )
    weekly_metrics.index = weekly_metrics.index.strftime('%Y-%m-%d')

    weekly_metrics_csv = OUTPUT_DIR + "weekly_metrics.csv"
    print(f"Writing weekly_metrics metrics to {weekly_metrics_csv}")
    weekly_metrics.to_csv(weekly_metrics_csv)
    print(weekly_metrics)

    grouped_metrics = (
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
    print(grouped_metrics)

    contributor_metrics = (
        raw_metrics.groupby(['type_of_contribution', 'user_login'])
        .agg(
            {
                "number": "size",
                "business_days_to_merge": "count",
                "business_days_to_merge": "mean",
                "number_of_commenters": "mean",
                "number_of_comments": "mean",
                "number_of_pushes": "mean",
                "number_of_pushes": "mean",
                "number_of_gradle_check_failures": "mean"
            }
        )
        .sort_values(by='number', ascending=False)
        .nlargest(10, ['number'])
        .reset_index()
    )
    with pd.option_context('display.max_rows', None):
        print(contributor_metrics)


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
    parser.add_argument("--page-limit", help="Limit how much data is pulled from GitHub by page count", type=int, default=PAGE_COUNT_LIMIT)
    global ARGS
    ARGS = parser.parse_args()

    HEADERS["Authorization"] = f"Bearer {ARGS.token}"

    ARGS.token = "<HIDDEN>"
    print(f'Arguments: {ARGS}')

    pull_requests = get_pull_requests(ARGS.since, ARGS.pr)
    pr_metrics = calculate_metrics(pull_requests)
    print_metrics(pr_metrics)

if __name__ == "__main__":
    main()
