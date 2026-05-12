# Bosch eBike (Smart System) — Home Assistant Integration

A HACS-compatible Home Assistant custom integration that connects Bosch Smart System eBikes to Home Assistant via the official Bosch Data Act API. Exposes bike telemetry, ride history, aggregate statistics, and optional Flow+/ConnectModule data as native Home Assistant entities.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [HACS Installation](#hacs-installation)
- [Configuration](#configuration)
- [Entity Reference](#entity-reference)
- [Changing the Unit System](#changing-the-unit-system)
- [Flow+ and ConnectModule Feature Detection](#flow-and-connectmodule-feature-detection)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### 1. Bosch Flow App account

Your bike must be linked to the [Bosch eBike Flow app](https://www.bosch-ebike.com/en/products/apps/ebike-flow-app) before the integration can access any data. Ensure your bike appears in the Flow app and has recorded at least one ride.

### 2. Bosch Data Act Portal registration

The integration authenticates using the official Bosch Data Act API. You must register a developer application on the portal before setting up the integration.

**Steps:**

1. Go to [portal.bosch-ebike.com/data-act](https://portal.bosch-ebike.com/data-act) and sign in with your Bosch SingleKey ID.
2. Create a new application. Use a descriptive name such as "Home Assistant Integration".
3. Set the OAuth2 redirect URI to:
   ```
   https://<your-home-assistant-url>/auth/external/callback
   ```
   Replace `<your-home-assistant-url>` with your Home Assistant external URL (e.g. `https://homeassistant.local:8123`).
4. Submit the application for approval.

### 3. Approval process

Bosch manually reviews all Data Act Portal applications. Approval typically takes a few business days. You will receive a confirmation email when your application is approved. **You cannot complete the integration setup until your application is approved.**

If the integration shows an error about a pending application during setup, check your email for an approval notification and try again once approved.

### 4. Required OAuth2 scopes

Your Data Act Portal application must be granted the following scopes:

| Scope | Purpose |
|---|---|
| `bike:read` | Read bike telemetry and configuration |
| `rides:read` | Read ride history and statistics |
| `stats:read` | Read lifetime aggregate statistics |
| `battery:read` | Read battery state of charge (Flow+ only) |
| `location:read` | Read GPS location (ConnectModule only) |
| `alarm:read` | Read theft alarm status (ConnectModule only) |

### 5. Client credentials

After approval, note down your:
- **Client ID** — format: `euda-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
- **Client Secret**

You will need these during the Home Assistant setup.

---

## HACS Installation

### Add the custom repository

1. Open Home Assistant and navigate to **HACS** in the sidebar.
2. Click the three-dot menu (⋮) in the top-right corner and select **Custom repositories**.
3. Enter the repository URL:
   ```
   https://github.com/kieran-tanner-9/Bosch-eBike-Smart-System-Home-Assistant-Integration
   ```
4. Set the category to **Integration** and click **Add**.
5. The integration will appear in the HACS integration list. Click **Download** to install it.
6. Restart Home Assistant when prompted.

### Verify installation

After restarting, go to **Settings → Devices & Services → Add Integration** and search for **Bosch eBike (Smart System)**. If it appears in the list, the installation was successful.

---

## Configuration

### Step 1: Register application credentials

Before starting the config flow, you must register your Data Act Portal credentials with Home Assistant.

1. Go to **Settings → Devices & Services → Application Credentials** (or navigate directly to `/config/application_credentials`).
2. Click **Add Application Credentials**.
3. Select **Bosch eBike (Smart System)** from the integration dropdown.
4. Enter your **Client ID** and **Client Secret** from the Data Act Portal.
5. Click **Save**.

### Step 2: Add the integration

1. Go to **Settings → Devices & Services** and click **Add Integration**.
2. Search for and select **Bosch eBike (Smart System)**.
3. You will be redirected to the Bosch SingleKey ID login page. Sign in with the same account linked to your bike in the Flow app.
4. Grant the requested permissions when prompted.
5. You will be redirected back to Home Assistant automatically.

### Step 3: Select unit system

After the OAuth2 flow completes, you will be asked to choose your preferred unit system:

| Option | Distance | Speed | Elevation |
|---|---|---|---|
| **Metric** (default) | km | km/h | m |
| **Imperial** | mi | mph | ft |

Select your preference and click **Submit**. This can be changed later without re-authenticating — see [Changing the Unit System](#changing-the-unit-system).

### Step 4: Confirm setup

The integration will verify your credentials by fetching your bike list. If successful, a new device will appear for each bike registered in your Bosch account. All sensor entities will be created and begin polling data within 30 minutes.

---

## Entity Reference

All entities are grouped by the bike device they belong to. Entities marked **Flow+** require an active Flow+ subscription. Entities marked **ConnectModule** require a ConnectModule (BCM3100) hardware accessory paired with the bike.

### Bike Sensors

| Entity | Description | Metric Unit | Imperial Unit | Device Class |
|---|---|---|---|---|
| `sensor.odometer` | Total distance ridden | km | mi | Distance |
| `sensor.motor_hours` | Total motor operating time | h | h | Duration |
| `sensor.battery_charge_cycles` | Total battery charge cycles | — | — | — |
| `sensor.battery_lifetime_energy` | Total lifetime energy from battery | Wh | Wh | Energy |
| `sensor.next_service_odometer` | Odometer reading at next scheduled service | km | mi | Distance |
| `sensor.max_assist_speed` | Configured maximum motor-assist speed | km/h | mph | Speed |

### Ride Sensors (most recent ride)

| Entity | Description | Metric Unit | Imperial Unit | Device Class |
|---|---|---|---|---|
| `sensor.last_ride_distance` | Distance of the most recent ride | km | mi | Distance |
| `sensor.last_ride_duration` | Duration of the most recent ride | min | min | Duration |
| `sensor.last_ride_avg_speed` | Average speed during the most recent ride | km/h | mph | Speed |
| `sensor.last_ride_max_speed` | Maximum speed during the most recent ride | km/h | mph | Speed |
| `sensor.last_ride_elevation_gain` | Total elevation gained during the most recent ride | m | ft | Distance |
| `sensor.last_ride_elevation_loss` | Total elevation lost during the most recent ride | m | ft | Distance |
| `sensor.last_ride_calories` | Estimated calories burned during the most recent ride | kcal | kcal | Energy |
| `sensor.last_ride_date` | Timestamp when the most recent ride was completed | — | — | Timestamp |

### Aggregate Sensors (lifetime totals)

| Entity | Description | Metric Unit | Imperial Unit | Device Class |
|---|---|---|---|---|
| `sensor.total_rides` | Total number of recorded rides | — | — | — |
| `sensor.total_distance` | Sum of all ride distances | km | mi | Distance |
| `sensor.total_ride_time` | Sum of all ride durations | h | h | Duration |
| `sensor.total_calories` | Sum of all estimated calories burned | kcal | kcal | Energy |
| `sensor.total_elevation_gain` | Sum of all elevation gained across all rides | m | ft | Distance |
| `sensor.average_speed` | Mean average speed across all rides | km/h | mph | Speed |

### Flow+ Sensors

> These entities require an active **Flow+ subscription** in the Bosch eBike Flow app. They will show as `unavailable` if the subscription is inactive or has lapsed.

| Entity | Description | Metric Unit | Imperial Unit | Device Class |
|---|---|---|---|---|
| `sensor.last_ride_avg_rider_power` | Average rider power output during the most recent ride | W | W | Power |
| `sensor.last_ride_max_rider_power` | Peak rider power output during the most recent ride | W | W | Power |
| `sensor.last_ride_avg_cadence` | Average cadence during the most recent ride | RPM | RPM | — |
| `sensor.last_ride_max_cadence` | Peak cadence during the most recent ride | RPM | RPM | — |
| `sensor.last_ride_motor_power_ratio` | Ratio of motor power to total power during the most recent ride | % | % | — |
| `sensor.battery_soc` | Current battery state of charge | % | % | Battery |
| `sensor.battery_charging_status` | Current battery charging status (`charging`, `discharging`, `full`, `unknown`) | — | — | — |

### ConnectModule Sensors

> These entities require a **ConnectModule (BCM3100)** hardware accessory paired with the bike. They will show as `unavailable` if no ConnectModule is detected.

| Entity | Description | Metric Unit | Imperial Unit | Device Class |
|---|---|---|---|---|
| `device_tracker.bike_location` | Last known GPS location of the bike | — | — | GPS |
| `sensor.bike_location_accuracy` | GPS fix accuracy | m | ft | Distance |
| `sensor.bike_location_timestamp` | Timestamp of the last GPS fix | — | — | Timestamp |
| `binary_sensor.theft_alarm_active` | `on` when the theft alarm has been triggered | — | — | Tamper |
| `binary_sensor.alarm_armed` | `on` when the theft alarm is armed | — | — | Safety |

### Entity attributes

Every sensor entity exposes a `last_updated` attribute containing the UTC timestamp of the most recent successful data refresh. This is useful for automations that need to detect stale data.

---

## Changing the Unit System

You can switch between metric and imperial units at any time without removing and re-adding the integration.

1. Go to **Settings → Devices & Services**.
2. Find the **Bosch eBike (Smart System)** integration card and click **Configure**.
3. Select your preferred unit system from the dropdown.
4. Click **Submit**.

The integration will reload automatically and all affected sensor entities will reflect the new units on the next coordinator update (within 30 minutes, or immediately after the next poll cycle).

**Sensors affected by unit conversion:**

- Distance: `odometer`, `next_service_odometer`, `last_ride_distance`, `total_distance`, `last_ride_elevation_gain`, `last_ride_elevation_loss`, `total_elevation_gain`, `bike_location_accuracy`
- Speed: `max_assist_speed`, `last_ride_avg_speed`, `last_ride_max_speed`, `average_speed`

All other sensors (calories, power, cadence, timestamps, counts) are not affected by the unit system setting.

---

## Flow+ and ConnectModule Feature Detection

The integration automatically detects whether Flow+ and ConnectModule features are available for each bike. No manual configuration is required.

### Flow+ detection

Flow+ features are detected by the presence of enhanced ride data fields in the Bosch Data Act API response. If the API does not return Flow+ fields, the integration treats this as an inactive subscription and sets all Flow+ sensor states to `unavailable`. No error is raised.

When a Flow+ subscription lapses, the affected sensors will transition to `unavailable` on the next poll cycle. An informational message is logged to the Home Assistant log.

The battery state of charge (`battery_soc`) is polled more frequently than other data — every **15 minutes** by default — to keep charging status current.

### ConnectModule detection

ConnectModule features are detected by the presence of location and alarm fields in the API response. If these fields are absent, the integration treats this as "no ConnectModule paired" and sets all ConnectModule entity states to `unavailable` (or `not_home` for the device tracker). No error is raised.

**GPS signal loss:** When the ConnectModule cannot obtain a GPS fix (e.g. the bike is indoors or powered off), the `device_tracker` entity transitions to `not_home`. The last known coordinates are retained as entity attributes so map cards continue to show the bike's last known position.

**Theft alarm notifications:** When the theft alarm transitions from `off` to `on`, the integration automatically creates a Home Assistant persistent notification with the message "eBike theft alarm triggered" and the bike's name. This notification appears in the Home Assistant notification bell. You can also create your own automations using the `binary_sensor.theft_alarm_active` entity.

---

## Troubleshooting

### "Application not yet approved" error during setup

Your Bosch Data Act Portal application is still pending review. Check your email for an approval notification from Bosch. Once approved, restart the config flow from **Settings → Devices & Services → Add Integration**.

### "No application credentials found" error

You must register your Client ID and Client Secret in Home Assistant before starting the config flow. See [Step 1: Register application credentials](#step-1-register-application-credentials).

### Sensors show `unavailable` after setup

- **All sensors unavailable:** The integration may not have completed its first poll yet. Wait up to 30 minutes and check again. If the problem persists, check the Home Assistant logs for API errors.
- **Flow+ sensors unavailable:** Your Flow+ subscription may be inactive. Check the Flow app to confirm your subscription status.
- **ConnectModule sensors unavailable:** No ConnectModule is detected on your bike. Confirm the BCM3100 is paired in the Flow app.
- **Individual sensors unavailable:** The API did not return a value for that field. This is normal for some fields depending on your bike model and configuration.

### Re-authentication required

If the integration shows a "Re-authentication required" notification, your OAuth2 refresh token has expired or been revoked. Click the notification to re-run the OAuth2 flow. Your sensor history and configuration will be preserved.

### Data is stale or not updating

Check the `last_updated` attribute on any sensor entity. If it is more than 60 minutes old, the integration may be experiencing polling failures. Check the Home Assistant logs for `WARNING` or `ERROR` messages from `custom_components.bosch_ebike_ha`.

The integration uses exponential back-off when API calls fail, up to a maximum retry interval of 60 minutes. After 2 hours of continuous failure, all entities are marked `unavailable`.

### Checking the logs

To view integration logs:

1. Go to **Settings → System → Logs**.
2. Search for `bosch_ebike_ha`.

To enable debug logging, add the following to your `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.bosch_ebike_ha: debug
```

Restart Home Assistant after making this change. Debug logs include API endpoint calls and coordinator update cycles. **Credentials (tokens) are never logged at any level.**

### Multiple bikes

If you have more than one Bosch Smart System eBike registered in your account, each bike will appear as a separate device in Home Assistant after setup. All bikes share the same config entry and OAuth2 credentials. Each bike's coordinator polls independently, so a failure for one bike does not affect the others.

### HACS update not appearing

If a new version of the integration is available but not showing in HACS, try clicking the refresh button in the HACS integrations list. If the update still does not appear, re-add the custom repository URL in HACS settings.

---

## Support

- **Bug reports and feature requests:** [GitHub Issues](https://github.com/kieran-tanner-9/Bosch-eBike-Smart-System-Home-Assistant-Integration/issues)
- **Documentation:** [GitHub Repository](https://github.com/kieran-tanner-9/Bosch-eBike-Smart-System-Home-Assistant-Integration)
