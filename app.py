from flask import Flask, render_template, jsonify, request
import requests
from datetime import datetime, timedelta
import time
import json
import os 

app = Flask(__name__)

# --- Configuration ---
# PASTE YOUR Twelvedata API KEY HERE:
Twelvedata_API_KEY = "aba931dfdfd3490e9fe5b1c4ec1273a5"
BASE_URL = "wss://ws.twelvedata.com"

SYMBOLS = [
    "GOOGL", "IBM", "MSFT", "AAPL", "AMZN", "TSLA", "NVDA", "META"
]

# --- Helper to get Twelvedata stock data ---
# This function will now accept a 'timestamp_override'
def get_stock_data(symbol, timestamp_override=None):
    """
    Fetches real-time stock quote data for a given symbol from Finnhub.
    Includes error handling and prints raw API responses for debugging.
    """
    quote_url = f"{BASE_URL}/quote?symbol={symbol}&token={Twelvedata_API_KEY}"
    
    print(f"\n--- Fetching raw data for {symbol} from Twelvedata ---")
    print(f"Request URL: {quote_url}")

    try:
        # Make the request to Twelvedata API with a timeout
        res = requests.get(quote_url, timeout=5) 
        # Raise an HTTPError for bad responses (4xx or 5xx status codes)
        res.raise_for_status() 
        # Attempt to parse the JSON response
        data = res.json()
        print(f"Raw Twelvedata Response for {symbol}: {json.dumps(data, indent=2)}")
    except (requests.exceptions.RequestException, ValueError) as e:
        # Catch any request-related errors (e.g., network issues, timeouts, HTTP errors)
        # or JSON parsing errors (ValueError from res.json())
        print(f"Error fetching data for {symbol} from Twelvedata: {e}")
        return None

    def safe_get_number(key):
        """Helper to safely get numeric values from the API response."""
        val = data.get(key)
        if isinstance(val, (int, float)):
            return val
        return None

    current_price = safe_get_number("c")
    prev_close = safe_get_number("pc")
    open_price = safe_get_number("o")
    high_price = safe_get_number("h")
    low_price = safe_get_number("l")
    # The 'volume' key ('v') was commented out in your original code,
    # so it's not included in the processed_quote to avoid KeyError later.
    # If you need volume, uncomment 'volume = safe_get_number("v")' and ensure Finnhub provides it.

    # Use the provided timestamp_override, or fallback to current time if not provided
    formatted_timestamp = timestamp_override if timestamp_override else datetime.now().strftime('%I:%M:%S %p')
    
    change = None
    percent_change = None

    # Calculate change and percent change if current and previous close prices are available
    if current_price is not None and prev_close is not None:
        change = round(current_price - prev_close, 2)
        if prev_close != 0:
            percent_change = round((change / prev_close) * 100, 2)
        else:
            percent_change = 0.0 # Avoid division by zero if prev_close is 0

    processed_quote = {
        "symbol": symbol,
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "close": current_price,
        "prev_close": prev_close,
        "change": change,
        "percent_change": percent_change,
        "timestamp": formatted_timestamp,
        # "volume": volume # Uncomment if 'volume' is fetched and needed
    }
    print(f"Processed Quote for {symbol}: {processed_quote}")
    return processed_quote

# --- API Endpoints ---

@app.route("/")
def home():
    """
    Renders the homepage, attempting to load cached stock data first.
    If no cache or cache is invalid, fetches live data from Finnhub.
    """
    # Try loading cached stock data
    if os.path.exists('stock_data.json'):
        with open('stock_data.json', 'r') as f:
            try:
                data = json.load(f)
                # Ensure data is a list and not empty before accessing index 0
                if data and isinstance(data, list):
                    updated_time = data[0].get("timestamp", datetime.now().strftime("%I:%M:%S %p"))
                    print(f"DEBUG: Stocks data loaded from cache for homepage: {data}") # Added print for debugging
                    return render_template('index.html', stocks=data, updated_time=updated_time)
                else:
                    print("WARNING: Cached stock_data.json is empty or not a list. Fetching live data.")
            except json.JSONDecodeError as e:
                print(f"ERROR: Could not decode stock_data.json: {e}. Fetching live data.")
            except IndexError:
                print("WARNING: Cached stock_data.json is an empty list. Fetching live data.")
    
    # If file doesn't exist or loading failed, fetch data from API
    stocks = []
    batch_fetch_time = datetime.now().strftime("%I:%M:%S %p")

    for symbol in SYMBOLS:
        stock = get_stock_data(symbol, timestamp_override=batch_fetch_time)
        if stock:
            stocks.append(stock)
        time.sleep(0.5) # Add a small delay to respect Finnhub API rate limits (e.g., 30 calls/sec for free tier)

    # Save to stock_data.json for caching, only if stocks were successfully fetched
    if stocks:
        try:
            with open('stock_data.json', 'w') as f:
                json.dump(stocks, f, indent=2)
            print("DEBUG: Stocks data saved to stock_data.json.")
        except IOError as e:
            print(f"ERROR: Could not save stock_data.json: {e}")
    else:
        print("WARNING: No stock data fetched to save to cache.")

    # This print statement is crucial for debugging the 'UndefinedError' on the homepage
    print(f"DEBUG: Stocks data being passed to template for homepage: {stocks}") 
    return render_template('index.html', stocks=stocks, updated_time=batch_fetch_time)


