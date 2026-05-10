import argparse
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
from club import Club


GG_API_BASE_URL = 'https://www.geoguessr.com/api'
GG_CLUB_ACTIVITIES_ENDPOINT = f'{GG_API_BASE_URL}/v4/clubs/{{club_id}}/activities'
GG_CLUB_ENDPOINT = f'{GG_API_BASE_URL}/v4/clubs/{{club_id}}'
GG_USER_ENDPOINT = f'{GG_API_BASE_URL}/v3/users/{{user_id}}'
GG_USER_PROFILE_URL = 'https://www.geoguessr.com/user/{user_id}'
THROTTLE_TIME_MS = 10
FILTER_OUT_WEEKLIES = True


def main():
    load_dotenv()

    p = argparse.ArgumentParser()

    p.add_argument("--club_id", type=str, required=True)
    p.add_argument("--num_days", type=int, default=29)
    p.add_argument("--include_today_in_avg", action='store_true')
    p.add_argument("--include_member_stats", action='store_true')

    args = p.parse_args()

    items = load_items(args.num_days, args.club_id)

    club = load_club(args.club_id)

    plot_items(items, args.include_today_in_avg, club)

    if args.include_member_stats:
        write_inactivity_report(items, club)

    report_former_members(items, club)


def load_items(num_days: int, club_id: str) -> list[ActivityItem]:
    
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
        activities_url = f"{GG_CLUB_ACTIVITIES_ENDPOINT.format(club_id=club_id)}?limit=25"

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

            # Get the date
            date = activity.recordedAt.split('T')[0]

            # If the days set is already full and this is another day
            if len(days_set) >= num_days and date not in days_set:
                return all_activities

            days_set.add(date)
            all_activities.append(activity)

        if THROTTLE_TIME_MS:
            # Wait before reading the next batch
            time.sleep(THROTTLE_TIME_MS / 1000)

    return all_activities


def load_club(club_id: str) -> Club:
    session = requests.Session()
    gg_api_key = os.getenv('GG_API_KEY')
    session.cookies.set("_ncfa", gg_api_key)

    response = session.get(GG_CLUB_ENDPOINT.format(club_id=club_id))
    data = response.json()

    dacite_config = Config(convert_key=to_camel_case)
    return from_dict(Club, data, dacite_config)

def plot_items(items: list[ActivityItem], include_today_in_average: bool, club: Club):
    # Group by date
    xp_by_date = defaultdict(int)
    for item in items:
        date = datetime.fromisoformat(item.recordedAt).date()
        xp_by_date[date] += item.xpReward
    
    # Sort by date
    dates = sorted(xp_by_date.keys())
    xp_sums = [xp_by_date[d] for d in dates]
    
    xp_sums_for_avg = xp_sums

    if not include_today_in_average:
        xp_sums_for_avg = xp_sums[:-1]

    # Compute average XP
    avg_xp = sum(xp_sums_for_avg) / len(xp_sums_for_avg)

    # Plot
    plt.figure(figsize=(8, 4))
    plt.bar(range(len(dates)), xp_sums, width=1.0, color='skyblue', edgecolor='black')
    plt.axhline(avg_xp, color='red', linestyle='--', linewidth=1.5, label=f'Average ({avg_xp:.1f})')
    plt.axhline(600, color='green', linestyle=':', linewidth=1, label=f'Max')
    plt.xticks(range(len(dates)), [d.isoformat() for d in dates], rotation=90)
    plt.xlabel("Date")
    plt.ylabel("Total XP")
    plt.title(f"Club XP per day — {club.name} [{club.tag}]")
    plt.legend()
    plt.tight_layout()
    plt.savefig("xp_per_day.png", dpi=300)
    plt.close()


