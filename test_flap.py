import unittest
from flap import normalize
from bot import qualifies,advance_due
A='0x'+'1'*40
class FlapTests(unittest.TestCase):
 def setUp(self):
  self.s=dict(status=1,buyTaxRate=300,sellTaxRate=300,progress=85*10**16)
  self.t=dict(buyTaxRate=300,sellTaxRate=300,marketBps=2000,deflationBps=0,lpBps=0,dividendBps=8000)
 def test_qualifying_and_progress(self):
  t=normalize(A,self.s,self.t)
  self.assertTrue(t['verified']);self.assertEqual(t['bonding_percent'],85)
  self.assertIsNone(t['total_tax_bps']);self.assertFalse(qualifies(t))
  self.assertEqual(t['token_tax_bps'],300)
 def test_expanded_tax_rates(self):
  for rate in [100,200,300]:
   result=normalize(A,dict(self.s,buyTaxRate=rate,sellTaxRate=rate),dict(self.t,buyTaxRate=rate,sellTaxRate=rate))
   self.assertTrue(result['verified'])
   self.assertEqual(result['token_tax_bps'],rate)
   self.assertIsNone(result['total_tax_bps'])
  for rate in [0,50,150,250,400,500]:
   self.assertFalse(normalize(A,dict(self.s,buyTaxRate=rate,sellTaxRate=rate),dict(self.t,buyTaxRate=rate,sellTaxRate=rate))['verified'])
  self.assertFalse(normalize(A,dict(self.s,buyTaxRate=100,sellTaxRate=200),dict(self.t,buyTaxRate=100,sellTaxRate=200))['verified'])
 def test_asymmetric_and_inconsistent_excluded(self):
  self.assertFalse(normalize(A,dict(self.s,sellTaxRate=500),dict(self.t,sellTaxRate=500))['verified'])
  self.assertFalse(normalize(A,self.s,dict(self.t,buyTaxRate=500))['verified'])
 def test_rewards_required(self):
  self.assertFalse(normalize(A,self.s,dict(self.t,dividendBps=0))['verified'])
 def test_invalid_and_staged_excluded(self):
  for status in [0,2,3,5,99]:
   self.assertFalse(normalize(A,dict(self.s,status=status),self.t)['verified'])
 def test_migrated_not_advance(self):
  self.assertTrue(normalize(A,dict(self.s,status=4),self.t)['migrated'])
 def test_malformed(self):
  with self.assertRaises(ValueError):normalize(A,dict(self.s,progress=10**19),self.t)
  with self.assertRaises(ValueError):normalize(A,self.s,dict(self.t,dividendBps=-1))
  with self.assertRaises(ValueError):normalize(A,{},self.t)
