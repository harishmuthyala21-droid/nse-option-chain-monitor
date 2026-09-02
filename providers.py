from __future__ import annotations
import csv, os
from pathlib import Path
from .models import OptionRow

class CSVProvider:
    def __init__(self, path):
        self.path = Path(path)
    
    def get_option_chain(self, symbol, expiry=None):
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        
        out = []
        with self.path.open(newline='', encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                if r['symbol'].upper() != symbol.upper():
                    continue
                if expiry and r.get('expiry') and r['expiry'] != expiry:
                    continue
                
                out.append(OptionRow(
                    symbol=r['symbol'],
                    expiry=r.get('expiry', ''),
                    strike=float(r['strike']),
                    call_oi=float(r.get('call_oi', 0) or 0),
                    call_oi_change=float(r.get('call_oi_change', 0) or 0),
                    call_ltp=float(r.get('call_ltp', 0) or 0),
                    put_oi=float(r.get('put_oi', 0) or 0),
                    put_oi_change=float(r.get('put_oi_change', 0) or 0),
                    put_ltp=float(r.get('put_ltp', 0) or 0),
                    spot=float(r['spot'])
                ))
        return out

class DemoProvider:
    def get_option_chain(self, symbol, expiry=None):
        spot = 23914.0 if symbol.upper() == 'NIFTY' else 55200.0
        step = 50 if symbol.upper() == 'NIFTY' else 100
        center = round(spot / step) * step
        out = []
        
        for i in range(-10, 11):
            k = center + step * i
            d = abs(k - spot) / spot
            call = max(10000, 900000 * (1 - min(d * 7, .75)) + max(0, k - center) * 1200)
            put = max(10000, 820000 * (1 - min(d * 6, .72)) + max(0, center - k) * 1100)
            
            out.append(OptionRow(
                symbol=symbol.upper(),
                expiry=expiry or 'DEMO',
                strike=k,
                call_oi=call,
                call_oi_change=(95000 if k == center + step * 2 else 15000),
                call_ltp=max(1, spot - k) * .08 + 60,
                put_oi=put,
                put_oi_change=(65000 if k == center - step * 2 else 12000),
                put_ltp=max(1, k - spot) * .08 + 60,
                spot=spot
            ))
        return out

class AuthorizedProvider:
    def get_option_chain(self, symbol, expiry=None):
        raise NotImplementedError('Connect this adapter to your authorized broker/data API.')

def make_provider():
    mode = os.getenv('DATA_MODE', 'demo').lower()
    if mode == 'csv':
        return CSVProvider(os.getenv('CSV_PATH', 'data/option_chain.csv'))
    elif mode == 'broker':
        return AuthorizedProvider()
    else:
        return DemoProvider()
