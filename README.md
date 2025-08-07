# Email Automation Script

<img width="1142" height="654" alt="image" src="https://github.com/user-attachments/assets/786d3076-d417-4160-b424-d40111d9eda1" />

This Python script automates the process of creating a temporary email address, polling for incoming messages, and extracting confirmation links or codes from emails. It uses the `cloudscraper` library to handle HTTP requests and bypass Cloudflare protection, with optional proxy support for enhanced anonymity.


## Features
- Creates a temporary email address using a service like `web2.temp-mail.org`.
- Polls for incoming messages and retrieves the latest email.
- Extracts confirmation links or codes (numeric or alphanumeric) from email content (HTML or plain text).
- Supports optional proxy configuration via a single proxy URL.
- Robust error handling with retries and logging.
- Supports multiple languages and code formats for confirmation code extraction.

## Requirements
- Python 3.7 or higher
- Dependencies listed in `requirements.txt`:
  ```text
  cloudscraper>=1.2.71
  requests>=2.31.0
  typing-extensions>=4.12.2
