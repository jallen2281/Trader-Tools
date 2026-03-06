"""Network debugging script to compare dev vs production environment."""
import requests
import socket
import yfinance as yf

def check_network_info():
    """Check network configuration and external IP."""
    print("=" * 60)
    print("NETWORK DIAGNOSTICS")
    print("=" * 60)
    
    # Check hostname
    print(f"\n1. Hostname: {socket.gethostname()}")
    
    # Check external IP (what Yahoo Finance sees)
    try:
        response = requests.get('https://api.ipify.org?format=json', timeout=5)
        external_ip = response.json()['ip']
        print(f"2. External IP (what Yahoo sees): {external_ip}")
    except Exception as e:
        print(f"2. External IP check failed: {e}")
    
    # Check DNS resolution for Yahoo Finance
    try:
        yahoo_ips = socket.getaddrinfo('query1.finance.yahoo.com', 443, socket.AF_INET)
        print(f"3. Yahoo Finance DNS: {yahoo_ips[0][4][0]}")
    except Exception as e:
        print(f"3. Yahoo Finance DNS failed: {e}")
    
    # Check if we can reach Yahoo Finance
    print("\n4. Testing Yahoo Finance connectivity:")
    try:
        response = requests.get('https://query1.finance.yahoo.com', timeout=5)
        print(f"   - HTTP Status: {response.status_code}")
        print(f"   - Headers: {dict(response.headers)}")
    except Exception as e:
        print(f"   - Connection failed: {e}")
    
    # Test yfinance
    print("\n5. Testing yfinance library:")
    try:
        ticker = yf.Ticker('AAPL')
        info = ticker.info
        if info:
            print(f"   - yfinance works! Got data for AAPL")
            print(f"   - Sample: {list(info.keys())[:5]}")
        else:
            print(f"   - yfinance returned empty data")
    except Exception as e:
        print(f"   - yfinance failed: {e}")
    
    # Test download method
    print("\n6. Testing yf.download():")
    try:
        data = yf.download('AAPL', period='5d', progress=False)
        if not data.empty:
            print(f"   - Download works! Got {len(data)} rows")
            print(f"   - Latest close: ${data['Close'].iloc[-1]:.2f}")
        else:
            print(f"   - Download returned empty DataFrame")
    except Exception as e:
        print(f"   - Download failed: {e}")
    
    print("\n" + "=" * 60)
    print("Run this on BOTH dev server and in Kubernetes pod to compare!")
    print("=" * 60)

if __name__ == "__main__":
    check_network_info()
