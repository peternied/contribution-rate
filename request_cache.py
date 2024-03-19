import json
import os
from hashlib import sha256

class RequestCache(object):

    CACHE_DIR = ".request_cache"  # Directory to store cache files

    SAVE_COUNT = 0
    HIT_COUNT = 0
    MISS_COUNT = 0

    def get_cache_filename(self, pr_number, url, last_modified_time):
        """Generate a cache filename for a given pull request number, URL, and last modified time."""
        url_hash = sha256(url.encode("utf-8")).hexdigest()
        # Incorporate the last modified time into the filename
        filename = f"pr_{pr_number}/{last_modified_time}_{url_hash}.json"
        return os.path.join(self.CACHE_DIR, filename)


    def save_to_cache(self, pr_number, url, data, last_modified_time):
        """Save data to cache with the last modified timestamp as part of the filename."""
        if not os.path.exists(self.CACHE_DIR):
            os.makedirs(self.CACHE_DIR)
        cache_filename = self.get_cache_filename(pr_number, url, last_modified_time)
        os.makedirs(os.path.dirname(cache_filename), exist_ok=True)
        with open(cache_filename, "w") as cache_file:
            json.dump(data, cache_file)
        self.SAVE_COUNT = 1 + self.SAVE_COUNT


    def load_from_cache(self, pr_number, url, last_modified_time):
        """Attempt to load data from cache based on the last modified timestamp."""
        cache_filename = self.get_cache_filename(pr_number, url, last_modified_time)
        if os.path.exists(cache_filename):
            with open(cache_filename, "r") as cache_file:
                self.HIT_COUNT = 1 + self.HIT_COUNT
                return json.load(cache_file)
        return None


    def clear_cache(self):
        """Clear the cache contents"""
        if os.path.exists(self.CACHE_DIR):
            os.removedirs(self.CACHE_DIR)
        self.SAVE_COUNT = 0
        self.HIT_COUNT = 0
        self.MISS_COUNT = 0

    def stats(self):
        return {
            "hits": self.HIT_COUNT,
            "misses": self.MISS_COUNT,
            "stores": self.SAVE_COUNT,
        }


    def fetch(self, pr_number, url, last_modified_time, fetch_function):
        """Fetch PR data from GitHub API or cache, using the last modified timestamp for cache validation."""
        cache_data = self.load_from_cache(pr_number, url, last_modified_time)
        if cache_data is not None:
            print(
                f"Loading data from cache {self.get_cache_filename(pr_number, url, last_modified_time)} for PR #{pr_number} and URL '{url}' with timestamp {last_modified_time}."
            )
            return cache_data
        else:
            print(f"Fetching data from GitHub API for PR #{pr_number} and URL '{url}'.")
            self.MISS_COUNT = 1 + self.MISS_COUNT
            api_data = fetch_function(
                url
            )  # This should be an actual function to fetch data from the GitHub API
            self.save_to_cache(pr_number, url, api_data, last_modified_time)
            return api_data
