#!/usr/bin/env python3
# Copyright (c) 2022 The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

from decimal import Decimal, getcontext

from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import (
    assert_greater_than_or_equal,
    assert_greater_than,
    assert_equal,
)

class UnconfirmedInputTest(BitcoinTestFramework):
    def set_test_params(self):
        getcontext().prec=9
        self.setup_clean_chain = True
        self.num_nodes = 1

    def setup_and_fund_wallet(self, walletname):
        self.nodes[0].createwallet(walletname)
        wallet = self.nodes[0].get_wallet_rpc(walletname)

        self.def_wallet.sendtoaddress(address=wallet.getnewaddress(), amount=2)
        self.generate(self.nodes[0], 1) # confirm funding tx
        return wallet

    def skip_test_if_missing_module(self):
        self.skip_if_no_wallet()

    def calc_fee_rate(self, tx):
        fee = Decimal(-1e8) * tx["fee"]
        vsize = tx["decoded"]["vsize"]
        return fee / vsize

    def calc_set_fee_rate(self, txs):
        fees = Decimal(-1e8) * sum([tx["fee"] for tx in txs]) # fee is negative!
        vsizes = sum([tx["decoded"]["vsize"] for tx in txs])
        return fees / vsizes

    def assert_spends_only_parent(self, tx, parent_txid):
        number_inputs = len(tx["decoded"]["vin"])
        assert_equal(number_inputs, 1)
        txid_of_input = tx["decoded"]["vin"][0]["txid"]
        assert_equal(txid_of_input, parent_txid)

    def test_target_feerate_confirmed(self):
        self.log.info("Start test feerate with confirmed input")
        wallet = self.setup_and_fund_wallet("confirmed_wallet")

        spending_txid = wallet.sendtoaddress(address=self.def_wallet.getnewaddress(), amount=0.5, fee_rate=self.target_fee_rate)
        spending_tx = wallet.gettransaction(txid=spending_txid, verbose=True)
        resulting_fee_rate = self.calc_fee_rate(spending_tx)
        assert_greater_than_or_equal(resulting_fee_rate, self.target_fee_rate)

        self.generate(self.nodes[0], 1)
        wallet.unloadwallet()

    def test_target_feerate_unconfirmed_high(self):
        self.log.info("Start test feerate with high feerate unconfirmed input")
        wallet = self.setup_and_fund_wallet("unconfirmed_high_wallet")

        # Send unconfirmed transaction with high feerate to testing wallet
        funding_txid = wallet.sendtoaddress(address=wallet.getnewaddress(), amount=1, fee_rate=100)
        funding_tx = wallet.gettransaction(txid=funding_txid, verbose=True)
        resulting_fee_rate_funding = self.calc_fee_rate(funding_tx)
        assert_greater_than(resulting_fee_rate_funding, self.target_fee_rate)

        spending_txid = wallet.sendtoaddress(address=self.def_wallet.getnewaddress(), amount=0.5, fee_rate=self.target_fee_rate)
        spending_tx = wallet.gettransaction(txid=spending_txid, verbose=True)

        self.assert_spends_only_parent(spending_tx, funding_txid)

        resulting_fee_rate = self.calc_fee_rate(spending_tx)
        assert_greater_than_or_equal(resulting_fee_rate, self.target_fee_rate)
        resulting_ancestry_fee_rate = self.calc_set_fee_rate([funding_tx, spending_tx])
        assert_greater_than_or_equal(resulting_ancestry_fee_rate, self.target_fee_rate)

        self.generate(self.nodes[0], 1)
        wallet.unloadwallet()

    def test_target_feerate_unconfirmed_low(self):
        self.log.info("Start test feerate with low feerate unconfirmed input")
        wallet = self.setup_and_fund_wallet("unconfirmed_low_wallet")

        funding_txid = wallet.sendtoaddress(address=wallet.getnewaddress(), amount=1, fee_rate=1)
        funding_tx = wallet.gettransaction(txid=funding_txid, verbose=True)

        resulting_fee_rate_funding = self.calc_fee_rate(funding_tx)
        assert_greater_than(self.target_fee_rate, resulting_fee_rate_funding)

        spending_txid = wallet.sendtoaddress(address=self.def_wallet.getnewaddress(), amount=0.5, fee_rate=self.target_fee_rate)
        spending_tx = wallet.gettransaction(txid=spending_txid, verbose=True)

        self.assert_spends_only_parent(spending_tx, funding_txid)

        resulting_fee_rate = self.calc_fee_rate(spending_tx)
        assert_greater_than_or_equal(resulting_fee_rate, self.target_fee_rate)
        resulting_ancestry_fee_rate = self.calc_set_fee_rate([funding_tx, spending_tx])
        assert_greater_than_or_equal(resulting_ancestry_fee_rate, self.target_fee_rate)

        self.generate(self.nodes[0], 1)
        wallet.unloadwallet()

# TODO: Test: Do not count transactions with higher ancestor feerates towards total ancestor fees and size

    def run_test(self):
        self.log.info("Starting UnconfirmedInputTest!")
        self.target_fee_rate = 30
        self.def_wallet  = self.nodes[0].get_wallet_rpc(self.default_wallet_name)
        self.generate(self.nodes[0], 110)

        # Test that assumptions about meeting feerate and being able to test it hold
        self.test_target_feerate_confirmed()

        # Spend unconfirmed input with feerate higher than target feerate
        self.test_target_feerate_unconfirmed_high()

        # Actual test: Spend unconfirmed input with feerate lower than target feerate. Expect that parent gets bumped to target feerate.
        self.test_target_feerate_unconfirmed_low()

if __name__ == '__main__':
    UnconfirmedInputTest().main()
