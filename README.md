event-calendar-sync
Private GitHub Actions project that finds matching concerts and public social or fitness events, removes duplicates, and adds new events to an iCloud Calendar through CalDAV.
Ryan's default markets are Las Vegas, Los Angeles, San Diego, and San Francisco. The default target calendar is Concert + Social Alerts.
What It Uses
Ticketmaster Discovery API for music events
Bandsintown artist events API for music events
Public webpages with schema.org JSON-LD Event data for run clubs, track nights, fitness, wellness, community, and meetup-style events
iCloud Calendar CalDAV for writing events
Optional Discord webhook summaries
The project only reads official APIs, public webpages, public JSON-LD metadata, RSS, or ICS-style public data. It does not log in to private feeds, scrape private app pages, or bypass access controls.
Setup
In Apple Calendar, create a calendar named Concert + Social Alerts.

Generate an Apple app-specific password at appleid.apple.com.

In your private GitHub repository, add these GitHub Actions secrets:
ICLOUD_USERNAME: your Apple ID email
ICLOUD_APP_PASSWORD: your Apple app-specific password
TICKETMASTER_API_KEY: your Ticketmaster API key
BANDSINTOWN_APP_ID: your Bandsintown app id
TARGET_CALENDAR_NAME: optional, defaults to Concert + Social Alerts
ICLOUD_CALDAV_URL: optional, defaults to https://caldav.icloud.com
DISCORD_WEBHOOK_URL: optional

Copy config.example.yml to config.yml if you want to customize artists, cities, or public event pages.

Open the GitHub Actions tab, choose Event Calendar Sync, and run it manually with dry_run=true.

Review the logs. Dry runs print event titles, dates, and public links, but do not write to iCloud.

Run the workflow again with dry_run=false.

Confirm new events appear in Apple Calendar and TapCal.

Local Test Run
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src pytest
On Windows PowerShell:
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PYTHONPATH = "src"
pytest
Configuration
config.example.yml includes Ryan's artist watchlist and markets. Add public pages like this:
public_urls:
  - https://example.com/events
Public pages are used only when they are publicly reachable and include valid schema.org JSON-LD Event metadata with a date and location.
Safety Notes
Secrets are read only from environment variables or GitHub Actions secrets.
.env is not required and should not be committed.
DRY_RUN defaults to true.
The sync fails clearly if the target iCloud calendar does not exist.
Calendar event UIDs are deterministic, so reruns do not need a database to avoid adding the same event again.
