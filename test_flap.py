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
  self.assertTrue(qualifies(t));self.assertTrue(advance_due(t,85));self.assertFalse(advance_due(t,86))
 def test_asymmetric_and_inconsistent_excluded(self):
  self.assertFalse(qualifies(normalize(A,dict(self.s,sellTaxRate=500),dict(self.t,sellTaxRate=500))))
  self.assertFalse(qualifies(normalize(A,self.s,dict(self.t,buyTaxRate=500))))
 def test_rewards_required(self):
  self.assertFalse(qualifies(normalize(A,self.s,dict(self.t,dividendBps=0))))
 def test_invalid_and_staged_excluded(self):
  for status in [0,2,3,5,99]:
   self.assertFalse(qualifies(normalize(A,dict(self.s,status=status),self.t)))
 def test_migrated_not_advance(self):
  self.assertFalse(advance_due(normalize(A,dict(self.s,status=4),self.t),80))
 def test_malformed(self):
  with self.assertRaises(ValueError):normalize(A,dict(self.s,progress=10**19),self.t)
  with self.assertRaises(ValueError):normalize(A,self.s,dict(self.t,dividendBps=-1))
  with self.assertRaises(ValueError):normalize(A,{},self.t)
