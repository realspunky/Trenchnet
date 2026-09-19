import io
import sqlite3
import time
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from eth_abi import encode
from web3 import Web3
from scanner import setup, decode_launch, persist_batch, queue_candidate, deliver, Scanner, PORTAL, SIGNATURE, TYPES
from flap import normalize

A='0x'+'1'*40
NOW=2000000000

def event():
    return dict(address=PORTAL, topics=['0x'+Web3.keccak(text=SIGNATURE).hex().removeprefix('0x')],
        data='0x'+encode(TYPES,[NOW,A,1,A,'Example\nToken','TEST','ipfs://example']).hex(),
        blockNumber='0x65',transactionHash='0x'+'2'*64)

def snapshot(progress=85,status=1):
    return normalize(A,dict(status=status,buyTaxRate=300,sellTaxRate=300,progress=progress*10**16),
        dict(marketBps=2000,deflationBps=0,lpBps=0,dividendBps=8000,buyTaxRate=300,sellTaxRate=300))

class PilotTests(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:');setup(self.c)
        self.c.execute('CREATE TABLE users(id INTEGER PRIMARY KEY, threshold INTEGER)')
        self.t=decode_launch(event())
    def tearDown(self):self.c.close()
    def queue(self):
        with self.c:queue_candidate(self.c,self.t,snapshot(),12,85,NOW)
    def test_event_identity_and_metadata(self):
        self.assertEqual(self.t['name'],'ExampleToken')
        self.assertEqual(self.t['address'],A)
        for bad in [dict(event(),address='0x'+'3'*40),dict(event(),topics=[]),dict(event(),removed=True),dict(event(),data='0x00')]:
            with self.assertRaises(Exception):decode_launch(bad)
    def test_checkpoint_and_tokens_are_atomic(self):
        persist_batch(self.c,[self.t],101,'hash1')
        with self.assertRaises(KeyError):persist_batch(self.c,[dict(self.t,address='different'),{}],102,'hash2')
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM scan_tokens').fetchone()[0],1)
        self.assertEqual(self.c.execute('SELECT height FROM scan_cursor').fetchone()[0],101)
    def test_restart_dedup_and_threshold_crossing(self):
        with self.c:queue_candidate(self.c,self.t,snapshot(84),12,85,NOW)
        setup(self.c)
        self.queue();self.queue()
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM pilot_outbox').fetchone()[0],2)
        self.assertEqual(self.c.execute('SELECT DISTINCT recipient FROM pilot_outbox').fetchall(),[(12,)])
    def test_old_launch_migration_and_nonmatching_excluded(self):
        with self.c:
            queue_candidate(self.c,self.t,snapshot(70),12,85,NOW+601)
            queue_candidate(self.c,self.t,snapshot(99,4),12,85,NOW)
            queue_candidate(self.c,self.t,dict(snapshot(),verified=False),12,85,NOW)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM pilot_outbox').fetchone()[0],0)
    @patch('scanner.time.time',return_value=NOW)
    def test_success_and_ambiguous_delivery(self,_):
        self.queue();send=Mock(return_value={'message_id':44})
        deliver(self.c,'unused',send)
        self.assertEqual(send.call_args.args[2]['chat_id'],12)
        send.side_effect=TimeoutError()
        deliver(self.c,'unused',send);setup(self.c);deliver(self.c,'unused',send)
        self.assertEqual(send.call_count,2)
        self.assertEqual(self.c.execute('SELECT state FROM pilot_outbox ORDER BY id').fetchall(),[('sent',),('uncertain',)])
    @patch('scanner.time.time',return_value=NOW)
    def test_explicit_rate_limit_retries_after_delay(self,_):
        self.queue()
        send=Mock(side_effect=HTTPError('redacted',429,'rate limited',{},io.BytesIO(b'{"parameters":{"retry_after":30}}')))
        deliver(self.c,'unused',send)
        row=self.c.execute('SELECT state,attempts,next_attempt FROM pilot_outbox ORDER BY id LIMIT 1').fetchone()
        self.assertEqual(row,('pending',1,NOW+30))
    def test_stale_pending_alerts_expire(self):
        self.queue();send=Mock()
        with patch('scanner.time.time',return_value=NOW+301):deliver(self.c,'unused',send)
        send.assert_not_called()
        self.assertEqual(self.c.execute('SELECT DISTINCT state FROM pilot_outbox').fetchall(),[('expired',)])
    def test_inflight_on_restart_not_resent(self):
        self.queue();self.c.execute("UPDATE pilot_outbox SET state='sending'");self.c.commit()
        setup(self.c)
        self.assertEqual(self.c.execute('SELECT DISTINCT state FROM pilot_outbox').fetchall(),[('uncertain',)])
    def scanner(self):
        scanner=Scanner.__new__(Scanner)
        scanner.c=self.c;scanner.url='unused';scanner.recipient=12;scanner.topic=event()['topics'][0];scanner.reader=Mock()
        return scanner
    @patch('scanner.time.time',return_value=NOW)
    def test_scan_checkpoint_range_and_reorg_stop(self,_):
        persist_batch(self.c,[],100,'old')
        scanner=self.scanner();scanner.reader.inspect.return_value=snapshot()
        responses=[dict(number=hex(105),timestamp=hex(NOW),hash='new'),dict(hash='old'),[event()],dict(hash='new')]
        with patch('scanner.call',side_effect=responses) as rpc:scanner.scan()
        query=rpc.call_args_list[2].args[2][0]
        self.assertEqual((query['fromBlock'],query['toBlock']),('0x65','0x69'))
        self.assertEqual(self.c.execute('SELECT height FROM scan_cursor').fetchone()[0],105)
        with patch('scanner.call',side_effect=[responses[0],dict(hash='changed')]):
            with self.assertRaises(ValueError):scanner.scan()
    @patch('scanner.time.time',return_value=NOW)
    def test_malformed_log_never_advances_cursor(self,_):
        persist_batch(self.c,[],100,'old')
        responses=[dict(number=hex(105),timestamp=hex(NOW)),dict(hash='old'),[dict(event(),data='0x00')]]
        with patch('scanner.call',side_effect=responses):
            with self.assertRaises(Exception):self.scanner().scan()
        self.assertEqual(self.c.execute('SELECT height FROM scan_cursor').fetchone()[0],100)

if __name__=='__main__':unittest.main()