def write_inactivity_report(items: list[ActivityItem], club: Club, output_path: str = "inactive_members.txt"):
    # Build lookup tables
    user_id_to_nick = {cm.user.userId: cm.user.nick for cm in club.members}
    all_user_ids = set(user_id_to_nick.keys())

    # Group active userIds by date
    active_by_date: dict[str, set[str]] = defaultdict(set)
    for item in items:
        date = item.recordedAt.split('T')[0]
        active_by_date[date].add(item.userId)

    # Write report
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"Club: {club.name} [{club.tag}]\n\n")
        for date in sorted(active_by_date.keys()):
            inactive_user_ids = all_user_ids - active_by_date[date]

            # Resolve nicks, fall back to userId if necessary
            inactive_nicks = sorted(
                user_id_to_nick.get(user_id, user_id)
                for user_id in inactive_user_ids
            )

            f.write(f"Date: {date}\n")
            if inactive_nicks:
                for nick in inactive_nicks:
                    f.write(f"  - {nick}\n")
            else:
                f.write("  (No inactive members)\n")

            f.write("\n")



def report_former_members(items: list[ActivityItem], club: Club,
                          plot_path: str = "former_members_xp.png",
                          text_path: str = "former_members.txt"):
    current_user_ids = {cm.user.userId for cm in club.members}
    former_user_ids = {item.userId for item in items} - current_user_ids

    if not former_user_ids:
        print("No former members with activity found.")
        return

    # Fetch nicks for former members from the user endpoint
    session = requests.Session()
    session.cookies.set("_ncfa", os.getenv('GG_API_KEY'))

    former_user_info: dict[str, tuple[str, str]] = {}
    for user_id in former_user_ids:
        response = session.get(GG_USER_ENDPOINT.format(user_id=user_id))
        if response.status_code == 404:
            nick = f"[deleted user {user_id}]"
        else:
            nick = response.json().get('nick', user_id)
        profile_url = GG_USER_PROFILE_URL.format(user_id=user_id)
        former_user_info[user_id] = (nick, profile_url)
        if THROTTLE_TIME_MS:
            time.sleep(THROTTLE_TIME_MS / 1000)

    # Text report: nickname + profile link
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(f"Club: {club.name} [{club.tag}]\n\n")
        f.write("Former members with activity in the past period:\n\n")
        for user_id, (nick, profile_url) in sorted(former_user_info.items(), key=lambda kv: kv[1][0].lower()):
            f.write(f"  - {nick}: {profile_url}\n")

    # XP per former member per day
    xp_by_date_by_user: dict[datetime, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for item in items:
        if item.userId in former_user_ids:
            date = datetime.fromisoformat(item.recordedAt).date()
            xp_by_date_by_user[date][item.userId] += item.xpReward

    dates = sorted(xp_by_date_by_user.keys())
    sorted_user_ids = sorted(former_user_ids, key=lambda u: former_user_info[u][0].lower())

    _, ax = plt.subplots(figsize=(10, 5))
    bottom = [0] * len(dates)
    for user_id in sorted_user_ids:
        nick = former_user_info[user_id][0]
        values = [xp_by_date_by_user[d].get(user_id, 0) for d in dates]
        ax.bar(range(len(dates)), values, bottom=bottom, label=nick, edgecolor='black', width=1.0)
        bottom = [b + v for b, v in zip(bottom, values)]

    ax.set_xticks(range(len(dates)))
    ax.set_xticklabels([d.isoformat() for d in dates], rotation=90)
    ax.set_xlabel("Date")
    ax.set_ylabel("XP")
    ax.set_title(f"XP by former members — {club.name} [{club.tag}]")
    ax.legend(bbox_to_anchor=(1.02, 1), loc='upper left')
    plt.tight_layout()
    plt.savefig(plot_path, dpi=300, bbox_inches='tight')
    plt.close()


def to_camel_case(key: str) -> str:
    first_part, *remaining_parts = key.split('_')
    return first_part + ''.join(part.title() for part in remaining_parts)


if __name__ == '__main__':
    main()