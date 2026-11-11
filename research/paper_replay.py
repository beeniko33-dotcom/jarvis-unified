"""Auditable, restart-safe historical-data paper replay. Never connects to a broker."""
from __future__ import annotations
import argparse, csv, hashlib, json, sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

@dataclass(frozen=True)
class Bar:
    timestamp: str
    symbol: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

def dec(value: str, field: str) -> Decimal:
    try: result = Decimal(value)
    except (InvalidOperation, TypeError) as exc: raise ValueError(f"invalid {field}: {value!r}") from exc
    if not result.is_finite(): raise ValueError(f"{field} must be finite")
    return result

def load_bars(path: Path):
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    bars = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"timestamp","symbol","open","high","low","close","volume"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("CSV must contain timestamp,symbol,open,high,low,close,volume")
        for line, row in enumerate(reader, 2):
            try:
                stamp = datetime.fromisoformat(row["timestamp"].replace("Z","+00:00"))
                if stamp.tzinfo is None: raise ValueError("timestamp must include timezone")
                stamp = stamp.astimezone(timezone.utc).isoformat()
                symbol = row["symbol"].strip().upper()
                if not symbol: raise ValueError("symbol is required")
                values = {k: dec(row[k],k) for k in ("open","high","low","close","volume")}
                if any(values[k] <= 0 for k in ("open","high","low","close")) or values["volume"] < 0:
                    raise ValueError("prices must be positive and volume non-negative")
                if values["high"] < max(values["open"],values["close"],values["low"]): raise ValueError("inconsistent high")
                if values["low"] > min(values["open"],values["close"],values["high"]): raise ValueError("inconsistent low")
                bars.append(Bar(stamp,symbol,**values))
            except Exception as exc: raise ValueError(f"CSV line {line}: {exc}") from exc
    bars.sort(key=lambda b:(b.symbol,b.timestamp))
    if not bars: raise ValueError("CSV contains no bars")
    if len({(b.symbol,b.timestamp) for b in bars}) != len(bars): raise ValueError("duplicate symbol/timestamp bars")
    return bars,digest

