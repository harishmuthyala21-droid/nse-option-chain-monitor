import time
import requests
import numpy as np
import pandas as pd

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}

def create_nse_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    session.get("https://www.nseindia.com/option-chain", timeout=10)
    return session

def fetch_option_chain(session, symbol="NIFTY"):
    url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
    response = session.get(url, timeout=10)
    
    if response.status_code in (401, 403):
        session = create_nse_session()
        response = session.get(url, timeout=10)
        
    return response.json(), session

def calculate_max_pain(df):
    """
    Computes Max Pain strike across all valid strikes using vectorization.
    """
    strikes = df["Strike"].to_numpy()
    call_oi = df["Call_OI"].to_numpy()
    put_oi = df["Put_OI"].to_numpy()
    
    total_loss = []
    for s in strikes:
        # Payout to Call buyers if price settles at s
        call_loss = np.sum(np.maximum(0, s - strikes) * call_oi)
        # Payout to Put buyers if price settles at s
        put_loss = np.sum(np.maximum(0, strikes - s) * put_oi)
        total_loss.append(call_loss + put_loss)
        
    min_loss_idx = np.argmin(total_loss)
    return strikes[min_loss_idx]

def compute_multi_strike_pcr(df, spot, strikes_above_below=5):
    """
    Extracts +/- N strikes around ATM and calculates concentrated PCR.
    """
    # Identify the closest ATM strike
    df["ATM_Diff"] = (df["Strike"] - spot).abs()
    atm_idx = df["ATM_Diff"].idxmin()
    
    # Slice +/- N strikes around ATM
    start_pos = max(0, df.index.get_loc(atm_idx) - strikes_above_below)
    end_pos = min(len(df), df.index.get_loc(atm_idx) + strikes_above_below + 1)
    
    atm_window = df.iloc[start_pos:end_pos]
    
    sum_put_oi = atm_window["Put_OI"].sum()
    sum_call_oi = atm_window["Call_OI"].sum()
    
    pcr = round(sum_put_oi / sum_call_oi, 3) if sum_call_oi > 0 else 0.0
    return pcr, atm_window["Strike"].min(), atm_window["Strike"].max()

def parse_chain_data(data):
    records = data["records"]["data"]
    expiry = data["records"]["expiryDates"][0]
    spot = data["records"]["underlyingValue"]

    strikes, call_oi, put_oi, call_chg, put_chg = [], [], [], [], []

    for item in records:
        if item.get("expiryDate") == expiry:
            strike = item["strikePrice"]
            ce = item.get("CE", {})
            pe = item.get("PE", {})

            strikes.append(strike)
            call_oi.append(ce.get("openInterest", 0))
            put_oi.append(pe.get("openInterest", 0))
            call_chg.append(ce.get("changeinOpenInterest", 0))
            put_chg.append(pe.get("changeinOpenInterest", 0))

    df = pd.DataFrame({
        "Strike": strikes,
        "Call_OI": call_oi,
        "Call_Chg_OI": call_chg,
        "Put_OI": put_oi,
        "Put_Chg_OI": put_chg
    }).sort_values("Strike").reset_index(drop=True)

    return df, spot

def run_advanced_monitor(symbol="NIFTY", interval_sec=60):
    session = create_nse_session()
    previous_multi_pcr = None
    
    print(f"--- Monitoring {symbol} Advanced Greeks & Flow (Refresh: {interval_sec}s) ---")

    while True:
        try:
            raw_data, session = fetch_option_chain(session, symbol=symbol)
            df, spot = parse_chain_data(raw_data)
            
            # 1. Calculate Max Pain
            max_pain = calculate_max_pain(df)
            
            # 2. Multi-Strike PCR (ATM +/- 5 strikes = 11 strikes cluster)
            current_multi_pcr, lower_strike, upper_strike = compute_multi_strike_pcr(df, spot, strikes_above_below=5)
            
            # 3. PCR Delta calculation
            if previous_multi_pcr is not None:
                pcr_delta = round(current_multi_pcr - previous_multi_pcr, 4)
            else:
                pcr_delta = 0.0
            previous_multi_pcr = current_multi_pcr

            # 4. Institutional levels
            res_strike = df.loc[df["Call_OI"].idxmax()]["Strike"]
            sup_strike = df.loc[df["Put_OI"].idxmax()]["Strike"]

            # Flow state indicator
            bias = "BULLISH (Put Writing)" if pcr_delta > 0.01 else ("BEARISH (Call Writing)" if pcr_delta < -0.01 else "NEUTRAL / BALANCED")

            print(f"\n[{time.strftime('%H:%M:%S')}] Spot: {spot:.2f} | Max Pain: {max_pain}")
            print(f"Key S/R: Support @ {sup_strike} | Resistance @ {res_strike}")
            print(f"ATM PCR [{int(lower_strike)} - {int(upper_strike)}]: {current_multi_pcr:.3f} | PCR Delta: {pcr_delta:+.4f}")
            print(f"Flow Bias: {bias}")

        except Exception as err:
            print(f"Fetch failed: {err}. Re-establishing connection...")
            session = create_nse_session()

        time.sleep(interval_sec)

if __name__ == "__main__":
    run_advanced_monitor("NIFTY", interval_sec=60)
