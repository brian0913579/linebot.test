# LINE Bot Garage Door Controller

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/10563/badge)](https://www.bestpractices.dev/projects/10563)

A highly secure, robust, and location-aware LINE Bot service designed to remotely control a garage door via the LINE messaging platform. Built with a Python/Flask backend and designed to be deployed natively on Google Cloud (App Engine). Validated users can open and close the garage door **only** after providing verifiable proof of their physical proximity to the garage location.

<img src="static/demo.gif" width="400px" alt="LINE Bot Demo" />

## 📖 Table of Contents

- [Features](#-features)
- [How It Works (System Workflow)](#-how-it-works-system-workflow)
- [Architecture & Tech Stack](#-architecture--tech-stack)
- [Project Structure](#-project-structure)
- [Prerequisites](#-prerequisites)
- [Installation & Local Development](#-installation--local-development)
- [Deployment (GCP App Engine)](#-deployment-gcp-app-engine)
- [Environment Configuration](#-environment-configuration)
- [Admin & User Management](#-admin--user-management)
- [Security Model](#-security-model)

---

## ✨ Features

- **Strict User Authentication**: Only permitted LINE identities registered in the database can trigger commands. Unrecognized users are automatically slotted into a "pending approval" queue for admin review.
- **Physical Geofencing Verification**: Before commands are unlocked, users must grant GPS location access via a one-time link. The Haversine formula calculates distance to the configured `PARK_LAT`/`PARK_LNG`.
- **Admin Dashboard**: Easy-to-use Basic-Auth protected web UI (`/admin`) to approve, reject, or remove users dynamically.
- **Ephemeral Access Tokens**: Communication between the LINE app and the browser-based Location UI uses single-use tokens with short exact Time-To-Live (TTL).
- **TLS-Encrypted Message Queuing (MQTT)**: Commands are transmitted over fully encrypted MQTT pipelines directly to the IoT garage door hardware using Certificate Authority verification.
- **Google Cloud Native Backend**: Hooks into **Google Cloud Datastore** for NoSQL user persistence, **Google Secret Manager** for credentials, and **Cloud Storage** for dynamic certificate loading.
- **Resilient Memory/Redis Caching**: Built to leverage Redis for robust token storage, or gracefully falling back to in-memory caching.
- **API Defense System**: Inherent X-Line-Signature payload verification, IP tracking rate limiters (`flask-limiter`), strict `Content-Type` checks, and rigid HTTP Security Headers.

---

## ⚙️ How It Works (System Workflow)

1. **Trigger**: An approved user sends the text command `"開關門"` to the LINE Bot.
2. **Challenge**: The bot generates a single-use verification token and replies with a secure verification URI.
3. **Verification**: The user taps the link on their mobile device, rendering `static/verify.html`, which triggers browser GPS (`navigator.geolocation`) and POSTs the exact coordinates to `/api/verify-location`.
4. **Validation**: The backend calculates the Haversine distance, checks if it's within `MAX_DIST_KM`, logs rate limits, checks token TTLs, and marks the user "Authorized". (Optionally skips this check if the user is in `DEBUG_MODE`).
5. **Operation**: A Quick-Reply template is pushed back to the user via LINE providing `🟢 開門` (Open) and `🔴 關門` (Close) postback actions.
6. **Execution**: Pressing a button triggers a Postback Event on the webhook, which immediately connects to the external MQTT Broker via TLS and publishes (`qos=1`) the `up` or `down` string payload to `garage/command`.

---

## 🏗 Architecture & Tech Stack

- **Framework**: Python 3.11 with `Flask`, `Gunicorn`.
- **Messaging Integration**: `line-bot-sdk` (v3).
- **Database (Users)**: Google Cloud Datastore (`google-cloud-datastore`).
- **IoT Payload Delivery**: `paho-mqtt`.
- **Security & Caching**: Custom Flask decorators, `Flask-Limiter`, Secret Manager (`google-cloud-secret-manager`).
- **Target Environment**: Google App Engine Standard (`app.yaml`).

---

## 📂 Project Structure

```text
/linebot.test/
├── app.py                     # Primary Flask entrypoint / API routing
├── app.yaml                   # GCP App Engine deployment configuration
├── requirements.txt           # Python dependency locks
├── config/
│   ├── config_module.py       # Static environment variables / constant fallback
│   └── secret_manager.py      # GCP Secret Manager integration wrapper
├── core/
│   ├── line_webhook.py        # LINE Platform inbound event handling/logic
│   ├── models.py              # GC Datastore logic for Allowed/Pending users
│   ├── mqtt_handler.py        # Configures TLS client + publishes MQTT topics
│   └── token_manager.py       # TTL Token issuance and cleanup service
├── middleware/
│   ├── middleware.py          # Line Signature Validation, JSON requirements, Header config
│   ├── rate_limiter.py        # IP-based DOS prevention via Flask-Limiter
│   └── cache_manager.py       # Redis hooks for multi-instance distributed state
├── static/
│   └── verify.html            # Client-side JS geolocation capture template
├── templates/
│   └── admin.html             # Jinja2 template for the /admin dashboard
├── docs/                      # Interactive Swagger/OpenAPI route generators
└── tests/                     # Pytest suite
```

---

## 🛠 Prerequisites

- Python 3.11+
- A Google Cloud Platform (GCP) Project (with App Engine, Datastore, and Secret Manager enabled)
- A LINE Developer account (Messaging API channel created)
- An MQTT broker supporting TLS (e.g., EMQX Cloud, AWS IoT, HiveMQ)
- Valid TLS CA Certificates for the broker
- (Optional) Redis server for horizontally-scaled token caching

---

## 💻 Installation & Local Development

1. **Clone the repository:**

   ```bash
   git clone https://github.com/brian13579/linebot.test.git
   cd linebot.test
   ```

2. **Set up virtual environment:**

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure Environment:**
   Copy `.env.example` to `.env`. For local testing without GCP Secret Manager, enter your variable fallbacks here.

4. **Service Account Key (for local GCP Datastore mapping):**
   Ensure you have configured local default credentials or point the `GOOGLE_APPLICATION_CREDENTIALS` env var to your service account key JSON.

5. **Run the App Locally:**
   ```bash
   python app.py
   ```
   _Available on `http://localhost:8080`_

---

## 🚀 Deployment (GCP App Engine)

Deploying seamlessly scales the application relying on App Engine Standard endpoints.

1. **Initialize `gcloud`:**

   ```bash
   gcloud auth login
   gcloud config set project YOUR_PROJECT_ID
   ```

2. **Upload SSL / Certificate files via Cloud Storage** (Defined in `app.yaml` under `CRT_BUCKET`):

   ```bash
   gsutil cp /path/to/emqxsl-ca.crt gs://line-bot-assets/
   ```

3. **Populate Secret Manager** with expected exact keys (`LINE_CHANNEL_ACCESS_TOKEN`, `LINE_CHANNEL_SECRET`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`).

4. **Deploy Web App:**

   ```bash
   gcloud app deploy app.yaml
   ```

5. **Update LINE Developer Console**: Set your webhook URL to `https://YOUR_PROJECT_ID.appspot.com/webhook`. Ensure it verifies successfully.

---

## ⚙️ Environment Configuration

| Variable                      | Description                                        |
| :---------------------------- | :------------------------------------------------- |
| `LINE_CHANNEL_ACCESS_TOKEN`   | LINE API Token (Preferably in GCP Secret Manager)  |
| `LINE_CHANNEL_SECRET`         | LINE Secret (Preferably in GCP Secret Manager)     |
| `ADMIN_USERNAME` / `PASSWORD` | Basic Auth credentials for the `/admin` page       |
| `MQTT_BROKER`                 | URL/Host of the MQTT Server                        |
| `MQTT_PORT` / `MQTT_TOPIC`    | e.g. `8883` / `garage/command`                     |
| `PARK_LAT` / `PARK_LNG`       | Float degrees of the physical garage target        |
| `MAX_DIST_KM`                 | Allowable geofence limit in kilometers (e.g., `1`) |
| `RATE_LIMIT_ENABLED`          | Boolean string (`true`/`false`)                    |

---

## 👥 Admin & User Management

To manage access efficiently:

1. Navigate to `/admin` (e.g., `https://your-app.appspot.com/admin`).
2. Login using the Basic Auth credentials provided to Secret Manager (`ADMIN_USERNAME` and `ADMIN_PASSWORD`).
3. You will see two panels:
   - **Pending Users**: Denotes LINE users who attempted to message the bot but were halted for not having access. You can click **Approve** (moves to authorized collection) or **Reject** (drops them).
   - **Active Users**: A list of currently permitted identities. You can **Delete** access immediately from here.

_(All states are mapped securely under the hood to Google Cloud Datastore under `allowed_users` and `pending_users` kinds)._

---

## 🔒 Security Model

- **Webhook Validation:** Rejects any `POST` to `/webhook` that does not match the symmetric HMAC-SHA256 signature calculated from `LINE_CHANNEL_SECRET`.
- **Geofencing:** Requires explicitly polled coordinate parameters; relies on HTML5 native HTTPS location prompts bound inside an unguessable rotating URL.
- **Action Decoupling:** Emits a unique Quick Reply mapped internal token (`generate_token()`) ensuring that the postback payloads injected towards MQTT cannot be replayed globally later.
- **Hardware Isolation:** Isolates the HTTP Webhook application domain entirely from the hardware protocol. They only bridge safely over outgoing TCP SSL/TLS.
- **Header Armoring:** Restricts frame options, forces XSS protections, prevents MIME type sniffing via Custom Decorators.

---

## 🐛 Troubleshooting

- **502 Bad Gateway / Loading Animation Hanging**: Usually caused by Secret Manager missing environment mappings preventing initialization. Use `gcloud app logs read`.
- **MQTT Certificates Not Resolving**: The system attempts to download `.crt` files dynamically to `/tmp/` on boot using `init_persistence()`. Verify Cloud Storage permissions via the App Engine default service account.
- **Geolocation "Inaccurate"**: Ensure users have Wi-Fi turned on for their phones. The Javascript is flagged with `enableHighAccuracy: true`.

---

## 📜 License & Contact

This project is licensed under the [MIT License](LICENSE).

For core bug tracking, question handling, or integration details, open a repository issue or contact: `cool.brian1206cool@gmail.com`.
