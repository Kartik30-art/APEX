import pytest
from apex.streaming import TwelveDataForexStream, StreamNotConfigured

def test_stream_requires_provider_key(monkeypatch):
    monkeypatch.delenv("TWELVEDATA_API_KEY",raising=False)
    with pytest.raises(StreamNotConfigured):
        TwelveDataForexStream()

def test_stream_rejects_more_than_eight_symbols():
    stream=TwelveDataForexStream(api_key="test-only")
    with pytest.raises(ValueError):
        stream.start([f"FX{i}" for i in range(9)])