@app.route('/chart-data')
def chart_data():
    """
    Fetches historical chart data from Yahoo Finance for a given symbol and range.
    Includes comprehensive error handling and logging.
    """
    symbol = request.args.get('symbol', 'AAPL')
    data_range = request.args.get('range', '1y')
    interval = request.args.get('interval', '1d')

    # Yahoo Finance API URL
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={data_range}&interval={interval}"
    headers = {"User-Agent": "Mozilla/5.0"} # Essential for Yahoo Finance to avoid 403 Forbidden

    print(f"\n--- Fetching chart data for {symbol} from Yahoo Finance ---")
    print(f"Request URL: {url}")

    try:
        # Make the request to Yahoo Finance API with a timeout
        response = requests.get(url, headers=headers, timeout=10) 
        # Raise an HTTPError for bad responses (4xx or 5xx status codes)
        response.raise_for_status() 
        # Print a snippet of the raw response text for debugging
        print(f"Raw Yahoo Finance Chart Response for {symbol} (first 500 chars): {response.text[:500]}...")
        # Attempt to parse the JSON response
        data = response.json()

        result = data.get('chart', {}).get('result', [])
        if not result:
            print(f"ERROR: No chart data found in Yahoo Finance response for {symbol}.")
            return jsonify({'error': 'No chart data found for the given symbol and range.'}), 404
        
        result = result[0]
        timestamps = result.get('timestamp', [])
        closes = result.get('indicators', {}).get('quote', [{}])[0].get('close', [])

        labels = []
        prices = []

        for ts, close in zip(timestamps, closes):
            # Ensure 'close' is a valid number before appending to prices
            if isinstance(close, (int, float)) and close is not None:
                labels.append(datetime.fromtimestamp(ts).strftime('%Y-%m-%d'))
                prices.append(round(close, 2))
            else:
                print(f"WARNING: Skipping invalid close price for {symbol} at timestamp {ts}: {close}")

        print(f"Processed Chart Data for {symbol}: Labels={len(labels)}, Prices={len(prices)}")
        return jsonify({
            'symbol': symbol,
            'labels': labels,
            'prices': prices
        })

    except requests.exceptions.RequestException as e:
        # Catch any request-related errors (e.g., network issues, timeouts, HTTP errors from Yahoo)
        print(f"ERROR: Request to Yahoo Finance failed for {symbol}: {e}")
        return jsonify({'error': f"Failed to connect to Yahoo Finance for chart data: {e}"}), 500
    except json.JSONDecodeError as e:
        # Catch JSON parsing errors if Yahoo Finance sends non-JSON or malformed JSON
        print(f"ERROR: JSON decoding failed for Yahoo Finance chart data for {symbol}: {e}")
        print(f"ERROR: Raw response text was: {response.text[:500]}...") # Print snippet of problematic response
        return jsonify({'error': f"Failed to parse Yahoo Finance response for chart data: {e}"}), 500
    except Exception as e: # Catch any other unexpected errors
        print(f"ERROR: An unexpected error occurred in chart_data for {symbol}: {e}")
        return jsonify({'error': f"An unexpected error occurred: {e}"}), 500

