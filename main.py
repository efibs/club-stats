from collections import defaultdict
from datetime import datetime
import os
import sys
import time
from dacite import Config, from_dict
from dotenv import load_dotenv
from matplotlib import pyplot as plt
import requests

from activity_item import ActivityItem


GG_API_BASE_URL = 'https://www.geoguessr.com/api'
GG_CLUB_ACTIVITIES_ENDPOINT = f'{GG_API_BASE_URL}/v4/clubs/{sys.argv[1]}/activities'
THROTTLE_TIME_MS = 10
FILTER_OUT_WEEKLIES = True


def main():
    load_dotenv()

    num_days = int(sys.argv[2])

    items = load_items(num_days)

    plot_items(items)


def load_items(num_days: int) -> list[ActivityItem]:
    
    # Get the GG API key
    gg_api_key = os.getenv('GG_API_KEY')

    # Create a session
    session = requests.Session()

    # Set the ncfa cookie on the session
    session.cookies.set("_ncfa", gg_api_key)

    # Build the dacite config
    dacite_config = Config(convert_key=to_camel_case)

    days_set = set()
    all_activities = []
    pagination_token = None

    while len(days_set) <= num_days:
        # Build the final url
        activities_url = f"{GG_CLUB_ACTIVITIES_ENDPOINT}?limit=25"

        if pagination_token:
            activities_url += f"&paginationToken={pagination_token}"

        # Read the activities
        response = session.get(activities_url)

        # Get json data
        data = response.json()

        # Deserialize
        activities = [from_dict(ActivityItem, item, dacite_config) for item in data['items']]

        # Set the pagination token
        pagination_token = data['paginationToken']

        # Print progress
        print('Current date: ', activities[-1].recordedAt)

        # Save activities
        for activity in activities:
            # if the weekly filter is active and the entry is a weekly
            if (FILTER_OUT_WEEKLIES and activity.xpReward == 1000):
                continue

            date = activity.recordedAt.split('T')[0]
            days_set.add(date)
            all_activities.append(activity)

        if THROTTLE_TIME_MS:
            # Wait before reading the next batch
            time.sleep(THROTTLE_TIME_MS / 1000)

    return all_activities


def plot_items(items: list[ActivityItem]):
    # Group by date
    xp_by_date = defaultdict(int)
    for item in items:
        date = datetime.fromisoformat(item.recordedAt).date()
        xp_by_date[date] += item.xpReward
    
    # Sort by date and skip oldest day as it might not be filled
    dates = sorted(xp_by_date.keys())[1:]
    xp_sums = [xp_by_date[d] for d in dates]
    
    # Compute average XP
    avg_xp = sum(xp_sums) / len(xp_sums)

    # Plot
    plt.figure(figsize=(8, 4))
    plt.bar(range(len(dates)), xp_sums, width=1.0, color='skyblue', edgecolor='black')
    plt.axhline(avg_xp, color='red', linestyle='--', linewidth=1.5, label=f'Average ({avg_xp:.1f})')
    plt.xticks(range(len(dates)), [d.isoformat() for d in dates], rotation=90)
    plt.xlabel("Date")
    plt.ylabel("Total XP")
    plt.title("Club XP per day")
    plt.legend()
    plt.tight_layout()
    plt.savefig("xp_per_day.png", dpi=300)
    plt.close()


def to_camel_case(key: str) -> str:
    first_part, *remaining_parts = key.split('_')
    return first_part + ''.join(part.title() for part in remaining_parts)


if __name__ == '__main__':
    main()