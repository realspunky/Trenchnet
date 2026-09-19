"""Read-only Flap BNB state reader. No transaction signing or wallet required."""
import json
import os
import re
import sys
import time
from decimal import Decimal

PORTAL = '0xe2cE6ab80874Fa9Fa2aAE65D277Dd6B8e65C9De0'
HELPER = '0x53841c73217735F37BC1775538b03b23feFD8346'
STATE_FIELDS = [('status','uint8'),('reserve','uint256'),('circulatingSupply','uint256'),
 ('price','uint256'),('tokenVersion','uint8'),('r','uint256'),('h','uint256'),('k','uint256'),
 ('dexSupplyThresh','uint256'),('quoteTokenAddress','address'),('nativeToQuoteSwapEnabled','bool'),
 ('extensionID','bytes32'),('buyTaxRate','uint256'),('sellTaxRate','uint256'),('pool','address'),
 ('progress','uint256'),('lpFeeProfile','uint8'),('dexId','uint8')]
TAX_FIELDS = [('marketBps','uint16'),('deflationBps','uint16'),('lpBps','uint16'),
 ('dividendBps','uint16'),('buyTaxRate','uint16'),('sellTaxRate','uint16'),
 ('burntTokenAmount','uint256'),('totalQuoteSentToDividend','uint256'),
 ('totalQuoteAddedToLiquidity','uint256'),('totalTokenAddedToLiquidity','uint256'),
 ('totalQuoteSentToMarketing','uint256'),('dividendToken','address'),('quoteToken','address'),
 ('minimumShareBalance','uint256')]
VAULT_FIELDS = [('addr','address'),('factory','address'),('riskLevel','uint8'),
 ('isOfficialVault','bool'),('isVault','bool'),('isAIConsumer','bool')]

def components(fields):
    return [{'name': name, 'type': typ} for name,typ in fields]

def abi(name, fields):
    return [{'name':name,'type':'function','stateMutability':'view',
             'inputs':[{'name':'token','type':'address'}],
             'outputs':[{'name':'result','type':'tuple','components':fields}]}]

def normalize(address, state, tax):
    """Require matching tax observations; unknown states fail closed."""
    if not re.fullmatch(r'0x[0-9a-fA-F]{40}', address):
        raise ValueError('Invalid token address')
    required = ['status','buyTaxRate','sellTaxRate','progress']
    if any(type(state.get(k)) is not int for k in required):
        raise ValueError('Incomplete state')
    if not 0 <= state['progress'] <= 10**18:
        raise ValueError('Invalid progress scale')
    allocations = ['marketBps','deflationBps','lpBps','dividendBps']
    if any(type(tax.get(k)) is not int or not 0 <= tax[k] <= 10000 for k in allocations):
        raise ValueError('Invalid allocation')
    if sum(tax[k] for k in allocations) > 10000:
        raise ValueError('Allocation exceeds 100%')
    consistent = all(type(tax.get(k)) is int and state[k] == tax[k]
                     for k in ['buyTaxRate','sellTaxRate'])
    eligible = (consistent and state['status'] in (1,4)
                and state['buyTaxRate'] == state['sellTaxRate'] == 300
                and tax['dividendBps'] > 0)
    return dict(address=address.lower(), chain='bnb', launchpad='flap', verified=eligible,
        total_tax_bps=300 if eligible else None, holder_rewards=tax['dividendBps'] > 0,
        buy_tax_bps=state['buyTaxRate'], sell_tax_bps=state['sellTaxRate'],
        bonding_percent=float(Decimal(state['progress']) / Decimal(10**16)),
        migrated=state['status']==4, status=state['status'],
        dividend_allocation_bps=tax['dividendBps'],
        reward_token=tax.get('dividendToken'), minimum_share_balance=str(tax.get('minimumShareBalance','')),
        tax_allocations={k:tax[k] for k in allocations},
        explorer_url='https://bscscan.com/token/'+address.lower())

class Reader:
    def __init__(self, url):
        from web3 import Web3
        self.w3 = Web3(Web3.HTTPProvider(url, request_kwargs={'timeout':20}))
        if self.w3.eth.chain_id != 56:
            raise ValueError('RPC is not BNB mainnet')
        for addr in [PORTAL,HELPER]:
            if not self.w3.eth.get_code(Web3.to_checksum_address(addr)):
                raise ValueError('Documented contract has no code on this RPC')
        self.portal = self.w3.eth.contract(address=Web3.to_checksum_address(PORTAL),
            abi=abi('getTokenV8Safe', components(STATE_FIELDS)))
        fields = components(TAX_FIELDS) + [{'name':'vaultInfo','type':'tuple','components':components(VAULT_FIELDS)}]
        self.helper = self.w3.eth.contract(address=Web3.to_checksum_address(HELPER),
            abi=abi('getTaxTokenInfoV2',fields))
    def inspect(self, address):
        address=self.w3.to_checksum_address(address)
        # Both reads use the same block to avoid mixed-time tax/progress values.
        block=self.w3.eth.get_block('finalized')
        if not -60 <= time.time()-block['timestamp'] <= 300:
            raise ValueError('Finalized block is stale or clock is incorrect')
        height=block['number']
        state=dict(zip([x[0] for x in STATE_FIELDS],
            self.portal.functions.getTokenV8Safe(address).call(block_identifier=height)))
        tax=dict(zip([x[0] for x in TAX_FIELDS]+['vaultInfo'],
            self.helper.functions.getTaxTokenInfoV2(address).call(block_identifier=height)))
        result=normalize(address,state,tax)
        result.update(block_number=height,block_hash=block['hash'].hex())
        return result

if __name__=='__main__':
    url=os.environ.get('BNB_RPC_URL','https://bsc-dataseed.bnbchain.org')
    if not url or len(sys.argv)!=2:
        raise SystemExit('Set BNB_RPC_URL securely, then run: python flap.py TOKEN_ADDRESS')
    try:
        print(json.dumps(Reader(url).inspect(sys.argv[1]),indent=2))
    except Exception:
        raise SystemExit('Read failed. Check RPC configuration, finalized-block support and token contract. No alert emitted.')