@app.route('/api/calculate_comparison')
def calculate_comparison():
    """
    Calculates stock investment comparison based on historical data.
    This function makes an internal API call to /chart-data.
    Includes robust error handling for the internal API call.
    """
    symbols_str = request.args.get('symbols', '')
    start_investment_str = request.args.get('investment', '10000')
    years_str = request.args.get('years', '10')

    print(f"\n--- Starting calculate_comparison for symbols: {symbols_str} ---")

    if not symbols_str:
        return jsonify({"error": "Please provide stock symbols."}), 400

    symbols = [s.strip().upper() for s in symbols_str.split(',') if s.strip()]
    
    try:
        start_investment = float(start_investment_str)
        investment_years = int(years_str)
        if investment_years <= 0:
            raise ValueError("Investment years must be positive.")
    except ValueError as e:
        print(f"ERROR: Invalid investment or years input: {e}")
        return jsonify({"error": f"Invalid investment or years: {e}"}), 400

    comparison_results = []
    chart_data_points = []

    PLACEHOLDER_ANNUAL_YIELD = 0.02 # 2% annual yield for DRIP calculation

    for symbol in symbols:
        print(f"Fetching historical data for comparison for {symbol} for {investment_years} years.")
        
        chart_api_url = f"{request.url_root}chart-data?symbol={symbol}&range={investment_years}y&interval=1d"
        
        historical_data = {} # Initialize in case of errors

        try:
            # Make the internal API call to our own /chart-data endpoint
            response = requests.get(chart_api_url, timeout=15) # Added timeout for robustness
            
            # Log the status code and a snippet of the response text for debugging
            print(f"DEBUG: /chart-data API Status Code for {symbol}: {response.status_code}")
            print(f"DEBUG: /chart-data API Response Text for {symbol} (first 200 chars): {response.text[:200]}...")

            # Raise an HTTPError for bad responses (e.g., 404, 500 from /chart-data endpoint)
            response.raise_for_status() 
            # Attempt to parse JSON from the internal API response
            historical_data = response.json() 

        except requests.exceptions.RequestException as e:
            # Catches network errors, timeouts, or HTTP errors (from raise_for_status)
            print(f"ERROR: Request to internal /chart-data API failed for {symbol}: {e}")
            historical_data = {"error": f"Failed to fetch chart data from internal API: {e}"}
        except json.JSONDecodeError as e:
            # Catches errors if the internal /chart-data endpoint returns non-JSON
            print(f"ERROR: JSON decoding failed for internal /chart-data API response for {symbol}: {e}")
            print(f"ERROR: Raw response text from /chart-data for {symbol} was: {response.text[:500]}...")
            historical_data = {"error": f"Failed to parse chart data from internal API: {e}"}
        
        # Check if the historical_data dictionary contains an 'error' key
        if historical_data.get('error'):
            print(f"Error fetching historical data for {symbol}: {historical_data['error']}")
            comparison_results.append({
                "symbol": symbol,
                "start_investment": start_investment,
                "annual_yield": "N/A",
                "end_value_no_drip": "N/A",
                "end_value_with_drip": "N/A",
                "chart_labels": [],
                "chart_prices": [],
                "error_message": historical_data['error'] # Pass error message to frontend
            })
            continue # Skip to the next symbol if there was an error

        labels = historical_data.get('labels', [])
        prices = historical_data.get('prices', [])

        if not labels or len(prices) < 2:
            print(f"Not enough historical data for {symbol} for {investment_years} years.")
            comparison_results.append({
                "symbol": symbol,
                "start_investment": start_investment,
                "annual_yield": "N/A",
                "end_value_no_drip": "N/A",
                "end_value_with_drip": "N/A",
                "chart_labels": [],
                "chart_prices": [],
                "error_message": "Not enough historical data for calculation."
            })
            continue # Skip to the next symbol if data is insufficient

        start_price = prices[0]
        end_price = prices[-1]

        if start_price == 0:
            annual_growth_rate = 0
            print(f"WARNING: Start price for {symbol} is 0, setting annual growth rate to 0.")
        else:
            # Ensure investment_years is not 0 to avoid division by zero in exponentiation
            if investment_years == 0:
                annual_growth_rate = 0 
                print(f"WARNING: Investment years for {symbol} is 0, setting annual growth rate to 0.")
            else:
                annual_growth_rate = ((end_price / start_price)**(1 / investment_years)) - 1
        
        end_value_no_drip = start_investment * ((1 + annual_growth_rate)**investment_years)

        end_value_with_drip = start_investment * ((1 + annual_growth_rate + PLACEHOLDER_ANNUAL_YIELD)**investment_years)

        comparison_results.append({
            "symbol": symbol,
            "start_investment": start_investment,
            "annual_yield": f"{PLACEHOLDER_ANNUAL_YIELD * 100:.1f}%",
            "end_value_no_drip": round(end_value_no_drip, 2),
            "end_value_with_drip": round(end_value_with_drip, 2),
            "chart_labels": labels,
            "chart_prices": prices
        })

        # Normalize prices for charting based on the initial investment amount
        normalized_prices = [(price / start_price) * start_investment for price in prices]
        chart_data_points.append({
            "symbol": symbol,
            "labels": labels,
            "prices": normalized_prices
        })
        time.sleep(0.5) # Add a small delay between requests to Yahoo Finance via /chart-data

    print(f"Finished calculate_comparison. Results count: {len(comparison_results)}")
    return jsonify({
        "comparison_table": comparison_results,
        "comparison_chart_data": chart_data_points
    })

