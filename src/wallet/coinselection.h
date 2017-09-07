// Copyright (c) 2017 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_COINSELECTION_H
#define BITCOIN_COINSELECTION_H

#include "amount.h"
#include "primitives/transaction.h"
#include "random.h"
#include "wallet/wallet.h"

bool SelectCoinsBnB(std::vector<CInputCoin>& utxo_pool, const CAmount& target_value, const CAmount& cost_of_change, std::set<CInputCoin>& out_set,
    CAmount& value_ret, std::vector<CAmount>& fee_vec, std::vector<CAmount>& long_term_fee_vec, CAmount& fee_ret);

// Random coin selection algorithm if no exact match is found 
bool RandomSelector(std::vector<CInputCoin>& utxo_pool, const CAmount& nTargetValue, std::set<CInputCoin>& out_set, CAmount& value_ret);

// Largest first coin selection algorithm guarantees selection if it is possible.
// Can produce change smaller than MIN_CHANGE if no other solution.
bool LargestFirstSelector(std::vector<CInputCoin>& utxo_pool, const CAmount& nTargetValue, std::set<CInputCoin>& out_set, CAmount& value_ret);

#endif // BITCOIN_COINSELECTION_H
