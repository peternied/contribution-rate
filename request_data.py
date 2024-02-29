import json
import os
from hashlib import sha256

CACHE_DIR = ".request_cache"  # Directory to store cache files


def get_cache_filename(pr_number, url, last_modified_time):
    """Generate a cache filename for a given pull request number, URL, and last modified time."""
    url_hash = sha256(url.encode("utf-8")).hexdigest()
    # Incorporate the last modified time into the filename
    filename = f"pr_{pr_number}_{url_hash}_{last_modified_time}.json"
    return os.path.join(CACHE_DIR, filename)


def save_to_cache(pr_number, url, data, last_modified_time):
    """Save data to cache with the last modified timestamp as part of the filename."""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)
    cache_filename = get_cache_filename(pr_number, url, last_modified_time)
    with open(cache_filename, "w") as cache_file:
        json.dump(data, cache_file)


def load_from_cache(pr_number, url, last_modified_time):
    """Attempt to load data from cache based on the last modified timestamp."""
    cache_filename = get_cache_filename(pr_number, url, last_modified_time)
    if os.path.exists(cache_filename):
        with open(cache_filename, "r") as cache_file:
            return json.load(cache_file)
    return None


def fetch(pr_number, url, last_modified_time, fetch_function):
    """Fetch PR data from GitHub API or cache, using the last modified timestamp for cache validation."""
    cache_data = load_from_cache(pr_number, url, last_modified_time)
    if cache_data is not None:
        print(
            f"Loading data from cache {get_cache_filename(pr_number, url, last_modified_time)} for PR #{pr_number} and URL '{url}' with timestamp {last_modified_time}."
        )
        return cache_data
    else:
        print(f"Fetching data from GitHub API for PR #{pr_number} and URL '{url}'.")
        api_data = fetch_function(
            url
        )  # This should be an actual function to fetch data from the GitHub API
        save_to_cache(pr_number, url, api_data, last_modified_time)
        return api_data
