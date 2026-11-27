from decimal import Decimal
from pathlib import Path
import pytest
from apex.instruments import NSE_INR_FUTURES, FeeSchedule, calculate_futures_valuation, whole_contracts
from apex.storage import APEXStore
from apex.broker import LiveBrokerGateway, LiveExecutionLocked, OrderRequest, PaperBroker
from apex.providers import TwelveDataForexProvider, LicensedIndiaJSONProvider, ProviderNotConfigured
from apex.ai_research import AIResearch, AIProviderNotConfigured

def test_nse_usdinr_contract_value_and_tick_value():
 r=calculate_futures_valuation(NSE_INR_FUTURES['USDINR'],contracts=2,entry_price=Decimal('83'),exit_price=Decimal('83.01'),side='buy')
 assert r.gross_pnl_quote==Decimal('20') and r.tick_value_quote==Decimal('5') and r.notional_quote==Decimal('166000')
def test_jpyinr_quotation_factor():
 r=calculate_futures_valuation(NSE_INR_FUTURES['JPYINR'],contracts=1,entry_price=Decimal('55'),exit_price=Decimal('55.01'),side='buy')
 assert r.gross_pnl_quote==Decimal('10') and r.tick_value_quote==Decimal('2.5')
def test_fee_schedule():
 r=calculate_futures_valuation(NSE_INR_FUTURES['USDINR'],contracts=1,entry_price=Decimal('83'),exit_price=Decimal('83.01'),side='buy',fees=FeeSchedule(brokerage_per_order=Decimal('10')))
 assert r.estimated_fees_quote>=Decimal('20') and r.net_pnl_quote<r.gross_pnl_quote
def test_whole_contracts():
 assert whole_contracts(Decimal('2500'),NSE_INR_FUTURES['USDINR'])==2
def test_store_backup(tmp_path):
 from datetime import datetime,timezone
 from apex.data_validation import Candle
 store=APEXStore(str(tmp_path/'main.sqlite'))
 c=Candle(datetime(2026,1,1,tzinfo=timezone.utc),Decimal('1'),Decimal('2'),Decimal('0.5'),Decimal('1.5'),Decimal('10'))
 assert store.save_candles('forex','EURUSD','1h',[c],'fixture')==1
 assert store.load_candles('forex','EURUSD','1h')==[c]
 b=store.backup(str(tmp_path/'backup.sqlite'))
 assert b['integrity']=='ok' and Path(b['path']).exists() and len(b['sha256'])==64
def test_paper_broker_idempotency(tmp_path):
 store=APEXStore(str(tmp_path/'apex.sqlite')); broker=PaperBroker(store)
 order=OrderRequest('india_currency_derivatives','USDINR','buy',Decimal('1'))
 assert broker.place_order(order,'fixed-id')['status']=='PENDING_PAPER'
 with pytest.raises(Exception): broker.place_order(order,'fixed-id')
def test_live_gateway_locked():
 with pytest.raises(LiveExecutionLocked): LiveBrokerGateway().place_order(OrderRequest('forex','EURUSD','buy',Decimal('1')),'id')
def test_adapters_fail_closed_without_credentials(monkeypatch):
 for k in ('TWELVEDATA_API_KEY','APEX_INDIA_DATA_URL','OPENAI_API_KEY','GEMINI_API_KEY','ANTHROPIC_API_KEY'): monkeypatch.delenv(k,raising=False)
 with pytest.raises(ProviderNotConfigured): TwelveDataForexProvider()
 with pytest.raises(ProviderNotConfigured): LicensedIndiaJSONProvider()
 with pytest.raises(AIProviderNotConfigured): AIResearch().ask('openai','review')
