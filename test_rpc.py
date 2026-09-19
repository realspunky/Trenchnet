import unittest
import time
from rpc_check import check
class RPCTests(unittest.TestCase):
 def mock(self,url,method,params):
  return {'eth_chainId':'0x38','eth_getBlockByNumber':{'number':'0x123','timestamp':hex(int(time.time()))},'eth_getCode':'0x1234','eth_getLogs':[]}[method]
 def test_ok(self):
  self.assertTrue(check('hidden',self.mock)['log_query_supported'])
 def test_wrong_chain(self):
  with self.assertRaises(ValueError):check('hidden',lambda *args:'0x61')
 def test_disabled_logs(self):
  def rpc(url,method,params):
   if method=='eth_getLogs':raise ValueError('Disabled')
   return self.mock(url,method,params)
  self.assertFalse(check('hidden',rpc)['log_query_supported'])

 def test_stale_block(self):
  def rpc(url,method,params):
   if method=='eth_getBlockByNumber':return {'number':'0x123','timestamp':'0x1'}
   return self.mock(url,method,params)
  with self.assertRaises(ValueError):check('hidden',rpc)
