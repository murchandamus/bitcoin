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

        ancestor_aware_txid = wallet.sendtoaddress(address=self.def_wallet.getnewaddress(), amount=0.5, fee_rate=self.target_fee_rate)
        ancestor_aware_tx = wallet.gettransaction(txid=ancestor_aware_txid, verbose=True)
        resulting_fee_rate = self.calc_fee_rate(ancestor_aware_tx)
        assert_greater_than_or_equal(resulting_fee_rate, self.target_fee_rate)

        self.generate(self.nodes[0], 1)
        wallet.unloadwallet()

    def test_target_feerate_unconfirmed_high(self):
        self.log.info("Start test feerate with high feerate unconfirmed input")
        wallet = self.setup_and_fund_wallet("unconfirmed_high_wallet")

        # Send unconfirmed transaction with high feerate to testing wallet
        parent_txid = wallet.sendtoaddress(address=wallet.getnewaddress(), amount=1, fee_rate=100)
        parent_tx = wallet.gettransaction(txid=parent_txid, verbose=True)
        resulting_fee_rate_funding = self.calc_fee_rate(parent_tx)
        assert_greater_than(resulting_fee_rate_funding, self.target_fee_rate)

        ancestor_aware_txid = wallet.sendtoaddress(address=self.def_wallet.getnewaddress(), amount=0.5, fee_rate=self.target_fee_rate)
        ancestor_aware_tx = wallet.gettransaction(txid=ancestor_aware_txid, verbose=True)

        self.assert_spends_only_parent(ancestor_aware_tx, parent_txid)

        resulting_fee_rate = self.calc_fee_rate(ancestor_aware_tx)
        assert_greater_than_or_equal(resulting_fee_rate, self.target_fee_rate)
        resulting_ancestry_fee_rate = self.calc_set_fee_rate([parent_tx, ancestor_aware_tx])
        assert_greater_than_or_equal(resulting_ancestry_fee_rate, self.target_fee_rate)

        self.generate(self.nodes[0], 1)
        wallet.unloadwallet()

    def test_target_feerate_unconfirmed_low(self):
        self.log.info("Start test feerate with low feerate unconfirmed input")
        wallet = self.setup_and_fund_wallet("unconfirmed_low_wallet")

        parent_txid = wallet.sendtoaddress(address=wallet.getnewaddress(), amount=1, fee_rate=1)
        parent_tx = wallet.gettransaction(txid=parent_txid, verbose=True)

        resulting_fee_rate_funding = self.calc_fee_rate(parent_tx)
        assert_greater_than(self.target_fee_rate, resulting_fee_rate_funding)

        ancestor_aware_txid = wallet.sendtoaddress(address=self.def_wallet.getnewaddress(), amount=0.5, fee_rate=self.target_fee_rate)
        ancestor_aware_tx = wallet.gettransaction(txid=ancestor_aware_txid, verbose=True)

        self.assert_spends_only_parent(ancestor_aware_tx, parent_txid)

        resulting_fee_rate = self.calc_fee_rate(ancestor_aware_tx)
        assert_greater_than_or_equal(resulting_fee_rate, self.target_fee_rate)
        resulting_ancestry_fee_rate = self.calc_set_fee_rate([parent_tx, ancestor_aware_tx])
        assert_greater_than_or_equal(resulting_ancestry_fee_rate, self.target_fee_rate)
        assert_greater_than_or_equal(self.target_fee_rate*1.5, resulting_ancestry_fee_rate)

        self.generate(self.nodes[0], 1)
        wallet.unloadwallet()

    def test_chain_of_unconfirmed_low(self):
        self.log.info("Start test with parent and grandparent tx")
        wallet = self.setup_and_fund_wallet("unconfirmed_low_chain_wallet")

        grandparent_txid = wallet.sendtoaddress(address=wallet.getnewaddress(), amount=1.8, fee_rate=1)
        gp_tx = wallet.gettransaction(txid=grandparent_txid, verbose=True)
        resulting_fee_rate_grandparent = self.calc_fee_rate(gp_tx)

        assert_greater_than(self.target_fee_rate, resulting_fee_rate_grandparent)

        parent_txid = wallet.sendtoaddress(address=wallet.getnewaddress(), amount=1.5, fee_rate=2)
        p_tx = wallet.gettransaction(txid=parent_txid, verbose=True)
        resulting_fee_rate_parent = self.calc_fee_rate(p_tx)

        assert_greater_than(self.target_fee_rate, resulting_fee_rate_parent)

        ancestor_aware_txid = wallet.sendtoaddress(address=self.def_wallet.getnewaddress(), amount=1.3, fee_rate=self.target_fee_rate)
        ancestor_aware_tx = wallet.gettransaction(txid=ancestor_aware_txid, verbose=True)

        resulting_fee_rate = self.calc_fee_rate(ancestor_aware_tx)
        assert_greater_than_or_equal(resulting_fee_rate, self.target_fee_rate)
        resulting_ancestry_fee_rate = self.calc_set_fee_rate([gp_tx, p_tx, ancestor_aware_tx])
        assert_greater_than_or_equal(resulting_ancestry_fee_rate, self.target_fee_rate)
        assert_greater_than_or_equal(self.target_fee_rate*1.5, resulting_ancestry_fee_rate)

        self.generate(self.nodes[0], 1)
        wallet.unloadwallet()

    def test_two_low_feerate_unconfirmed_parents(self):
        self.log.info("Start test with two unconfirmed parent txs")
        wallet = self.setup_and_fund_wallet("two_parents_wallet")

        # Add second UTXO to tested wallet
        self.def_wallet.sendtoaddress(address=wallet.getnewaddress(), amount=2)
        self.generate(self.nodes[0], 1) # confirm funding tx

        parent_one_txid = wallet.sendtoaddress(address=wallet.getnewaddress(), amount=1.5, fee_rate=2)
        p_one_tx = wallet.gettransaction(txid=parent_one_txid, verbose=True)
        resulting_fee_rate_parent_one = self.calc_fee_rate(p_one_tx)

        assert_greater_than(self.target_fee_rate, resulting_fee_rate_parent_one)

        parent_two_txid = wallet.sendtoaddress(address=wallet.getnewaddress(), amount=1.5, fee_rate=1)
        p_two_tx = wallet.gettransaction(txid=parent_two_txid, verbose=True)
        resulting_fee_rate_parent_two = self.calc_fee_rate(p_two_tx)

        assert_greater_than(self.target_fee_rate, resulting_fee_rate_parent_two)

        ancestor_aware_txid = wallet.sendtoaddress(address=self.def_wallet.getnewaddress(), amount=2.8, fee_rate=self.target_fee_rate)
        ancestor_aware_tx = wallet.gettransaction(txid=ancestor_aware_txid, verbose=True)

        resulting_fee_rate = self.calc_fee_rate(ancestor_aware_tx)
        assert_greater_than_or_equal(resulting_fee_rate, self.target_fee_rate)
        resulting_ancestry_fee_rate = self.calc_set_fee_rate([p_one_tx, p_two_tx, ancestor_aware_tx])
        assert_greater_than_or_equal(resulting_ancestry_fee_rate, self.target_fee_rate)
        assert_greater_than_or_equal(self.target_fee_rate*1.1, resulting_ancestry_fee_rate)

        self.generate(self.nodes[0], 1)
        wallet.unloadwallet()

    def test_mixed_feerate_unconfirmed_parents(self):
        self.log.info("Start test with two unconfirmed parent txs one of which has a higher feerate")
        wallet = self.setup_and_fund_wallet("two_mixed_parents_wallet")

        # Add second UTXO to tested wallet
        self.def_wallet.sendtoaddress(address=wallet.getnewaddress(), amount=2)
        self.generate(self.nodes[0], 1) # confirm funding tx

        high_parent_txid = wallet.sendtoaddress(address=wallet.getnewaddress(), amount=1.5, fee_rate=self.target_fee_rate*2)
        p_high_tx = wallet.gettransaction(txid=high_parent_txid, verbose=True)
        resulting_fee_rate_high_parent = self.calc_fee_rate(p_high_tx)

        # This time the parent is greater than the child
        assert_greater_than(resulting_fee_rate_high_parent, self.target_fee_rate)

        parent_low_txid = wallet.sendtoaddress(address=wallet.getnewaddress(), amount=1.5, fee_rate=1)
        p_low_tx = wallet.gettransaction(txid=parent_low_txid, verbose=True)
        resulting_fee_rate_parent_low = self.calc_fee_rate(p_low_tx)

        assert_greater_than(self.target_fee_rate, resulting_fee_rate_parent_low)

        ancestor_aware_txid = wallet.sendtoaddress(address=self.def_wallet.getnewaddress(), amount=2.8, fee_rate=self.target_fee_rate)
        ancestor_aware_tx = wallet.gettransaction(txid=ancestor_aware_txid, verbose=True)

        resulting_fee_rate = self.calc_fee_rate(ancestor_aware_tx)
        assert_greater_than_or_equal(resulting_fee_rate, self.target_fee_rate)
        resulting_ancestry_fee_rate = self.calc_set_fee_rate([p_high_tx, p_low_tx, ancestor_aware_tx])
        assert_greater_than_or_equal(resulting_ancestry_fee_rate, self.target_fee_rate)

        resulting_bumped_ancestry_fee_rate = self.calc_set_fee_rate([p_low_tx, ancestor_aware_tx])
        assert_greater_than_or_equal(resulting_bumped_ancestry_fee_rate, self.target_fee_rate)
        assert_greater_than_or_equal(self.target_fee_rate*1.1, resulting_bumped_ancestry_fee_rate)

        self.generate(self.nodes[0], 1)
        wallet.unloadwallet()

    def test_chain_of_high_low(self):
        # TODO: Test: Do not count transactions with higher ancestor feerates towards total ancestor fees and size
        self.log.info("Start test with low parent and high grandparent tx")
        wallet = self.setup_and_fund_wallet("high_low_chain_wallet")

        grandparent_txid = wallet.sendtoaddress(address=wallet.getnewaddress(), amount=1.8, fee_rate=self.target_fee_rate * 10)
        gp_tx = wallet.gettransaction(txid=grandparent_txid, verbose=True)
        resulting_fee_rate_grandparent = self.calc_fee_rate(gp_tx)

        # grandparent has higher feerate
        assert_greater_than(resulting_fee_rate_grandparent, self.target_fee_rate)

        parent_txid = wallet.sendtoaddress(address=wallet.getnewaddress(), amount=1.5, fee_rate=1)
        p_tx = wallet.gettransaction(txid=parent_txid, verbose=True)
        resulting_fee_rate_parent = self.calc_fee_rate(p_tx)

        assert_greater_than(self.target_fee_rate, resulting_fee_rate_parent)

        ancestor_aware_txid = wallet.sendtoaddress(address=self.def_wallet.getnewaddress(), amount=1.3, fee_rate=self.target_fee_rate)
        ancestor_aware_tx = wallet.gettransaction(txid=ancestor_aware_txid, verbose=True)

        resulting_fee_rate = self.calc_fee_rate(ancestor_aware_tx)
        assert_greater_than_or_equal(resulting_fee_rate, self.target_fee_rate)
        resulting_ancestry_fee_rate = self.calc_set_fee_rate([p_tx, ancestor_aware_tx])
        assert_greater_than_or_equal(resulting_ancestry_fee_rate, self.target_fee_rate)
        assert_greater_than_or_equal(self.target_fee_rate*1.1, resulting_ancestry_fee_rate)
        resulting_ancestry_fee_rate_with_high_feerate_gp = self.calc_set_fee_rate([gp_tx, p_tx, ancestor_aware_tx])
        assert_greater_than_or_equal(resulting_ancestry_fee_rate_with_high_feerate_gp, self.target_fee_rate*1.1)

        self.generate(self.nodes[0], 1)
        wallet.unloadwallet()

    def test_chain_of_high_low_below_target_feerate(self):
        # TODO: Test that grandparent gets bumped if it has a low feerate, but parent has lower feerate
        self.log.info("Start test with low parent and higher low grandparent tx")
        wallet = self.setup_and_fund_wallet("low_and_lower_chain_wallet")

        grandparent_txid = wallet.sendtoaddress(address=wallet.getnewaddress(), amount=1.8, fee_rate=5)
        gp_tx = wallet.gettransaction(txid=grandparent_txid, verbose=True)
        resulting_fee_rate_grandparent = self.calc_fee_rate(gp_tx)

        # grandparent has higher feerate
        assert_greater_than(self.target_fee_rate, resulting_fee_rate_grandparent)

        parent_txid = wallet.sendtoaddress(address=wallet.getnewaddress(), amount=1.5, fee_rate=1)
        p_tx = wallet.gettransaction(txid=parent_txid, verbose=True)
        resulting_fee_rate_parent = self.calc_fee_rate(p_tx)

        assert_greater_than(self.target_fee_rate, resulting_fee_rate_parent)

        ancestor_aware_txid = wallet.sendtoaddress(address=self.def_wallet.getnewaddress(), amount=1.3, fee_rate=self.target_fee_rate)
        ancestor_aware_tx = wallet.gettransaction(txid=ancestor_aware_txid, verbose=True)

        resulting_fee_rate = self.calc_fee_rate(ancestor_aware_tx)
        assert_greater_than_or_equal(resulting_fee_rate, self.target_fee_rate)
        resulting_ancestry_fee_rate = self.calc_set_fee_rate([gp_tx, p_tx, ancestor_aware_tx])
        assert_greater_than_or_equal(resulting_ancestry_fee_rate, self.target_fee_rate)
        assert_greater_than_or_equal(self.target_fee_rate*1.1, resulting_ancestry_fee_rate)

        self.generate(self.nodes[0], 1)
        wallet.unloadwallet()

    def test_target_feerate_unconfirmed_low_overlapping_ancestry(self):
        # TODO: when two UTXOs have overlapping ancestry, we'll bump the ancestors twice
        self.log.info("Start test where two UTXOs have overlapping ancestry")
        wallet = self.setup_and_fund_wallet("overlapping_ancestry_wallet")

        parent_txid = wallet.sendtoaddress(address=wallet.getnewaddress(), amount=1, fee_rate=1)
        parent_tx = wallet.gettransaction(txid=parent_txid, verbose=True)

        resulting_fee_rate_funding = self.calc_fee_rate(parent_tx)
        assert_greater_than(self.target_fee_rate, resulting_fee_rate_funding)

        # spend both outputs from parent transaction
        ancestor_aware_txid = wallet.sendtoaddress(address=self.def_wallet.getnewaddress(), amount=1.5, fee_rate=self.target_fee_rate)
        ancestor_aware_tx = wallet.gettransaction(txid=ancestor_aware_txid, verbose=True)

        resulting_fee_rate = self.calc_fee_rate(ancestor_aware_tx)
        assert_greater_than_or_equal(resulting_fee_rate, self.target_fee_rate)
        resulting_ancestry_fee_rate = self.calc_set_fee_rate([parent_tx, ancestor_aware_tx])
        assert_greater_than_or_equal(resulting_ancestry_fee_rate, self.target_fee_rate)
        assert_greater_than_or_equal(self.target_fee_rate*1.1, resulting_ancestry_fee_rate)

        self.generate(self.nodes[0], 1)
        wallet.unloadwallet()


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

        # Actual test: Spend unconfirmed input with unconfirmed parent both of which have a feerate lower than target feerate. Expect that both ancestors get bumped to target feerate.
        self.test_chain_of_unconfirmed_low()

        # Actual test: Spend unconfirmed inputs from two parents with low feerates
        self.test_two_low_feerate_unconfirmed_parents()

        # Actual test: Spend unconfirmed inputs from two parents with mixed feerates
        self.test_mixed_feerate_unconfirmed_parents()

        # Actual test: Spend chain with high grandparent low parent
        self.test_chain_of_high_low()

        # Actual test: Spend chain with low grandparent lower parent
        # TODO: self.test_chain_of_high_low_below_target_feerate()

        # Actual test: Spend two UTXOs with overlapping ancestry, ensure not bumping twice
        # TODO: self.test_target_feerate_unconfirmed_low_overlapping_ancestry()

if __name__ == '__main__':
    UnconfirmedInputTest().main()
