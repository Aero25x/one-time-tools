import cloudscraper
import json
import time
import re
import os
from typing import Optional, Dict, Any
from urllib.parse import urljoin
import logging
from html import unescape

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EmailAutomation:
    def __init__(
        self,
        proxy_url: Optional[str] = None,
        temp_mail_url: str = "https://web2.temp-mail.org",
        link_pattern: str = r'href="(https://[^"]*?(?:\?[^"]*|verify|confirm|token|code)[^"]*?)"',
        code_pattern: str = r'\b\d{4,8}\b(?<!margin|padding|width|height)'
    ):
        self.scraper = cloudscraper.create_scraper(allow_brotli=True, disableCloudflareV1=True)
        self.temp_mail_url = temp_mail_url
        self.link_pattern = link_pattern
        self.code_pattern = code_pattern
        self.proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
        self.max_retries = 3
        self.retry_delay = 2

    def _make_request(self, method: str, url: str, **kwargs) -> Optional[Dict[str, Any]]:
        for attempt in range(self.max_retries):
            try:
                response = self.scraper.request(method, url, proxies=self.proxies, timeout=30, **kwargs)
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Request to {url} failed with status {response.status_code}: {response.text[:200]}")
            except Exception as e:
                logger.error(f"Request to {url} failed: {e}")
            time.sleep(self.retry_delay * (2 ** attempt))
        return None

    def get_temp_mail(self) -> Optional[Dict[str, str]]:
        url = urljoin(self.temp_mail_url, "/mailbox")
        response = self._make_request("POST", url)
        if response:
            logger.info(f"Created mailbox: {response.get('mailbox')}")
            return {"mailbox": response.get("mailbox"), "token": response.get("token")}
        return None

    def poll_for_messages(self, token: str, max_attempts: int = 360, poll_interval: int = 5) -> Optional[str]:
        url = urljoin(self.temp_mail_url, "/messages")
        headers = {"Authorization": f"Bearer {token}"}
        for attempt in range(max_attempts):
            response = self._make_request("GET", url, headers=headers)
            if response and response.get("messages"):
                message_id = response["messages"][0].get("_id")
                return message_id
            time.sleep(poll_interval)
        logger.error("No messages found after polling")
        return None

    def get_message_details(self, token: str, message_id: str) -> Optional[Dict[str, Any]]:
        url = urljoin(self.temp_mail_url, f"/messages/{message_id}")
        headers = {"Authorization": f"Bearer {token}"}
        response = self._make_request("GET", url, headers=headers)
        if response:
            return response
        return None

    def _clean_html(self, body_html: str) -> str:
        if not body_html:
            return ""
        # Remove <style> blocks
        body_html = re.sub(r'<style[^>]*>.*?</style>', '', body_html, flags=re.DOTALL)
        # Remove inline CSS (style attributes)
        body_html = re.sub(r'\s*style="[^"]*"', '', body_html)
        # Remove HTML tags
        clean_text = re.sub(r'<[^>]+>', ' ', body_html)
        # Decode HTML entities
        clean_text = unescape(clean_text)
        # Normalize whitespace
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        return clean_text

    def extract_confirmation_link(self, body_html: str, body_text: str) -> Optional[str]:
        all_links = []
        if body_html:
            all_links = re.findall(self.link_pattern, body_html)
            if all_links:
                link = all_links[0]
                return self._follow_redirects(link)
        if body_text:
            all_links = re.findall(self.link_pattern, body_text)
            if all_links:
                link = all_links[0]
                return self._follow_redirects(link)
        return None

    def _follow_redirects(self, url: str) -> Optional[str]:
        try:
            response = self.scraper.get(url, proxies=self.proxies, timeout=30, allow_redirects=True)
            final_url = response.url
            return final_url
        except Exception as e:
            logger.error(f"Failed to follow redirects for {url}: {e}")
            return url

    def extract_confirmation_code(self, body_html: str, body_text: str) -> Optional[str]:
        """
        Extract a confirmation code from email body (HTML or plain text) using multiple context patterns.
        Supports numeric, alphanumeric, and hyphenated codes in various languages and formats.
        """
        # Try cleaned HTML first
        clean_html = self._clean_html(body_html)
        if clean_html:
            # Define multiple context patterns for different languages and phrasings
            context_patterns = [
                r'(?:код подтверждения|confirmation code|verify code|verification code|auth code|authentication code|your code|код верификации|код для подтверждения|код активации)\s*[:\-]?\s*(\b\d{4,8}\b)',  # Numeric 4-8 digits
                r'(?:код подтверждения|confirmation code|verify code|verification code|auth code|authentication code|your code|код верификации|код для подтверждения|код активации)\s*[:\-]?\s*([A-Za-z0-9]{6,12}\b)',  # Alphanumeric 6-12 chars
                r'(?:код подтверждения|confirmation code|verify code|verification code|auth code|authentication code|your code|код верификации|код для подтверждения|код активации)\s*[:\-]?\s*([A-Za-z0-9\-]{6,16}\b)',  # Alphanumeric with hyphens
                r'(?:code|код)\s*[:\-]?\s*(\b\d{4,8}\b)',  # Shortened context for "code" or "код"
                r'(?:code|код)\s*[:\-]?\s*([A-Za-z0-9]{6,12}\b)',  # Shortened context for alphanumeric
                r'(?:your\s*code\s*is|here\s*is\s*your\s*code|use\s*this\s*code)\s*[:\-]?\s*(\b\d{4,8}\b)',  # English variations
                r'(?:your\s*code\s*is|here\s*is\s*your\s*code|use\s*this\s*code)\s*[:\-]?\s*([A-Za-z0-9]{6,12}\b)',  # English alphanumeric
            ]

            # Try each context pattern
            for pattern in context_patterns:
                match = re.search(pattern, clean_html, re.IGNORECASE)
                if match:
                    code = match.group(1)
                    return code

            # Fallback to general code pattern (exclude common false positives)
            matches = re.findall(self.code_pattern, clean_html)
            if matches:
                code = matches[0]
                logger.info(f"Extracted fallback confirmation code: {code} (from HTML)")
                return code

        # Fallback to plain text
        if body_text:
            for pattern in context_patterns:
                match = re.search(pattern, body_text, re.IGNORECASE)
                if match:
                    code = match.group(1)
                    logger.info(f"Extracted confirmation code: {code} (pattern: {pattern})")
                    return code

            # Fallback to general code pattern
            matches = re.findall(self.code_pattern, body_text)
            if matches:
                code = matches[0]
                logger.info(f"Extracted fallback confirmation code: {code} (from text)")
                return code

        logger.warning("No confirmation code found in email body")
        return None

    def run(self) -> Dict[str, Any]:
        result = {
            "status": "failed",
            "email": None,
            "confirmation_link": None,
            "confirmation_code": None
        }

        mail_info = self.get_temp_mail()
        if not mail_info:
            logger.error("Failed to create temporary mailbox")
            return result
        result["email"] = mail_info["mailbox"]

        message_id = self.poll_for_messages(mail_info["token"])
        if not message_id:
            return result

        message_details = self.get_message_details(mail_info["token"], message_id)
        if not message_details:
            return result

        body_html = message_details.get("bodyHtml", "")
        body_text = message_details.get("bodyText", "")

        result["confirmation_link"] = self.extract_confirmation_link(body_html, body_text)
        result["confirmation_code"] = self.extract_confirmation_code(body_html, body_text)

        if result["confirmation_link"] or result["confirmation_code"]:
            result["status"] = "success"

        return result

print("""



  _    _ _     _     _             _____          _
 | |  | (_)   | |   | |           / ____|        | |
 | |__| |_  __| | __| | ___ _ __ | |     ___   __| | ___
 |  __  | |/ _` |/ _` |/ _ \ '_ \| |    / _ \ / _` |/ _ \\
 | |  | | | (_| | (_| |  __/ | | | |___| (_) | (_| |  __/
 |_|  |_|_|\__,_|\__,_|\___|_| |_|\_____\___/ \__,_|\___|

              Mail by Aero25x

            Join us to get more scripts
            https://t.me/hidden_coding


    """)


if __name__ == "__main__":
    proxy_url = os.getenv("PROXY_URL", None)  # e.g., "http://user:pass@p.webshare.io:80" or None
    link_pattern = r'href="(https://[^"]*?(?:\?[^"]*|verify|confirm|token|code)[^"]*?)"'
    code_pattern = r'\b\d{4,8}\b(?<!margin|padding|width|height)'
    automation = EmailAutomation(proxy_url=proxy_url, link_pattern=link_pattern, code_pattern=code_pattern)
    result = automation.run()
    print(json.dumps(result, indent=4))