class PaperReplay:
    STRATEGY_ID="sma-crossover-long"
    STRATEGY_VERSION="1.0.0"
    def __init__(self,database:Path,*,starting_cash=Decimal("10000"),fast=10,slow=30,
                 risk_fraction=Decimal("0.01"),fee_bps=Decimal("10"),slippage_bps=Decimal("5"),
                 max_daily_loss_fraction=Decimal("0.02")):
        if fast<2 or slow<=fast: raise ValueError("require 2 <= fast < slow")
        if starting_cash<=0 or not (0<risk_fraction<=Decimal("0.02")): raise ValueError("invalid starting cash or risk fraction")
        if fee_bps<0 or slippage_bps<0 or not (0<max_daily_loss_fraction<=Decimal("0.10")): raise ValueError("invalid costs or daily loss limit")
        self.fast,self.slow=fast,slow
        self.risk_fraction,self.fee_bps,self.slippage_bps=risk_fraction,fee_bps,slippage_bps
        self.max_daily_loss_fraction=max_daily_loss_fraction
        database.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(database)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS bars(symbol TEXT,ts TEXT,close TEXT,source_sha256 TEXT,PRIMARY KEY(symbol,ts));
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,ts TEXT,symbol TEXT,kind TEXT,payload TEXT,previous_hash TEXT,event_hash TEXT UNIQUE);
        CREATE TABLE IF NOT EXISTS account(id INTEGER PRIMARY KEY CHECK(id=1),cash TEXT,equity TEXT,realized TEXT,peak_equity TEXT,day TEXT,day_start_equity TEXT);
        CREATE TABLE IF NOT EXISTS positions(symbol TEXT PRIMARY KEY,quantity TEXT,entry_price TEXT,entry_fee TEXT,opened_at TEXT);
        """)
        self.db.execute("INSERT OR IGNORE INTO account VALUES(1,?,?,?,?,?,?)",
          (str(starting_cash),str(starting_cash),"0",str(starting_cash),"",str(starting_cash)))
        self.db.commit()
    def close(self): self.db.close()
    def _account(self):
        row=self.db.execute("SELECT cash,equity,realized,peak_equity,day,day_start_equity FROM account WHERE id=1").fetchone()
        return [Decimal(row[i]) if i in (0,1,2,3,5) else row[i] for i in range(6)]
    def _event(self,ts,symbol,kind,payload):
        last=self.db.execute("SELECT event_hash FROM events ORDER BY id DESC LIMIT 1").fetchone()
        prev=last[0] if last else "GENESIS"
        encoded=json.dumps(payload,sort_keys=True,separators=(",",":"))
        digest=hashlib.sha256("|".join((ts,symbol,kind,encoded,prev)).encode()).hexdigest()
        self.db.execute("INSERT INTO events(ts,symbol,kind,payload,previous_hash,event_hash) VALUES(?,?,?,?,?,?)",
                        (ts,symbol,kind,encoded,prev,digest))
    def _save(self,cash,equity,realized,peak,day,day_start):
        self.db.execute("UPDATE account SET cash=?,equity=?,realized=?,peak_equity=?,day=?,day_start_equity=? WHERE id=1",
                        tuple(map(str,(cash,equity,realized,peak,day,day_start))))
    def replay(self,bars:Iterable[Bar],source_sha256:str):
        grouped={}
        for bar in bars: grouped.setdefault(bar.symbol,[]).append(bar)
        for symbol,series in grouped.items():
            closes=[]
            for bar in series:
                inserted=self.db.execute("INSERT OR IGNORE INTO bars VALUES(?,?,?,?)",
                    (symbol,bar.timestamp,str(bar.close),source_sha256)).rowcount
                if not inserted: continue
                closes.append(bar.close)
                if len(closes)<=self.slow: continue
                fast_now=sum(closes[-self.fast:],Decimal(0))/self.fast
                slow_now=sum(closes[-self.slow:],Decimal(0))/self.slow
                fast_prev=sum(closes[-self.fast-1:-1],Decimal(0))/self.fast
                slow_prev=sum(closes[-self.slow-1:-1],Decimal(0))/self.slow
                up=fast_prev<=slow_prev and fast_now>slow_now
                down=fast_prev>=slow_prev and fast_now<slow_now
                cash,equity,realized,peak,day,day_start=self._account()
                # Mark all open symbols to their latest observed close before risk checks.
                market_value=Decimal("0")
                for held_symbol, qty_s in self.db.execute("SELECT symbol,quantity FROM positions").fetchall():
                    latest=self.db.execute("SELECT close FROM bars WHERE symbol=? ORDER BY ts DESC LIMIT 1",(held_symbol,)).fetchone()
                    if latest: market_value += Decimal(qty_s) * Decimal(latest[0])
                equity=cash+market_value
                current_day=bar.timestamp[:10]
                if day!=current_day: day,day_start=current_day,equity
                pos=self.db.execute("SELECT quantity,entry_price,entry_fee FROM positions WHERE symbol=?",(symbol,)).fetchone()
                self._event(bar.timestamp,symbol,"observation",{"strategy_id":self.STRATEGY_ID,"strategy_version":self.STRATEGY_VERSION,
                    "signal":"buy" if up else "sell" if down else "hold","fast_sma":str(fast_now),"slow_sma":str(slow_now),
                    "close":str(bar.close),"source_sha256":source_sha256})
                if pos and down:
                    qty,entry,entry_fee=map(Decimal,pos)
                    fill=bar.close*(1-self.slippage_bps/Decimal(10000))
                    fee=abs(qty*fill)*self.fee_bps/Decimal(10000)
                    pnl=(fill-entry)*qty-fee-entry_fee
                    cash+=qty*fill-fee; realized+=pnl
                    self.db.execute("DELETE FROM positions WHERE symbol=?",(symbol,))
                    self._event(bar.timestamp,symbol,"exit_fill",{"strategy_id":self.STRATEGY_ID,"strategy_version":self.STRATEGY_VERSION,
                        "reason":"sma_cross_down","quantity":str(qty),"price":str(fill),"fee":str(fee),"realized_net_pnl":str(pnl)})
                elif not pos and up and equity>0:
                    allowed=max(Decimal(0),day_start-equity)<day_start*self.max_daily_loss_fraction
                    notional=min(cash,equity*self.risk_fraction)
                    if allowed and notional>0:
                        fill=bar.close*(1+self.slippage_bps/Decimal(10000))
                        qty=notional/fill; fee=notional*self.fee_bps/Decimal(10000)
                        cash-=notional+fee
                        self.db.execute("INSERT INTO positions VALUES(?,?,?,?,?)",(symbol,str(qty),str(fill),str(fee),bar.timestamp))
                        self._event(bar.timestamp,symbol,"entry_fill",{"strategy_id":self.STRATEGY_ID,"strategy_version":self.STRATEGY_VERSION,
                            "reason":"sma_cross_up","quantity":str(qty),"price":str(fill),"notional":str(notional),"fee":str(fee),
                            "risk_fraction":str(self.risk_fraction)})
                    else: self._event(bar.timestamp,symbol,"risk_reject",{"reason":"daily_loss_limit" if not allowed else "insufficient_equity"})
                market_value=Decimal("0")
                for held_symbol, qty_s in self.db.execute("SELECT symbol,quantity FROM positions").fetchall():
                    latest=self.db.execute("SELECT close FROM bars WHERE symbol=? ORDER BY ts DESC LIMIT 1",(held_symbol,)).fetchone()
                    if latest: market_value += Decimal(qty_s) * Decimal(latest[0])
                equity=cash+market_value
                peak=max(peak,equity)
                self._save(cash,equity,realized,peak,day,day_start)
            self.db.commit()
        return self.report()
    def verify_chain(self):
        previous="GENESIS"
        for ts,symbol,kind,payload,prev,event_hash in self.db.execute("SELECT ts,symbol,kind,payload,previous_hash,event_hash FROM events ORDER BY id"):
            expected=hashlib.sha256("|".join((ts,symbol,kind,payload,previous)).encode()).hexdigest()
            if prev!=previous or event_hash!=expected: return False
            previous=event_hash
        return True
    def report(self):
        cash,equity,realized,peak,day,day_start=self._account()
        count=lambda kind:self.db.execute("SELECT COUNT(*) FROM events WHERE kind=?",(kind,)).fetchone()[0]
        positions=self.db.execute("SELECT symbol,quantity,entry_price FROM positions ORDER BY symbol").fetchall()
        return {"strategy_id":self.STRATEGY_ID,"strategy_version":self.STRATEGY_VERSION,
            "bars_processed":self.db.execute("SELECT COUNT(*) FROM bars").fetchone()[0],
            "distinct_utc_days":self.db.execute("SELECT COUNT(DISTINCT substr(ts,1,10)) FROM bars").fetchone()[0],
            "entries":count("entry_fill"),"exits":count("exit_fill"),"risk_rejections":count("risk_reject"),
            "realized_net_pnl":str(realized),"cash":str(cash),"equity":str(equity),"peak_equity":str(peak),
            "open_positions":[{"symbol":s,"quantity":q,"entry_price":p} for s,q,p in positions],
            "event_count":self.db.execute("SELECT COUNT(*) FROM events").fetchone()[0],
            "event_chain_valid":self.verify_chain(),
            "validation_note":"Historical-data paper replay only; no live feed, broker connection, forecast or profit guarantee."}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv",type=Path); parser.add_argument("--db",type=Path,default=Path("var/research_paper.sqlite3"))
    parser.add_argument("--fast",type=int,default=10); parser.add_argument("--slow",type=int,default=30)
    parser.add_argument("--min-days",type=int,default=1)
    args=parser.parse_args()
    try:
        bars,digest=load_bars(args.csv)
        engine=PaperReplay(args.db,fast=args.fast,slow=args.slow)
        try: result=engine.replay(bars,digest)
        finally: engine.close()
    except (OSError,ValueError,sqlite3.Error) as exc: parser.error(str(exc))
    print(json.dumps(result,indent=2))
    return 0 if result["distinct_utc_days"]>=args.min_days and result["event_chain_valid"] else 2
if __name__=="__main__": raise SystemExit(main())
