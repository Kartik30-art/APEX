"""Market-data adapters. Credentials are read only from environment variables."""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from .data_validation import Candle, validate_candles
from .models import Quote

class ProviderNotConfigured(RuntimeError): pass
class ProviderError(RuntimeError): pass

def _json_get(url: str, headers: dict | None = None, timeout: int = 15):
    request = Request(url, headers=headers or {"User-Agent":"APEX-Research/0.2"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise ProviderError(f"Market-data request failed: {type(exc).__name__}") from exc
    if isinstance(payload, dict) and payload.get("status") == "error":
        raise ProviderError(str(payload.get("message", "provider returned an error")))
    return payload

class TwelveDataForexProvider:
    """Twelve Data REST adapter; use only under a plan permitting your use case."""
    BASE = "https://api.twelvedata.com"
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("TWELVEDATA_API_KEY")
        if not self.api_key:
            raise ProviderNotConfigured("Set TWELVEDATA_API_KEY in the deployment environment")

    def quote(self, symbol: str) -> Quote:
        params = urlencode({"symbol":symbol,"apikey":self.api_key})
        data = _json_get(f"{self.BASE}/quote?{params}")
        stamp = datetime.fromisoformat(data["datetime"].replace(" ","T")).replace(tzinfo=timezone.utc)
        return Quote(symbol,Decimal(str(data["bid"])),Decimal(str(data["ask"])),stamp,"twelvedata")

    def candles(self, symbol: str, interval: str = "1min", outputsize: int = 500) -> list[Candle]:
        if not 2 <= outputsize <= 5000: raise ValueError("outputsize must be between 2 and 5000")
        params = urlencode({"symbol":symbol,"interval":interval,"outputsize":outputsize,"order":"ASC","apikey":self.api_key})
        data = _json_get(f"{self.BASE}/time_series?{params}")
        values = data.get("values")
        if not isinstance(values,list): raise ProviderError("Provider response did not contain candle values")
        result=[]
        for row in values:
            stamp=datetime.fromisoformat(row["datetime"].replace(" ","T")).replace(tzinfo=timezone.utc)
            result.append(Candle(stamp,Decimal(row["open"]),Decimal(row["high"]),Decimal(row["low"]),Decimal(row["close"]),Decimal(row.get("volume","0") or "0")))
        report=validate_candles(result)
        if not report.valid: raise ProviderError("Provider candles failed validation: "+"; ".join(report.errors))
        return result

class LicensedIndiaJSONProvider:
    """User-configured licensed India vendor endpoint; no exchange-page scraping."""
    def __init__(self, endpoint: str | None = None, token: str | None = None):
        self.endpoint=endpoint or os.getenv("APEX_INDIA_DATA_URL")
        self.token=token or os.getenv("APEX_INDIA_DATA_TOKEN")
        if not self.endpoint: raise ProviderNotConfigured("Set APEX_INDIA_DATA_URL for your licensed India data vendor")

    def candles(self, symbol: str) -> list[Candle]:
        separator="&" if "?" in self.endpoint else "?"
        url=self.endpoint+separator+urlencode({"symbol":symbol})
        headers={"User-Agent":"APEX-Research/0.2"}
        if self.token: headers["Authorization"]=f"Bearer {self.token}"
        data=_json_get(url,headers=headers)
        values=data.get("values") if isinstance(data,dict) else data
        if not isinstance(values,list): raise ProviderError("India vendor response must be a list or contain values[]")
        result=[Candle(datetime.fromisoformat(str(x["timestamp"]).replace("Z","+00:00")),Decimal(str(x["open"])),Decimal(str(x["high"])),Decimal(str(x["low"])),Decimal(str(x["close"])),Decimal(str(x.get("volume","0")))) for x in values]
        report=validate_candles(result)
        if not report.valid: raise ProviderError("India vendor candles failed validation: "+"; ".join(report.errors))
        return result