@app.route('/stock_data')
def stock_data():
    """
    Provides real-time stock data for all defined symbols.
    Uses get_stock_data helper function.
    """
    stock_list = []
    batch_fetch_time = datetime.now().strftime("%I:%M:%S %p") # Consistent time for dynamic updates too
    for symbol in SYMBOLS:
        quote = get_stock_data(symbol, timestamp_override=batch_fetch_time) # Pass consistent time
        if quote:
            # 'volume' was commented out in get_stock_data, so it's removed here to prevent KeyError.
            # If you enable volume fetching in get_stock_data, you can add it back here.
            data = {
                'symbol': symbol,
                'open': quote['open'],
                'close': quote['close'],
                'high': quote['high'],
                'low': quote['low'],
                'change': quote['change'],
                'percent_change': quote['percent_change'],
                'timestamp': quote['timestamp'] 
            }
        else:
            # Provide 'N/A' for all fields if stock data fetch failed
            data = {
                'symbol': symbol,
                'open': 'N/A',
                'close': 'N/A',
                'high': 'N/A',
                'low': 'N/A',
                'change': 'N/A',
                'percent_change': 'N/A',
                'timestamp': 'N/A'
            }
        stock_list.append(data)
    print(f"DEBUG: Returning stock_list for /stock_data: {stock_list}")
    return jsonify(stock_list)
def calculate_value_no_drip(initial_investment, annual_yield_percent, period_years):
    # annual_yield_percent is like 0.6 (for 0.6%)
    yield_decimal = annual_yield_percent / 100
    # Assuming annual yield is applied to the initial investment for dividend calculation
    # This is simplified: actual dividends are usually based on share count * dividend per share
    total_dividends = initial_investment * yield_decimal * period_years
    final_value = initial_investment + total_dividends
    return round(final_value, 2) # Round to 2 decimal places

# Function to calculate value (With DRIP - compound interest on investment + reinvested dividends)
def calculate_value_with_drip(initial_investment, annual_yield_percent, period_years):
    yield_decimal = annual_yield_percent / 100
    # Assuming the "annual yield" implies the rate at which the investment grows compounded annually
    # This is a simplification, as DRIP means reinvesting dividends, which adds shares, not just value.
    # For a true DRIP calculation, you'd need initial share price, dividend per share, share growth.
    # Here, we're treating annual yield as a compound growth rate.
    final_value = initial_investment * (1 + yield_decimal)**period_years
    return round(final_value, 2) # Round to 2 decimal places


@app.route('/', methods=['GET'])
def index():
    # Initial page load, just render the form
    return render_template('index.html')

@app.route('/compare_stocks', methods=['POST'])
def compare_stocks():
    symbols = request.form.getlist('symbols[]')
    investments = [float(inv) for inv in request.form.getlist('investments[]')]
    annual_yields = [float(yield_val) for yield_val in request.form.getlist('annual_yields[]')]
    period = int(request.form['period'])

    comparison_results = {
        'tickers': [],
        'rows': [],
        'period': period
    }

    for i in range(len(symbols)):
        symbol = symbols[i].upper() # Convert to uppercase for consistency
        investment = investments[i]
        annual_yield = annual_yields[i] # This is like 0.6 for 0.6%

        # Calculate values
        value_no_drip = calculate_value_no_drip(investment, annual_yield, period)
        value_with_drip = calculate_value_with_drip(investment, annual_yield, period)

        comparison_results['tickers'].append(symbol)
        comparison_results['rows'].append({
            'ticker': symbol,
            'starting_investment': f"{investment:,.0f}", # Format as e.g., 10,000
            'annual_yield': f"{annual_yield:.1f}%", # Format as e.g., 0.6%
            'value_no_drip': f"{value_no_drip:,.0f}", # Format as e.g., 12,500
            'value_with_drip': f"{value_with_drip:,.0f}" # Format as e.g., 14,800
        })

    # Render the template again, but now pass the comparison_results
    return render_template('comparison_form.html', comparison_data=comparison_results)


if __name__ == "__main__":
    app.run(debug=False)
