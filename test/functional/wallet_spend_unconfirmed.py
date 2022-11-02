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

    def assert_undershoots_target(self, tx):
        resulting_fee_rate = self.calc_fee_rate(tx)
        assert_greater_than_or_equal(self.target_fee_rate, resulting_fee_rate)

    def assert_beats_target(self, tx):
        resulting_fee_rate = self.calc_fee_rate(tx)
        assert_greater_than_or_equal(resulting_fee_rate, self.target_fee_rate)

    def test_target_feerate_confirmed(self):
        self.log.info("Start test feerate with confirmed input")
        wallet = self.setup_and_fund_wallet("confirmed_wallet")

        ancestor_aware_txid = wallet.sendtoaddress(address=self.def_wallet.getnewaddress(), amount=0.5, fee_rate=self.target_fee_rate)
        ancestor_aware_tx = wallet.gettransaction(txid=ancestor_aware_txid, verbose=True)
        self.assert_beats_target(ancestor_aware_tx)

        self.generate(self.nodes[0], 1)
        wallet.unloadwallet()

    def test_target_feerate_unconfirmed_high(self):
        self.log.info("Start test feerate with high feerate unconfirmed input")
        wallet = self.setup_and_fund_wallet("unconfirmed_high_wallet")

        # Send unconfirmed transaction with high feerate to testing wallet
        parent_txid = wallet.sendtoaddress(address=wallet.getnewaddress(), amount=1, fee_rate=100)
        parent_tx = wallet.gettransaction(txid=parent_txid, verbose=True)
        self.assert_beats_target(parent_tx)

        ancestor_aware_txid = wallet.sendtoaddress(address=self.def_wallet.getnewaddress(), amount=0.5, fee_rate=self.target_fee_rate)
        ancestor_aware_tx = wallet.gettransaction(txid=ancestor_aware_txid, verbose=True)

        self.assert_spends_only_parent(ancestor_aware_tx, parent_txid)

        self.assert_beats_target(ancestor_aware_tx)
        resulting_ancestry_fee_rate = self.calc_set_fee_rate([parent_tx, ancestor_aware_tx])
        assert_greater_than_or_equal(resulting_ancestry_fee_rate, self.target_fee_rate)

        self.generate(self.nodes[0], 1)
        wallet.unloadwallet()

    def test_target_feerate_unconfirmed_low(self):
        self.log.info("Start test feerate with low feerate unconfirmed input")
        wallet = self.setup_and_fund_wallet("unconfirmed_low_wallet")

        parent_txid = wallet.sendtoaddress(address=wallet.getnewaddress(), amount=1, fee_rate=1)
        parent_tx = wallet.gettransaction(txid=parent_txid, verbose=True)

        self.assert_undershoots_target(parent_tx)
        resulting_fee_rate_funding = self.calc_fee_rate(parent_tx)
        assert_greater_than(self.target_fee_rate, resulting_fee_rate_funding)

        ancestor_aware_txid = wallet.sendtoaddress(address=self.def_wallet.getnewaddress(), amount=0.5, fee_rate=self.target_fee_rate)
        ancestor_aware_tx = wallet.gettransaction(txid=ancestor_aware_txid, verbose=True)

        self.assert_spends_only_parent(ancestor_aware_tx, parent_txid)

        self.assert_beats_target(ancestor_aware_tx)
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

        self.assert_undershoots_target(gp_tx)

        parent_txid = wallet.sendtoaddress(address=wallet.getnewaddress(), amount=1.5, fee_rate=2)
        p_tx = wallet.gettransaction(txid=parent_txid, verbose=True)

        self.assert_undershoots_target(p_tx)

        ancestor_aware_txid = wallet.sendtoaddress(address=self.def_wallet.getnewaddress(), amount=1.3, fee_rate=self.target_fee_rate)
        ancestor_aware_tx = wallet.gettransaction(txid=ancestor_aware_txid, verbose=True)

        self.assert_beats_target(ancestor_aware_tx)
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
        self.assert_undershoots_target(p_one_tx)

        parent_two_txid = wallet.sendtoaddress(address=wallet.getnewaddress(), amount=1.5, fee_rate=1)
        p_two_tx = wallet.gettransaction(txid=parent_two_txid, verbose=True)
        self.assert_undershoots_target(p_two_tx)

        ancestor_aware_txid = wallet.sendtoaddress(address=self.def_wallet.getnewaddress(), amount=2.8, fee_rate=self.target_fee_rate)
        ancestor_aware_tx = wallet.gettransaction(txid=ancestor_aware_txid, verbose=True)

        self.assert_beats_target(ancestor_aware_tx)
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
        # This time the parent is greater than the child
        self.assert_beats_target(p_high_tx)

        parent_low_txid = wallet.sendtoaddress(address=wallet.getnewaddress(), amount=1.5, fee_rate=1)
        p_low_tx = wallet.gettransaction(txid=parent_low_txid, verbose=True)
        # Other parent needs bump
        self.assert_undershoots_target(p_low_tx)

        ancestor_aware_txid = wallet.sendtoaddress(address=self.def_wallet.getnewaddress(), amount=2.8, fee_rate=self.target_fee_rate)
        ancestor_aware_tx = wallet.gettransaction(txid=ancestor_aware_txid, verbose=True)

        self.assert_beats_target(ancestor_aware_tx)
        resulting_ancestry_fee_rate = self.calc_set_fee_rate([p_high_tx, p_low_tx, ancestor_aware_tx])
        assert_greater_than_or_equal(resulting_ancestry_fee_rate, self.target_fee_rate)

        resulting_bumped_ancestry_fee_rate = self.calc_set_fee_rate([p_low_tx, ancestor_aware_tx])
        assert_greater_than_or_equal(resulting_bumped_ancestry_fee_rate, self.target_fee_rate)
        assert_greater_than_or_equal(self.target_fee_rate*1.1, resulting_bumped_ancestry_fee_rate)

        self.generate(self.nodes[0], 1)
        wallet.unloadwallet()

    def test_chain_of_high_low(self):
        self.log.info("Start test with low parent and high grandparent tx")
        wallet = self.setup_and_fund_wallet("high_low_chain_wallet")

        grandparent_txid = wallet.sendtoaddress(address=wallet.getnewaddress(), amount=1.8, fee_rate=self.target_fee_rate * 10)
        gp_tx = wallet.gettransaction(txid=grandparent_txid, verbose=True)
        # grandparent has higher feerate
        self.assert_beats_target(gp_tx)

        parent_txid = wallet.sendtoaddress(address=wallet.getnewaddress(), amount=1.5, fee_rate=1)
        # parent is low feerate
        p_tx = wallet.gettransaction(txid=parent_txid, verbose=True)
        self.assert_undershoots_target(p_tx)

        ancestor_aware_txid = wallet.sendtoaddress(address=self.def_wallet.getnewaddress(), amount=1.3, fee_rate=self.target_fee_rate)
        ancestor_aware_tx = wallet.gettransaction(txid=ancestor_aware_txid, verbose=True)

        self.assert_beats_target(ancestor_aware_tx)
        resulting_ancestry_fee_rate = self.calc_set_fee_rate([p_tx, ancestor_aware_tx])
        assert_greater_than_or_equal(resulting_ancestry_fee_rate, self.target_fee_rate)
        assert_greater_than_or_equal(self.target_fee_rate*1.1, resulting_ancestry_fee_rate)
        resulting_ancestry_fee_rate_with_high_feerate_gp = self.calc_set_fee_rate([gp_tx, p_tx, ancestor_aware_tx])
        assert_greater_than_or_equal(resulting_ancestry_fee_rate_with_high_feerate_gp, self.target_fee_rate*1.1)

        self.generate(self.nodes[0], 1)
        wallet.unloadwallet()

    def test_chain_of_high_low_below_target_feerate(self):
        self.log.info("Start test with low parent and higher low grandparent tx")
        wallet = self.setup_and_fund_wallet("low_and_lower_chain_wallet")

        grandparent_txid = wallet.sendtoaddress(address=wallet.getnewaddress(), amount=1.8, fee_rate=5)
        gp_tx = wallet.gettransaction(txid=grandparent_txid, verbose=True)

        # grandparent has higher feerate, but below target
        self.assert_undershoots_target(gp_tx)

        parent_txid = wallet.sendtoaddress(address=wallet.getnewaddress(), amount=1.5, fee_rate=1)
        p_tx = wallet.gettransaction(txid=parent_txid, verbose=True)
        # parent even lower
        self.assert_undershoots_target(p_tx)

        ancestor_aware_txid = wallet.sendtoaddress(address=self.def_wallet.getnewaddress(), amount=1.3, fee_rate=self.target_fee_rate)
        ancestor_aware_tx = wallet.gettransaction(txid=ancestor_aware_txid, verbose=True)

        self.assert_beats_target(ancestor_aware_tx)
        resulting_ancestry_fee_rate = self.calc_set_fee_rate([gp_tx, p_tx, ancestor_aware_tx])
        assert_greater_than_or_equal(resulting_ancestry_fee_rate, self.target_fee_rate)
        assert_greater_than_or_equal(self.target_fee_rate*1.1, resulting_ancestry_fee_rate)

        self.generate(self.nodes[0], 1)
        wallet.unloadwallet()

    def test_target_feerate_unconfirmed_low_sffo(self):
        self.log.info("Start test feerate with low feerate unconfirmed input, while subtracting from output")
        wallet = self.setup_and_fund_wallet("unconfirmed_low_wallet_sffo")

        parent_txid = wallet.sendtoaddress(address=wallet.getnewaddress(), amount=1, fee_rate=1)
        parent_tx = wallet.gettransaction(txid=parent_txid, verbose=True)

        self.assert_undershoots_target(parent_tx)

        ancestor_aware_txid = wallet.sendtoaddress(address=self.def_wallet.getnewaddress(), amount=0.5, fee_rate=self.target_fee_rate, subtractfeefromamount=True)
        ancestor_aware_tx = wallet.gettransaction(txid=ancestor_aware_txid, verbose=True)

        self.assert_spends_only_parent(ancestor_aware_tx, parent_txid)

        self.assert_beats_target(ancestor_aware_tx)
        resulting_ancestry_fee_rate = self.calc_set_fee_rate([parent_tx, ancestor_aware_tx])
        assert_greater_than_or_equal(resulting_ancestry_fee_rate, self.target_fee_rate)
        assert_greater_than_or_equal(self.target_fee_rate*1.5, resulting_ancestry_fee_rate)

        self.generate(self.nodes[0], 1)
        wallet.unloadwallet()

    def test_preset_input_cpfp(self):
        self.log.info("Start test with preset input from low feerate unconfirmed transaction")
        wallet = self.setup_and_fund_wallet("preset_input")

        parent_txid = wallet.sendtoaddress(address=wallet.getnewaddress(), amount=1, fee_rate=1)
        parent_tx = wallet.gettransaction(txid=parent_txid, verbose=True)

        self.assert_undershoots_target(parent_tx)

        number_outputs = len(parent_tx["decoded"]["vout"])
        assert_equal(number_outputs, 2)

        # we don't care which of the two outputs we spent, they're both ours
        ancestor_aware_txid = wallet.send(outputs=[{self.def_wallet.getnewaddress(): 0.5}], fee_rate=self.target_fee_rate, options={"add_inputs": True, "inputs": [{"txid": parent_txid, "vout": 0}]})["txid"]
        ancestor_aware_tx = wallet.gettransaction(txid=ancestor_aware_txid, verbose=True)

        self.assert_spends_only_parent(ancestor_aware_tx, parent_txid)

        self.assert_beats_target(ancestor_aware_tx)
        resulting_ancestry_fee_rate = self.calc_set_fee_rate([parent_tx, ancestor_aware_tx])
        assert_greater_than_or_equal(resulting_ancestry_fee_rate, self.target_fee_rate)
        assert_greater_than_or_equal(self.target_fee_rate*1.5, resulting_ancestry_fee_rate)

        self.generate(self.nodes[0], 1)
        wallet.unloadwallet()

    def test_rbf_bumping(self):
        self.log.info("Start test to rbf a transaction unconfirmed input to bump it")
        wallet = self.setup_and_fund_wallet("bump")

        parent_txid = wallet.sendtoaddress(address=wallet.getnewaddress(), amount=1, fee_rate=1)
        parent_tx = wallet.gettransaction(txid=parent_txid, verbose=True)

        self.assert_undershoots_target(parent_tx)

        to_be_rbfed_ancestor_aware_txid = wallet.sendtoaddress(address=self.def_wallet.getnewaddress(), amount=0.5, fee_rate=self.target_fee_rate, subtractfeefromamount=True)
        ancestor_aware_tx = wallet.gettransaction(txid=to_be_rbfed_ancestor_aware_txid, verbose=True)

        self.assert_spends_only_parent(ancestor_aware_tx, parent_txid)

        self.assert_beats_target(ancestor_aware_tx)
        resulting_ancestry_fee_rate = self.calc_set_fee_rate([parent_tx, ancestor_aware_tx])
        assert_greater_than_or_equal(resulting_ancestry_fee_rate, self.target_fee_rate)
        assert_greater_than_or_equal(self.target_fee_rate*1.5, resulting_ancestry_fee_rate)

        bumped_ancestor_aware_txid = wallet.bumpfee(txid=to_be_rbfed_ancestor_aware_txid, options={"fee_rate": self.target_fee_rate * 2} )["txid"]
        bumped_ancestor_aware_tx = wallet.gettransaction(txid=bumped_ancestor_aware_txid, verbose=True)
        self.assert_spends_only_parent(bumped_ancestor_aware_tx, parent_txid)

        resulting_bumped_fee_rate = self.calc_fee_rate(bumped_ancestor_aware_tx)
        assert_greater_than_or_equal(resulting_bumped_fee_rate, 2*self.target_fee_rate)
        resulting_bumped_ancestry_fee_rate = self.calc_set_fee_rate([parent_tx, bumped_ancestor_aware_tx])
        assert_greater_than_or_equal(resulting_bumped_ancestry_fee_rate, 2*self.target_fee_rate)
        assert_greater_than_or_equal(2*self.target_fee_rate*1.5, resulting_bumped_ancestry_fee_rate)

        self.generate(self.nodes[0], 1)
        wallet.unloadwallet()

    def test_sibling_tx_gets_ignored(self):
        self.log.info("Start test where a low-fee sibling tx gets created and check that bumping ignores it")
        wallet = self.setup_and_fund_wallet("ignore-sibling")

        parent_txid = wallet.sendtoaddress(address=wallet.getnewaddress(), amount=1, fee_rate=2)
        parent_tx = wallet.gettransaction(txid=parent_txid, verbose=True)

        self.assert_undershoots_target(parent_tx)

        # create sibling tx
        sibling_txid = wallet.sendtoaddress(address=self.def_wallet.getnewaddress(), amount=0.9, fee_rate=1)
        sibling_tx = wallet.gettransaction(txid=sibling_txid, verbose=True)
        self.assert_undershoots_target(sibling_tx)

        # spend both outputs from parent transaction
        ancestor_aware_txid = wallet.sendtoaddress(address=self.def_wallet.getnewaddress(), amount=0.5, fee_rate=self.target_fee_rate)
        ancestor_aware_tx = wallet.gettransaction(txid=ancestor_aware_txid, verbose=True)

        self.assert_spends_only_parent(ancestor_aware_tx, parent_txid)

        self.assert_beats_target(ancestor_aware_tx)
        resulting_ancestry_fee_rate = self.calc_set_fee_rate([parent_tx, ancestor_aware_tx])
        assert_greater_than_or_equal(resulting_ancestry_fee_rate, self.target_fee_rate)
        assert_greater_than_or_equal(self.target_fee_rate*1.1, resulting_ancestry_fee_rate)

        self.generate(self.nodes[0], 1)
        wallet.unloadwallet()

    def test_sibling_tx_bumps_parent(self):
        self.log.info("Start test where a high-fee sibling tx bumps the parent")
        wallet = self.setup_and_fund_wallet("generous-sibling")

        parent_txid = wallet.sendtoaddress(address=wallet.getnewaddress(), amount=1, fee_rate=1)
        parent_tx = wallet.gettransaction(txid=parent_txid, verbose=True)
        self.assert_undershoots_target(parent_tx)

        # create sibling tx
        sibling_txid = wallet.sendtoaddress(address=self.def_wallet.getnewaddress(), amount=0.9, fee_rate=100)
        sibling_tx = wallet.gettransaction(txid=sibling_txid, verbose=True)
        self.assert_beats_target(sibling_tx)

        # spend both outputs from parent transaction
        ancestor_aware_txid = wallet.sendtoaddress(address=self.def_wallet.getnewaddress(), amount=0.5, fee_rate=self.target_fee_rate)
        ancestor_aware_tx = wallet.gettransaction(txid=ancestor_aware_txid, verbose=True)

        self.assert_spends_only_parent(ancestor_aware_tx, parent_txid)

        self.assert_beats_target(ancestor_aware_tx)
        # Child is only paying for itself…
        resulting_fee_rate = self.calc_fee_rate(ancestor_aware_tx)
        assert_greater_than_or_equal(1.05 * self.target_fee_rate, resulting_fee_rate)
        # …because sibling bumped to parent to ~50 s/vB, while our target is 30 s/vB
        resulting_ancestry_fee_rate_sibling = self.calc_set_fee_rate([parent_tx, sibling_tx])
        assert_greater_than_or_equal(resulting_ancestry_fee_rate_sibling, self.target_fee_rate)
        # and our resulting "ancestry feerate" is therefore BELOW target feerate
        resulting_ancestry_fee_rate = self.calc_set_fee_rate([parent_tx, ancestor_aware_tx])
        assert_greater_than_or_equal(self.target_fee_rate, resulting_ancestry_fee_rate)

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
        self.test_chain_of_high_low_below_target_feerate()

        # Actual test: Check that fee is calculated correctly when bumping while subtracting fee from output
        self.test_target_feerate_unconfirmed_low_sffo()

        # Actual test: Check that parents of preset unconfirmed inputs get cpfp'ed
        self.test_preset_input_cpfp()

        # Actual test: Check that RBFing a transaction with unconfirmed input gets the right feerate
        self.test_rbf_bumping()

        # Actual test: Create sibling tx with low fee and check it gets ignored
        self.test_sibling_tx_gets_ignored()

        # Actual test: Create sibling tx with high fee and check that new child only pays for itself
        self.test_sibling_tx_bumps_parent()

if __name__ == '__main__':
    UnconfirmedInputTest().main()
