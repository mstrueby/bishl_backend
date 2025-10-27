import datetime
import socket
import ssl
from urllib.parse import urlparse


def check_ssl_certificate(url):
    """Check SSL certificate validity for a given URL"""
    parsed_url = urlparse(url)
    hostname = parsed_url.hostname
    port = parsed_url.port or 443

    try:
        # Create SSL context
        context = ssl.create_default_context()

        # Connect and get certificate
        with socket.create_connection((hostname, port), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()

        # Check that certificate was retrieved
        if not cert:
            print("❌ Failed to retrieve certificate")
            return False

        # Check certificate details
        print(f"Certificate for {hostname}:")
        print(f"Subject: {cert.get('subject')}")
        print(f"Issuer: {cert.get('issuer')}")
        print(f"Version: {cert.get('version')}")
        print(f"Serial Number: {cert.get('serialNumber')}")

        # Check expiration
        not_after_str = cert.get("notAfter")
        not_before_str = cert.get("notBefore")
        
        if not not_after_str or not isinstance(not_after_str, str):
            print("❌ Invalid certificate expiration date")
            return False
            
        if not not_before_str or not isinstance(not_before_str, str):
            print("❌ Invalid certificate start date")
            return False
            
        not_after = datetime.datetime.strptime(not_after_str, "%b %d %H:%M:%S %Y %Z")
        not_before = datetime.datetime.strptime(not_before_str, "%b %d %H:%M:%S %Y %Z")

        print(f"Valid from: {not_before}")
        print(f"Valid until: {not_after}")

        now = datetime.datetime.now()
        if now < not_before:
            print("❌ Certificate is not yet valid")
            return False
        elif now > not_after:
            print("❌ Certificate has expired")
            return False
        else:
            days_until_expiry = (not_after - now).days
            print(f"✅ Certificate is valid ({days_until_expiry} days until expiry)")
            return True

    except ssl.SSLError as e:
        print(f"❌ SSL Error: {e}")
        return False
    except OSError as e:
        print(f"❌ Socket Error: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def check_ssl_with_requests(url):
    """Check SSL certificate using requests library"""
    import requests

    try:
        # This will raise an exception if SSL verification fails
        response = requests.get(url, timeout=10, verify=True)
        print(f"✅ SSL certificate is valid for {url}")
        print(f"Status code: {response.status_code}")
        return True
    except requests.exceptions.SSLError as e:
        print(f"❌ SSL verification failed: {e}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
        return False


if __name__ == "__main__":
    # Test with ISHD API
    ishd_url = "https://www.ishd.de/api/licenses/clubs/39/teams/1.%20Herren.json"

    print("=== SSL Certificate Check ===")
    check_ssl_certificate(ishd_url)

    print("\n=== Requests SSL Check ===")
    check_ssl_with_requests(ishd_url)
